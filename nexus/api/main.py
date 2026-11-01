"""NEXUS FastAPI Application Entry Point."""
import os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nexus.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize all services. Shutdown: nothing special needed."""
    logger.info("NEXUS startup: loading services...")
    from nexus.api.deps import init_app_services
    init_app_services()
    logger.info("NEXUS ready.")
    yield
    logger.info("NEXUS shutting down.")


app = FastAPI(
    title="NEXUS - Agentic Tool Orchestration Platform",
    description="Scalable agentic API orchestration with pre-retrieval tool selection.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from nexus.api.routers import health, registry, search, chat, rag, system, paypal, benchmark

app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(registry.router, prefix="/api", tags=["Registry"])
app.include_router(search.router, prefix="/api", tags=["Search"])
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(rag.router, prefix="/api", tags=["RAG"])
app.include_router(system.router, prefix="/api", tags=["System"])
app.include_router(paypal.router, prefix="/api", tags=["PayPal"])
app.include_router(benchmark.router, prefix="/api", tags=["Benchmark"])


@app.get("/")
def root():
    return {
        "name": "NEXUS",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
