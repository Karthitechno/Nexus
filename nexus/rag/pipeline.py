"""RAG Pipeline: document ingestion and retrieval-augmented generation."""
import os, logging, re
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings

logger = logging.getLogger("nexus.rag")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
RAG_COLLECTION = "nexus_rag_docs"
RAG_DOCS_DIR = Path("data/rag_docs")
CHROMA_PERSIST_DIR = "data/chroma_db"


def _extract_text_from_file(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(str(file_path)) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            return "\n".join(pages)
        except ImportError:
            logger.warning("pdfplumber not installed, skipping PDF extraction")
            return ""
        except Exception as e:
            logger.error("PDF extraction failed for %s: %s", file_path, e)
            return ""
    elif suffix in (".txt", ".md"):
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.error("Text read failed for %s: %s", file_path, e)
            return ""
    else:
        logger.warning("Unsupported file type: %s", suffix)
        return ""


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks."""
    if not text.strip():
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


class RAGPipeline:
    def __init__(self, chroma_persist_dir: str = CHROMA_PERSIST_DIR):
        self.chroma_persist_dir = chroma_persist_dir
        self._client: Optional[chromadb.ClientAPI] = None
        self._collection = None
        self._embedder = None
        self._llm = None
        RAG_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    def _get_client(self):
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self.chroma_persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
        return self._client

    def _get_collection(self):
        if self._collection is None:
            self._collection = self._get_client().get_or_create_collection(
                name=RAG_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _get_embedder(self):
        if self._embedder is None:
            from nexus.retrieval.embedder import ModelManager
            self._embedder = ModelManager()
        return self._embedder

    def _get_llm(self):
        if self._llm is None:
            api_key = os.environ.get("GOOGLE_API_KEY", "")
            if not api_key:
                return None
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
                self._llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)
            except Exception as e:
                logger.warning("Could not initialize Gemini LLM: %s", e)
                return None
        return self._llm

    def ingest_file(self, file_path: str, filename: str = None) -> Dict[str, Any]:
        """Ingest a file into the RAG vector store. Returns ingestion stats."""
        path = Path(file_path)
        if not filename:
            filename = path.name

        text = _extract_text_from_file(path)
        if not text.strip():
            return {"filename": filename, "chunks_indexed": 0, "status": "EMPTY", "message": "No text extracted."}

        chunks = _chunk_text(text)
        if not chunks:
            return {"filename": filename, "chunks_indexed": 0, "status": "EMPTY", "message": "No chunks generated."}

        # Embed chunks
        embedder = self._get_embedder()
        embeddings = embedder.embed_texts(chunks)

        collection = self._get_collection()

        # Build IDs (filename + chunk index, deduplicated)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", filename)
        ids = [f"{safe_name}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]

        # Upsert (handles re-ingestion)
        collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info("Ingested %d chunks from '%s'", len(chunks), filename)
        return {
            "filename": filename,
            "chunks_indexed": len(chunks),
            "status": "SUCCESS",
            "message": f"Indexed {len(chunks)} chunks.",
        }

    def ingest_bytes(self, content: bytes, filename: str) -> Dict[str, Any]:
        """Save uploaded bytes to disk then ingest."""
        dest = RAG_DOCS_DIR / filename
        dest.write_bytes(content)
        return self.ingest_file(str(dest), filename)

    def query(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        """Retrieve relevant chunks and generate an answer."""
        if not question.strip():
            return {"answer": "Please provide a question.", "sources": [], "chunks_used": 0}

        collection = self._get_collection()
        if collection.count() == 0:
            return {
                "answer": "The knowledge base is empty. Please upload documents first.",
                "sources": [],
                "chunks_used": 0,
            }

        embedder = self._get_embedder()
        q_embedding = embedder.embed_texts([question])[0]

        results = collection.query(
            query_embeddings=[q_embedding],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        if not docs:
            return {"answer": "No relevant documents found.", "sources": [], "chunks_used": 0}

        sources = list(dict.fromkeys(m.get("source", "") for m in metas))  # unique, ordered

        llm = self._get_llm()
        if llm:
            context = "\n\n---\n\n".join(docs)
            prompt = (
                f"You are a helpful assistant. Answer the question based solely on the provided context.\n\n"
                f"Context:\n{context}\n\n"
                f"Question: {question}\n\n"
                f"Answer concisely and cite the source documents."
            )
            try:
                response = llm.invoke(prompt)
                answer = response.content if hasattr(response, "content") else str(response)
            except Exception as e:
                logger.error("LLM generation failed: %s", e)
                answer = "LLM generation failed. Raw context:\n\n" + "\n\n".join(docs[:3])
        else:
            # No LLM: return concatenated chunks as answer
            answer = (
                "**[LLM not configured - returning retrieved context]**\n\n"
                + "\n\n---\n\n".join(docs[:3])
            )

        return {"answer": answer, "sources": sources, "chunks_used": len(docs)}

    def list_documents(self) -> List[str]:
        """List all ingested document filenames."""
        collection = self._get_collection()
        if collection.count() == 0:
            return []
        results = collection.get(include=["metadatas"])
        metas = results.get("metadatas", [])
        sources = list(dict.fromkeys(m.get("source", "") for m in metas if m))
        return sources
