"""Tests for Milestone 1: Eval Set and Metrics."""
import json
import pytest
from pathlib import Path
from nexus.eval.metrics import (
    calculate_recall_at_k,
    calculate_precision_at_k,
    calculate_reciprocal_rank,
    evaluate_parameter_validity,
    summarize_benchmark,
    QueryEvaluationResult
)
from nexus.eval.distractors import generate_synthetic_distractors


def test_eval_dataset_structure():
    eval_file = Path("data/eval/queries.json")
    assert eval_file.exists(), "queries.json must exist"
    
    with open(eval_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "queries" in data
    queries = data["queries"]
    assert len(queries) >= 40, f"Expected at least 40 queries, got {len(queries)}"
    
    query_types = set()
    for q in queries:
        assert "id" in q
        assert "query" in q and len(q["query"]) > 5
        assert "ground_truth_tools" in q and len(q["ground_truth_tools"]) >= 1
        assert "query_type" in q
        assert "service" in q
        query_types.add(q["query_type"])
        
    # Check that required types are represented
    assert "single_step" in query_types
    assert "multi_step" in query_types
    assert "hard_negative" in query_types
    assert "paraphrase" in query_types
    assert "vague" in query_types


def test_metrics_calculation():
    # Test Recall@K
    gt = ["paypal_invoices_create", "paypal_invoices_send"]
    retrieved_perfect = ["paypal_invoices_create", "paypal_invoices_send", "paypal_invoices_get"]
    assert calculate_recall_at_k(retrieved_perfect, gt, k=5) == 1.0
    
    retrieved_partial = ["paypal_invoices_create", "paypal_orders_create"]
    assert calculate_recall_at_k(retrieved_partial, gt, k=5) == 0.5
    
    retrieved_none = ["paypal_orders_create", "paypal_orders_get"]
    assert calculate_recall_at_k(retrieved_none, gt, k=5) == 0.0
    
    # Test Precision@K
    assert calculate_precision_at_k(retrieved_perfect, gt, k=5) == 2 / 5
    
    # Test MRR
    assert calculate_reciprocal_rank(["tool_a", "paypal_invoices_create"], ["paypal_invoices_create"]) == 0.5
    assert calculate_reciprocal_rank(["paypal_invoices_create"], ["paypal_invoices_create"]) == 1.0
    assert calculate_reciprocal_rank(["tool_a", "tool_b"], ["paypal_invoices_create"]) == 0.0
    
    # Test Parameter Validity
    expected = {"amount": 50.0, "recipient_email": "bob@example.com"}
    extracted = {"amount": 50.0, "recipient_email": "bob@example.com", "extra": "val"}
    assert evaluate_parameter_validity(extracted, expected) == 1.0
    
    partial_extracted = {"amount": 50.0}
    assert evaluate_parameter_validity(partial_extracted, expected) == 0.5


def test_synthetic_distractors():
    distractors_100 = generate_synthetic_distractors(100)
    assert len(distractors_100) == 100
    
    tool_ids = set()
    for d in distractors_100:
        assert d["is_synthetic"] is True
        assert d["tool_id"] not in tool_ids
        tool_ids.add(d["tool_id"])
        assert "paypal" not in d["tool_id"]
        assert "paypal" not in d["service"]
        assert d["risk_level"] in ["HIGH", "LOW"]


def test_benchmark_summary():
    results = [
        QueryEvaluationResult(
            query_id="eval_1",
            query="test 1",
            ground_truth_tools=["tool_a"],
            retrieved_tools=["tool_a", "tool_b"],
            recall_at_5=1.0,
            precision_at_5=0.2,
            reciprocal_rank=1.0,
            retrieval_latency_ms=15.0,
            parameter_validity=1.0,
            end_to_end_success=True,
            llm_calls=2,
            total_tokens=450
        ),
        QueryEvaluationResult(
            query_id="eval_2",
            query="test 2",
            ground_truth_tools=["tool_b"],
            retrieved_tools=["tool_c", "tool_b"],
            recall_at_5=1.0,
            precision_at_5=0.2,
            reciprocal_rank=0.5,
            retrieval_latency_ms=25.0,
            parameter_validity=0.8,
            end_to_end_success=True,
            llm_calls=3,
            total_tokens=600
        )
    ]
    summary = summarize_benchmark(results)
    assert summary.total_queries == 2
    assert summary.mean_recall_at_5 == 1.0
    assert summary.mean_mrr == 0.75
    assert summary.mean_retrieval_latency_ms == 20.0
    assert summary.mean_llm_calls_per_request == 2.5

