"""Tool Registry Repository Interface and JSON Implementation."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
import json
import os
import threading
from pathlib import Path
from nexus.models.tool import ToolDefinition, ToolFilter


class IToolRepository(ABC):
    """Abstract Repository interface for Tool Definitions. Postgres-ready."""

    @abstractmethod
    def get(self, tool_id: str) -> Optional[ToolDefinition]:
        """Fetch single tool by ID."""
        pass

    @abstractmethod
    def list(self, filter_opts: Optional[ToolFilter] = None) -> List[ToolDefinition]:
        """List tools with optional filters."""
        pass

    @abstractmethod
    def create(self, tool: ToolDefinition) -> ToolDefinition:
        """Create new tool. Raises ValueError if ID already exists."""
        pass

    @abstractmethod
    def update(self, tool: ToolDefinition) -> ToolDefinition:
        """Update existing tool. Raises KeyError if not found."""
        pass

    @abstractmethod
    def delete(self, tool_id: str) -> bool:
        """Delete tool by ID. Returns True if deleted."""
        pass

    @abstractmethod
    def set_active(self, tool_id: str, is_active: bool) -> ToolDefinition:
        """Enable or disable a tool."""
        pass

    @abstractmethod
    def count(self) -> int:
        """Total number of tools in registry."""
        pass


class JsonToolRepository(IToolRepository):
    """Thread-safe JSON file-backed tool repository implementation."""

    def __init__(self, storage_path: str = "data/registry/tools.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._tools: Dict[str, ToolDefinition] = {}
        self._change_listeners: List[Callable[[str, Optional[ToolDefinition], str], None]] = []
        self._load()

    @property
    def content_hash(self) -> str:
        """Returns compact hash of current repository state for cache invalidation."""
        import hashlib
        with self._lock:
            parts = [f"{t.tool_id}:{getattr(t, 'content_hash', '')}" for t in sorted(self._tools.values(), key=lambda x: x.tool_id)]
            return hashlib.sha256(";".join(parts).encode()).hexdigest()[:16]

    def add_change_listener(self, callback: Callable[[str, Optional[ToolDefinition], str], None]):
        """Register callback for tool changes: callback(tool_id, tool_definition, action)."""
        self._change_listeners.append(callback)

    def _notify(self, tool_id: str, tool: Optional[ToolDefinition], action: str):
        for listener in self._change_listeners:
            try:
                listener(tool_id, tool, action)
            except Exception as e:
                # Log or ignore listener failure to maintain transaction integrity
                pass

    def _load(self):
        with self._lock:
            if self.storage_path.exists():
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._tools = {
                            item["tool_id"]: ToolDefinition.model_validate(item)
                            for item in data
                        }
                except (json.JSONDecodeError, KeyError) as e:
                    self._tools = {}
            else:
                self._tools = {}
                self._save()

    def _save(self):
        with self._lock:
            temp_path = self.storage_path.with_suffix(".tmp")
            data = [tool.model_dump() for tool in self._tools.values()]
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(temp_path, self.storage_path)

    def get(self, tool_id: str) -> Optional[ToolDefinition]:
        with self._lock:
            return self._tools.get(tool_id)

    def list(self, filter_opts: Optional[ToolFilter] = None) -> List[ToolDefinition]:
        with self._lock:
            items = list(self._tools.values())
            if not filter_opts:
                return items
            
            filtered = []
            for t in items:
                if filter_opts.service and t.service.lower() != filter_opts.service.lower():
                    continue
                if filter_opts.category and t.category.lower() != filter_opts.category.lower():
                    continue
                if filter_opts.method and t.method.upper() != filter_opts.method.upper():
                    continue
                if filter_opts.is_active is not None and t.is_active != filter_opts.is_active:
                    continue
                if filter_opts.search:
                    term = filter_opts.search.lower()
                    text = f"{t.name} {t.description} {t.endpoint} {t.tool_id}".lower()
                    if term not in text:
                        continue
                filtered.append(t)
            return filtered

    def create(self, tool: ToolDefinition) -> ToolDefinition:
        with self._lock:
            if tool.tool_id in self._tools:
                raise ValueError(f"Tool with ID '{tool.tool_id}' already exists.")
            self._tools[tool.tool_id] = tool
            self._save()
            self._notify(tool.tool_id, tool, "CREATE")
            return tool

    def update(self, tool: ToolDefinition) -> ToolDefinition:
        with self._lock:
            if tool.tool_id not in self._tools:
                raise KeyError(f"Tool with ID '{tool.tool_id}' not found.")
            self._tools[tool.tool_id] = tool
            self._save()
            self._notify(tool.tool_id, tool, "UPDATE")
            return tool

    def delete(self, tool_id: str) -> bool:
        with self._lock:
            if tool_id in self._tools:
                deleted = self._tools.pop(tool_id)
                self._save()
                self._notify(tool_id, None, "DELETE")
                return True
            return False

    def set_active(self, tool_id: str, is_active: bool) -> ToolDefinition:
        with self._lock:
            if tool_id not in self._tools:
                raise KeyError(f"Tool with ID '{tool_id}' not found.")
            tool = self._tools[tool_id]
            tool.is_active = is_active
            self._save()
            self._notify(tool_id, tool, "UPDATE")
            return tool

    def count(self) -> int:
        with self._lock:
            return len(self._tools)

