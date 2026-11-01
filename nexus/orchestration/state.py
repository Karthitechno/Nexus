"""LangGraph State Definition for NEXUS Orchestrator."""
from typing import TypedDict, List, Dict, Any, Optional


class NexusState(TypedDict, total=False):
    query: str
    thread_id: str
    request_id: str
    intent: str  # "TOOL", "RAG", "SYSTEM_SEARCH", "CLARIFY"
    service_routed: Optional[str]
    retrieved_tools: List[Dict[str, Any]]
    retrieval_scores: Dict[str, float]
    cross_encoder_scores: Dict[str, float]
    llm_confidence: Optional[float]
    plan: List[Dict[str, Any]]
    current_step_index: int
    pending_approval: Optional[Dict[str, Any]]
    approval_status: Optional[str]  # "PENDING", "APPROVED", "REJECTED"
    missing_fields: List[str]
    clarification_prompt: Optional[str]
    execution_results: List[Dict[str, Any]]
    session_sticky_tools: List[str]
    entity_context: Dict[str, Any]  # Deterministic active entity blackboard across turns & agents
    resolved_memory_slots: Dict[str, str]  # Audit map of parameters bound from inter-agent memory
    rag_sources: List[str]
    final_response: str
    error: Optional[str]
    trace: Dict[str, Any]
