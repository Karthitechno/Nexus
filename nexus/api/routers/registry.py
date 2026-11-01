"""Tool Registry API routes."""
import json, logging
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from nexus.api.deps import get_repository
from nexus.models.tool import ToolDefinition, ToolFilter
from nexus.registry.importer import PostmanImporter, UniversalSpecImporter

logger = logging.getLogger("nexus.api.registry")
router = APIRouter()


class RegisterToolRequest(BaseModel):
    tool_id: str
    name: str
    service: str
    category: str
    description: str
    method: str
    endpoint: str
    parameters: dict = {}
    request_schema: dict = {}
    permission: str = "api.execute"
    risk_level: str = "LOW"
    example_queries: list = []


@router.post("/tools/import")
async def import_collection(file: UploadFile = File(...)):
    """Import OpenAPI 3.x, Swagger 2.0, or Postman JSON collection dynamically."""
    repo = get_repository()
    content = await file.read()
    try:
        spec_data = json.loads(content.decode("utf-8", errors="replace"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file.")

    importer = UniversalSpecImporter()
    try:
        tools = importer.import_any(spec_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Import parsing failed: {e}")

    imported, skipped, errors, tool_ids = [], [], [], []
    for tool in tools:
        try:
            repo.create(tool)
            imported.append(tool.tool_id)
            tool_ids.append(tool.tool_id)
        except ValueError as e:
            skipped.append({"tool_id": tool.tool_id, "reason": str(e)})
        except Exception as e:
            errors.append({"tool_id": tool.tool_id, "error": str(e)})

    return {
        "imported": len(imported),
        "skipped": len(skipped),
        "errors": len(errors),
        "tool_ids": tool_ids,
        "total_tools": repo.count(),
        "skipped_details": skipped,
        "error_details": errors,
    }


@router.post("/tools/register")
def register_tool(req: RegisterToolRequest):
    """Register a single tool definition."""
    repo = get_repository()
    tool = ToolDefinition(**req.model_dump())
    try:
        created = repo.create(tool)
        return {"status": "created", "tool_id": created.tool_id}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/tools")
def list_tools(
    service: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
):
    """List tools with optional filters."""
    repo = get_repository()
    filter_opts = ToolFilter(service=service, category=category, method=method,
                              is_active=is_active, search=search)
    tools = repo.list(filter_opts)
    return {"tools": [t.model_dump() for t in tools], "count": len(tools)}


@router.get("/tools/stats")
def registry_stats():
    """Registry summary statistics."""
    repo = get_repository()
    all_tools = repo.list()
    by_service, by_category, by_method, by_risk = {}, {}, {}, {}
    for t in all_tools:
        by_service[t.service] = by_service.get(t.service, 0) + 1
        by_category[t.category] = by_category.get(t.category, 0) + 1
        by_method[t.method] = by_method.get(t.method, 0) + 1
        by_risk[t.risk_level] = by_risk.get(t.risk_level, 0) + 1
    active = sum(1 for t in all_tools if t.is_active)
    return {
        "total": len(all_tools),
        "active": active,
        "inactive": len(all_tools) - active,
        "by_service": by_service,
        "by_category": by_category,
        "by_method": by_method,
        "by_risk_level": by_risk,
    }


@router.get("/tools/{tool_id}")
def get_tool(tool_id: str):
    repo = get_repository()
    tool = repo.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found.")
    return tool.model_dump()


@router.delete("/tools/{tool_id}")
def delete_tool(tool_id: str):
    repo = get_repository()
    deleted = repo.delete(tool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found.")
    return {"status": "deleted", "tool_id": tool_id}


@router.post("/tools/{tool_id}/enable")
def enable_tool(tool_id: str):
    repo = get_repository()
    try:
        tool = repo.set_active(tool_id, True)
        return {"status": "enabled", "tool_id": tool.tool_id}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found.")


@router.post("/tools/{tool_id}/disable")
def disable_tool(tool_id: str):
    repo = get_repository()
    try:
        tool = repo.set_active(tool_id, False)
        return {"status": "disabled", "tool_id": tool.tool_id}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found.")
