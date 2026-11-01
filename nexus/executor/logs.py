"""Execution log repository - JSON-backed, append-only."""
import json, threading, time
from pathlib import Path
from typing import List, Dict, Any, Optional

class ExecutionLog:
    def __init__(self, request_id, tool_id, status, latency_ms, timestamp=None, error=None, response_summary=None):
        self.request_id = request_id
        self.tool_id = tool_id
        self.status = status
        self.latency_ms = latency_ms
        self.timestamp = timestamp or time.time()
        self.error = error
        self.response_summary = response_summary

    def to_dict(self):
        return {
            "request_id": self.request_id,
            "tool_id": self.tool_id,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "error": self.error,
            "response_summary": self.response_summary,
        }

class ExecutionLogRepository:
    def __init__(self, storage_path="data/logs/execution_logs.json"):
        self.path = Path(storage_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._logs: List[Dict] = []
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path) as f:
                    self._logs = json.load(f)
            except Exception:
                self._logs = []

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self._logs[-5000:], f, indent=2)  # keep last 5000

    def append(self, log: ExecutionLog):
        with self._lock:
            self._logs.append(log.to_dict())
            self._save()

    def get_by_request_id(self, request_id: str) -> Optional[Dict]:
        with self._lock:
            matches = [l for l in self._logs if l["request_id"] == request_id]
            return matches[-1] if matches else None

    def get_recent(self, limit=100) -> List[Dict]:
        with self._lock:
            return list(reversed(self._logs[-limit:]))

    def get_failures(self, limit=50) -> List[Dict]:
        with self._lock:
            fails = [l for l in self._logs if l["status"] not in ("SUCCESS", "STAGED")]
            return list(reversed(fails[-limit:]))

    def count(self) -> int:
        return len(self._logs)
