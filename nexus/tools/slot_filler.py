"""Schema-Constrained Slot Filling with Deterministic Resolvers and LLM Output."""
import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from pydantic import ValidationError
from nexus.models.tool import ToolDefinition
from nexus.tools.resolvers import (
    resolve_date_window,
    resolve_amount,
    resolve_email,
    resolve_currency,
    resolve_entity_id
)
from nexus.tools.dynamic_factory import create_pydantic_schema_from_tool

logger = logging.getLogger("nexus.slot_filler")


class SlotFiller:
    """Fills parameters for selected tools under strict schema constraints with memory blackboard resolution."""

    def fill_slots(
        self,
        query: str,
        tool: ToolDefinition,
        context_params: Optional[Dict[str, Any]] = None,
        entity_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fill parameters for a tool.
        
        Returns dict with:
            "parameters": Dict[str, Any]
            "is_valid": bool
            "missing_fields": List[str]
            "clarification_prompt": Optional[str]
            "resolved_memory_slots": Dict[str, str]
        """
        # 1. Deterministic Extraction Pass from user query
        deterministic_values = self._deterministic_pass(query, tool)

        # Merge in conversation/prior step context params if supplied
        if context_params:
            for k, v in context_params.items():
                if k not in deterministic_values and v is not None:
                    deterministic_values[k] = v

        # 2. Check required fields
        schema_cls = create_pydantic_schema_from_tool(tool)
        required_fields = list(tool.parameters.get("required", [])) if isinstance(tool.parameters, dict) else []

        # 3. Inter-Agent Entity Memory Blackboard Resolution (Zero LLM, <0.1ms deterministic bind)
        resolved_memory_slots: Dict[str, str] = {}
        if entity_context:
            entity_key_map = {
                "invoice_id": ["last_invoice_id", "invoice_id", "last_active_id"],
                "dispute_id": ["last_dispute_id", "dispute_id", "last_active_id"],
                "order_id": ["last_order_id", "order_id", "last_active_id"],
                "capture_id": ["last_capture_id", "capture_id"],
                "recipient_email": ["last_recipient", "recipient_email"],
                "email": ["last_recipient", "recipient_email"],
                "amount": ["last_amount"],
            }
            for req in required_fields:
                if req not in deterministic_values or deterministic_values[req] in [None, ""]:
                    candidates = entity_key_map.get(req, [req, f"last_{req}"])
                    for cand in candidates:
                        val = entity_context.get(cand)
                        if val is not None and str(val).strip() != "":
                            deterministic_values[req] = val
                            resolved_memory_slots[req] = str(val)
                            logger.info(
                                "Auto-bound missing required slot '%s' for tool '%s' from entity blackboard candidate '%s' = %s",
                                req, tool.tool_id, cand, val
                            )
                            break

        # 4. LLM Extraction Pass (if Gemini configured and we STILL have unfilled fields)
        api_key = os.getenv("GOOGLE_API_KEY")
        still_unfilled = [
            req for req in required_fields
            if req not in deterministic_values or deterministic_values[req] in [None, ""]
        ]
        if api_key and still_unfilled:
            llm_values = self._llm_extraction_pass(query, tool, deterministic_values)
            PLACEHOLDER_STRINGS = {
                "VALUE_REQUIRED", "REQUIRED", "UNKNOWN", "N/A", "NONE", "NULL",
                "<REQUIRED>", "<INVOICE_ID>", "YOUR_INVOICE_ID", "STRING", "PROMPT",
                "OPTIONAL", "ANY", "NOT_SPECIFIED", "TBD"
            }
            filtered_llm = {}
            for k, v in llm_values.items():
                if isinstance(v, str):
                    cleaned = v.strip()
                    if cleaned.upper() in PLACEHOLDER_STRINGS or (cleaned.startswith("<") and cleaned.endswith(">")):
                        continue
                filtered_llm[k] = v
            deterministic_values.update(filtered_llm)

        # 5. Strict Pydantic Schema Validation
        PLACEHOLDER_STRINGS = {
            "VALUE_REQUIRED", "REQUIRED", "UNKNOWN", "N/A", "NONE", "NULL",
            "<REQUIRED>", "<INVOICE_ID>", "YOUR_INVOICE_ID", "STRING", "PROMPT",
            "OPTIONAL", "ANY", "NOT_SPECIFIED", "TBD"
        }
        missing_fields: List[str] = []
        for req in required_fields:
            val = deterministic_values.get(req)
            if val in [None, ""]:
                missing_fields.append(req)
            elif isinstance(val, str) and (
                val.strip().upper() in PLACEHOLDER_STRINGS
                or (val.startswith("<") and val.endswith(">"))
            ):
                missing_fields.append(req)
                deterministic_values.pop(req, None)

        if missing_fields:
            # Strictly do not guess! Return clarification prompt
            fields_str = ", ".join(missing_fields)
            clarification = (
                f"To execute {tool.name}, I need the following required information: {fields_str}. "
                f"Could you please provide this detail?"
            )
            return {
                "parameters": deterministic_values,
                "is_valid": False,
                "missing_fields": missing_fields,
                "clarification_prompt": clarification,
                "resolved_memory_slots": resolved_memory_slots,
            }

        # Validate against schema
        try:
            validated_obj = schema_cls.model_validate(deterministic_values)
            validated_params = validated_obj.model_dump(exclude_none=True)
            return {
                "parameters": validated_params,
                "is_valid": True,
                "missing_fields": [],
                "clarification_prompt": None,
                "resolved_memory_slots": resolved_memory_slots,
            }
        except ValidationError as e:
            logger.warning(f"Validation error for {tool.tool_id}: {e}")
            missing = [err["loc"][0] for err in e.errors() if err["type"] == "missing"]
            return {
                "parameters": deterministic_values,
                "is_valid": False,
                "missing_fields": [str(m) for m in missing],
                "clarification_prompt": f"Invalid or missing parameters for {tool.name}: {e.errors()}",
                "resolved_memory_slots": resolved_memory_slots,
            }

    def _deterministic_pass(self, query: str, tool: ToolDefinition) -> Dict[str, Any]:
        """Extract all deterministic entities and map to tool schema properties."""
        extracted: Dict[str, Any] = {}
        props = tool.parameters.get("properties", {}) if isinstance(tool.parameters, dict) else {}

        # Dates / Time windows
        date_window = resolve_date_window(query)
        if date_window:
            start_iso, end_iso = date_window
            if "start_date" in props:
                extracted["start_date"] = start_iso
            if "end_date" in props:
                extracted["end_date"] = end_iso
            if "start_time" in props:
                extracted["start_time"] = start_iso
            if "end_time" in props:
                extracted["end_time"] = end_iso

        # Amount
        amount = resolve_amount(query)
        if amount is not None:
            if "amount" in props:
                extracted["amount"] = amount
            if "value" in props:
                extracted["value"] = amount

        # Email
        email = resolve_email(query)
        if email is not None:
            for email_key in ["recipient_email", "email_address", "receiver", "client_email"]:
                if email_key in props:
                    extracted[email_key] = email
            if "primary_recipients" in props:
                extracted["primary_recipients"] = [{"billing_info": {"email_address": email}}]

        # Currency
        currency = resolve_currency(query)
        if "currency_code" in props:
            extracted["currency_code"] = currency
        if "currency" in props:
            extracted["currency"] = currency

        # Specific Entity IDs
        if "invoice_id" in props:
            inv_id = resolve_entity_id(query, "INV")
            if inv_id:
                extracted["invoice_id"] = inv_id

        if "dispute_id" in props:
            disp_id = resolve_entity_id(query, "DISP")
            if disp_id:
                extracted["dispute_id"] = disp_id

        if "authorization_id" in props:
            auth_id = resolve_entity_id(query, "AUTH")
            if auth_id:
                extracted["authorization_id"] = auth_id

        return extracted

    def _llm_extraction_pass(
        self,
        query: str,
        tool: ToolDefinition,
        known_values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call Gemini to extract remaining slots under strict JSON schema enforcement."""
        try:
            from google import genai
            from google.genai import types

            client = genai.Client()
            schema_cls = create_pydantic_schema_from_tool(tool)

            prompt = (
                f"Extract parameter values from the following user query for the tool '{tool.name}'.\n"
                f"Description: {tool.description}\n"
                f"Known values already extracted: {json.dumps(known_values)}\n"
                f"User Query: {query}\n"
                f"Extract only the parameters mentioned or clearly implied in the query. Do not hallucinate."
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema_cls,
                    temperature=0.0,
                )
            )

            if response.text:
                extracted = json.loads(response.text)
                return {k: v for k, v in extracted.items() if v is not None}
        except Exception as e:
            logger.warning(f"LLM extraction pass skipped or failed: {e}")

        return {}
