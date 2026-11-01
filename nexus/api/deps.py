"""Application-wide service singletons initialized at startup."""
import logging, threading
from typing import Optional

logger = logging.getLogger("nexus.deps")
_lock = threading.Lock()
_singletons: dict = {}


def init_app_services():
    """Initialize all services once at startup. Call from FastAPI lifespan."""
    with _lock:
        if _singletons.get("initialized"):
            return

        logger.info("Initializing NEXUS services...")

        from nexus.registry.repository import JsonToolRepository
        from nexus.executor.logs import ExecutionLogRepository
        from nexus.retrieval.embedder import ModelManager
        from nexus.retrieval.chroma_index import ChromaToolIndex
        from nexus.retrieval.hybrid import HybridRetriever
        from nexus.executor.executor import GenericExecutor
        from nexus.rag.pipeline import RAGPipeline
        from nexus.rag.system_search import SystemSearch
        from nexus.orchestration.graph import NexusOrchestrator
        from nexus.storage.redis_client import RedisManager
        from nexus.storage.memory import EntityMemoryStore
        from nexus.orchestration.checkpointer import RedisCheckpointSaver

        redis_mgr = RedisManager.get_instance()
        checkpointer = RedisCheckpointSaver(redis_mgr=redis_mgr)
        memory_store = EntityMemoryStore.get_instance(redis_mgr=redis_mgr)

        repo = JsonToolRepository("data/registry/tools.json")
        log_repo = ExecutionLogRepository("data/logs/execution_logs.json")

        # Warm up the model singleton (loads once, subsequent calls return same instance)
        ModelManager()

        # HybridRetriever builds its own BM25, ModelManager, and Chroma internals.
        # Pass only the already-built ChromaIndex so we control persist_dir.
        chroma_index = ChromaToolIndex(persist_directory="data/chroma_db")

        retriever = HybridRetriever(
            repository=repo,
            chroma_index=chroma_index,
            redis_mgr=redis_mgr,
        )

        executor = GenericExecutor(
            repository=repo,
            log_repo=log_repo,
            redis_mgr=redis_mgr,
            memory_store=memory_store,
        )
        rag = RAGPipeline(chroma_persist_dir="data/chroma_db")
        system_search = SystemSearch(repository=repo, log_repo=log_repo)

        orchestrator = NexusOrchestrator(
            repository=repo,
            retriever=retriever,
            executor=executor,
            rag_pipeline=rag,
            system_search=system_search,
            checkpointer=checkpointer,
            redis_mgr=redis_mgr,
            memory_store=memory_store,
        )

        _singletons.update({
            "initialized": True,
            "repository": repo,
            "log_repo": log_repo,
            "retriever": retriever,
            "executor": executor,
            "rag": rag,
            "system_search": system_search,
            "orchestrator": orchestrator,
            "redis": redis_mgr,
            "memory": memory_store,
        })
        logger.info("NEXUS services initialized. %d tools in registry.", repo.count())


def get_repository():
    return _singletons["repository"]

def get_log_repo():
    return _singletons["log_repo"]

def get_retriever():
    return _singletons["retriever"]

def get_executor():
    return _singletons["executor"]

def get_rag_pipeline():
    return _singletons["rag"]

def get_system_search():
    return _singletons["system_search"]

def get_orchestrator():
    return _singletons["orchestrator"]

def get_redis_manager():
    return _singletons.get("redis")

def get_memory_store():
    return _singletons.get("memory")
