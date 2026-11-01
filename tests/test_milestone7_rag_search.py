"""Tests for Milestone 7: RAG Pipeline and System Search."""
import pytest
from pathlib import Path
from nexus.models.tool import ToolDefinition
from nexus.registry.repository import JsonToolRepository
from nexus.executor.logs import ExecutionLogRepository, ExecutionLog
from nexus.rag.system_search import SystemSearch


def _seed_repo(repo, n=5):
    for i in range(n):
        service = "invoicing" if i < 3 else "payments"
        tool = ToolDefinition(
            tool_id=f"tool_{i:03d}",
            name=f"Tool {i}",
            service=service,
            category="test",
            description=f"Test tool {i}",
            method="GET" if i % 2 == 0 else "POST",
            endpoint=f"/v1/test/{i}",
        )
        repo.create(tool)


def test_system_search_registry_overview(tmp_path):
    repo = JsonToolRepository(str(tmp_path / "tools.json"))
    log_repo = ExecutionLogRepository(str(tmp_path / "logs.json"))
    _seed_repo(repo, 5)
    ss = SystemSearch(repo, log_repo)
    result = ss.get_registry_overview()
    assert "5 tools" in result["summary"]
    assert result["data"]["total_tools"] == 5


def test_system_search_stats(tmp_path):
    repo = JsonToolRepository(str(tmp_path / "tools.json"))
    log_repo = ExecutionLogRepository(str(tmp_path / "logs.json"))
    _seed_repo(repo, 5)
    ss = SystemSearch(repo, log_repo)
    stats = ss.get_registry_stats()
    assert stats["data"]["total"] == 5
    assert "invoicing" in stats["data"]["by_service"]
    assert "payments" in stats["data"]["by_service"]


def test_system_search_request_status(tmp_path):
    repo = JsonToolRepository(str(tmp_path / "tools.json"))
    log_repo = ExecutionLogRepository(str(tmp_path / "logs.json"))
    log_repo.append(ExecutionLog("req_abc123", "tool_001", "SUCCESS", 120.5))
    ss = SystemSearch(repo, log_repo)
    result = ss.get_request_status("req_abc123")
    assert "req_abc123" in result["summary"]
    assert result["data"]["status"] == "SUCCESS"


def test_system_search_unknown_returns_overview(tmp_path):
    repo = JsonToolRepository(str(tmp_path / "tools.json"))
    log_repo = ExecutionLogRepository(str(tmp_path / "logs.json"))
    _seed_repo(repo, 3)
    ss = SystemSearch(repo, log_repo)
    result = ss.search("What is the current state of the system?")
    assert "summary" in result


def test_rag_pipeline_chunk_function():
    """Test chunking logic without filesystem or model deps."""
    from nexus.rag.pipeline import _chunk_text
    text = "A" * 1200
    chunks = _chunk_text(text, chunk_size=500, overlap=100)
    assert len(chunks) >= 3
    assert all(len(c) <= 500 for c in chunks)


def test_rag_pipeline_extract_text_txt(tmp_path):
    """Test text extraction for .txt files."""
    from nexus.rag.pipeline import _extract_text_from_file
    f = tmp_path / "test.txt"
    f.write_text("Hello NEXUS documentation!")
    text = _extract_text_from_file(f)
    assert "Hello NEXUS" in text


def test_rag_pipeline_extract_text_md(tmp_path):
    """Test text extraction for .md files."""
    from nexus.rag.pipeline import _extract_text_from_file
    f = tmp_path / "test.md"
    f.write_text("# NEXUS Guide\nThis is a guide.")
    text = _extract_text_from_file(f)
    assert "NEXUS Guide" in text
