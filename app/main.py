"""
MailMind — FastAPI Application Entry Point.
Assembles all routers, mounts static files, wires DI container.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.dependencies import init_container
from app.api.routes import chat, ingest, ui


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: wire DI container. Shutdown: clean up (nothing needed)."""
    settings = get_settings()
    init_container(settings)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        description=(
            "Email RAG Chatbot with thread memory, "
            "inline citations, and pluggable LLM providers."
        ),
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Static files ─────────────────────────────────────────────────────────
    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(ui.router)
    app.include_router(chat.router)
    app.include_router(ingest.router)

    return app


app = create_app()
