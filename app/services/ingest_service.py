"""
Ingest Service — SRP: only responsible for parsing and indexing emails + attachments.
Reads the Enron CSV, slices a coherent set of threads, builds chunk store.
Also scans data/attachments/<message_id>/ for PDF/DOCX/TXT/HTML files.
"""
from __future__ import annotations

import email as email_lib
import hashlib
import re
import time
from collections import defaultdict
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

from app.core.config import Settings
from app.domain.models import Chunk, IngestStats, SourceType
from app.repositories.chunk_repository import ChunkRepository

CHUNK_WORDS = 300    # ~400 tokens per chunk
OVERLAP_WORDS = 50   # word overlap between consecutive chunks

BUSINESS_KEYWORDS = [
    "contract", "invoice", "payment", "budget", "approval",
    "meeting", "agreement", "proposal", "report", "project",
    "deal", "offer", "purchase", "vendor", "client",
]

MAX_EMAILS_TO_SCAN = 10_000
MIN_THREAD_MSGS = 3
MAX_THREAD_MSGS = 20
MAX_THREADS = 15


class IngestService:
    """
    Parses raw Enron email CSV + attachment files → structured Chunk objects → saves to repository.
    Single Responsibility: knows about email/attachment parsing and chunking, nothing else.
    """

    def __init__(self, chunk_repo: ChunkRepository, settings: Settings) -> None:
        self._repo = chunk_repo
        self._settings = settings

    def ingest_csv(self, csv_path: str) -> IngestStats:
        import pandas as pd

        t0 = time.perf_counter()
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {path}")

        print(f"[ingest] Loading {path} ...")
        df = pd.read_csv(path)
        print(f"[ingest] {len(df):,} raw emails found.")

        # ── Parse emails ────────────────────────────────────────────
        parsed: list[dict] = []
        for _, row in df.iterrows():
            p = self._parse_raw_email(str(row.get("message", "")))
            if p and p["body"] and len(p["body"]) > 50:
                parsed.append(p)
            if len(parsed) >= MAX_EMAILS_TO_SCAN:
                break

        print(f"[ingest] Parsed {len(parsed)} valid emails.")

        # ── Thread grouping ─────────────────────────────────────────
        thread_map: dict[str, list[dict]] = defaultdict(list)
        for em in parsed:
            subject = re.sub(
                r"^(Re:|Fwd:|FW:|RE:|FWD:)\s*", "", em["subject"],
                flags=re.IGNORECASE,
            ).strip()
            if any(kw in subject.lower() for kw in BUSINESS_KEYWORDS):
                thread_map[subject].append(em)

        good_threads = {
            s: msgs
            for s, msgs in thread_map.items()
            if MIN_THREAD_MSGS <= len(msgs) <= MAX_THREAD_MSGS
        }
        selected = dict(
            sorted(good_threads.items(), key=lambda x: len(x[1]), reverse=True)[:MAX_THREADS]
        )
        print(f"[ingest] Selected {len(selected)} threads.")

        # ── Build email chunks ──────────────────────────────────────
        all_chunks: list[Chunk] = []
        # msg_meta: message_id -> {thread_id, thread_subject} for attachment lookup
        msg_meta: dict[str, dict] = {}
        for t_idx, (subject, messages) in enumerate(selected.items()):
            thread_id = f"T-{t_idx+1:04d}"
            for msg in messages:
                raw_id = msg["message_id"] or f"{thread_id}-{id(msg)}"
                message_id = "m_" + hashlib.md5(raw_id.encode()).hexdigest()[:6]
                chunk = Chunk(
                    doc_id=f"{message_id}_body",
                    message_id=message_id,
                    thread_id=thread_id,
                    text=(
                        f"Subject: {msg['subject']}\n"
                        f"From: {msg['from']}\n"
                        f"To: {msg['to']}\n\n"
                        f"{msg['body']}"
                    ),
                    source_type=SourceType.EMAIL,
                    subject=msg["subject"],
                    from_addr=msg["from"],
                    to_addr=msg["to"],
                    date=str(msg["date"]) if msg["date"] else "",
                    thread_subject=subject,
                )
                all_chunks.append(chunk)
                msg_meta[message_id] = {
                    "thread_id": thread_id,
                    "thread_subject": subject,
                }

        # ── Ingest attachments ──────────────────────────────────────
        attachments_dir = self._settings.data_dir / "attachments"
        attachment_chunks = self._ingest_attachments(msg_meta, attachments_dir)
        all_chunks.extend(attachment_chunks)

        self._repo.save_many(all_chunks)

        email_count = len([c for c in all_chunks if c.source_type == SourceType.EMAIL])
        total_chars = sum(len(c.text) for c in all_chunks)
        duration = round(time.perf_counter() - t0, 2)
        stats = IngestStats(
            threads=len(selected),
            messages=email_count,
            attachments=len(attachment_chunks),
            total_chars=total_chars,
            duration_s=duration,
        )
        print(
            f"[ingest] Done in {duration}s — {stats.threads} threads, "
            f"{stats.messages} emails, {stats.attachments} attachment chunks."
        )
        return stats

    # ── Attachment ingestion ──────────────────────────────────────────────────

    def _ingest_attachments(
        self,
        msg_meta: dict[str, dict],
        attachments_dir: Path,
    ) -> list[Chunk]:
        """
        Scan attachments_dir/<message_id>/ for PDF/DOCX/TXT/HTML files.
        Returns a list of Chunk objects with page_no set for PDFs.
        """
        chunks: list[Chunk] = []
        if not attachments_dir.exists():
            return chunks

        for msg_dir in sorted(attachments_dir.iterdir()):
            if not msg_dir.is_dir():
                continue
            message_id = msg_dir.name
            meta = msg_meta.get(message_id)
            if not meta:
                continue  # attachment for un-indexed message — skip

            thread_id = meta["thread_id"]
            thread_subject = meta["thread_subject"]

            for file_path in sorted(msg_dir.iterdir()):
                if not file_path.is_file():
                    continue
                ext = file_path.suffix.lower()
                try:
                    if ext == ".pdf":
                        fc = self._parse_pdf(file_path, message_id, thread_id, thread_subject)
                    elif ext in (".docx", ".doc"):
                        fc = self._parse_docx(file_path, message_id, thread_id, thread_subject)
                    elif ext == ".txt":
                        fc = self._parse_txt(file_path, message_id, thread_id, thread_subject)
                    elif ext in (".html", ".htm"):
                        fc = self._parse_html(file_path, message_id, thread_id, thread_subject)
                    else:
                        continue
                    chunks.extend(fc)
                    print(f"[ingest]   {file_path.name}: {len(fc)} chunk(s)")
                except Exception as exc:
                    print(f"[ingest] Warning — could not parse {file_path.name}: {exc}")

        return chunks

    # ── Per-format parsers ────────────────────────────────────────────────────

    @staticmethod
    def _parse_pdf(
        path: Path, message_id: str, thread_id: str, thread_subject: str
    ) -> list[Chunk]:
        """Parse PDF page by page; preserve page numbers for citations."""
        try:
            import pypdf
        except ImportError:
            raise ImportError("pypdf is required. Run: pip install pypdf")

        chunks: list[Chunk] = []
        reader = pypdf.PdfReader(str(path))
        for page_num, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            sub = IngestService._chunk_text(
                text, message_id, thread_id, thread_subject,
                SourceType.PDF, page_num, path.name,
            )
            chunks.extend(sub)
        return chunks

    @staticmethod
    def _parse_docx(
        path: Path, message_id: str, thread_id: str, thread_subject: str
    ) -> list[Chunk]:
        """Parse DOCX; split into 300-word chunks."""
        try:
            from docx import Document
        except ImportError:
            raise ImportError("python-docx is required. Run: pip install python-docx")

        doc = Document(str(path))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return IngestService._chunk_text(
            text, message_id, thread_id, thread_subject,
            SourceType.DOCX, None, path.name,
        )

    @staticmethod
    def _parse_txt(
        path: Path, message_id: str, thread_id: str, thread_subject: str
    ) -> list[Chunk]:
        """Parse plain-text file."""
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        return IngestService._chunk_text(
            text, message_id, thread_id, thread_subject,
            SourceType.TXT, None, path.name,
        )

    @staticmethod
    def _parse_html(
        path: Path, message_id: str, thread_id: str, thread_subject: str
    ) -> list[Chunk]:
        """Strip HTML tags and chunk as plain text."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError("beautifulsoup4 is required. Run: pip install beautifulsoup4")

        html = path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n").strip()
        return IngestService._chunk_text(
            text, message_id, thread_id, thread_subject,
            SourceType.HTML, None, path.name,
        )

    # ── Chunking helper ──────────────────────────────────────────────────────

    @staticmethod
    def _chunk_text(
        text: str,
        message_id: str,
        thread_id: str,
        thread_subject: str,
        source_type: SourceType,
        page_no: Optional[int],
        filename: str,
    ) -> list[Chunk]:
        """
        Split text into ~CHUNK_WORDS-word chunks with OVERLAP_WORDS overlap.
        For PDFs, all sub-chunks of the same page share the same page_no.
        """
        words = text.split()
        if not words:
            return []

        chunks: list[Chunk] = []
        stem = Path(filename).stem[:20]
        start = 0
        chunk_idx = 0
        while start < len(words):
            end = min(start + CHUNK_WORDS, len(words))
            chunk_text = " ".join(words[start:end]).strip()
            if len(chunk_text) > 30:
                # doc_id: unique per chunk even when multiple chunks share a page
                doc_id = f"{message_id}_{stem}_p{page_no}_c{chunk_idx}"
                chunks.append(Chunk(
                    doc_id=doc_id,
                    message_id=message_id,
                    thread_id=thread_id,
                    text=chunk_text,
                    source_type=source_type,
                    page_no=page_no,
                    filename=filename,
                    thread_subject=thread_subject,
                ))
            start += CHUNK_WORDS - OVERLAP_WORDS
            chunk_idx += 1

        return chunks

    # ── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_raw_email(raw: str) -> Optional[dict]:
        try:
            msg = email_lib.message_from_string(raw)
            date_str = msg.get("Date", "")
            date = None
            try:
                date = parsedate_to_datetime(date_str)
            except Exception:
                pass

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                        except Exception:
                            pass
            else:
                try:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                except Exception:
                    body = str(msg.get_payload())

            return {
                "message_id": msg.get("Message-ID", "").strip(),
                "date":       date,
                "from":       msg.get("From", "").strip(),
                "to":         msg.get("To", "").strip(),
                "cc":         msg.get("Cc", "").strip(),
                "subject":    msg.get("Subject", "").strip(),
                "body":       body.strip(),
            }
        except Exception:
            return None
