

"""Tests for Milestone 4: Dynamic Tools, Slot Filling, Resolvers, and Multi-Step Planning."""
import pytest
from datetime import datetime, timezone
from nexus.models.tool import ToolDefinition
from nexus.tools.resolvers import (
    resolve_date_window,
    resolve_amount,
    resolve_email,
    resolve_currency,
    resolve_entity_id
)
from nexus.tools.dynamic_factory import (
    create_pydantic_schema_from_tool,
    convert_to_structured_tool
)
from nexus.tools.slot_filler import SlotFiller
from nexus.tools.planner import MultiStepPlanner


def test_deterministic_resolvers():
    # 1. Date window
    fixed_now = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)
    res_last_month = resolve_date_window("Show transactions from last month", now=fixed_now)
    assert res_last_month is not None
    start, end = res_last_month
    assert start.startswith("2026-09-01")
    assert end.startswith("2026-09-30")
    
    res_7_days = resolve_date_window("Invoices in the last 7 days", now=fixed_now)
    assert res_7_days is not None
    assert res_7_days[0].startswith("2026-10-23")
    
    # 2. Amounts
    assert resolve_amount("Send invoice for $50.00 to Bob") == 50.0
    assert resolve_amount("Total sales was $1250 last week") == 1250.0
    assert resolve_amount("Charge 75 USD") == 75.0
    
    # 3. Email
    assert resolve_email("Send bill to bob@example.com right now") == "bob@example.com"
    assert resolve_email("No email here") is None
    
    # 4. Currency
    assert resolve_currency("Invoice for 50 EUR") == "EUR"
    assert resolve_currency("Invoice for $50") == "USD"
    
    # 5. Entity IDs
    assert resolve_entity_id("Details for invoice INV2-9988-7766", "INV") == "INV2-9988-7766"
    assert resolve_entity_id("Accept claim on dispute DISP-1010", "DISP") == "DISP-1010"


def test_dynamic_pydantic_schema():
    tool = ToolDefinition(
        tool_id="test_invoice_create",
        name="Create Invoice",
        service="invoicing",
        category="invoices",
        description="Creates draft invoice",
        method="POST",
        endpoint="/v2/invoicing/invoices",
        parameters={
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Invoice total amount"},
                "recipient_email": {"type": "string", "description": "Customer email"},
                "note": {"type": "string", "description": "Optional merchant memo"}
            },
            "required": ["amount", "recipient_email"]
        }
    )
    
    schema_cls = create_pydantic_schema_from_tool(tool)
    
    # Valid instantiation
    valid_instance = schema_cls(amount=50.0, recipient_email="bob@example.com")
    assert valid_instance.amount == 50.0
    assert valid_instance.recipient_email == "bob@example.com"
    assert valid_instance.note is None
    
    # StructuredTool wrapping
    structured = convert_to_structured_tool(tool)
    assert structured.name == "test_invoice_create"
    assert structured.args_schema == schema_cls


def test_slot_filling_and_clarification():
    tool = ToolDefinition(
        tool_id="paypal_invoices_create",
        name="Create Invoice",
        service="invoicing",
        category="invoices",
        description="Creates draft invoice",
        method="POST",
        endpoint="/v2/invoicing/invoices",
        parameters={
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Invoice amount"},
                "recipient_email": {"type": "string", "description": "Recipient email"}
            },
            "required": ["amount", "recipient_email"]
        }
    )
    
    filler = SlotFiller()
    
    # Complete information
    res_complete = filler.fill_slots("Send an invoice for $50 to bob@example.com", tool)
    assert res_complete["is_valid"] is True
    assert res_complete["parameters"]["amount"] == 50.0
    assert res_complete["parameters"]["recipient_email"] == "bob@example.com"
    assert len(res_complete["missing_fields"]) == 0
    
    # Missing email: should NOT guess, must request clarification
    res_missing = filler.fill_slots("Send an invoice for $50", tool)
    assert res_missing["is_valid"] is False
    assert "recipient_email" in res_missing["missing_fields"]
    assert "clarification_prompt" in res_missing
    assert "recipient_email" in res_missing["clarification_prompt"]


def test_multi_step_planner():
    class DummyRetriever:
        def retrieve(self, query, top_k=3, session_sticky_tools=None):
            q = query.lower()
            if "create" in q or "invoice" in q:
                t1 = ToolDefinition(
                    tool_id="paypal_invoices_create",
                    name="Create Invoice",
                    service="invoicing",
                    category="invoices",
                    description="Create invoice",
                    method="POST",
                    endpoint="/v2/invoicing/invoices",
                    risk_level="HIGH"
                )
                return {"tools": [t1]}
            elif "send" in q:
                t2 = ToolDefinition(
                    tool_id="paypal_invoices_send",
                    name="Send Invoice",
                    service="invoicing",
                    category="invoices",
                    description="Send invoice",
                    method="POST",
                    endpoint="/v2/invoicing/invoices/{invoice_id}/send",
                    parameters={"properties": {"invoice_id": {"type": "string"}}, "required": ["invoice_id"]},
                    risk_level="HIGH"
                )
                return {"tools": [t2]}
            return {"tools": []}

    planner = MultiStepPlanner(DummyRetriever())
    compound_query = "Create an invoice for $50 to bob@example.com and send it right away"
    plan = planner.plan(compound_query)
    
    assert len(plan) == 2
    assert plan[0]["tool_id"] == "paypal_invoices_create"
    assert plan[1]["tool_id"] == "paypal_invoices_send"
    assert plan[1]["dependencies"].get("invoice_id") == "$step_1.id"
