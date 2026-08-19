---
title: Domain review — ingestion and workers
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: engineering, ops
reviewed_commit: 09a102a
---

# Domain: ingestion and workers

Canonical findings: [critical](../01-critical.md) C-001 C-011 C-012 C-015 C-016 · [high](../02-high.md) H-007 H-011 H-012 H-030 H-031 · [medium](../03-medium.md) M-011 M-015 M-024 M-029 · risk register R-02 R-03 R-05 R-10.

## What looks solid (from contracts + worker layout)

- Durable jobs in Supabase, worker poll/lease/heartbeat (`apps/worker`).
- Privileged Storage secret isolated from `WorkerSettings`.
- Scan/quarantine/promote path documented; ClamAV runbook exists **for file uploads**.
- Crawl policy + egress proxy; BM25 outbox; graph pointer switch; current_version atomicity.
- Governance deny-by-default **in the library**; index graph currently hardcodes scan-fresh flags (C-016).

## Live defects (re-inspected)

1. Website crawl enqueues hybrid_index with `review_approved: True` and no scan event (C-011).
2. Parser sandbox falls back to in-process in the worker (C-012). Staging worker has no Docker socket.
3. Heartbeat lease loss does not abort the graph; dead-letter UPDATE is not lease-conditional (C-015).
4. Index graph sets `scan_evidence_current=True` regardless of a scan row (C-016).
5. Embedding ledger is not a skip-cache (H-030).
6. No document-delete HTTP; Storage bytes remain (H-031, GAP-07-14).

## Unverified operational reality

| Topic | Status |
| --- | --- |
| 500 text pages / 100 OCR pages per hour | Not proven at launch hardware |
| BM25 p95 lag &lt; 5 min at 1M chunks | Seed only (p95 ~99s on tiny corpus) |
| Graph versions/hour | Unmeasured; envelope 15 |
| ClamAV signature freshness on staging | Not Run |
| Poison message / max attempts | Designed; soak unproven |
| Duplicate OpenAI spend on retry | Checkpoints intended; prove with usage rows |

## Production rules for ingestion

1. Keep real company files out until C-001.
2. Do not bulk-onboard graph.
3. Treat figures as `media_limitation` (R-10) — UI notice already in the product language.
4. Rebuild BM25 after restore; never treat ParadeDB as backup.
5. Worker replicas: leases must remain SKIP LOCKED; graph writer concurrency-one.

This review did not re-read every parser adapter. Residual parser CVEs belong in Trivy/image policy plus sandbox, not in "we parsed PDF once locally."
