"""Tests for Milestone 5: LangGraph Orchestration, Intent Routing, and Human-in-the-Loop Approval."""
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from nexus.models.tool import ToolDefinition
from nexus.registry.repository import JsonToolRepository
from nexus.orchestration.graph import NexusOrchestrator


class MockRetriever:
    def __init__(self, write_tool: ToolDefinition, read_tool: ToolDefinition):
        self.write_tool = write_tool
        self.read_tool = read_tool

    def retrieve(self, query, top_k=5, session_sticky_tools=None):
        lower = query.lower()
        if "send" in lower or "create" in lower:
            return {"tools": [self.write_tool], "retrieval_scores": {"paypal_invoices_create": 0.03}}
        return {"tools": [self.read_tool], "retrieval_scores": {"paypal_invoices_list": 0.03}}


def test_intent_routing_and_branches(tmp_path):
    repo = JsonToolRepository(str(tmp_path / "tools.json"))
    
    write_tool = ToolDefinition(
        tool_id="paypal_invoices_create",
        name="Create Invoice",
        service="invoicing",
        category="invoices",
        description="Creates draft invoice",
        method="POST",
        endpoint="/v2/invoicing/invoices",
        parameters={"properties": {"amount": {"type": "number"}, "recipient_email": {"type": "string"}}, "required": []},
        risk_level="HIGH"
    )
    read_tool = ToolDefinition(
        tool_id="paypal_invoices_list",
        name="List Invoices",
        service="invoicing",
        category="invoices",
        description="Lists invoices",
        method="GET",
        endpoint="/v2/invoicing/invoices",
        parameters={"properties": {}},
        risk_level="LOW"
    )
    repo.create(write_tool)
    repo.create(read_tool)
    
    retriever = MockRetriever(write_tool, read_tool)
    memory = MemorySaver()
    orchestrator = NexusOrchestrator(
        repository=repo,
        retriever=retriever,
        checkpointer=memory
    )

    # 1. Test System Search Intent
    config_sys = {"configurable": {"thread_id": "thread_sys_1"}}
    res_sys = orchestrator.graph.invoke({"query": "Show all available tools in registry"}, config=config_sys)
    assert res_sys["intent"] == "SYSTEM_SEARCH"
    assert "System Registry" in res_sys["final_response"]

    # 2. Test RAG Intent
    config_rag = {"configurable": {"thread_id": "thread_rag_1"}}
    res_rag = orchestrator.graph.invoke({"query": "What does the user manual say about refund policy documentation?"}, config=config_rag)
    assert res_rag["intent"] == "RAG"
    assert "documentation" in res_rag["final_response"].lower()

    # 3. Test Safe Read Tool (GET) -> No interrupt required
    config_read = {"configurable": {"thread_id": "thread_read_1"}}
    res_read = orchestrator.graph.invoke({"query": "List all active invoices"}, config=config_read)
    assert res_read["intent"] == "TOOL"
    assert res_read["approval_status"] == "NOT_REQUIRED"
    assert "Execution Summary" in res_read["final_response"]


def test_human_approval_interrupt_and_resume(tmp_path):
    repo = JsonToolRepository(str(tmp_path / "tools.json"))
    
    write_tool = ToolDefinition(
        tool_id="paypal_invoices_create",
        name="Create Invoice",
        service="invoicing",
        category="invoices",
        description="Creates draft invoice",
        method="POST",
        endpoint="/v2/invoicing/invoices",
        parameters={
            "properties": {
                "amount": {"type": "number"},
                "recipient_email": {"type": "string"}
            },
            "required": ["amount", "recipient_email"]
        },
        risk_level="HIGH"
    )
    read_tool = ToolDefinition(
        tool_id="paypal_invoices_list",
        name="List Invoices",
        service="invoicing",
        category="invoices",
        description="Lists invoices",
        method="GET",
        endpoint="/v2/invoicing/invoices",
        risk_level="LOW"
    )
    repo.create(write_tool)
    
    retriever = MockRetriever(write_tool, read_tool)
    memory = MemorySaver()
    orchestrator = NexusOrchestrator(
        repository=repo,
        retriever=retriever,
        checkpointer=memory
    )

    thread_id = "test_thread_approval_100"
    config = {"configurable": {"thread_id": thread_id}}

    # 1. Run mutating query: should interrupt for human approval!
    initial_state = {"query": "Send an invoice for $50 to bob@example.com"}
    events = list(orchestrator.graph.stream(initial_state, config=config))
    
    # Check interrupt payload
    current_snapshot = orchestrator.graph.get_state(config)
    assert len(current_snapshot.tasks) > 0
    interrupts = current_snapshot.tasks[0].interrupts
    assert len(interrupts) > 0
    interrupt_data = interrupts[0].value
    assert interrupt_data["action"] == "APPROVAL_REQUIRED"
    assert interrupt_data["details"]["tool_id"] == "paypal_invoices_create"
    assert interrupt_data["details"]["parameters"]["amount"] == 50.0

    # 2. Resume execution with human approval!
    resumed = orchestrator.graph.invoke(
        Command(resume={"approved": True}),
        config=config
    )
    assert resumed["approval_status"] == "APPROVED"
    assert len(resumed["execution_results"]) > 0
    assert "Execution Summary" in resumed["final_response"]

