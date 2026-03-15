#!/usr/bin/env python3
"""
create_sample_attachments.py — Generate sample PDF attachments for the MailMind demo.

Reads data/chunks.json to find real message IDs, then creates:
  data/attachments/<message_id>/vendor_contract.pdf       (3 pages)
  data/attachments/<message_id>/budget_approval.pdf       (2 pages)
  data/attachments/<message_id>/meeting_minutes.txt       (plain text)

Run ONCE after `python ingest.py`, then re-run ingest to index the attachments:
    python create_sample_attachments.py
    python ingest.py --csv Data/emails.csv
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _ascii(text: str) -> str:
    """Replace common non-ASCII chars with ASCII equivalents."""
    replacements = {
        "\u201c": '"', "\u201d": '"',   # curly double quotes
        "\u2018": "'", "\u2019": "'",   # curly single quotes
        "\u2014": "-", "\u2013": "-",   # em dash, en dash
        "\u2500": "-",                   # box-drawing horizontal
        "\u2019": "'",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def create_pdf(path: Path, pages: list[str]) -> None:
    """Create a multi-page PDF using fpdf2."""
    try:
        from fpdf import FPDF
    except ImportError:
        print("[sample] fpdf2 not found. Run: pip install fpdf2")
        raise

    pdf = FPDF()
    pdf.set_margins(left=15, top=15, right=15)
    pdf.set_auto_page_break(auto=True, margin=15)
    for page_text in pages:
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)
        # Pass the whole page text; multi_cell handles \n internally
        pdf.multi_cell(w=pdf.w - 30, h=6, txt=_ascii(page_text).strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    print(f"[sample] Created {path} ({len(pages)} pages)")


def create_txt(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip(), encoding="utf-8")
    print(f"[sample] Created {path}")


def main() -> None:
    chunks_path = Path("data/chunks.json")
    if not chunks_path.exists():
        print("[sample] data/chunks.json not found. Run ingest.py first.")
        sys.exit(1)

    chunks = json.loads(chunks_path.read_text())

    # Gather first 3 distinct message IDs from T-0001
    t1_ids: list[str] = []
    for c in chunks:
        if c["thread_id"] == "T-0001" and c["message_id"] not in t1_ids:
            t1_ids.append(c["message_id"])
        if len(t1_ids) >= 3:
            break

    if len(t1_ids) < 3:
        # Fall back to whatever thread has the most messages
        from collections import Counter
        tid = Counter(c["thread_id"] for c in chunks).most_common(1)[0][0]
        t1_ids = []
        for c in chunks:
            if c["thread_id"] == tid and c["message_id"] not in t1_ids:
                t1_ids.append(c["message_id"])
            if len(t1_ids) >= 3:
                break

    if not t1_ids:
        print("[sample] No messages found in chunks.json.")
        sys.exit(1)

    att_dir = Path("data/attachments")
    mid0, mid1, mid2 = t1_ids[0], t1_ids[1], t1_ids[2]

    # ── Attachment 1: vendor_contract.pdf (3 pages) ──────────────────────────
    create_pdf(
        att_dir / mid0 / "vendor_contract.pdf",
        pages=[
            """\
VENDOR CONTRACT AGREEMENT
Effective Date: October 1, 2001

This Storage Services Agreement is entered into between
Enron Corp (Client) and SecureStore Solutions Inc (Vendor).

The purpose of this agreement is to define the terms under which
SecureStore Solutions will provide off-site data storage and archival
services to Enron Corp for a period of twelve (12) months.

Parties:
  Client:  Enron Corp, 1400 Smith Street, Houston, TX 77002
  Vendor:  SecureStore Solutions Inc, 500 Data Pkwy, Dallas, TX 75201

This document supersedes all prior verbal or written negotiations
between the parties regarding storage services.""",

            """\
TERMS AND CONDITIONS

1. SERVICES
   Vendor shall provide 500 GB of encrypted off-site storage capacity,
   accessible 24/7 with 99.9% uptime SLA.

2. PRICING
   Annual contract value: $48,000 USD
   Payment schedule: Quarterly in advance ($12,000 per quarter)
   First payment due: November 1, 2001

3. DATA SECURITY
   All data shall be encrypted using AES-256. Vendor shall not access
   client data without written authorisation.

4. TERMINATION
   Either party may terminate with 60 days written notice after the
   initial 12-month period.

5. PENALTIES
   Downtime beyond SLA thresholds will attract a 5% credit per
   affected quarter.""",

            """\
