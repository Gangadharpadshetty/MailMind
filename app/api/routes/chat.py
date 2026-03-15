"""
Chat API Routes — thin HTTP layer, no business logic (SRP).
All logic is in RAGService (DIP via Depends).
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_rag_service, get_provider_factory
from app.core.exceptions import (
    SessionNotFoundError,
    ThreadNotFoundError,
    ProviderNotFoundError,
)
from app.domain.models import (
    AskRequest, AskResponse,
    StartSessionRequest, StartSessionResponse,
    SwitchThreadRequest, ResetSessionRequest,
    ThreadListResponse, ThreadInfo,
    ProviderListResponse,
)
from app.services.rag_service import RAGService
from app.providers.factory import LLMProviderFactory

router = APIRouter(prefix="/api", tags=["chat"])


def _handle_domain_errors(exc: Exception):
    if isinstance(exc, SessionNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ThreadNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ProviderNotFoundError):
        raise HTTPException(status_code=400, detail=str(exc))
    # No provider configured (e.g. missing API keys) — surface as 503 so the
    # UI can display a friendly configuration message instead of a crash.
    if isinstance(exc, RuntimeError) and "No LLM provider available" in str(exc):
        raise HTTPException(status_code=503, detail=str(exc))
    raise HTTPException(status_code=500, detail=str(exc))


@router.get("/threads", response_model=ThreadListResponse)
def list_threads(rag: RAGService = Depends(get_rag_service)):
    """List all indexed email threads."""
    threads = rag._chunks.list_threads()
    return ThreadListResponse(
        threads=[
            ThreadInfo(
                thread_id=tid,
                subject=data["subject"],
                message_count=data["message_count"],
            )
            for tid, data in threads.items()
        ]
    )


@router.post("/start_session", response_model=StartSessionResponse)
def start_session(
    req: StartSessionRequest,
    rag: RAGService = Depends(get_rag_service),
):
    try:
        return rag.start_session(req.thread_id)
    except Exception as e:
        _handle_domain_errors(e)


@router.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    rag: RAGService = Depends(get_rag_service),
):
    try:
        return rag.ask(req)
    except Exception as e:
        _handle_domain_errors(e)


@router.post("/switch_thread", response_model=StartSessionResponse)
def switch_thread(
    req: SwitchThreadRequest,
    rag: RAGService = Depends(get_rag_service),
):
    try:
        return rag.switch_thread(req)
    except Exception as e:
        _handle_domain_errors(e)


@router.post("/reset_session")
def reset_session(
    req: ResetSessionRequest,
    rag: RAGService = Depends(get_rag_service),
):
    try:
        return rag.reset_session(req.session_id)
    except Exception as e:
        _handle_domain_errors(e)


@router.get("/providers", response_model=ProviderListResponse)
def list_providers(
    rag: RAGService = Depends(get_rag_service),
    factory: LLMProviderFactory = Depends(get_provider_factory),
):
    """Return all registered LLM providers for the UI selector."""
    return ProviderListResponse(
        providers=factory.list_available(),
        current=rag.current_provider_id(),
    )


@router.post("/providers/{provider_id}/select")
def select_provider(
    provider_id: str,
    rag: RAGService = Depends(get_rag_service),
):
    """Hot-swap the active LLM provider (Open/Closed: no restart needed)."""
    try:
        rag.set_provider(provider_id)
        return {"status": "ok", "provider": provider_id}
    except Exception as e:
        _handle_domain_errors(e)
