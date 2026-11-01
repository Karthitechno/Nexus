"""Tests for Enhancements: Universal OpenAPI Importer, Auto-Healing, and Streaming."""
import os
import sys
import json
import pytest

sys.path.insert(0, r"d:\Nexus")

from nexus.registry.importer import UniversalSpecImporter, OpenApiImporter, PostmanImporter
from nexus.models.tool import ToolDefinition


def test_openapi_importer_parses_swagger_spec():
    sample_openapi = {
        "openapi": "3.0.0",
        "info": {
            "title": "Stripe Payments Mock",
            "version": "1.0.0",
        },
        "paths": {
            "/v1/charges": {
                "post": {
                    "operationId": "create_charge",
                    "summary": "Create a new payment charge",
                    "description": "Captures a charge on customer card",
                    "tags": ["charges"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["amount", "currency"],
                                    "properties": {
                                        "amount": {"type": "number", "description": "Amount in cents"},
                                        "currency": {"type": "string", "description": "3-letter currency code"},
                                        "customer_id": {"type": "string", "description": "Customer ID"}
                                    }
                                }
                            }
                        }
                    }
                },
                "get": {
                    "operationId": "list_charges",
                    "summary": "List all charges",
                    "tags": ["charges"],
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer"}, "required": False}
                    ]
                }
            }
        }
    }

    importer = UniversalSpecImporter()
    tools = importer.import_any(sample_openapi)

    assert len(tools) == 2
    tool_map = {t.tool_id: t for t in tools}

    assert "create_charge" in tool_map
    charge_tool = tool_map["create_charge"]
    assert charge_tool.method == "POST"
    assert charge_tool.risk_level == "HIGH"
    assert "amount" in charge_tool.parameters.get("required", [])

    assert "list_charges" in tool_map
    list_tool = tool_map["list_charges"]
    assert list_tool.method == "GET"
    assert list_tool.risk_level == "LOW"
    assert "limit" in list_tool.parameters.get("properties", {})


def test_universal_spec_importer_detects_postman():
    sample_postman = {
        "info": {
            "_postman_id": "test-id-123",
            "name": "Custom Postman Service"
        },
        "item": [
            {
                "name": "Check Health",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "https://api.example.com/health",
                        "path": ["health"]
                    }
                }
            }
        ]
    }

    importer = UniversalSpecImporter()
    tools = importer.import_any(sample_postman)
    assert len(tools) == 1
    assert tools[0].endpoint == "/health"
    assert tools[0].method == "GET"

