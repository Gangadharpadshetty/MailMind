#!/usr/bin/env python3
"""
ingest.py — Standalone script to parse the Enron CSV and build indexes.

Usage:
    python ingest.py                         # uses path from .env / default
    python ingest.py --csv data/emails.csv
    python ingest.py --csv data/emails.csv --vectors   # also build LanceDB

DigitalOcean: set GEMINI_API_KEY and KAGGLE_KEY in the environment.
"""
import argparse
import sys
import time
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import get_settings
from app.repositories.chunk_repository import ChunkRepository
from app.services.ingest_service import IngestService
from app.services.retrieval_service import RetrievalService


def main():
    parser = argparse.ArgumentParser(description="MailMind — Email Ingest Pipeline")
    parser.add_argument("--csv",     default="", help="Path to Enron emails.csv")
    parser.add_argument("--vectors", action="store_true", help="Build LanceDB vector index (slower)")
    args = parser.parse_args()

    settings = get_settings()
    csv_path = args.csv or str(settings.enron_csv)

    print("=" * 60)
    print("  MailMind Ingest Pipeline")
    print("=" * 60)
    print(f"  CSV path  : {csv_path}")
    print(f"  Data dir  : {settings.data_dir}")
    print(f"  Vectors   : {'yes' if args.vectors else 'no (BM25 only)'}")
    print("=" * 60)

    # ── Repositories ──────────────────────────────────────────────
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    chunk_repo = ChunkRepository(
        data_dir=settings.data_dir,
        lancedb_dir=settings.lancedb_dir,
    )

    # ── Ingest ────────────────────────────────────────────────────
    t0 = time.perf_counter()
    svc = IngestService(chunk_repo=chunk_repo, settings=settings)
    stats = svc.ingest_csv(csv_path)

    print()
    print("📧 Ingest Summary")
    print(f"   Threads     : {stats.threads}")
    print(f"   Messages    : {stats.messages}")
    print(f"   Attachments : {stats.attachments} chunks")
    print(f"   Chars       : {stats.total_chars:,}")
    print(f"   Duration    : {stats.duration_s}s")

    # ── Build indexes ─────────────────────────────────────────────
    retrieval_svc = RetrievalService(chunk_repo, settings)
    retrieval_svc.build_index(embed=args.vectors)

    total = round(time.perf_counter() - t0, 1)
    print()
    print(f"✅  Done in {total}s — ready to run `uvicorn app.main:app --reload`")


if __name__ == "__main__":
    main()
