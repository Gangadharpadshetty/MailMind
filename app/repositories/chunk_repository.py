"""
Chunk Repository — Repository Pattern.
Abstracts all storage concerns away from business logic (SRP, DIP).

Storage layers:
  - RAM list (ALL_CHUNKS): fast BM25 indexing
  - LanceDB table: vector similarity search
  - JSON file: persistence across restarts
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Optional

from app.domain.interfaces import IChunkRepository
from app.domain.models import Chunk, SourceType


class ChunkRepository(IChunkRepository):
    """
    Concrete chunk repository with dual storage:
    an in-memory list for BM25 and a LanceDB table for vector search.
    """

    def __init__(self, data_dir: Path, lancedb_dir: Path) -> None:
        self._data_dir = data_dir
        self._lancedb_dir = lancedb_dir
        self._chunks: list[Chunk] = []
        self._threads: dict[str, dict[str, Any]] = {}
        self._json_path = data_dir / "chunks.json"
        self._threads_path = data_dir / "threads.json"

    # ── Write ────────────────────────────────────────────────────────────────

    def save_many(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks
        self._rebuild_thread_map()
        self._persist()

    def _rebuild_thread_map(self) -> None:
        self._threads = {}
        for c in self._chunks:
            if c.thread_id not in self._threads:
                self._threads[c.thread_id] = {
                    "subject": c.thread_subject,
                    "message_count": 0,
                    "messages": [],
                }
            self._threads[c.thread_id]["message_count"] += 1
            self._threads[c.thread_id]["messages"].append(c.message_id)

    def _persist(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        # Save chunk metadata (without embeddings — those live in LanceDB)
        rows = []
        for c in self._chunks:
            rows.append({
                "doc_id": c.doc_id,
                "message_id": c.message_id,
                "thread_id": c.thread_id,
                "text": c.text,
                "source_type": c.source_type,
                "page_no": c.page_no,
                "filename": c.filename,
                "subject": c.subject,
                "from_addr": c.from_addr,
                "to_addr": c.to_addr,
                "date": c.date,
                "thread_subject": c.thread_subject,
            })
        self._json_path.write_text(json.dumps(rows, ensure_ascii=False))
        self._threads_path.write_text(json.dumps(self._threads, ensure_ascii=False))

    # ── Read ─────────────────────────────────────────────────────────────────

    def load(self) -> bool:
        """Load previously persisted chunks. Returns True if successful."""
        if not self._json_path.exists():
            return False
        rows = json.loads(self._json_path.read_text())
        self._chunks = [
            Chunk(
                doc_id=r["doc_id"],
                message_id=r["message_id"],
                thread_id=r["thread_id"],
                text=r["text"],
                source_type=r.get("source_type", "email"),
                page_no=r.get("page_no"),
                filename=r.get("filename"),
                subject=r.get("subject", ""),
                from_addr=r.get("from_addr", ""),
                to_addr=r.get("to_addr", ""),
                date=r.get("date", ""),
                thread_subject=r.get("thread_subject", ""),
            )
            for r in rows
        ]
        if self._threads_path.exists():
            self._threads = json.loads(self._threads_path.read_text())
        else:
            self._rebuild_thread_map()
        return True

    def get_all(self) -> list[Chunk]:
        return self._chunks

    def get_by_thread(self, thread_id: str) -> list[Chunk]:
        return [c for c in self._chunks if c.thread_id == thread_id]

    def list_threads(self) -> dict[str, Any]:
        return self._threads

    def count(self) -> int:
        return len(self._chunks)

    def is_loaded(self) -> bool:
        return len(self._chunks) > 0
