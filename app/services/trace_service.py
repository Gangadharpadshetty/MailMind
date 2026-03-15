"""
Trace Service — Observer Pattern variant.
Writes one JSONL record per turn (SRP: only logging).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from app.domain.interfaces import ITracer
from app.domain.models import Chunk, Citation


class TraceService(ITracer):
    """Appends structured records to runs/<timestamp>/trace.jsonl."""

    def __init__(self, runs_dir: Path) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = runs_dir / timestamp
        run_dir.mkdir(parents=True, exist_ok=True)
        self._trace_path = run_dir / "trace.jsonl"
        print(f"[trace] Writing to {self._trace_path}")

    def log(
        self,
        *,
        session_id: str,
        thread_id: str,
        user_text: str,
        rewrite: str,
        retrieved: list[Chunk],
        answer: str,
        citations: list[Citation],
        latency_total: float,
        latency_rewrite: float,
        latency_retrieve: float,
        latency_generate: float,
        token_count: int,
        provider: str,
    ) -> str:
        trace_id = "tr_" + uuid.uuid4().hex[:6]
        record = {
            "trace_id":   trace_id,
            "timestamp":  datetime.now().isoformat(),
            "session_id": session_id,
            "thread_id":  thread_id,
            "provider":   provider,
            # Input
            "user_text":  user_text,
            "rewrite":    rewrite,
            # Retrieval
            "retrieved": [
                {
                    "doc_id":     r.doc_id,
                    "message_id": r.message_id,
                    "score":      r.score,
                    "snippet":    r.text[:100],
                }
                for r in retrieved
            ],
            "retrieved_count": len(retrieved),
            # Output
            "answer":    answer,
            "citations": [
                {"type": c.type, "message_id": c.message_id, "page": c.page}
                for c in citations
            ],
            # Performance
            "latency": {
                "total_s":    latency_total,
                "rewrite_s":  latency_rewrite,
                "retrieve_s": latency_retrieve,
                "generate_s": latency_generate,
            },
            "token_count": token_count,
        }
        with open(self._trace_path, "a") as f:
            f.write(json.dumps(record) + "\n")
        return trace_id

    def get_stats(self) -> dict:
        """Read back latency stats from the current run's trace file."""
        if not self._trace_path.exists():
            return {}
        records = [json.loads(line) for line in self._trace_path.open()]
        if not records:
            return {}
        latencies = sorted(r["latency"]["total_s"] for r in records)
        tokens = [r["token_count"] for r in records]
        p95_idx = max(0, int(len(latencies) * 0.95) - 1)
        return {
            "total_turns": len(records),
            "p50_latency":  latencies[len(latencies) // 2],
            "p95_latency":  latencies[p95_idx],
            "avg_tokens":   int(sum(tokens) / len(tokens)),
            "trace_file":   str(self._trace_path),
        }
