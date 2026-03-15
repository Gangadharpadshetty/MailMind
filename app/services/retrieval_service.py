"""
Retrieval Service — SRP: only responsible for finding relevant chunks.
Implements hybrid BM25 + vector search with Reciprocal Rank Fusion (RRF).
Depends on IChunkRepository and IEmbedder abstractions (DIP).
"""
from __future__ import annotations

import re
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi

from app.core.config import Settings
from app.domain.interfaces import IRetriever
from app.domain.models import Chunk
from app.repositories.chunk_repository import ChunkRepository


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return text.split()


class RetrievalService(IRetriever):
    """
    Hybrid retriever:
      1. BM25 keyword search (always available)
      2. Dense vector search via LanceDB (when embeddings are built)
      3. RRF (Reciprocal Rank Fusion) to merge both result lists
    Thread-scoped by default; pass thread_id=None for global search.
    """

    def __init__(self, chunk_repo: ChunkRepository, settings: Settings) -> None:
        self._repo = chunk_repo
        self._settings = settings
        self._bm25: Optional[BM25Okapi] = None
        self._bm25_chunks: list[Chunk] = []
        self._lancedb_table = None
        self._embed_model = None

    # ── Index building ───────────────────────────────────────────────────────

    def build_index(self, embed: bool = True) -> None:
        """Build BM25 index and optionally vector index."""
        chunks = self._repo.get_all()
        if not chunks:
            raise RuntimeError("No chunks in repository. Run ingest first.")

        self._build_bm25(chunks)
        if embed:
            self._build_vector_index(chunks)

    def _build_bm25(self, chunks: list[Chunk]) -> None:
        print(f"[retrieval] Building BM25 index over {len(chunks)} chunks...")
        self._bm25_chunks = chunks
        corpus = [_tokenize(c.text) for c in chunks]
        self._bm25 = BM25Okapi(corpus)
        print("[retrieval] BM25 ready.")

    def _build_vector_index(self, chunks: list[Chunk]) -> None:
        try:
            import lancedb
            from sentence_transformers import SentenceTransformer

            print(f"[retrieval] Loading embed model '{self._settings.embed_model}'...")
            self._embed_model = SentenceTransformer(self._settings.embed_model)

            texts = [c.text[:512] for c in chunks]
            print(f"[retrieval] Embedding {len(texts)} chunks...")
            embeddings = self._embed_model.encode(
                texts, batch_size=64, show_progress_bar=True, convert_to_numpy=True
            )

            db = lancedb.connect(str(self._settings.lancedb_dir))
            rows = [
                {
                    "vector":      embeddings[i].tolist(),
                    "doc_id":      c.doc_id,
                    "message_id":  c.message_id,
                    "thread_id":   c.thread_id,
                    "source_type": str(c.source_type),
                    "page_no":     c.page_no or 0,
                    "filename":    c.filename or "",
                    "text":        c.text[:1000],
                    "subject":     c.subject,
                    "from_addr":   c.from_addr,
                    "date":        c.date,
                }
                for i, c in enumerate(chunks)
            ]

            if "emails" in db.table_names():
                db.drop_table("emails")
            self._lancedb_table = db.create_table("emails", data=rows)
            print(f"[retrieval] LanceDB table created with {self._lancedb_table.count_rows()} rows.")

        except ImportError as e:
            print(f"[retrieval] Vector index skipped (missing deps: {e}). BM25-only mode.")
        except Exception as e:
            print(f"[retrieval] Vector index error: {e}. Falling back to BM25-only.")

    def load_vector_index(self) -> None:
        """Reload an existing LanceDB index and embeddings model (no re-embedding)."""
        try:
            import lancedb
            from sentence_transformers import SentenceTransformer

            db = lancedb.connect(str(self._settings.lancedb_dir))
            if "emails" in db.table_names():
                self._lancedb_table = db.open_table("emails")
                self._embed_model = SentenceTransformer(self._settings.embed_model)
                print("[retrieval] Loaded existing LanceDB table.")
        except Exception as e:
            print(f"[retrieval] Could not load vector index: {e}")

    # ── Retrieval ────────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        thread_id: Optional[str],
        top_k: int = 6,
    ) -> list[Chunk]:
        if not self._bm25:
            # Auto-rebuild if chunks are loaded but index was not built yet
            self.build_index(embed=False)

        bm25_ranked = self._bm25_search(query, thread_id, top_k)
        vec_ranked  = self._vector_search(query, thread_id, top_k) if self._lancedb_table else []

        # ── RRF fusion ───────────────────────────────────────────────────────
        k = self._settings.rrf_k
        rrf: dict[int, float] = {}
        for rank, idx in enumerate(bm25_ranked):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (k + rank + 1)
        for rank, idx in enumerate(vec_ranked):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (k + rank + 1)

        final = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:top_k]

        bm25_scores = self._bm25.get_scores(_tokenize(query)) if self._bm25 else []

        results: list[Chunk] = []
        for idx, rrf_score in final:
            chunk = self._bm25_chunks[idx]
            c = Chunk(**{
                "doc_id":       chunk.doc_id,
                "message_id":   chunk.message_id,
                "thread_id":    chunk.thread_id,
                "text":         chunk.text,
                "source_type":  chunk.source_type,
                "page_no":      chunk.page_no,
                "filename":     chunk.filename,
                "subject":      chunk.subject,
                "from_addr":    chunk.from_addr,
                "to_addr":      chunk.to_addr,
                "date":         chunk.date,
                "thread_subject": chunk.thread_subject,
                "score":        round(rrf_score, 4),
                "bm25_score":   round(float(bm25_scores[idx]), 4) if len(bm25_scores) > idx else 0.0,
            })
            results.append(c)
        return results

    # ── Private helpers ──────────────────────────────────────────────────────

    def _bm25_search(
        self, query: str, thread_id: Optional[str], top_k: int
    ) -> list[int]:
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = np.argsort(scores)[::-1]
        if thread_id:
            ranked = [
                i for i in ranked
                if self._bm25_chunks[i].thread_id == thread_id
            ]
        return list(ranked[: top_k * 2])

    def _vector_search(
        self, query: str, thread_id: Optional[str], top_k: int
    ) -> list[int]:
        try:
            query_vec = self._embed_model.encode([query])[0].tolist()
            search = self._lancedb_table.search(query_vec)
            if thread_id:
                search = search.where(f"thread_id = '{thread_id}'")
            vec_results = search.limit(top_k * 2).to_list()

            doc_id_to_idx = {c.doc_id: i for i, c in enumerate(self._bm25_chunks)}
            return [
                doc_id_to_idx[r["doc_id"]]
                for r in vec_results
                if r["doc_id"] in doc_id_to_idx
            ]
        except Exception as e:
            print(f"[retrieval] Vector search error: {e}")
            return []
