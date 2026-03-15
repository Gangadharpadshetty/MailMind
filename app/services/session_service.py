"""
Session Service — SRP: manages conversation memory and entity state.
"""
from __future__ import annotations

import re

from app.domain.models import Session
from app.repositories.session_repository import InMemorySessionRepository


def build_context_string(session: Session) -> str:
    """Format rolling turns + entity notes into a rewrite-prompt context block."""
    parts: list[str] = []

    if session.turns:
        history = "\n".join([
            f"User: {t['user']}\nAssistant: {t['bot'][:200]}"
            for t in session.turns[-3:]
        ])
        parts.append(f"Recent conversation:\n{history}")

    if session.entities:
        ent_str = ", ".join([
            f"{k}: {', '.join(v) if isinstance(v, list) else v}"
            for k, v in session.entities.items()
        ])
        parts.append(f"Known entities: {ent_str}")

    return "\n\n".join(parts)


class SessionService:
    """
    Orchestrates session lifecycle and memory updates.
    Delegates storage to ISessionRepository (DIP).
    """

    def __init__(self, session_repo: InMemorySessionRepository) -> None:
        self._repo = session_repo

    def create_session(self, thread_id: str) -> Session:
        return self._repo.create(thread_id)

    def get_session(self, session_id: str) -> Session:
        session = self._repo.get(session_id)
        if session is None:
            from app.core.exceptions import SessionNotFoundError
            raise SessionNotFoundError(session_id)
        return session

    def update_memory(self, session: Session, user_text: str, bot_answer: str) -> None:
        """Append turn and extract entities from the conversation."""
        session.turns.append({"user": user_text, "bot": bot_answer})
        if len(session.turns) > 4:
            session.turns.pop(0)
        session.last_answer = bot_answer
        self._extract_entities(session, user_text + " " + bot_answer)
        self._repo.update(session)

    def switch_thread(self, session: Session, thread_id: str) -> None:
        session.thread_id = thread_id
        session.turns = []
        session.entities = {}
        session.last_answer = ""
        self._repo.update(session)

    def reset_session(self, session_id: str) -> None:
        self._repo.delete(session_id)

    # ── Private ──────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_entities(session: Session, text: str) -> None:
        # Dollar amounts
        amounts = re.findall(r"\$[\d,]+(?:\.\d+)?", text)
        if amounts:
            session.entities["amounts"] = amounts[-3:]

        # Dates
        dates = re.findall(
            r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
            r"|\d{4}-\d{2}-\d{2}",
            text, re.IGNORECASE,
        )
        if dates:
            session.entities["dates"] = dates[-3:]

        # Filenames
        files = re.findall(r"[\w_-]+\.(?:pdf|doc|docx|txt|xlsx)", text, re.IGNORECASE)
        if files:
            session.entities["files"] = list(set(files))[:5]

        # Person names (two capitalised words)
        names = re.findall(r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", text)
        if names:
            session.entities["people"] = list(set(names))[:5]
