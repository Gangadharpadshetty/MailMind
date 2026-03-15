"""
Domain Interfaces — Interface Segregation & Dependency Inversion Principles.

Each interface is small and focused (ISP).
All services depend on these abstractions, not concretions (DIP).
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
from .models import (
    Chunk, Session, AskResponse, Citation,
    LLMProviderInfo, IngestStats,
)


# ── I: Retrieval ────────────────────────────────────────────────────────────

class IRetriever(ABC):
    """Retrieve relevant chunks from the index."""

    @abstractmethod
    def retrieve(
        self,
        query: str,
        thread_id: Optional[str],
        top_k: int = 6,
    ) -> list[Chunk]:
        ...


class IEmbedder(ABC):
    """Produce dense embeddings for text."""

    @abstractmethod
    def encode(self, texts: list[str]) -> list[list[float]]:
        ...


# ── I: Generation ───────────────────────────────────────────────────────────

class IGenerator(ABC):
    """Generate answers and rewrites with an LLM."""

    @abstractmethod
    def generate_answer(
        self,
        query: str,
        chunks: list[Chunk],
        session: Session,
        thread_subject: str,
    ) -> tuple[str, list[Citation], int]:
        """Returns (answer_text, citations, token_count)."""
        ...

    @abstractmethod
    def rewrite_query(self, user_text: str, session: Session) -> str:
        ...

    @property
    @abstractmethod
    def provider_info(self) -> LLMProviderInfo:
        ...


# ── I: Session / Memory ─────────────────────────────────────────────────────

class ISessionRepository(ABC):
    """CRUD for conversation sessions."""

    @abstractmethod
    def create(self, thread_id: str) -> Session:
        ...

    @abstractmethod
    def get(self, session_id: str) -> Optional[Session]:
        ...

    @abstractmethod
    def update(self, session: Session) -> None:
        ...

    @abstractmethod
    def delete(self, session_id: str) -> None:
        ...


# ── I: Chunk Storage ────────────────────────────────────────────────────────

class IChunkRepository(ABC):
    """Store and retrieve document chunks."""

    @abstractmethod
    def save_many(self, chunks: list[Chunk]) -> None:
        ...

    @abstractmethod
    def get_by_thread(self, thread_id: str) -> list[Chunk]:
        ...

    @abstractmethod
    def list_threads(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...


# ── I: Tracing ──────────────────────────────────────────────────────────────

class ITracer(ABC):
    """Write one structured record per turn."""

    @abstractmethod
    def log(self, record: dict) -> str:
        """Write record, return trace_id."""
        ...


# ── I: Ingest ───────────────────────────────────────────────────────────────

class IIngestService(ABC):
    """Parse raw email data and populate the chunk repository."""

    @abstractmethod
    def ingest_csv(self, csv_path: str) -> IngestStats:
        ...
