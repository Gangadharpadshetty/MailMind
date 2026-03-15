# DATASET.md — Enron Email Slice

## Source
- **Name**: Enron Email Dataset
- **Link**: https://www.kaggle.com/datasets/wcukierski/enron-email-dataset
- **License**: Public domain (released by FERC during Enron investigation, 2003)

## Selection Criteria
The ingest pipeline (`ingest.py`) automatically creates a coherent slice:

| Filter | Value |
|--------|-------|
| Sample size scanned | First 10,000 emails |
| Subject keywords | contract, invoice, payment, budget, approval, meeting, agreement, proposal, report, project, deal, offer, purchase, vendor, client |
| Thread min size | 3 messages |
| Thread max size | 20 messages |
| Threads selected | Top 15 by message count |

## Resulting Counts (typical run)
| Metric | Count |
|--------|-------|
| Threads | 10–15 |
| Messages | 80–200 |
| Attachments | 0 (email bodies only in base run) |
| Approx. text size | ~300–800 KB |

## Preprocessing
1. Raw email string parsed with Python's `email` stdlib
2. Subject lines normalised (Re:/Fwd: stripped)
3. Thread grouping by normalised subject
4. Stable `message_id` = `m_` + MD5(original Message-ID)[:6]
5. Chunk text = `Subject + From + To + body`

## Adding Attachments
Place `.pdf` / `.txt` / `.docx` files alongside the CSV as `data/attachments/<message_id>/<filename>`.
The `IngestService` is designed with the **Open/Closed Principle** — extend `AttachmentParser` without touching existing code.
