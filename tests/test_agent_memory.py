"""Comprehensive Test Suite for NEXUS Inter-Agent Entity Memory Blackboard & Pass-by-Reference Store."""
import pytest
import uuid
from typing import Dict, Any

from nexus.storage.memory import EntityMemoryStore
from nexus.storage.redis_client import RedisManager
from nexus.tools.slot_filler import SlotFiller
from nexus.models.tool import ToolDefinition
from nexus.registry.repository import JsonToolRepository
from nexus.orchestration.graph import NexusOrchestrator
from nexus.orchestration.state import NexusState


@pytest.fixture
def memory_store():
    store = EntityMemoryStore()
    return store


@pytest.fixture
def sample_send_invoice_tool() -> ToolDefinition:
    return ToolDefinition(
        tool_id="paypal_rest_apis_send_invoice",
        name="Send Invoice",
        service="invoicing",
        category="invoices",
        description="Sends a draft invoice to a customer.",
        method="POST",
        endpoint="/v2/invoicing/invoices/{invoice_id}/send",
        parameters={
            "type": "object",
            "required": ["invoice_id"],
            "properties": {
                "invoice_id": {"type": "string", "description": "The ID of the invoice to send."}
            }
        },
        risk_level="HIGH"
    )


def test_entity_memory_store_basic_crud(memory_store):
    thread_id = f"thread_test_{uuid.uuid4().hex[:8]}"

    # Set entities
    memory_store.set_entity(thread_id, "last_invoice_id", "INV2-TEST-1234-5678-90AB")
    memory_store.set_entity(thread_id, "last_recipient", "alice@example.com")
    memory_store.set_entity(thread_id, "last_amount", "150.00")

    # Get single
    assert memory_store.get_entity(thread_id, "last_invoice_id") == "INV2-TEST-1234-5678-90AB"
    assert memory_store.get_entity(thread_id, "last_recipient") == "alice@example.com"
    assert memory_store.get_entity(thread_id, "nonexistent") is None

    # Get full context
    ctx = memory_store.get_entity_context(thread_id)
    assert ctx["last_invoice_id"] == "INV2-TEST-1234-5678-90AB"
    assert ctx["last_recipient"] == "alice@example.com"
    assert ctx["last_amount"] == "150.00"

    # Clear context
    memory_store.clear_context(thread_id)
    assert memory_store.get_entity_context(thread_id) == {}


def test_deterministic_extraction_from_invoice_creation(memory_store):
    thread_id = f"thread_extract_{uuid.uuid4().hex[:8]}"

    # Simulated PayPal invoice creation response
    tool_output = {
        "status": "SUCCESS",
        "tool_id": "paypal_rest_apis_create_draft_invoice",
        "response": {
            "id": "INV2-4W7Q-WD5Y-4HZK-ELPK",
            "status": "DRAFT",
            "amount": {"currency_code": "USD", "value": "75.50"},
            "primary_recipients": [
                {"billing_info": {"email_address": "client@acme.com"}}
            ]
        }
    }

    extracted = memory_store.extract_and_record_entities(
        thread_id,
        "paypal_rest_apis_create_draft_invoice",
        tool_output
    )

    assert extracted["last_invoice_id"] == "INV2-4W7Q-WD5Y-4HZK-ELPK"
    assert extracted["invoice_id"] == "INV2-4W7Q-WD5Y-4HZK-ELPK"
    assert extracted["last_amount"] == "75.50"
    assert extracted["last_recipient"] == "client@acme.com"
    assert extracted["last_tool_executed"] == "paypal_rest_apis_create_draft_invoice"

    # Context in store is updated
    stored_ctx = memory_store.get_entity_context(thread_id)
    assert stored_ctx["last_invoice_id"] == "INV2-4W7Q-WD5Y-4HZK-ELPK"


def test_deterministic_extraction_from_href_pattern(memory_store):
    thread_id = f"thread_href_{uuid.uuid4().hex[:8]}"

    # When PayPal returns only href link without top-level id
    tool_output = {
        "status": "SUCCESS",
        "tool_id": "paypal_rest_apis_create_draft_invoice",
        "response": {
            "href": "https://api.sandbox.paypal.com/v2/invoicing/invoices/INV2-R3UA-9DKG-DXUA-R7P5",
            "rel": "self",
            "method": "GET"
        }
    }

    extracted = memory_store.extract_and_record_entities(
        thread_id,
        "paypal_rest_apis_create_draft_invoice",
        tool_output
    )

    assert extracted["last_invoice_id"] == "INV2-R3UA-9DKG-DXUA-R7P5"
    assert memory_store.get_entity(thread_id, "last_invoice_id") == "INV2-R3UA-9DKG-DXUA-R7P5"


