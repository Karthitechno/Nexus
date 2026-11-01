# NEXUS - Agentic Tool Orchestration Platform

NEXUS solves LLM tool-selection degradation at scale (50–5,000+ APIs) by using pre-retrieval routing: the LLM **never** sees the full tool catalog.

## Architecture

```
User Query → Intent Router → [RAG | System Search | Hybrid Retrieval]
                                              ↓
                               BM25 + ChromaDB → RRF → Cross-Encoder
                                              ↓
                               Slot Filling → Plan → Approval Gate
                                              ↓
                               Generic Executor → PayPal API
```

## Quick Start

### Prerequisites
- Python 3.11+ (Conda env `spidy`)
- Node.js 18+ with pnpm
- (Optional) Google API key for Gemini LLM
- (Optional) PayPal sandbox credentials

### 1. Configure Environment
```bash
cp .env.example .env
# Edit .env with your API keys
```

### 2. Seed Tool Registry
```bash
conda run -n spidy python -m nexus.registry.seed
# Imports 28 verified PayPal API tools
```

### 3. Start Backend
```bash
conda run -n spidy uvicorn nexus.api.main:app --host 0.0.0.0 --port 8000 --reload
# Or: python -m uvicorn nexus.api.main:app --port 8000
```
API docs available at http://localhost:8000/docs

### 4. Start Frontend
```bash
cd frontend
pnpm install
pnpm dev
# Frontend at http://localhost:5173
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Service health and tool count |
| `/api/tools` | GET | List all tools (filterable) |
| `/api/tools/stats` | GET | Registry statistics |
| `/api/tools/{id}` | GET | Get single tool definition |
| `/api/tools/import` | POST | Import Postman JSON collection |
| `/api/tools/register` | POST | Register a single tool |
| `/api/tools/{id}` | DELETE | Remove tool from registry |
| `/api/tools/{id}/enable` | POST | Enable a tool |
| `/api/tools/{id}/disable` | POST | Disable a tool |
| `/api/tools/search` | POST | Hybrid semantic search |
| `/api/chat` | POST | Send query through NEXUS agent |
| `/api/chat/approve` | POST | Approve/reject a pending write operation |
| `/api/rag/upload` | POST | Upload PDF/TXT/MD to knowledge base |
| `/api/rag/query` | POST | Query knowledge base |
| `/api/rag/documents` | GET | List ingested documents |
| `/api/system/search` | POST | Search registry and logs |
| `/api/system/logs` | GET | Recent execution logs |
| `/api/system/logs/{id}` | GET | Lookup log by request_id |
| `/api/paypal/status` | GET | PayPal credential status |
| `/api/benchmark/run` | POST | Run A vs B benchmark |
| `/api/benchmark/results` | GET | Get benchmark results |

## Importing a Postman Collection

```bash
curl -X POST http://localhost:8000/api/tools/import \
  -F "file=@your_collection.json"
```

Or use the Tool Registry page in the frontend.

## Running Tests

```bash
conda run -n spidy python -m pytest tests/ -v
```

## What Works / What Is Unverified

### ✅ Verified (code complete, tests written)
- Tool registry: CRUD, import Postman collections, enable/disable, search
- Hybrid retrieval: BM25 + ChromaDB + RRF + Cross-Encoder rerank
- Slot filling with deterministic resolvers (dates, amounts, emails)
- Multi-step planning with dependency resolution
- LangGraph orchestration with human-in-the-loop approval
- RAG pipeline: TXT/MD ingestion, chunking, embedding, retrieval
- System search over registry and execution logs
- All FastAPI endpoints

### ⚠️ Unverified (requires credentials)
- PayPal live/sandbox API calls (credentials not configured)
- Gemini LLM enrichment, conditional rerank, slot filling (no GOOGLE_API_KEY)
- LangSmith tracing (no LANGSMITH_API_KEY)

### 🚫 Not Implemented
- Real-time streaming chat responses
- Multi-user authentication / API keys
- Postgres migration (JSON file repository sufficient for development)
- GPU acceleration (RTX 5050 sm_120 incompatible with installed PyTorch CUDA)

## Security Notes
- All secrets in backend `.env` only — never sent to frontend or LLM context
- LLM never receives raw API URLs, only tool names and schemas
- Only registered, allowlisted tools can be executed
- Write operations (POST/PUT/DELETE) require explicit human approval
- Input validation via Pydantic on all endpoints
