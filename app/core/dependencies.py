"""
Dependency Injection Container — wires all components together.
FastAPI calls get_rag_service() per-request via Depends().
All collaborators are singletons (created once at startup).
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.providers.factory import LLMProviderFactory
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.session_repository import InMemorySessionRepository
from app.services.ingest_service import IngestService
from app.services.rag_service import RAGService
from app.services.retrieval_service import RetrievalService
from app.services.session_service import SessionService
from app.services.trace_service import TraceService


# ── Singleton instances ───────────────────────────────────────────────────────

_chunk_repo: ChunkRepository | None = None
_retrieval_svc: RetrievalService | None = None
_session_svc: SessionService | None = None
_trace_svc: TraceService | None = None
_provider_factory: LLMProviderFactory | None = None
_rag_svc: RAGService | None = None


def init_container(settings: Settings) -> None:
    """Call once at FastAPI startup to build the DI graph."""
    global _chunk_repo, _retrieval_svc, _session_svc
    global _trace_svc, _provider_factory, _rag_svc

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.runs_dir.mkdir(parents=True, exist_ok=True)

    _chunk_repo = ChunkRepository(
        data_dir=settings.data_dir,
        lancedb_dir=settings.lancedb_dir,
    )

    # Load previously indexed data if it exists
    loaded = _chunk_repo.load()
    if loaded:
        print(f"[startup] Loaded {_chunk_repo.count()} chunks from disk.")

    _retrieval_svc = RetrievalService(_chunk_repo, settings)
    if loaded:
        _retrieval_svc.build_index(embed=False)   # BM25 only for fast start
        _retrieval_svc.load_vector_index()         # attach existing LanceDB

    _session_svc   = SessionService(InMemorySessionRepository())
    _trace_svc     = TraceService(settings.runs_dir)
    _provider_factory = LLMProviderFactory(settings)

    _rag_svc = RAGService(
        chunk_repo=_chunk_repo,
        retrieval_svc=_retrieval_svc,
        session_svc=_session_svc,
        trace_svc=_trace_svc,
        provider_factory=_provider_factory,
    )


# ── FastAPI dependency providers ──────────────────────────────────────────────

def get_rag_service() -> RAGService:
    if _rag_svc is None:
        raise RuntimeError("Container not initialised. Call init_container() at startup.")
    return _rag_svc


def get_chunk_repo() -> ChunkRepository:
    if _chunk_repo is None:
        raise RuntimeError("Container not initialised.")
    return _chunk_repo


def get_retrieval_service() -> RetrievalService:
    if _retrieval_svc is None:
        raise RuntimeError("Container not initialised.")
    return _retrieval_svc


def get_ingest_service(
    settings: Settings = None,
) -> IngestService:
    s = settings or get_settings()
    repo = get_chunk_repo()
    return IngestService(chunk_repo=repo, settings=s)


def get_provider_factory() -> LLMProviderFactory:
    if _provider_factory is None:
        raise RuntimeError("Container not initialised.")
    return _provider_factory


def get_trace_service() -> TraceService:
    if _trace_svc is None:
        raise RuntimeError("Container not initialised.")
    return _trace_svc