def test_pass_by_reference_payload_offloading(memory_store):
    thread_id = f"thread_ref_{uuid.uuid4().hex[:8]}"

    # Simulate large collection of 50 invoices
    large_payload = {
        "total_items": 50,
        "items": [{"id": f"INV2-0000-0000-0000-{i:04d}", "amount": {"value": str(i * 10)}} for i in range(50)]
    }

    ref_info = memory_store.store_payload(thread_id, large_payload, summary="50 invoices collection")
    assert ref_info["reference"].startswith("ref:blob_")
    assert ref_info["size_bytes"] > 500

    # Pointer is saved in entity context
    ctx = memory_store.get_entity_context(thread_id)
    assert ctx["last_payload_ref"] == ref_info["reference"]

    # Dereferencing resolves full payload
    resolved = memory_store.resolve_payload(ref_info["reference"])
    assert resolved["total_items"] == 50
    assert len(resolved["items"]) == 50
    assert resolved["items"][0]["id"] == "INV2-0000-0000-0000-0000"


def test_slot_filler_binds_from_entity_context(sample_send_invoice_tool):
    filler = SlotFiller()

    # Query with pronoun / missing ID
    query = "Now send that invoice"

    # Case A: Without entity context -> Missing required field
    res_no_context = filler.fill_slots(query, sample_send_invoice_tool, entity_context=None)
    assert res_no_context["is_valid"] is False
    assert "invoice_id" in res_no_context["missing_fields"]
    assert "clarification_prompt" in res_no_context
    assert "invoice_id" in res_no_context["clarification_prompt"]

    # Case B: With entity context containing last_invoice_id -> Auto-binds!
    entity_ctx = {"last_invoice_id": "INV2-AUTO-BIND-9999-XXXX"}
    res_with_context = filler.fill_slots(query, sample_send_invoice_tool, entity_context=entity_ctx)
    assert res_with_context["is_valid"] is True
    assert res_with_context["missing_fields"] == []
    assert res_with_context["clarification_prompt"] is None
    assert res_with_context["parameters"]["invoice_id"] == "INV2-AUTO-BIND-9999-XXXX"
    assert res_with_context["resolved_memory_slots"]["invoice_id"] == "INV2-AUTO-BIND-9999-XXXX"


def test_multi_turn_inter_agent_memory_resolution(monkeypatch):
    """Simulates multi-turn session:
    Turn 1: Agent creates an invoice.
    Turn 2: Agent sends the invoice using pronoun without re-specifying the invoice ID.
    """
    repo = JsonToolRepository("data/registry/tools.json")
    memory_store = EntityMemoryStore()
    thread_id = f"thread_multi_{uuid.uuid4().hex[:8]}"

    # 1. Turn 1: Simulate Agent A creating invoice
    creation_result = {
        "tool_id": "paypal_rest_apis_create_draft_invoice",
        "status": "SUCCESS",
        "response": {
            "id": "INV2-MULT-ITUR-NTEST-0001",
            "status": "DRAFT",
            "amount": {"value": "99.00"}
        }
    }
    # Harvester records into thread blackboard
    memory_store.extract_and_record_entities(thread_id, "paypal_rest_apis_create_draft_invoice", creation_result)

    # 2. Turn 2: User says "send that invoice"
    followup_query = "send that invoice"
    send_tool = repo.get("paypal_rest_apis_send_invoice")
    assert send_tool is not None

    filler = SlotFiller()
    entity_ctx = memory_store.get_entity_context(thread_id)
    assert entity_ctx.get("last_invoice_id") == "INV2-MULT-ITUR-NTEST-0001"

    filled = filler.fill_slots(followup_query, send_tool, entity_context=entity_ctx)
    assert filled["is_valid"] is True
    assert filled["missing_fields"] == []
    assert filled["parameters"]["invoice_id"] == "INV2-MULT-ITUR-NTEST-0001"
    assert filled["resolved_memory_slots"]["invoice_id"] == "INV2-MULT-ITUR-NTEST-0001"

