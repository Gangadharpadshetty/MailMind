"""
Domain Models — pure data classes, no business logic.
All services speak in terms of these models (SRP).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    EMAIL = "email"
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    HTML = "html"


# ── Core domain objects ──────────────────────────────────────────────────────

@dataclass
class Chunk:
    """One searchable unit: email body or attachment page."""
    doc_id: str
    message_id: str
    thread_id: str
    text: str
    source_type: SourceType = SourceType.EMAIL
    page_no: Optional[int] = None
    filename: Optional[str] = None
    subject: str = ""
    from_addr: str = ""
    to_addr: str = ""
    date: str = ""
    thread_subject: str = ""
    score: float = 0.0
    bm25_score: float = 0.0
    embedding: Optional[list[float]] = None


@dataclass
class Session:
    """Conversation state locked to one email thread."""
    session_id: str
    thread_id: str
    turns: list[dict[str, str]] = field(default_factory=list)   # last 4 turns
    entities: dict[str, Any] = field(default_factory=dict)       # people/dates/amounts/files
    last_answer: str = ""
    search_outside_thread: bool = False


@dataclass
class Citation:
    type: str           # "email" | "pdf"
    message_id: str
    page: Optional[int] = None


# ── API request / response models ────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    thread_id: str = Field(..., example="T-0001")


class StartSessionResponse(BaseModel):
    session_id: str
    thread_id: str
    thread_subject: str


class AskRequest(BaseModel):
    session_id: str
    text: str = Field(..., min_length=1, max_length=2000)
    search_outside_thread: bool = False


class CitationSchema(BaseModel):
    type: str
    message_id: str
    page: Optional[int] = None


class RetrievedItem(BaseModel):
    doc_id: str
    score: float


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationSchema]
    rewrite: str
    retrieved: list[RetrievedItem]
    trace_id: str
    latency: str
    tokens: int
    provider: str


class SwitchThreadRequest(BaseModel):
    session_id: str
    thread_id: str


class ResetSessionRequest(BaseModel):
    session_id: str


class ThreadInfo(BaseModel):
    thread_id: str
    subject: str
    message_count: int


class ThreadListResponse(BaseModel):
    threads: list[ThreadInfo]


# ── Provider info (for UI selector) ─────────────────────────────────────────

class LLMProviderInfo(BaseModel):
    id: str            # e.g. "gemini", "openrouter/mistral-7b"
    name: str          # Display name
    description: str
    is_free: bool = True


class ProviderListResponse(BaseModel):
    providers: list[LLMProviderInfo]
    current: str


# ── Ingest ───────────────────────────────────────────────────────────────────

class IngestStats(BaseModel):
    threads: int
    messages: int
    attachments: int = 0
    total_chars: int = 0
    duration_s: float = 0.0
