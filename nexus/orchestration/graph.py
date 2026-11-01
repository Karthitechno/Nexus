"""NEXUS LangGraph Orchestrator State Machine."""
import os
import time
import uuid
import logging
import json
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from nexus.orchestration.state import NexusState
from nexus.retrieval.hybrid import HybridRetriever
from nexus.tools.planner import MultiStepPlanner
from nexus.tools.slot_filler import SlotFiller
from nexus.registry.repository import IToolRepository
from nexus.storage.redis_client import RedisManager
from nexus.storage.memory import EntityMemoryStore

logger = logging.getLogger("nexus.graph")


class NexusOrchestrator:
    """Stateful LangGraph orchestrator governing request lifecycle and approval breakpoints."""

    def __init__(
        self,
        repository: IToolRepository,
        retriever: HybridRetriever,
        executor=None,
        rag_pipeline=None,
        system_search=None,
        checkpointer=None,
        redis_mgr: Optional[RedisManager] = None,
        memory_store: Optional[EntityMemoryStore] = None,
    ):
        self.repository = repository
        self.retriever = retriever
        self.planner = MultiStepPlanner(retriever)
        self.slot_filler = SlotFiller()
        self.executor = executor
        self.rag_pipeline = rag_pipeline
        self.system_search = system_search
        self.checkpointer = checkpointer or MemorySaver()
        self.redis = redis_mgr or RedisManager.get_instance()
        self.memory_store = memory_store or EntityMemoryStore.get_instance(redis_mgr=self.redis)
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(NexusState)

        # Register nodes
        builder.add_node("intent_and_route", self._node_intent_and_route)
        builder.add_node("rag_handler", self._node_rag_handler)
        builder.add_node("system_search_handler", self._node_system_search_handler)
        builder.add_node("retrieve_tools", self._node_retrieve_tools)
        builder.add_node("plan_and_validate", self._node_plan_and_validate)
        builder.add_node("approval_gate", self._node_approval_gate)
        builder.add_node("execute_tools", self._node_execute_tools)
        builder.add_node("respond", self._node_respond)

        # Entry point
        builder.set_entry_point("intent_and_route")

        # Conditional edges from intent_and_route
        builder.add_conditional_edges(
            "intent_and_route",
            self._route_intent,
            {
                "RAG": "rag_handler",
                "SYSTEM_SEARCH": "system_search_handler",
                "TOOL": "retrieve_tools",
                "CLARIFY": "respond",
            }
        )

        builder.add_edge("rag_handler", "respond")
        builder.add_edge("system_search_handler", "respond")

        # After tool retrieval -> plan and validate
        builder.add_edge("retrieve_tools", "plan_and_validate")

        # After plan & validate: check if clarification needed or proceed to approval
        builder.add_conditional_edges(
            "plan_and_validate",
            self._route_plan_outcome,
            {
                "CLARIFY": "respond",
                "PROCEED": "approval_gate",
            }
        )

        # After approval gate: check if approved or needs execution
        builder.add_edge("approval_gate", "execute_tools")
        builder.add_edge("execute_tools", "respond")
        builder.add_edge("respond", END)

        return builder.compile(checkpointer=self.checkpointer)

    def _route_intent(self, state: NexusState) -> str:
        return state.get("intent", "TOOL")

    def _route_plan_outcome(self, state: NexusState) -> str:
        if state.get("clarification_prompt"):
            return "CLARIFY"
        return "PROCEED"

    def _node_intent_and_route(self, state: NexusState) -> Dict[str, Any]:
        """Classify user intent: TOOL, RAG, SYSTEM_SEARCH, or CLARIFY."""
        start_time = time.time()
        query = state.get("query", "").strip()
        request_id = state.get("request_id") or str(uuid.uuid4())
        trace = state.get("trace", {})
        trace["request_id"] = request_id
        trace["start_timestamp"] = time.time()

        lower = query.lower()

        # 1. System Search Intent (queries about registry, logs, request status, tool discovery)
        if any(term in lower for term in [
            "available tools", "show all tools", "list tools", "system status",
            "request status", "execution log", "system search", "registered apis", "tool count",
            "what tools", "which tools", "find tools", "search tools", "search for tools",
            "tools for", "tools available", "payment tools", "invoice tools", "dispute tools"
        ]) or (("tool" in lower or "tools" in lower) and any(w in lower for w in ["search", "find", "show", "list", "available", "what", "which", "how many"])):
            intent = "SYSTEM_SEARCH"
        # 2. RAG Intent (documentation, user manuals, policy guidelines, how-to guides)
        elif any(term in lower for term in [
            "documentation", "user guide", "manual", "policy", "policies", "terms", "terms of service",
            "refund policy", "refund policies", "payment terms", "guide", "guidelines",
            "what does the doc say", "according to the guide", "pdf documentation",
            "how do i", "how does", "what are the rules", "faq"
        ]):
            intent = "RAG"
        # 3. Direct Tool Actions / API Requests
        else:
            intent = "TOOL"

        latency_ms = (time.time() - start_time) * 1000.0
        trace["intent_latency_ms"] = latency_ms

        # Load active entity blackboard for this thread
        thread_id = state.get("thread_id", "")
        persisted_context = self.memory_store.get_entity_context(thread_id) if thread_id else {}
        entity_ctx = dict(state.get("entity_context", {}))
        entity_ctx.update(persisted_context)

        return {
            "request_id": request_id,
            "intent": intent,
            "entity_context": entity_ctx,
            "trace": trace,
            "clarification_prompt": None,
            "final_response": None,
            "execution_results": [],
            "plan": [],
            "missing_fields": [],
            "retrieved_tools": [],
            "approval_status": None,
            "pending_approval": None,
        }

    def _node_retrieve_tools(self, state: NexusState) -> Dict[str, Any]:
        """Execute hybrid retrieval (BM25 + Chroma + RRF + Cross-Encoder)."""
        start_time = time.time()
        query = state.get("query", "")
        session_sticky = state.get("session_sticky_tools", [])

        res = self.retriever.retrieve(
            query=query,
            top_k=5,
            session_sticky_tools=session_sticky
        )

        tools = res.get("tools", [])
        trace = state.get("trace", {})
        trace["retrieval_latency_ms"] = (time.time() - start_time) * 1000.0
        trace["retrieved_tool_ids"] = [t.tool_id for t in tools]

        if not tools:
            return {
                "retrieved_tools": [],
                "retrieval_scores": res.get("retrieval_scores", {}),
                "cross_encoder_scores": res.get("cross_encoder_scores", {}),
                "llm_confidence": res.get("llm_confidence"),
                "service_routed": res.get("service_routed"),
                "clarification_prompt": "I could not find an appropriate API tool matching your request in the registry.",
                "trace": trace,
            }

        return {
            "retrieved_tools": [t.model_dump() for t in tools],
            "retrieval_scores": res.get("retrieval_scores", {}),
            "cross_encoder_scores": res.get("cross_encoder_scores", {}),
            "llm_confidence": res.get("llm_confidence"),
            "service_routed": res.get("service_routed"),
            "trace": trace,
        }

    def _node_plan_and_validate(self, state: NexusState) -> Dict[str, Any]:
        """Decompose query, model dependencies, and run schema-constrained slot filling."""
        query = state.get("query", "")
        session_sticky = state.get("session_sticky_tools", [])

        # If already clarified as no-match, exit
        if state.get("clarification_prompt"):
            return {}

        plan = self.planner.plan(query, session_sticky_tools=session_sticky)
        trace = state.get("trace", {})
        trace["plan_steps_count"] = len(plan)

        # Slot fill each planned step with inter-agent blackboard context
        context_params: Dict[str, Any] = {}
        entity_ctx = state.get("entity_context", {})
        all_resolved_memory: Dict[str, str] = dict(state.get("resolved_memory_slots", {}))

        for step in plan:
            tool_def = step["tool_definition"]
            fill_result = self.slot_filler.fill_slots(
                step["sub_query"],
                tool_def,
                context_params=context_params,
                entity_context=entity_ctx,
            )

            step["parameters"] = fill_result["parameters"]
            all_resolved_memory.update(fill_result.get("resolved_memory_slots", {}))
            deps = step.get("dependencies", {})
            actual_missing = [f for f in fill_result.get("missing_fields", []) if f not in deps]

            # If any step is missing required fields not satisfied by dependencies or memory, stop and clarify
            if actual_missing:
                step["is_valid"] = False
                return {
                    "plan": plan,
                    "missing_fields": actual_missing,
                    "clarification_prompt": fill_result["clarification_prompt"],
                    "resolved_memory_slots": all_resolved_memory,
                    "trace": trace,
                }

            step["is_valid"] = True

            # Update context params for chaining
            context_params.update(fill_result["parameters"])

        trace["resolved_memory_slots"] = all_resolved_memory

        return {
            "plan": plan,
            "missing_fields": [],
            "clarification_prompt": None,
            "resolved_memory_slots": all_resolved_memory,
            "trace": trace,
        }

    def _node_approval_gate(self, state: NexusState) -> Dict[str, Any]:
        """Inspect plan risk level. Trigger interrupt() for mutating writes if not approved."""
        plan = state.get("plan", [])
        approval_status = state.get("approval_status")

        # Check if already approved by human resume
        if approval_status == "APPROVED":
            return {"pending_approval": None}

        # Check if any step requires human approval (risk_level == HIGH)
        high_risk_steps = [s for s in plan if s.get("risk_level") == "HIGH"]
        if high_risk_steps:
            # Build structured list of all steps so the user sees the complete multi-step plan
            formatted_steps = []
            for s in plan:
                tool_def = s.get("tool_definition")
                method = getattr(tool_def, "method", "POST") if tool_def else "POST"
                endpoint = getattr(tool_def, "endpoint", "") if tool_def else ""
                formatted_steps.append({
                    "step_index": s.get("step_index", 1),
                    "tool_id": s.get("tool_id"),
                    "name": s.get("tool_name", s.get("tool_id")),
                    "method": method,
                    "endpoint": endpoint,
                    "parameters": s.get("parameters", {}),
                    "risk_level": s.get("risk_level", "LOW")
                })

            primary_step = high_risk_steps[0]
            params = primary_step.get("parameters", {})
            amt = params.get("amount")
            recipient = params.get("recipient_email")
            if isinstance(params.get("primary_recipients"), list) and params["primary_recipients"]:
                recipient = params["primary_recipients"][0].get("billing_info", {}).get("email_address", recipient)

            pending_details = {
                "environment": "Sandbox",
                "total_steps": len(plan),
                "steps": formatted_steps,
                "tool_id": primary_step.get("tool_id"),
                "tool_name": primary_step.get("tool_name", primary_step.get("tool_id")),
                "method": getattr(primary_step.get("tool_definition"), "method", "POST") if primary_step.get("tool_definition") else "POST",
                "endpoint": getattr(primary_step.get("tool_definition"), "endpoint", "") if primary_step.get("tool_definition") else "",
                "amount": f"${float(amt):.2f}" if amt else None,
                "recipient": recipient,
                "parameters": params,
                "warning": "Sandbox environment: Confirm authorization to execute the planned operation(s).",
            }

            # Store pending approval in Redis with 15-minute TTL
            req_id = state.get("request_id", "")
            appr_key = f"nexus:approval:{req_id}"
            if req_id and self.redis.is_available():
                try:
                    self.redis.set(appr_key, json.dumps(pending_details), ex=900)
                except Exception:
                    pass

            user_decision = interrupt({
                "action": "APPROVAL_REQUIRED",
                "details": pending_details,
            })

            # Check if approval window expired in Redis (when Redis is available)
            if req_id and self.redis.is_available() and not self.redis.get(appr_key):
                return {
                    "approval_status": "REJECTED",
                    "final_response": "Action cancelled: approval window expired (15 minutes limit exceeded). Please re-submit your request.",
                    "pending_approval": None,
                }

            # Clear approval key upon decision
            if req_id and self.redis.is_available():
                self.redis.delete(appr_key)

            # Upon resume, user_decision is passed back
            if isinstance(user_decision, dict) and user_decision.get("approved"):
                return {"approval_status": "APPROVED", "pending_approval": None}
            else:
                return {
                    "approval_status": "REJECTED",
                    "final_response": "Action cancelled by user approval denial.",
                    "pending_approval": None,
                }

        return {"approval_status": "NOT_REQUIRED", "pending_approval": None}

    def _node_execute_tools(self, state: NexusState) -> Dict[str, Any]:
        """Execute planned steps using Generic API Executor."""
        plan = state.get("plan", [])
        results: List[Dict[str, Any]] = []
        sticky_tools = list(state.get("session_sticky_tools", []))
        entity_ctx = dict(state.get("entity_context", {}))
        thread_or_req = state.get("thread_id") or state.get("request_id") or ""

        # If rejected, skip execution
        if state.get("approval_status") == "REJECTED":
            return {"execution_results": []}

        previous_outputs: Dict[str, Any] = {}

        for step in plan:
            tool_id = step.get("tool_id")
            params = dict(step.get("parameters", {}))
            deps = step.get("dependencies", {})

            # Resolve step dependencies, e.g. "$step_1.id"
            for dep_param, dep_target in deps.items():
                if dep_target.startswith("$step_"):
                    step_key = dep_target[1:].split(".")[0]
                    prop_key = dep_target.split(".")[1] if "." in dep_target else "id"
                    if step_key in previous_outputs:
                        prev = previous_outputs[step_key]
                        val = prev.get(prop_key) if isinstance(prev, dict) else None
                        if not val and prop_key in ("id", "invoice_id") and isinstance(prev, dict):
                            val = prev.get("id") or prev.get("invoice_id")
                            if not val and "href" in prev:
                                val = prev["href"].rstrip("/").split("/")[-1]
                        if val:
                            params[dep_param] = val

            # Execute via Generic Executor if provided
            if self.executor:
                exec_res = self.executor.execute(
                    tool_id=tool_id,
                    parameters=params,
                    request_id=state.get("request_id"),
                    thread_id=state.get("thread_id"),
                )
                # Auto-Healing Reflection Loop: If execution failed, attempt LLM self-correction
                if exec_res.get("status") != "SUCCESS":
                    healed_res = self._attempt_auto_heal(step, params, exec_res, state)
                    if healed_res and healed_res.get("status") == "SUCCESS":
                        logger.info("Self-healing reflection loop successfully resolved %s", tool_id)
                        exec_res = healed_res
                        trace = state.get("trace", {})
                        trace["auto_healed"] = True
                        trace["healed_tool"] = tool_id
            else:
                exec_res = {
                    "tool_id": tool_id,
                    "status": "SUCCESS",
                    "response": {"simulated": True, "params": params},
                    "message": f"Tool {tool_id} staged successfully."
                }

            # Inter-agent entity extraction & payload reference offloading
            harvested = self.memory_store.extract_and_record_entities(
                thread_or_req,
                tool_id,
                exec_res,
            )
            entity_ctx.update(harvested)

            # Check if payload is large (>5 items or large JSON) -> store pass-by-reference
            resp_body = exec_res.get("response")
            if resp_body and isinstance(resp_body, dict):
                items = resp_body.get("items")
                if isinstance(items, list) and len(items) > 5:
                    ref_info = self.memory_store.store_payload(
                        thread_or_req,
                        resp_body,
                        summary=f"Collection of {len(items)} records from {tool_id}",
                    )
                    exec_res["payload_reference"] = ref_info["reference"]

            results.append(exec_res)
            previous_outputs[f"step_{step.get('step_index', 1)}"] = exec_res.get("response", {})

            if tool_id not in sticky_tools:
                sticky_tools.append(tool_id)

        # Keep last 5 session sticky tools and persist in Redis for follow-up turns
        sticky_tools = sticky_tools[-5:]
        req_id = state.get("request_id")
        if sticky_tools and req_id and self.redis.is_available():
            try:
                self.redis.set(f"nexus:session:{req_id}:sticky", json.dumps(sticky_tools), ex=7200)
            except Exception:
                pass

        return {
            "execution_results": results,
            "session_sticky_tools": sticky_tools,
            "entity_context": entity_ctx,
        }

    def _attempt_auto_heal(
        self,
        step: Dict[str, Any],
        params: Dict[str, Any],
        failed_res: Dict[str, Any],
        state: NexusState
    ) -> Optional[Dict[str, Any]]:
        """Auto-healing reflection loop: inspects API error and uses LLM to heal parameters."""
        tool_id = step.get("tool_id", "")
        tool_def = step.get("tool_definition")
        error_msg = failed_res.get("message", "")
        error_body = failed_res.get("response", {})

        if failed_res.get("status") not in ("API_ERROR", "FAILED"):
            return None

        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None

        try:
            from google import genai
            client = genai.Client()
            schema_json = json.dumps(getattr(tool_def, "parameters", {}) if tool_def else {})
            prompt = (
                f"You are an API Auto-Healing reflection agent in NEXUS.\n"
                f"The tool '{tool_id}' failed with the following error from the external API:\n"
                f"Error: {error_msg}\n"
                f"API Response Details: {json.dumps(error_body)}\n\n"
                f"Current Parameters Passed: {json.dumps(params)}\n"
                f"Tool Parameter Schema: {schema_json}\n\n"
                f"Task: Fix the parameters so that the API call succeeds based on the error message.\n"
                f"Return ONLY a valid JSON object of the corrected parameters. Do not include markdown code fences or extra text."
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"temperature": 0.0}
            )
            text = (response.text or "").strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            healed_params = json.loads(text)
            if isinstance(healed_params, dict) and healed_params:
                logger.info("Attempting auto-healed execution for %s with corrected params: %s", tool_id, healed_params)
                healed_exec = self.executor.execute(
                    tool_id=tool_id,
                    parameters=healed_params,
                    request_id=state.get("request_id"),
                    thread_id=state.get("thread_id"),
                )
                if healed_exec.get("status") == "SUCCESS":
                    healed_exec["auto_healed"] = True
                    healed_exec["original_error"] = error_msg
                    return healed_exec
        except Exception as e:
            logger.warning("Auto-healing reflection loop encountered an exception: %s", e)
        return None

    def _node_rag_handler(self, state: NexusState) -> Dict[str, Any]:
        """Handle documentation and RAG questions via standalone RAG pipeline."""
        query = state.get("query", "")
        if self.rag_pipeline:
            answer_data = self.rag_pipeline.query(query)
            return {
                "final_response": answer_data.get("answer", "No answer found in documentation."),
                "rag_sources": answer_data.get("sources", []),
            }
        return {
            "final_response": f"RAG Pipeline documentation lookup for: '{query}'. Knowledge base is ready.",
            "rag_sources": [],
        }

    def _node_system_search_handler(self, state: NexusState) -> Dict[str, Any]:
        """Handle meta-queries over tool registry and execution logs."""
        query = state.get("query", "")
        if self.system_search:
            res = self.system_search.search(query)
            return {"final_response": res.get("summary", "System search completed.")}
        
        # Fallback system search info
        count = self.repository.count()
        return {
            "final_response": f"NEXUS System Registry currently manages {count} verified tools across all services."
        }

    def _node_respond(self, state: NexusState) -> Dict[str, Any]:
        """Format user-facing response and finalize trace according to Output Contract."""
        request_id = state.get("request_id", "")
        trace = state.get("trace", {})
        trace["total_latency_ms"] = (time.time() - trace.get("start_timestamp", time.time())) * 1000.0

        # Clarification prompt has precedence
        if state.get("clarification_prompt"):
            return {"final_response": state["clarification_prompt"], "trace": trace}

        # If already set by RAG, system search, or rejection
        if state.get("final_response"):
            req_footer = f"\n\n*Request ID: `{request_id}`*"
            return {"final_response": state["final_response"] + req_footer, "trace": trace}

        results = state.get("execution_results", [])
        if not results:
            return {"final_response": "I could not complete the requested operation.", "trace": trace}

        human_parts: List[str] = []

        # Analyze outcomes across execution results
        for res in results:
            status = res.get("status", "UNKNOWN")
            tid = res.get("tool_id", "")
            data = res.get("response") or {}
            msg = res.get("message", "")

            if status != "SUCCESS":
                human_parts.append(f"⚠️ **Operation failed on tool `{tid}`:** {msg}")
                continue

            # Dynamic Collection / List responses across ANY service
            items = None
            if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
                items = data["items"]
            elif isinstance(data, list):
                items = data

            if items is not None:
                total = data.get("total_items") if isinstance(data, dict) else len(items)
                if total is None:
                    total = len(items)
                
                # Derive entity name dynamically from tool_id or data
                entity_name = tid.split("_")[-1] if "_" in tid else "record"
                noun = entity_name if entity_name.endswith("s") else f"{entity_name}s"
                
                human_parts.append(f"You have **{total} {noun}** in your account.\n")
                if items and isinstance(items[0], dict):
                    first_item = items[0]
                    # Check for invoice-like schema
                    if "detail" in first_item or "primary_recipients" in first_item:
                        human_parts.append("| Invoice # | Status | Amount | Recipient | Date |")
                        human_parts.append("| :--- | :---: | :---: | :--- | :--- |")
                        for item in items[:5]:
                            inv_num = item.get("detail", {}).get("invoice_number", item.get("id", "N/A"))
                            st = item.get("status", "UNKNOWN")
                            recips = item.get("primary_recipients") or []
                            email = recips[0].get("billing_info", {}).get("email_address", "—") if recips else "—"
                            amt = item.get("amount", {}).get("value")
                            amt_str = f"${float(amt):.2f}" if amt else "—"
                            dt = item.get("detail", {}).get("invoice_date", "—")
                            human_parts.append(f"| `{inv_num}` | **{st}** | {amt_str} | {email} | {dt} |")
                    else:
                        # Dynamic generic table generation for ANY API service
                        top_keys = [k for k in first_item.keys() if isinstance(first_item[k], (str, int, float, bool))][:5]
                        if top_keys:
                            headers = " | ".join([k.replace("_", " ").title() for k in top_keys])
                            separators = " | ".join([":---" for _ in top_keys])
                            human_parts.append(f"| {headers} |")
                            human_parts.append(f"| {separators} |")
                            for item in items[:5]:
                                row_vals = " | ".join([str(item.get(k, "—")) for k in top_keys])
                                human_parts.append(f"| {row_vals} |")
                    if len(items) > 5:
                        human_parts.append(f"\n*(Showing 5 of {len(items)} {noun})*")

            # Dynamic Creation / Write actions
            elif "create" in tid or "draft" in tid:
                res_id = data.get("id") or (data.get("href", "").rstrip("/").split("/")[-1] if data.get("href") else "N/A")
                amt = None
                recipient = None
                for step in state.get("plan", []):
                    if step.get("tool_id") == tid:
                        p = step.get("parameters", {})
                        amt = p.get("amount")
                        recipient = p.get("recipient_email") or p.get("recipient")
                        break
                details_txt = ""
                if amt and recipient:
                    details_txt = f" for **${float(amt):.2f}** to **{recipient}**"
                elif amt:
                    details_txt = f" for **${float(amt):.2f}**"
                elif recipient:
                    details_txt = f" to **{recipient}**"
                human_parts.append(f"Invoice **`{res_id}`** was created{details_txt}.")

            # Dynamic Dispatch / Send actions
            elif "send" in tid:
                href = data.get("href")
                inv_id = None
                for step in state.get("plan", []):
                    if step.get("tool_id") == tid:
                        inv_id = step.get("parameters", {}).get("invoice_id")
                        break
                id_txt = f" **`{inv_id}`**" if inv_id else ""
                link_txt = f" [View in PayPal Sandbox]({href})" if href else ""
                human_parts.append(f"Invoice{id_txt} was sent to the recipient.{link_txt}")

            # Generic dynamic fallback
            else:
                human_parts.append(f"✅ Completed **{tid.replace('_', ' ').title()}** successfully.")

        # Request ID footer in markdown
        human_parts.append(f"\n\n*Request ID: `{request_id}`*")

        return {"final_response": "\n".join(human_parts), "trace": trace}

