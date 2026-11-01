"""Evaluation metrics for NEXUS platform."""
from typing import List, Dict, Any, Optional
import time
from pydantic import BaseModel, Field


class QueryEvaluationResult(BaseModel):
    query_id: str
    query: str
    ground_truth_tools: List[str]
    retrieved_tools: List[str]
    recall_at_5: float
    precision_at_5: float
    reciprocal_rank: float
    retrieval_latency_ms: float
    parameter_validity: float  # 0.0 to 1.0
    end_to_end_success: bool
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error: Optional[str] = None


class BenchmarkSummary(BaseModel):
    total_queries: int
    mean_recall_at_5: float
    mean_precision_at_5: float
    mean_mrr: float
    mean_parameter_validity: float
    end_to_end_success_rate: float
    mean_retrieval_latency_ms: float
    p95_retrieval_latency_ms: float
    mean_llm_calls_per_request: float
    mean_tokens_per_request: float
    total_llm_calls: int
    total_tokens: int


def calculate_recall_at_k(retrieved: List[str], ground_truth: List[str], k: int = 5) -> float:
    """Calculate Recall@K: fraction of ground truth tools retrieved in top K."""
    if not ground_truth:
        return 1.0
    top_k = set(retrieved[:k])
    gt_set = set(ground_truth)
    hits = len(top_k.intersection(gt_set))
    return hits / len(gt_set)


def calculate_precision_at_k(retrieved: List[str], ground_truth: List[str], k: int = 5) -> float:
    """Calculate Precision@K: fraction of top K retrieved that are in ground truth."""
    if k <= 0:
        return 0.0
    top_k = set(retrieved[:k])
    gt_set = set(ground_truth)
    hits = len(top_k.intersection(gt_set))
    return hits / k


def calculate_reciprocal_rank(retrieved: List[str], ground_truth: List[str], k: int = 5) -> float:
    """Calculate reciprocal rank of the first relevant tool in top K."""
    gt_set = set(ground_truth)
    for idx, tool in enumerate(retrieved[:k]):
        if tool in gt_set:
            return 1.0 / (idx + 1)
    return 0.0


# Backward compatibility aliases
compute_recall_at_k = calculate_recall_at_k
compute_precision_at_k = calculate_precision_at_k
compute_mrr = calculate_reciprocal_rank


def evaluate_parameter_validity(extracted_params: Dict[str, Any], expected_params: Dict[str, Any]) -> float:
    """Evaluate what fraction of expected parameters were extracted accurately."""
    if not expected_params:
        return 1.0  # Nothing required to extract
    if not extracted_params:
        return 0.0
    
    matches = 0
    for key, expected_val in expected_params.items():
        if key in extracted_params:
            val = extracted_params[key]
            if isinstance(expected_val, float):
                try:
                    if abs(float(val) - expected_val) < 0.01:
                        matches += 1
                except (ValueError, TypeError):
                    pass
            elif isinstance(expected_val, str) and isinstance(val, str):
                if expected_val.lower() == val.lower() or expected_val.lower() in val.lower():
                    matches += 1
            elif val == expected_val:
                matches += 1
    return matches / len(expected_params)


def summarize_benchmark(results: List[QueryEvaluationResult]) -> BenchmarkSummary:
    """Compute aggregate benchmark metrics across all evaluated queries."""
    if not results:
        return BenchmarkSummary(
            total_queries=0,
            mean_recall_at_5=0.0,
            mean_precision_at_5=0.0,
            mean_mrr=0.0,
            mean_parameter_validity=0.0,
            end_to_end_success_rate=0.0,
            mean_retrieval_latency_ms=0.0,
            p95_retrieval_latency_ms=0.0,
            mean_llm_calls_per_request=0.0,
            mean_tokens_per_request=0.0,
            total_llm_calls=0,
            total_tokens=0,
        )

    n = len(results)
    latencies = sorted([r.retrieval_latency_ms for r in results])
    p95_idx = int(n * 0.95)
    p95_latency = latencies[min(p95_idx, n - 1)]

    total_calls = sum(r.llm_calls for r in results)
    total_toks = sum(r.total_tokens for r in results)

    return BenchmarkSummary(
        total_queries=n,
        mean_recall_at_5=sum(r.recall_at_5 for r in results) / n,
        mean_precision_at_5=sum(r.precision_at_5 for r in results) / n,
        mean_mrr=sum(r.reciprocal_rank for r in results) / n,
        mean_parameter_validity=sum(r.parameter_validity for r in results) / n,
        end_to_end_success_rate=sum(1.0 for r in results if r.end_to_end_success) / n,
        mean_retrieval_latency_ms=sum(r.retrieval_latency_ms for r in results) / n,
        p95_retrieval_latency_ms=p95_latency,
        mean_llm_calls_per_request=total_calls / n,
        mean_tokens_per_request=total_toks / n,
        total_llm_calls=total_calls,
        total_tokens=total_toks,
    )

