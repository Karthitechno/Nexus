"""System search and execution logs endpoints."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from nexus.api.deps import get_system_search, get_log_repo

router = APIRouter()


class SystemSearchRequest(BaseModel):
    query: str


@router.post("/system/search")
def system_search(req: SystemSearchRequest):
    ss = get_system_search()
    result = ss.search(req.query)
    return result


@router.get("/system/logs")
def get_logs(limit: int = Query(50, ge=1, le=500)):
    log_repo = get_log_repo()
    logs = log_repo.get_recent(limit)
    return {"logs": logs, "count": len(logs)}


@router.get("/system/logs/{request_id}")
def get_log_by_request_id(request_id: str):
    log_repo = get_log_repo()
    log = log_repo.get_by_request_id(request_id)
    if not log:
        raise HTTPException(status_code=404, detail=f"No log found for request_id: {request_id}")
    return log
