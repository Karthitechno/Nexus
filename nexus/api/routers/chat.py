"""Chat endpoint - orchestrates the full NEXUS pipeline."""
import uuid, logging, json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from nexus.api.deps import get_orchestrator

logger = logging.getLogger("nexus.api.chat")
router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    thread_id: Optional[str] = None
    session_sticky_tools: list = []


class ApproveRequest(BaseModel):
    thread_id: str
    approved: bool


@router.post("/chat")
def chat(req: ChatRequest):
    orchestrator = get_orchestrator()
    thread_id = req.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "query": req.query,
        "thread_id": thread_id,
        "session_sticky_tools": req.session_sticky_tools,
        "clarification_prompt": None,
        "final_response": None,
        "execution_results": [],
        "plan": [],
        "missing_fields": [],
        "retrieved_tools": [],
        "approval_status": None,
        "pending_approval": None,
    }

    try:
        # Stream to detect interrupts
        events = list(orchestrator.graph.stream(initial_state, config=config))
        snapshot = orchestrator.graph.get_state(config)

        # Check for interrupt (approval needed)
        pending_interrupt = None
        if snapshot.tasks:
            for task in snapshot.tasks:
                if task.interrupts:
                    pending_interrupt = task.interrupts[0].value
                    break

        if pending_interrupt:
            return {
                "thread_id": thread_id,
                "status": "PENDING_APPROVAL",
                "interrupt": pending_interrupt,
                "response": None,
                "intent": None,
                "selected_tools": [],
                "request_id": None,
                "trace": {},
            }

        # Get final state
        final_state = snapshot.values
        return {
            "thread_id": thread_id,
            "status": "COMPLETED",
            "interrupt": None,
            "response": final_state.get("final_response", ""),
            "intent": final_state.get("intent"),
            "selected_tools": _format_selected_tools(final_state),
            "request_id": final_state.get("request_id"),
            "trace": final_state.get("trace", {}),
            "execution_results": final_state.get("execution_results", []),
            "approval_status": final_state.get("approval_status"),
            "entity_context": final_state.get("entity_context", {}),
            "resolved_memory_slots": final_state.get("resolved_memory_slots", {}),
        }

    except Exception as e:
        logger.exception("Chat error")
        raise HTTPException(status_code=500, detail=f"Orchestration error: {str(e)}")


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Stream LangGraph orchestration events as Server-Sent Events (SSE)."""
    orchestrator = get_orchestrator()
    thread_id = req.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    def event_generator():
        initial_state = {
            "query": req.query,
            "thread_id": thread_id,
            "session_sticky_tools": req.session_sticky_tools,
        }
        yield f"data: {json.dumps({'type': 'start', 'thread_id': thread_id})}\n\n"

        try:
            for step_event in orchestrator.graph.stream(initial_state, config=config):
                for node_name, node_update in step_event.items():
                    if node_name == "intent_and_route":
                        intent = node_update.get("intent", "TOOL")
                        yield f"data: {json.dumps({'type': 'thought', 'stage': 'Intent', 'message': f'Classified intent: {intent}'})}\n\n"
                    elif node_name == "retrieve_tools":
                        tools = [t.get('name') for t in node_update.get('retrieved_tools', [])][:3]
                        tools_str = ', '.join(tools) if tools else 'Registry tools'
                        yield f"data: {json.dumps({'type': 'thought', 'stage': 'Retrieval', 'message': f'Retrieved candidates: {tools_str}'})}\n\n"
                    elif node_name == "plan_and_validate":
                        if node_update.get("clarification_prompt"):
                            yield f"data: {json.dumps({'type': 'thought', 'stage': 'Validation', 'message': 'Schema validation identified missing required parameters.'})}\n\n"
                        else:
                            plan_count = len(node_update.get('plan', []))
                            yield f"data: {json.dumps({'type': 'thought', 'stage': 'Planning', 'message': f'Formulated {plan_count}-step execution plan.'})}\n\n"
                    elif node_name == "execute_tools":
                        auto_healed = node_update.get("trace", {}).get("auto_healed")
                        msg = 'Self-healing reflection executed successfully.' if auto_healed else 'Executing verified API calls in Sandbox...'
                        yield f"data: {json.dumps({'type': 'thought', 'stage': 'Execution', 'message': msg})}\n\n"

            # Check if interrupted for human approval
            snapshot = orchestrator.graph.get_state(config)
            pending_interrupt = None
            if snapshot.tasks:
                for task in snapshot.tasks:
                    if task.interrupts:
                        pending_interrupt = task.interrupts[0].value
                        break

            if pending_interrupt:
                yield f"data: {json.dumps({'type': 'interrupt', 'status': 'PENDING_APPROVAL', 'thread_id': thread_id, 'interrupt': pending_interrupt})}\n\n"
            else:
                final_val = snapshot.values
                yield f"data: {json.dumps({'type': 'complete', 'status': 'COMPLETED', 'thread_id': thread_id, 'response': final_val.get('final_response', ''), 'request_id': final_val.get('request_id'), 'trace': final_val.get('trace', {}), 'execution_results': final_val.get('execution_results', []), 'selected_tools': _format_selected_tools(final_val)})}\n\n"
        except Exception as e:
            logger.exception("Streaming error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/chat/approve")
def approve_chat(req: ApproveRequest):
    """Resume a paused graph after human approval/rejection."""
    from langgraph.types import Command
    orchestrator = get_orchestrator()
    config = {"configurable": {"thread_id": req.thread_id}}

    try:
        result = orchestrator.graph.invoke(
            Command(resume={"approved": req.approved}),
            config=config,
        )
        return {
            "thread_id": req.thread_id,
            "status": "COMPLETED",
            "approved": req.approved,
            "response": result.get("final_response", ""),
            "request_id": result.get("request_id"),
            "execution_results": result.get("execution_results", []),
            "approval_status": result.get("approval_status"),
            "trace": result.get("trace", {}),
        }
    except Exception as e:
        logger.exception("Approve error")
        raise HTTPException(status_code=500, detail=f"Resume error: {str(e)}")


def _format_selected_tools(state: Dict[str, Any]) -> list:
    tools = state.get("retrieved_tools", [])
    if isinstance(tools, list):
        return [
            {
                "tool_id": t.get("tool_id") if isinstance(t, dict) else getattr(t, "tool_id", ""),
                "name": t.get("name") if isinstance(t, dict) else getattr(t, "name", ""),
                "service": t.get("service") if isinstance(t, dict) else getattr(t, "service", ""),
                "method": t.get("method") if isinstance(t, dict) else getattr(t, "method", ""),
                "endpoint": t.get("endpoint") if isinstance(t, dict) else getattr(t, "endpoint", ""),
                "risk_level": t.get("risk_level") if isinstance(t, dict) else getattr(t, "risk_level", ""),
            }
            for t in tools
        ]
    return []
