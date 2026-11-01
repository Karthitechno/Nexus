"""Embedding and Cross-Encoder Model Singleton."""
import threading
import logging
from typing import List, Tuple
from sentence_transformers import SentenceTransformer, CrossEncoder

logger = logging.getLogger("nexus.embedder")

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CROSS_ENCODER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class ModelManager:
    """Manages neural models loaded once at startup."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ModelManager, cls).__new__(cls)
                cls._instance._init_models()
            return cls._instance

    def _init_models(self):
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME} (CPU)...")
        # Force CPU device to ensure stability and compatibility across all hardware
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")
        logger.info(f"Loading cross-encoder model: {CROSS_ENCODER_MODEL_NAME} (CPU)...")
        self.cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL_NAME, device="cpu")
        logger.info("Models loaded successfully.")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Compute 384-dimensional dense embeddings for a list of texts."""
        if not texts:
            return []
        embeddings = self.embedding_model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_query(self, query: str) -> List[float]:
        """Compute embedding for a single search query."""
        emb = self.embedding_model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
        return emb[0].tolist()

    def rerank(self, query: str, candidate_texts: List[str]) -> List[float]:
        """Compute cross-encoder relevance scores for (query, candidate) pairs."""
        if not candidate_texts:
            return []
        pairs = [(query, text) for text in candidate_texts]
        scores = self.cross_encoder.predict(pairs)
        return [float(s) for s in scores]


def get_model_manager() -> ModelManager:
    """Get the singleton ModelManager instance."""
    return ModelManager()

