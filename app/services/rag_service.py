"""
RAG Service — Chain of Responsibility orchestrator (SRP: pipeline coordination).
  Step 1 → Rewrite query using session memory
  Step 2 → Retrieve relevant chunks
  Step 3 → Generate grounded answer with citations
  Step 4 → Update session memory
  Step 5 → Log trace

All heavy lifting is delegated to injected collaborators (DIP).
"""
from __future__ import annotations

import time

from app.core.exceptions import SessionNotFoundError, ThreadNotFoundError
from app.domain.interfaces import IGenerator
from app.domain.models import (
    AskRequest, AskResponse, CitationSchema, RetrievedItem,
    StartSessionResponse, SwitchThreadRequest,
)
from app.providers.factory import LLMProviderFactory
from app.repositories.chunk_repository import ChunkRepository
from app.services.retrieval_service import RetrievalService
from app.services.session_service import SessionService
from app.services.trace_service import TraceService


class RAGService:
    """
    Orchestrates the full question-answering pipeline.
    Holds no business logic of its own — only coordinates collaborators.
    """

    def __init__(
        self,
        chunk_repo: ChunkRepository,
        retrieval_svc: RetrievalService,
        session_svc: SessionService,
        trace_svc: TraceService,
        provider_factory: LLMProviderFactory,
    ) -> None:
        self._chunks = chunk_repo
        self._retrieval = retrieval_svc
        self._session = session_svc
        self._trace = trace_svc
        self._factory = provider_factory
        # Active provider — can be swapped at runtime (Strategy).
        # If no providers are configured (no API keys), delay provider
        # creation until the first ask() call and surface a clear error.
        self._provider_id: str | None = provider_factory.default_provider_id() or None
        self._provider: IGenerator | None = (
            provider_factory.create(self._provider_id)
            if self._provider_id
            else None
        )

    # ── Provider hot-swap ────────────────────────────────────────────────────

    def set_provider(self, provider_id: str) -> None:
        """Switch LLM provider without restarting (OCP: adding providers never changes this)."""
        self._provider = self._factory.create(provider_id)
        self._provider_id = provider_id

    def current_provider_id(self) -> str | None:
        return self._provider_id

    # ── Session management ────────────────────────────────────────────────────

    def start_session(self, thread_id: str) -> StartSessionResponse:
        threads = self._chunks.list_threads()
        if thread_id not in threads:
            raise ThreadNotFoundError(thread_id)
        session = self._session.create_session(thread_id)
        return StartSessionResponse(
            session_id=session.session_id,
            thread_id=thread_id,
            thread_subject=threads[thread_id]["subject"],
        )

    def switch_thread(self, req: SwitchThreadRequest) -> StartSessionResponse:
        threads = self._chunks.list_threads()
        if req.thread_id not in threads:
            raise ThreadNotFoundError(req.thread_id)
        session = self._session.get_session(req.session_id)
        self._session.switch_thread(session, req.thread_id)
        return StartSessionResponse(
            session_id=session.session_id,
            thread_id=req.thread_id,
            thread_subject=threads[req.thread_id]["subject"],
        )

    def reset_session(self, session_id: str) -> dict:
        self._session.reset_session(session_id)
        return {"status": "reset", "session_id": session_id}

    # ── Main ask pipeline ─────────────────────────────────────────────────────

    def ask(self, req: AskRequest) -> AskResponse:
        if self._provider is None or self._provider_id is None:
            # Fail fast with a clear message that the UI / API can surface.
            raise RuntimeError(
                "No LLM provider available. "
                "Set GROQ_API_KEY in .env and restart the server."
            )
        session = self._session.get_session(req.session_id)
        if req.search_outside_thread:
            session.search_outside_thread = True

        threads = self._chunks.list_threads()
        thread_subject = threads.get(session.thread_id, {}).get("subject", "")

        t0 = time.perf_counter()

        # Step 1 — Rewrite
        t1 = time.perf_counter()
        rewrite = self._provider.rewrite_query(req.text, session)
        t_rewrite = round(time.perf_counter() - t1, 3)

        # Step 2 — Retrieve
        t2 = time.perf_counter()
        thread_filter = None if session.search_outside_thread else session.thread_id
        chunks = self._retrieval.retrieve(
            rewrite, thread_id=thread_filter, top_k=self._chunks.count() and 6 or 6
        )
        t_retrieve = round(time.perf_counter() - t2, 3)

        # Step 3 — Generate
        t3 = time.perf_counter()
        answer, citations, token_count = self._provider.generate_answer(
            rewrite, chunks, session, thread_subject
        )
        t_generate = round(time.perf_counter() - t3, 3)

        t_total = round(time.perf_counter() - t0, 3)

        # Step 4 — Update memory
        self._session.update_memory(session, req.text, answer)

        # Step 5 — Log trace
        trace_id = self._trace.log(
            session_id=req.session_id,
            thread_id=session.thread_id,
            user_text=req.text,
            rewrite=rewrite,
            retrieved=chunks,
            answer=answer,
            citations=citations,
            latency_total=t_total,
            latency_rewrite=t_rewrite,
            latency_retrieve=t_retrieve,
            latency_generate=t_generate,
            token_count=token_count,
            provider=self._provider_id,
        )

        return AskResponse(
            answer=answer,
            citations=[
                CitationSchema(type=c.type, message_id=c.message_id, page=c.page)
                for c in citations
            ],
            rewrite=rewrite,
            retrieved=[
                RetrievedItem(doc_id=c.doc_id, score=c.score) for c in chunks
            ],
            trace_id=trace_id,
            latency=(
                f"{t_total}s "
                f"(rewrite:{t_rewrite}s "
                f"retrieve:{t_retrieve}s "
                f"generate:{t_generate}s)"
            ),
            tokens=token_count,
            provider=self._provider_id,
        )
