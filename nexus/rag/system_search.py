"""System Search: structured queries over the tool registry and execution logs."""
import logging
from typing import Dict, Any, List, Optional
from nexus.registry.repository import IToolRepository
from nexus.models.tool import ToolFilter
from nexus.executor.logs import ExecutionLogRepository

logger = logging.getLogger("nexus.system_search")


class SystemSearch:
    def __init__(self, repository: IToolRepository, log_repo: ExecutionLogRepository):
        self.repository = repository
        self.log_repo = log_repo

    def search(self, query: str) -> Dict[str, Any]:
        """Route natural-language system query to structured search."""
        lower = query.lower()

        # Route to specific handlers
        if any(t in lower for t in ["request status", "request_id", "req_"]):
            # Extract request ID from query
            import re
            match = re.search(r"(req_[a-zA-Z0-9_-]+|[0-9a-f-]{36})", query)
            if match:
                return self.get_request_status(match.group(1))
            return {"summary": "Please provide a request ID to look up its status.", "data": []}

        elif any(t in lower for t in ["failure", "failed", "error", "errors"]):
            return self.get_recent_failures()

        elif any(t in lower for t in ["recent", "logs", "history", "last"]):
            return self.get_recent_logs()

        elif any(t in lower for t in ["tool count", "how many tools", "count"]):
            return self.get_registry_stats()

        elif any(t in lower for t in ["service", "category", "filter", "by service", "tool", "tools", "search", "find"]):
            return self.search_tools_structured(query)

        else:
            return self.get_registry_overview()

    def get_registry_overview(self) -> Dict[str, Any]:
        all_tools = self.repository.list()
        active = [t for t in all_tools if t.is_active]
        services = {}
        for t in all_tools:
            services.setdefault(t.service, 0)
            services[t.service] += 1

        summary_lines = [
            f"NEXUS Registry contains **{len(all_tools)} tools** ({len(active)} active).",
            "",
            "**By Service:**",
        ]
        for svc, cnt in sorted(services.items()):
            active_in_svc = sum(1 for t in all_tools if t.service == svc and t.is_active)
            summary_lines.append(f"- `{svc}`: {cnt} tools ({active_in_svc} active)")

        log_count = self.log_repo.count()
        summary_lines.append(f"\n**Execution Logs:** {log_count} recorded requests.")

        return {
            "summary": "\n".join(summary_lines),
            "data": {
                "total_tools": len(all_tools),
                "active_tools": len(active),
                "by_service": services,
                "log_count": log_count,
            },
        }

    def get_registry_stats(self) -> Dict[str, Any]:
        all_tools = self.repository.list()
        by_service: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        by_method: Dict[str, int] = {}
        high_risk = 0

        for t in all_tools:
            by_service[t.service] = by_service.get(t.service, 0) + 1
            by_category[t.category] = by_category.get(t.category, 0) + 1
            by_method[t.method] = by_method.get(t.method, 0) + 1
            if t.risk_level == "HIGH":
                high_risk += 1

        return {
            "summary": (
                f"Registry stats: {len(all_tools)} tools total, "
                f"{high_risk} high-risk, across {len(by_service)} services."
            ),
            "data": {
                "total": len(all_tools),
                "high_risk": high_risk,
                "by_service": by_service,
                "by_category": by_category,
                "by_method": by_method,
            },
        }

    def search_tools_structured(self, query: str) -> Dict[str, Any]:
        """Text search over registry name/description/service/category."""
        import re
        search_term = re.sub(r"\b(search\s+for|find|show|list|get|tools?|available|all|managing|about|for)\b", "", query, flags=re.I).strip()
        search_term = search_term or query
        filter_opts = ToolFilter(search=search_term)
        tools = self.repository.list(filter_opts)

        if not tools:
            # Fallback to individual meaningful words
            words = [w for w in search_term.split() if len(w) > 3]
            for w in words:
                tools = self.repository.list(ToolFilter(search=w))
                if tools:
                    search_term = w
                    break

        if not tools:
            tools = [t for t in self.repository.list() if t.is_active][:10]
            summary_lines = [f"Here are active tools from the registry:"]
        else:
            summary_lines = [f"Found **{len(tools)} tools** related to `{search_term}`:"]

        for t in tools[:8]:
            summary_lines.append(f"- **{t.name}** (`{t.method} {t.endpoint}`): {t.description}")

        tool_list = [
            {"tool_id": t.tool_id, "name": t.name, "service": t.service,
             "method": t.method, "is_active": t.is_active}
            for t in tools[:20]
        ]
        return {
            "summary": "\n".join(summary_lines),
            "data": tool_list,
        }

    def get_request_status(self, request_id: str) -> Dict[str, Any]:
        log = self.log_repo.get_by_request_id(request_id)
        if not log:
            return {
                "summary": f"No execution log found for request_id: `{request_id}`",
                "data": None,
            }
        return {
            "summary": (
                f"Request `{request_id}`: tool=`{log['tool_id']}`, "
                f"status=`{log['status']}`, latency={log['latency_ms']:.1f}ms"
            ),
            "data": log,
        }

    def get_recent_logs(self, limit: int = 20) -> Dict[str, Any]:
        logs = self.log_repo.get_recent(limit)
        return {
            "summary": f"Last {len(logs)} execution logs.",
            "data": logs,
        }

    def get_recent_failures(self, limit: int = 20) -> Dict[str, Any]:
        fails = self.log_repo.get_failures(limit)
        return {
            "summary": f"Found {len(fails)} recent failures.",
            "data": fails,
        }
