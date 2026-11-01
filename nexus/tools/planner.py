"""Multi-Step Task Decomposition and Dependency DAG Planner."""
import re
from typing import List, Dict, Any, Optional
from nexus.models.tool import ToolDefinition
from nexus.retrieval.hybrid import HybridRetriever


class MultiStepPlanner:
    """Decomposes complex multi-intent requests and models dependencies."""

    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever

    def plan(
        self,
        query: str,
        session_sticky_tools: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Decompose query into sequential execution steps with dependency mappings."""
        sub_queries = self._decompose_query(query)
        steps: List[Dict[str, Any]] = []

        for idx, sub_q in enumerate(sub_queries):
            retrieval_res = self.retriever.retrieve(
                sub_q,
                top_k=3,
                session_sticky_tools=session_sticky_tools
            )
            tools = retrieval_res.get("tools", [])
            selected_tool = tools[0] if tools else None

            if not selected_tool:
                continue

            dependencies = self._find_dependencies(selected_tool, steps)

            step_data = {
                "step_index": idx + 1,
                "sub_query": sub_q,
                "tool_id": selected_tool.tool_id,
                "tool_name": selected_tool.name,
                "tool_definition": selected_tool,
                "dependencies": dependencies,
                "risk_level": selected_tool.risk_level,
                "status": "PLANNED",
            }
            steps.append(step_data)

        if not steps:
            retrieval_res = self.retriever.retrieve(query, top_k=3, session_sticky_tools=session_sticky_tools)
            tools = retrieval_res.get("tools", [])
            if tools:
                steps.append({
                    "step_index": 1,
                    "sub_query": query,
                    "tool_id": tools[0].tool_id,
                    "tool_name": tools[0].name,
                    "tool_definition": tools[0],
                    "dependencies": {},
                    "risk_level": tools[0].risk_level,
                    "status": "PLANNED",
                })

        return steps

    def _decompose_query(self, query: str) -> List[str]:
        """Split compound queries into actionable subtasks."""
        # Check for multi-step conjunction markers using lookahead so actions are preserved
        split_patterns = [
            r"\s+and\s+then\s+",
            r"\s+then\s+",
            r"\s*,\s*and\s+(?:then\s+)?",
            r"\s+and\s+(?=(?:send|capture|verify|check|accept|refund)\b)",
        ]
        
        for pattern in split_patterns:
            parts = re.split(pattern, query, flags=re.IGNORECASE)
            if len(parts) > 1:
                cleaned = [p.strip() for p in parts if p.strip()]
                # If follow-up mentions "it", expand into clear referent
                if len(cleaned) == 2:
                    p2 = cleaned[1].lower()
                    if "send it" in p2:
                        cleaned[1] = "Send the invoice"
                    elif "capture it" in p2:
                        cleaned[1] = "Capture the order"
                    elif "accept claim" in p2:
                        cleaned[1] = "Accept dispute claim"
                return cleaned

        # Implicit multi-step: "Send an invoice for $50 to bob@example.com"
        # If user says "send [an/a] invoice" with creation parameters ($ or recipient email)
        # but WITHOUT an existing invoice ID (e.g. INV2-XXXX), it requires creating the draft first then sending it.
        q_lower = query.lower()
        if re.search(r"\bsend\s+(?:an?|the)?\s*invoice\b", q_lower):
            has_params = bool(re.search(r"(\$\s*\d+|\d+\s*(?:dollars|usd)|to\s+\S+@\S+)", query, re.I))
            has_existing_id = bool(re.search(r"\bINV2?-[A-Z0-9-]{4,}\b", query, re.I))
            if has_params and not has_existing_id:
                create_q = re.sub(r"\bsend\s+(?:an?|the)?\s*invoice", "Create an invoice", query, flags=re.I).strip()
                return [create_q, "Send the invoice"]

        return [query.strip()]

    def _find_dependencies(
        self,
        current_tool: ToolDefinition,
        previous_steps: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Detect if current_tool parameters depend on previous step outputs."""
        deps: Dict[str, str] = {}
        props = current_tool.parameters.get("properties", {}) if isinstance(current_tool.parameters, dict) else {}

        for prev in previous_steps:
            prev_id = prev.get("tool_id", "")
            prev_step_num = prev.get("step_index", 1)

            # Case 1: Invoicing create -> send (needs invoice_id)
            if "send" in current_tool.endpoint and ("invoice_id" in props or "{invoice_id}" in current_tool.endpoint):
                if "create" in prev_id or "invoices" in prev_id:
                    deps["invoice_id"] = f"$step_{prev_step_num}.id"

            # Case 2: Checkout order create -> capture (needs id / order_id)
            if "capture" in current_tool.endpoint and ("id" in props or "order_id" in props or "{id}" in current_tool.endpoint):
                if "orders" in prev_id:
                    key = "id" if ("id" in props or "{id}" in current_tool.endpoint) else "order_id"
                    deps[key] = f"$step_{prev_step_num}.id"

            # Case 3: Dispute get -> accept claim (needs dispute_id)
            if "accept-claim" in current_tool.endpoint and ("dispute_id" in props or "{dispute_id}" in current_tool.endpoint):
                if "disputes" in prev_id:
                    deps["dispute_id"] = f"$step_{prev_step_num}.id"

        return deps
