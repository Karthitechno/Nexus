"""Tool search endpoint."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from nexus.api.deps import get_retriever

router = APIRouter()

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    service: Optional[str] = None

@router.post("/tools/search")
def search_tools(req: SearchRequest):
    retriever = get_retriever()
    result = retriever.retrieve(query=req.query, top_k=req.top_k)
    tools = result.get("tools", [])
    return {
        "query": req.query,
        "results": [
            {
                "tool_id": t.tool_id,
                "name": t.name,
                "service": t.service,
                "category": t.category,
                "method": t.method,
                "endpoint": t.endpoint,
                "description": t.description,
                "risk_level": t.risk_level,
                "score": result.get("retrieval_scores", {}).get(t.tool_id),
                "cross_encoder_score": result.get("cross_encoder_scores", {}).get(t.tool_id),
            }
            for t in tools
        ],
        "count": len(tools),
        "service_routed": result.get("service_routed"),
    }
