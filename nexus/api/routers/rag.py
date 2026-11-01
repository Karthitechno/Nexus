"""RAG knowledge base endpoints."""
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from nexus.api.deps import get_rag_pipeline

logger = logging.getLogger("nexus.api.rag")
router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}


class RAGQueryRequest(BaseModel):
    question: str
    top_k: int = 5


@router.post("/rag/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a PDF/TXT/MD document to the knowledge base."""
    from pathlib import Path
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    rag = get_rag_pipeline()
    result = rag.ingest_bytes(content, file.filename)
    return result


@router.post("/rag/query")
def query_knowledge_base(req: RAGQueryRequest):
    """Query the RAG knowledge base."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    rag = get_rag_pipeline()
    result = rag.query(req.question, top_k=req.top_k)
    return result


@router.get("/rag/documents")
def list_documents():
    """List all ingested documents."""
    rag = get_rag_pipeline()
    docs = rag.list_documents()
    return {"documents": docs, "count": len(docs)}
