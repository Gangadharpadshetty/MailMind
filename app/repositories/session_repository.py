"""
Session Repository — Repository Pattern.
All session state lives in RAM (per-process). SRP: only manages sessions.
"""
import uuid
from typing import Optional

from app.domain.interfaces import ISessionRepository
from app.domain.models import Session


class InMemorySessionRepository(ISessionRepository):
    """
    Thread-safe in-memory session store.
    For multi-process deployments, swap this with a Redis-backed implementation
    without touching business logic (DIP, OCP).
    """

    def __init__(self) -> None:
        self._store: dict[str, Session] = {}

    def create(self, thread_id: str) -> Session:
        session_id = "sess_" + uuid.uuid4().hex[:8]
        session = Session(session_id=session_id, thread_id=thread_id)
        self._store[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._store.get(session_id)

    def update(self, session: Session) -> None:
        self._store[session.session_id] = session

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    def count(self) -> int:
        return len(self._store)