SIGNATURES AND APPROVAL

This agreement has been reviewed and approved by the finance and
legal departments of Enron Corp.

Approved Amount:   $48,000 USD (annual)
Approval Date:     October 15, 2001
Approved By:       J. Arnold, VP Finance, Enron Corp
Vendor Contact:    M. Davis, Account Manager, SecureStore Solutions

Client Signature:  ___________________________
                   J. Arnold, VP Finance

Vendor Signature:  ___________________________
                   M. Davis, Account Manager

Both parties agree to the terms outlined in this document.
Contract Reference: ESS-2001-0042""",
        ],
    )

    # ── Attachment 2: budget_approval.pdf (2 pages) ──────────────────────────
    create_pdf(
        att_dir / mid1 / "budget_approval.pdf",
        pages=[
            """\
BUDGET APPROVAL MEMORANDUM
Date: October 12, 2001
To:   Finance Committee, Enron Corp
From: J. Arnold, VP Finance
Re:   Storage Vendor Contract - Budget Approval Request

SUMMARY
This memo requests formal budget approval for the SecureStore Solutions
vendor contract totalling $48,000 for FY2002.

LINE ITEMS
  Off-site storage (500 GB, 12 months)  :  $38,400
  Setup and migration fee (one-time)    :  $5,600
  SLA monitoring portal (annual licence):  $4,000
  -------------------------------------------------
  TOTAL                                 :  $48,000

JUSTIFICATION
Current on-site storage infrastructure is at 94% capacity.
Failure to expand will risk data loss by Q1 2002.""",

            """\
FINANCE COMMITTEE APPROVAL

After review of the submitted budget proposal the Finance Committee
hereby approves the following:

  Approved Vendor     : SecureStore Solutions Inc
  Approved Amount     : $48,000 USD
  Budget Year         : FY2002 (October 2001 - September 2002)
  Cost Centre         : IT Infrastructure (CC-4412)
  Approval Date       : October 15, 2001

Committee Members Present:
  - J. Arnold      (Chair, VP Finance)       APPROVED
  - S. Buy         (Chief Risk Officer)      APPROVED
  - R. Causey      (Chief Accounting Officer) APPROVED

This approval is contingent on the vendor signing the SLA addendum
by October 31, 2001. Purchase order PO-2001-0388 has been raised.""",
        ],
    )

    # ── Attachment 3: meeting_minutes.txt ────────────────────────────────────
    create_txt(
        att_dir / mid2 / "meeting_minutes.txt",
        content="""\
MEETING MINUTES - VENDOR SELECTION COMMITTEE
Date:     September 28, 2001
Location: Enron HQ, Houston TX — Conference Room 3B
Attendees: J. Arnold, S. Buy, K. Lay (observer), IT Director P. Morse

AGENDA ITEM 1: Storage vendor shortlist review
  Three vendors were evaluated: SecureStore Solutions, DataVault Inc,
  and ArchivePro LLC.

  Scoring summary (out of 100):
    SecureStore Solutions : 87 — best price/performance, strong SLA
    DataVault Inc         : 74 — higher cost, limited uptime guarantee
    ArchivePro LLC        : 61 — good security but capacity constraints

AGENDA ITEM 2: Contract terms negotiation update
  J. Arnold confirmed that SecureStore agreed to reduce setup fee from
  $8,000 to $5,600 following negotiation on September 25, 2001.
  Final contract value agreed at $48,000 annually.

AGENDA ITEM 3: Approval timeline
  Finance committee approval memo to be circulated by October 10.
  Target contract signing: October 20, 2001.
  Service start date: November 1, 2001.

ACTION ITEMS:
  - J. Arnold  : Circulate budget approval memo (due Oct 10)
  - P. Morse   : Prepare data migration plan (due Oct 15)
  - Legal team : Review contract draft (due Oct 12)

Next meeting: October 18, 2001 at 10:00 AM.
""",
    )

    print()
    print("✅  Sample attachments created:")
    print(f"   {att_dir / mid0 / 'vendor_contract.pdf'}  (3 pages)")
    print(f"   {att_dir / mid1 / 'budget_approval.pdf'}  (2 pages)")
    print(f"   {att_dir / mid2 / 'meeting_minutes.txt'}")
    print()
    print("Now re-run ingest to index them:")
    print("   python ingest.py --csv Data/emails.csv")


if __name__ == "__main__":
    main()
