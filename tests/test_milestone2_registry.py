"""Tests for Milestone 2: Dynamic Tool Registry, Importer, and Enrichment."""
import json
import pytest
from pathlib import Path
from nexus.models.tool import ToolDefinition, ToolFilter
from nexus.registry.repository import JsonToolRepository
from nexus.registry.importer import PostmanImporter
from nexus.registry.enricher import ToolEnricher


def test_postman_importer():
    collection_path = Path("data/paypal_collection.json")
    assert collection_path.exists(), "PayPal collection file must exist"
    
    with open(collection_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    importer = PostmanImporter()
    tools = importer.import_collection(data)
    
    assert len(tools) >= 25, f"Expected >= 25 tools, imported {len(tools)}"
    
    # Check normalized fields on every tool
    for tool in tools:
        assert tool.tool_id and len(tool.tool_id) > 3
        assert tool.name
        assert tool.service
        assert tool.category
        assert tool.method in ["GET", "POST", "PUT", "DELETE", "PATCH"]
        assert tool.endpoint.startswith("/")
        assert isinstance(tool.parameters, dict)
        assert tool.risk_level in ["HIGH", "LOW"]
        assert tool.is_active is True
        assert tool.original_definition
        
        # Verify write operations are HIGH risk and GET are LOW risk
        if tool.method == "GET":
            assert tool.risk_level == "LOW"
        elif tool.method in ["POST", "PUT", "DELETE"]:
            assert tool.risk_level == "HIGH"


def test_repository_crud(tmp_path):
    repo_file = tmp_path / "test_tools.json"
    repo = JsonToolRepository(str(repo_file))
    
    # 1. Create
    tool = ToolDefinition(
        tool_id="test_invoices_create",
        name="Create Invoice",
        service="invoicing",
        category="invoices",
        description="Creates a new draft invoice.",
        method="POST",
        endpoint="/v2/invoicing/invoices",
        parameters={"type": "object", "properties": {"amount": {"type": "number"}}},
        risk_level="HIGH"
    )
    created = repo.create(tool)
    assert created.tool_id == "test_invoices_create"
    assert repo.count() == 1
    
    # 2. Duplicate ID rejection
    with pytest.raises(ValueError, match="already exists"):
        repo.create(tool)
        
    # 3. Read
    fetched = repo.get("test_invoices_create")
    assert fetched is not None
    assert fetched.name == "Create Invoice"
    
    # 4. Update
    tool.description = "Updated invoice description"
    updated = repo.update(tool)
    assert updated.description == "Updated invoice description"
    assert repo.get("test_invoices_create").description == "Updated invoice description"
    
    # 5. Enable/Disable
    repo.set_active("test_invoices_create", False)
    assert repo.get("test_invoices_create").is_active is False
    
    # 6. Filter & Search
    results = repo.list(ToolFilter(service="invoicing"))
    assert len(results) == 1
    
    empty_results = repo.list(ToolFilter(service="disputes"))
    assert len(empty_results) == 0
    
    search_results = repo.list(ToolFilter(search="invoice"))
    assert len(search_results) == 1
    
    # 7. Delete
    deleted = repo.delete("test_invoices_create")
    assert deleted is True
    assert repo.get("test_invoices_create") is None
    assert repo.count() == 0


def test_enrichment(tmp_path):
    cache_path = tmp_path / "test_enrich_cache.json"
    enricher = ToolEnricher(cache_file=str(cache_path))
    
    tools = [
        ToolDefinition(
            tool_id="paypal_invoices_send",
            name="Send Invoice",
            service="invoicing",
            category="invoices",
            description="Sends an invoice to recipient.",
            method="POST",
            endpoint="/v2/invoicing/invoices/{invoice_id}/send",
            parameters={"type": "object", "properties": {"invoice_id": {"type": "string"}}},
            risk_level="HIGH"
        )
    ]
    
    enriched = enricher.enrich_tools(tools)
    assert len(enriched) == 1
    tool = enriched[0]
    assert tool.is_generated is True
    assert len(tool.example_queries) >= 5, f"Expected >= 5 example queries, got {len(tool.example_queries)}"
    assert tool.description

