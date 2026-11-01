"""ChromaDB Vector Index for Tool Retrieval."""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import chromadb
from chromadb.config import Settings
from nexus.models.tool import ToolDefinition
from nexus.retrieval.embedder import get_model_manager

logger = logging.getLogger("nexus.chroma")


class ChromaToolIndex:
    """Persistent ChromaDB vector index with multi-vector representation and incremental hashing."""

    COLLECTION_NAME = "nexus_tools"

    def __init__(self, persist_directory: str = "data/chroma_db"):
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.model_manager = get_model_manager()
        self._init_client()

    def _init_client(self):
        try:
            self.client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(anonymized_telemetry=False, is_persistent=True)
            )
            self.collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.error(f"Error initializing ChromaDB collection: {e}. Rebuilding...")
            self._rebuild_collection()

    def _rebuild_collection(self):
        try:
            self.client.delete_collection(self.COLLECTION_NAME)
        except Exception:
            pass
        self.collection = self.client.create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

    def index_tools(self, tools: List[ToolDefinition], force: bool = False):
        """Incrementally index tools using multi-vector mapping and SHA-256 hashes."""
        if not tools:
            return

        # Fetch current existing documents metadata to compare hashes
        existing_metadatas = {}
        try:
            res = self.collection.get(include=["metadatas"])
            for doc_id, meta in zip(res["ids"], res["metadatas"]):
                existing_metadatas[doc_id] = meta or {}
        except Exception as e:
            logger.warning(f"Could not read existing vector metadata: {e}")

        ids_to_add: List[str] = []
        texts_to_add: List[str] = []
        metadatas_to_add: List[Dict[str, Any]] = []

        for tool in tools:
            current_hash = tool.content_hash()
            main_doc_id = f"{tool.tool_id}__main"

            # Check if main doc is up-to-date
            if not force and main_doc_id in existing_metadatas:
                old_hash = existing_metadatas[main_doc_id].get("content_hash")
                if old_hash == current_hash:
                    # Skip unchanged tool
                    continue

            # If re-indexing changed tool, remove old vectors first
            if main_doc_id in existing_metadatas:
                self.delete_tool(tool.tool_id)

            # 1. Main Searchable Text
            searchable_text = tool.get_searchable_text()
            ids_to_add.append(main_doc_id)
            texts_to_add.append(searchable_text)
            metadatas_to_add.append({
                "tool_id": tool.tool_id,
                "service": tool.service,
                "category": tool.category,
                "type": "main",
                "content_hash": current_hash,
                "is_active": str(tool.is_active),
            })

            # 2. Example Query Vectors
            for idx, ex_query in enumerate(tool.example_queries):
                q_doc_id = f"{tool.tool_id}__q_{idx}"
                ids_to_add.append(q_doc_id)
                texts_to_add.append(ex_query)
                metadatas_to_add.append({
                    "tool_id": tool.tool_id,
                    "service": tool.service,
                    "category": tool.category,
                    "type": "example_query",
                    "content_hash": current_hash,
                    "is_active": str(tool.is_active),
                })

        if ids_to_add:
            # Batch embedding
            embeddings = self.model_manager.embed_texts(texts_to_add)
            self.collection.upsert(
                ids=ids_to_add,
                embeddings=embeddings,
                documents=texts_to_add,
                metadatas=metadatas_to_add
            )
            logger.info(f"Indexed {len(ids_to_add)} vectors into ChromaDB for {len(tools)} tools.")

    def delete_tool(self, tool_id: str):
        """Remove all vectors associated with tool_id."""
        try:
            # Query IDs with tool_id in metadata
            results = self.collection.get(
                where={"tool_id": tool_id},
                include=["metadatas"]
            )
            if results and results["ids"]:
                self.collection.delete(ids=results["ids"])
                logger.info(f"Removed {len(results['ids'])} vectors for tool_id {tool_id}")
        except Exception as e:
            logger.warning(f"Failed to delete tool {tool_id} from Chroma: {e}")

    def query(self, query_text: str, top_k: int = 15, service_filter: Optional[str] = None) -> List[Tuple[str, float]]:
        """Search vector index. Returns list of (tool_id, cosine_similarity_score)."""
        query_vector = self.model_manager.embed_query(query_text)
        
        where_filter = {"is_active": "True"}
        if service_filter:
            where_filter = {"$and": [{"is_active": "True"}, {"service": service_filter}]}

        try:
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=min(top_k * 2, max(self.collection.count(), 1)),
                where=where_filter,
                include=["metadatas", "distances"]
            )
        except Exception as e:
            logger.warning(f"Chroma query failed with filter {where_filter}: {e}")
            # Fallback without service filter if filter had no match
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=min(top_k * 2, max(self.collection.count(), 1)),
                where={"is_active": "True"},
                include=["metadatas", "distances"]
            )

        if not results or not results["ids"] or not results["ids"][0]:
            return []

        # Deduplicate to tool_id level, keeping highest similarity score
        tool_scores: Dict[str, float] = {}
        for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
            tool_id = meta.get("tool_id")
            if not tool_id:
                continue
            # Cosine distance to similarity: similarity = 1 - distance
            similarity = 1.0 - dist
            if tool_id not in tool_scores or similarity > tool_scores[tool_id]:
                tool_scores[tool_id] = similarity

        sorted_tools = sorted(tool_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_tools[:top_k]

