"""Health check endpoint."""
import time
from fastapi import APIRouter
from nexus.api.deps import _singletons

router = APIRouter()
_start_time = time.time()

@router.get("/health")
def health():
    repo = _singletons.get("repository")
    tool_count = repo.count() if repo else 0
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "tool_count": tool_count,
        "services_initialized": _singletons.get("initialized", False),
    }
