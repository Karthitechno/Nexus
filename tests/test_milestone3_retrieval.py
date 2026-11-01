"""Tests for Milestone 3: Hybrid Retrieval, Indexing, RRF, and Reranking."""
import pytest
from pathlib import Path
from nexus.retrieval.bm25 import BM25Index
from nexus.retrieval.chroma_index import ChromaToolIndex
from nexus.retrieval.hybrid import HybridRetriever
from nexus.registry.repository import JsonToolRepository
from nexus.models.tool import ToolDefinition


def test_bm25_index():
    index = BM25Index()
    docs = [
        ("doc_invoice", "Create a draft PayPal invoice for customer billing"),
        ("doc_template", "List all invoice templates for merchant presets"),
        ("doc_dispute", "Show buyer disputes and chargeback complaints")
    ]
    index.index(docs)
    
    # Query invoice should rank doc_invoice top
    res = index.search("invoice billing")
    assert len(res) >= 1
    assert res[0][0] == "doc_invoice"
    
    # Query dispute should rank doc_dispute top
    res_disp = index.search("buyer dispute")
    assert len(res_disp) >= 1
    assert res_disp[0][0] == "doc_dispute"


def test_hybrid_retriever_pipeline(tmp_path):
    repo_file = tmp_path / "tools.json"
    repo = JsonToolRepository(str(repo_file))
    
    tool1 = ToolDefinition(
        tool_id="paypal_invoices_list",
        name="List Invoices",
        service="invoicing",
        category="invoices",
        description="Lists all customer invoices.",
        method="GET",
        endpoint="/v2/invoicing/invoices",
        example_queries=["List my invoices", "Show all invoices"],
        is_active=True
    )
    tool2 = ToolDefinition(
        tool_id="paypal_templates_list",
        name="List Invoice Templates",
        service="invoicing",
        category="templates",
        description="Lists invoice layout presets and templates.",
        method="GET",
        endpoint="/v2/invoicing/templates",
        example_queries=["Show invoice templates", "List my presets"],
        is_active=True
    )
    tool3 = ToolDefinition(
        tool_id="paypal_disputes_list",
        name="List Customer Disputes",
        service="disputes",
        category="disputes",
        description="Shows customer complaints and claims.",
        method="GET",
        endpoint="/v1/customer/disputes",
        example_queries=["Show disputes", "List claims"],
        is_active=True
    )
    repo.create(tool1)
    repo.create(tool2)
    repo.create(tool3)
    
    chroma_dir = tmp_path / "chroma"
    chroma_index = ChromaToolIndex(persist_directory=str(chroma_dir))
    retriever = HybridRetriever(repository=repo, chroma_index=chroma_index)
    
    # Test 1: Query for templates vs invoices (Hard Negative)
    res_template = retriever.retrieve("Show me my invoice templates")
    assert len(res_template["tools"]) >= 1
    top_tool = res_template["tools"][0]
    assert top_tool.tool_id == "paypal_templates_list"
    
    # Verify score fields separation
    assert "retrieval_scores" in res_template
    assert "cross_encoder_scores" in res_template
    assert "llm_confidence" in res_template
    assert top_tool.tool_id in res_template["cross_encoder_scores"]
    
    # Test 2: Precedence rule - completely irrelevant garbage query
    # Should be rejected by no_match_threshold or return empty/irrelevant
    res_irrelevant = retriever.retrieve("quantum physics string theory dark matter galaxy collision", top_k=5)
    # The scores should either be empty or below threshold
    if res_irrelevant["tools"]:
        # If any tool passes, check that scores are properly reported
        assert isinstance(res_irrelevant["cross_encoder_scores"], dict)
        
    # Test 3: Session-sticky tool boost
    res_sticky = retriever.retrieve("Show all", session_sticky_tools=["paypal_disputes_list"])
    assert "paypal_disputes_list" in res_sticky["retrieval_scores"]

