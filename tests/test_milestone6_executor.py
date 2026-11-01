"""Tests for Milestone 6: Generic Executor (all HTTP calls mocked)."""
import pytest
from unittest.mock import MagicMock, patch
from nexus.models.tool import ToolDefinition
from nexus.registry.repository import JsonToolRepository
from nexus.executor.executor import GenericExecutor
from nexus.executor.logs import ExecutionLogRepository


def _make_tool(method="GET", risk="LOW"):
    return ToolDefinition(
        tool_id="paypal_invoices_list",
        name="List Invoices",
        service="invoicing",
        category="invoices",
        description="Lists invoices",
        method=method,
        endpoint="/v2/invoicing/invoices",
        parameters={"properties": {"page_size": {"type": "integer", "location": "query"}}},
        risk_level=risk,
    )


def test_tool_not_found(tmp_path):
    repo = JsonToolRepository(str(tmp_path / "tools.json"))
    log_repo = ExecutionLogRepository(str(tmp_path / "logs.json"))
    executor = GenericExecutor(repo, log_repo)
    result = executor.execute("non_existent_tool", {}, "req_001")
    assert result["status"] == "TOOL_NOT_FOUND"
    assert result["tool_id"] == "non_existent_tool"


def test_credentials_missing(tmp_path):
    repo = JsonToolRepository(str(tmp_path / "tools.json"))
    tool = _make_tool()
    repo.create(tool)
    log_repo = ExecutionLogRepository(str(tmp_path / "logs.json"))
    executor = GenericExecutor(repo, log_repo)
    # Force no credentials
    executor.oauth.client_id = ""
    executor.oauth.client_secret = ""
    result = executor.execute("paypal_invoices_list", {}, "req_002")
    assert result["status"] == "NOT_CONFIGURED"
    assert "not configured" in result["message"].lower()


def test_successful_get_mock(tmp_path):
    repo = JsonToolRepository(str(tmp_path / "tools.json"))
    tool = _make_tool(method="GET")
    repo.create(tool)
    log_repo = ExecutionLogRepository(str(tmp_path / "logs.json"))
    executor = GenericExecutor(repo, log_repo)
    executor.oauth.client_id = "test_id"
    executor.oauth.client_secret = "test_secret"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"invoices": [], "total_items": 0}

    with patch("nexus.executor.executor.httpx.Client") as MockClient, \
         patch.object(executor.oauth, "get_token", return_value="fake_token"):
        instance = MockClient.return_value.__enter__.return_value
        instance.get.return_value = mock_response
        result = executor.execute("paypal_invoices_list", {"page_size": 10}, "req_003")

    assert result["status"] == "SUCCESS"
    assert result["response"]["total_items"] == 0
    assert result["latency_ms"] >= 0


def test_disabled_tool(tmp_path):
    repo = JsonToolRepository(str(tmp_path / "tools.json"))
    tool = _make_tool()
    repo.create(tool)
    repo.set_active("paypal_invoices_list", False)
    log_repo = ExecutionLogRepository(str(tmp_path / "logs.json"))
    executor = GenericExecutor(repo, log_repo)
    result = executor.execute("paypal_invoices_list", {}, "req_004")
    assert result["status"] == "TOOL_DISABLED"


def test_log_written_on_not_configured(tmp_path):
    repo = JsonToolRepository(str(tmp_path / "tools.json"))
    tool = _make_tool()
    repo.create(tool)
    log_repo = ExecutionLogRepository(str(tmp_path / "logs.json"))
    executor = GenericExecutor(repo, log_repo)
    executor.oauth.client_id = ""
    executor.oauth.client_secret = ""
    executor.execute("paypal_invoices_list", {}, "req_005")
    log = log_repo.get_by_request_id("req_005")
    assert log is not None
    assert log["status"] == "NOT_CONFIGURED"
