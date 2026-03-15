"""
UI Routes — serve Jinja2 HTML templates.
Thin layer: fetches data, passes to templates (SRP).
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.dependencies import get_rag_service, get_provider_factory, get_trace_service
from app.services.rag_service import RAGService
from app.providers.factory import LLMProviderFactory
from app.services.trace_service import TraceService

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    rag: RAGService = Depends(get_rag_service),
    factory: LLMProviderFactory = Depends(get_provider_factory),
):
    threads = rag._chunks.list_threads()
    providers = factory.list_available()
    current_provider = rag.current_provider_id()
    provider_label = "Not configured"
    if providers:
        # In the Gemini-only build there will be at most one provider, but this
        # also works if more are added later.
        provider_label = providers[0].name
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "threads": threads,
            "providers": providers,
            "current_provider": current_provider,
            "provider_label": provider_label,
            "total_threads": len(threads),
            "total_chunks": rag._chunks.count(),
        },
    )


@router.get("/stats", response_class=HTMLResponse)
def stats_page(
    request: Request,
    trace: TraceService = Depends(get_trace_service),
    rag: RAGService = Depends(get_rag_service),
):
    stats = trace.get_stats()
    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "stats": stats,
            "total_chunks": rag._chunks.count(),
            "total_threads": len(rag._chunks.list_threads()),
        },
    )
