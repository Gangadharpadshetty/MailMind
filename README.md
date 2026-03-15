# MailMind — Email RAG Chatbot

> Answers questions about email threads with grounded, cited responses.
> Built with **FastAPI + Jinja2 + Gemini + OpenRouter** using SOLID principles and design patterns.

---

## Architecture Overview

```
app/
├── core/           # Config, DI container, exceptions        [SRP]
├── domain/         # Pure models + interfaces                [ISP, DIP]
├── providers/      # LLM Strategy implementations            [OCP, Strategy]
│   ├── base.py             BaseLLMProvider (abstract)
│   ├── gemini_provider.py  Google Gemini
│   ├── openrouter_provider.py  OpenRouter (Mistral, LLaMA, Gemma, DeepSeek…)
│   └── factory.py          LLMProviderFactory               [Factory, OCP]
├── repositories/   # Storage adapters                        [Repository, DIP]
├── services/       # Business logic                          [SRP]
│   ├── ingest_service.py   Parse CSV → Chunks
│   ├── retrieval_service.py BM25 + LanceDB hybrid + RRF
│   ├── session_service.py  Conversation memory + entity notes
│   ├── rag_service.py      Pipeline orchestrator             [Chain of Responsibility]
│   └── trace_service.py    JSONL trace logger
├── api/routes/     # HTTP layer (thin)                       [SRP]
└── templates/      # Jinja2 HTML UI
```

### Design Patterns Used

| Pattern | Where |
|---------|-------|
| **Strategy** | `BaseLLMProvider` + `GeminiProvider` / `OpenRouterProvider` — swap LLM at runtime |
| **Factory** | `LLMProviderFactory` — register new providers without changing existing code |
| **Repository** | `ChunkRepository`, `InMemorySessionRepository` — decouple storage from logic |
| **Chain of Responsibility** | `RAGService.ask()` — rewrite → retrieve → generate → memory → trace |
| **Dependency Injection** | FastAPI `Depends()` + `app/core/dependencies.py` container |
| **Observer** | `TraceService` — logs every turn passively |

### SOLID Principles

| Principle | Applied where |
|-----------|--------------|
| **S**ingle Responsibility | Each service/class does exactly one thing |
| **O**pen/Closed | Add new LLM providers by registering in factory, never editing existing code |
| **L**iskov Substitution | All providers implement `BaseLLMProvider`; fully interchangeable |
| **I**nterface Segregation | `IRetriever`, `IGenerator`, `ISessionRepository`, `ITracer` — small, focused |
| **D**ependency Inversion | Services depend on interfaces, not concretions; injected at startup |

---

## Setup

### 1. Prerequisites
- Python 3.11+
- [Gemini API key](https://aistudio.google.com) (free) and/or [OpenRouter key](https://openrouter.ai) (free)
- Enron CSV from [Kaggle](https://www.kaggle.com/datasets/wcukierski/enron-email-dataset)

### 2. Install
```bash
git clone <repo>
cd mailmind
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure
```bash
cp .env.example .env
# Edit .env — add GEMINI_API_KEY and/or OPENROUTER_API_KEY
```

### 4. Ingest
```bash
# Download Enron CSV from Kaggle first, then:
python ingest.py --csv data/emails.csv

# Optional: also build vector index (slower but better recall)
python ingest.py --csv data/emails.csv --vectors
```

### 5. Run
```bash
uvicorn app.main:app --reload --port 8000
# Open http://localhost:8000
```

### Docker
```bash
cp .env.example .env   # fill in keys
docker compose up --build

# Run ingest first:
docker compose --profile ingest up ingest
docker compose up
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Chat UI |
| `GET` | `/stats` | Latency stats + trace info |
| `GET` | `/api/threads` | List all indexed threads |
| `POST` | `/api/start_session` | `{"thread_id": "T-0001"}` |
| `POST` | `/api/ask` | `{"session_id": "...", "text": "..."}` |
| `POST` | `/api/switch_thread` | Change thread mid-session |
| `POST` | `/api/reset_session` | Clear session memory |
| `GET` | `/api/providers` | List registered LLM providers |
| `POST` | `/api/providers/{id}/select` | Hot-swap LLM provider |
| `POST` | `/api/ingest` | Trigger ingest from running server |
| `GET` | `/api/ingest/status` | Check index status |
| `GET` | `/docs` | Interactive OpenAPI docs |

### Adding a New LLM Provider (OCP Demo)

```python
# 1. Create app/providers/my_provider.py
class MyProvider(BaseLLMProvider):
    def _call_llm(self, prompt: str) -> tuple[str, int]:
        # ... call your API
        return response_text, token_count

    @property
    def provider_info(self) -> LLMProviderInfo:
        return LLMProviderInfo(id="myprovider", name="My Provider", ...)

# 2. Register in factory.py _register_defaults()
self.register("myprovider", lambda: MyProvider(api_key=cfg.my_key))
# That's it — no other code changes needed.
```

---

## Retrieval Approach

1. **BM25** (`rank_bm25`) — keyword search, always available, fast
2. **Dense vectors** (`all-MiniLM-L6-v2` via `sentence-transformers` + `lancedb`) — semantic search
3. **RRF** (Reciprocal Rank Fusion, k=60) — merges both ranked lists
4. All results **scoped to active thread** by default (privacy)
5. `?search_outside_thread=true` enables global search

---

## Sample Questions (Thread T-0001)

1. "Who are the people involved in this thread?"
2. "What is the main topic being discussed?"
3. "When was the approval sent?" *(pronoun test)*
4. "What did they conclude?" *(ellipsis test)*
5. "Compare the draft in the earlier attachment with the final version"
6. "How much money was approved?"
7. "What attachments were referenced?"
8. "Summarise the timeline of this thread"
9. "Who sent the first message?" *(correction test)*
10. "What was still unresolved at the end?"

---

## Performance Targets

| Retrieval Mode | p95 Latency Target |
|----------------|--------------------|
| BM25 only | ≤ 2.5s @ top-k=8 (warm) |
| BM25 + vectors | ≤ 3.0s @ top-k=8 (warm) |

Check live stats at `/stats`.

---

## Trace Logs

Every turn is written to `runs/<timestamp>/trace.jsonl`:

```json
{
  "trace_id": "tr_abc123",
  "user_text": "What did they approve?",
  "rewrite": "What did finance approve in the storage vendor contract thread?",
  "retrieved": [{"doc_id": "m_9b2_body", "score": 0.032, "snippet": "..."}],
  "answer": "Finance approved $48,000 [msg: m_9b2]",
  "citations": [{"type": "email", "message_id": "m_9b2"}],
  "latency": {"total_s": 1.23, "rewrite_s": 0.4, "retrieve_s": 0.1, "generate_s": 0.73},
  "token_count": 312,
  "provider": "gemini/gemini-2.0-flash"
}
```
