

## Project Overview

MailMind is a FastAPI-based email RAG chatbot. It ingests the Enron email dataset into a hybrid BM25 + LanceDB vector index, then answers questions about email threads with inline citations, powered by Groq.

## Commands

### Setup
```bash
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

### Configure
Create `.env` in the project root. Required keys:
```
GROQ_API_KEY=...
DEFAULT_PROVIDER=groq
GROQ_MODEL=llama-3.3-70b-versatile
```
Get a free Groq key at https://console.groq.com → API Keys.

### Ingest (must be run before starting the server)
```bash
# BM25 index only (fast)
python ingest.py --csv Data/emails.csv

# BM25 + LanceDB vector index (slower, better recall)
python ingest.py --csv Data/emails.csv --vectors
```
Ingest output lands in `data/chunks.json`, `data/threads.json`, and `data/lancedb/`.

### Run
```bash
uvicorn app.main:app --reload --port 8000
# Open http://localhost:8000
# OpenAPI docs at http://localhost:8000/docs
```

### Docker
```bash
cp .env.example .env   # fill in keys
docker compose --profile ingest up ingest   # one-shot ingest
docker compose up                           # start API
```

## Architecture

### Request Flow
`POST /api/ask` → `chat.py` router → `RAGService.ask()` — a 5-step Chain of Responsibility:
1. **Rewrite** — LLM rewrites user query using session memory (resolves pronouns/ellipsis)
2. **Retrieve** — `RetrievalService.retrieve()`: BM25 + optional LanceDB vector search, fused with RRF (k=60)
3. **Generate** — LLM produces a grounded answer with inline `[msg: <id>]` citations
4. **Memory** — `SessionService.update_memory()` appends turn (rolling 4-turn window) and extracts entities
5. **Trace** — `TraceService` writes a JSONL record to `runs/<timestamp>/trace.jsonl`

### Dependency Injection
All singletons are created once in `app/core/dependencies.py::init_container()` at FastAPI startup. Routes receive services via `Depends(get_rag_service)` etc. There is no DI framework — it is a hand-wired module-level global container.

### LLM Provider System (Strategy + Factory)
- `app/providers/base.py` — `BaseLLMProvider(IGenerator, ABC)`. Contains all shared prompt-building logic (`build_answer_prompt`, `build_rewrite_prompt`, `extract_citations`, `sanitize_chunk`). Subclasses implement only `_call_llm(prompt) -> (str, int)`.
- `app/providers/groq_provider.py` — `GroqProvider` using the official `groq` Python SDK. Model is configurable via `GROQ_MODEL` (default: `llama-3.3-70b-versatile`).
- `app/providers/factory.py` — `LLMProviderFactory` maps string IDs to zero-arg lambdas. Register new providers in `_register_defaults()`; no other code changes needed (OCP).
- Active provider is held on `RAGService._provider` and can be hot-swapped at runtime via `POST /api/providers/{id}/select`.

### Domain Layer
- `app/domain/models.py` — all data classes (`Chunk`, `Session`, `Citation`) and Pydantic API schemas
- `app/domain/interfaces.py` — small abstract base classes (`IRetriever`, `IGenerator`, `ISessionRepository`, `IChunkRepository`, `ITracer`, `IIngestService`). Services depend only on these abstractions.

### Storage
- `ChunkRepository` (`app/repositories/chunk_repository.py`): in-memory list for BM25 + JSON files for persistence. LanceDB table managed by `RetrievalService`.
- `InMemorySessionRepository` (`app/repositories/session_repository.py`): dict-backed, no persistence (sessions are lost on restart).
- Chunk metadata persists to `data/chunks.json` / `data/threads.json`; LanceDB embeddings live in `data/lancedb/`.

### Configuration
`app/core/config.py::Settings` (pydantic-settings). Loaded once via `@lru_cache get_settings()`. Key settings: `groq_api_key`, `groq_model` (default `llama-3.3-70b-versatile`), `default_provider` (`groq`), `embed_model` (`all-MiniLM-L6-v2`), `top_k` (6), `rrf_k` (60), `data_dir`, `lancedb_dir`, `enron_csv` (defaults to `Data/emails.csv`).

## Adding a New LLM Provider

```python
# 1. app/providers/my_provider.py
class MyProvider(BaseLLMProvider):
    def _call_llm(self, prompt: str) -> tuple[str, int]:
        ...  # call API, return (response_text, token_count)

    @property
    def provider_info(self) -> LLMProviderInfo:
        return LLMProviderInfo(id="myprovider", name="My Provider", description="...", is_free=False)

# 2. Add the key to config.py Settings, then in factory.py _register_defaults():
self.register("myprovider", lambda: MyProvider(api_key=cfg.my_key))
```

## Key Paths

| Path | Purpose |
|------|---------|
| `app/main.py` | FastAPI app factory, lifespan wiring |
| `app/core/dependencies.py` | DI container (`init_container`) |w
| `app/services/rag_service.py` | Main ask pipeline |
| `app/services/retrieval_service.py` | BM25 + LanceDB + RRF |
| `app/providers/base.py` | Shared prompt logic + citation parsing |
| `ingest.py` | Standalone ingest CLI |
| `data/` | Persisted chunks and LanceDB index |
| `runs/` | Per-run JSONL trace logs |
