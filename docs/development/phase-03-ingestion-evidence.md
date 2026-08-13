---
title: Phase 3 ingestion evidence
owner: engineering-lead
status: draft
last-reviewed: 2026-08-13
audience: engineering, reviewers
phase: 3
---

# Phase 3 — Ingestion evidence

Canonical packet evidence and exit record for [Phase 3](../../.cursor/plans/hybrid-graph-rag/03-phase-ingestion.md). Packet 1 creates this file; later packets append. Phase status remains `pending` until Packet 8 and explicit user acceptance.

Related: [OPENAI_DATA_GOVERNANCE.md](../security/OPENAI_DATA_GOVERNANCE.md) · [SUBPROCESSOR_GOVERNANCE.md](../security/SUBPROCESSOR_GOVERNANCE.md) · [docs index](../README.md)

## Prerequisites

| Prerequisite | Evidence |
| --- | --- |
| Phase 1 complete/accepted | [phase-01-foundation-evidence.md](./phase-01-foundation-evidence.md) status `accepted` |
| Phase 2 complete/accepted | [phase-02-identity-data-evidence.md](./phase-02-identity-data-evidence.md) status `accepted` |
| User mandate | Continue through Phase 5 (Cursor chat) |

## Packet 1 — external-processing governance sign-off

### Quoted requirement

> Finalize and sign the OpenAI/LangSmith/Supabase/Vercel external-processing governance packet before any real company content reaches an external processor.

### Acceptance checks restated

- Every provider/data flow has verified settings or an explicit blocker; no undocumented company-content path remains.
- Allowed/prohibited/review categories and deny-by-default decision are complete and versioned.
- Both governance documents contain named approver/date and reciprocal links; evidence records whether real content remains prohibited.
- No pipeline implementation or real-content external call in this packet.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `docs/security/OPENAI_DATA_GOVERNANCE.md` | OpenAI flows, categories, detectors, decision |
| `docs/security/SUBPROCESSOR_GOVERNANCE.md` | LangSmith, Supabase, Vercel matrices |
| `packages/core/src/smart_rag_core/security/external_processing.py` | Pure deny-by-default decision record |
| `scripts/check_docs.py` | Rejects claimed sign-off without approver/evidence |
| Phase 1/2 evidence | Prerequisite acceptance |

### Primary documentation sources (2026-08-13)

- OpenAI data controls: <https://developers.openai.com/api/docs/guides/your-data>
- OpenAI business data: <https://openai.com/business-data/>
- LangSmith retention: <https://docs.langchain.com/langsmith/usage-and-billing>
- LangSmith purging: <https://docs.langchain.com/langsmith/data-purging-compliance>
- LangSmith redaction: <https://docs.langchain.com/langsmith/mask-inputs-outputs>
- Supabase GDPR/residency: <https://supabase.com/docs/guides/security/gdpr-compliance>
- Supabase DPA: <https://supabase.com/legal/dpa>

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run pytest tests/unit/test_external_processing_governance.py tests/contract/test_governance_docs.py -q` | 0 (8 passed) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |
| `uv run pyright packages/core/src/smart_rag_core/security/external_processing.py` | 0 |
| `uv run ruff check` (touched Packet 1 paths) | 0 |

### Decision posture

| Item | Value |
| --- | --- |
| Approver | user (Cursor chat; Phase 1–5 mandate; no legal name provided) |
| Approval date | 2026-08-13 |
| Framework status | accepted |
| Real company content external processing | **prohibited** until provider matrix rows are `verified` |
| Pre-approval real-content external call | **none occurred** in Packet 1 |
| Fabricated DPA/ZDR/region claims | **none**; org rows marked `unverified` |

### Negative tests

| Fixture | Result |
| --- | --- |
| Missing attestation | deny (`missing_attestation`) |
| Expired approval | deny (`expired_approval`) |
| Contradictory category | deny (`contradictory_category`) |
| Positive detector | deny (`sensitive_detector`) |
| Unverified provider + real content | deny (`unverified_provider_settings`) |
| Frontmatter `signed` without approver | docs check error |

### Unverified assumptions

- Live OpenAI org ZDR/DPA/region console values.
- LangSmith workspace retention/DPA for the customer account.
- Managed Supabase project region/backup/DPA acceptance.
- Vercel team DPA/subprocessor acceptance.

### Rollback

Revert governance Markdown, `external_processing.py`, docs check, and this evidence section; restore draft stubs.

### Next-packet handoff

Packet 2 may implement leased jobs against Phase 2 schema. Real company content must not reach OpenAI/LangSmith/managed Supabase/Vercel covered flows until provider verification updates flip `real_company_content_external_processing` and the decision input `provider_settings_verified`.

## Packet 2 — durable leased jobs, checkpoints, admission, dead letters

### Quoted requirement

> Implement leased, idempotent, priority-aware jobs with heartbeat, reclaim, retry, backpressure, spend admission, and dead-letter handling.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `supabase/migrations/20260813170000_job_leases_ledger_claim_v1.sql` | lease_token, ledger, claim RPCs, grants |
| `packages/core/src/smart_rag_core/jobs/` | repositories, admission, backoff, ledger |
| `apps/worker/src/smart_rag_worker/` | poll/claim/heartbeat lifecycle |
| `apps/agents/src/smart_rag_agents/ingestion/graph.py` | lease validate + boundary probe |
| `docs/ingestion/INGESTION_LIMITS.md` | operational limits registry |
| `docs/ingestion/JOB_STATE_MACHINE.md` | Mermaid state machines |

### Checkpointer posture

`langgraph-checkpoint-postgres` is **not pinned** in the workspace lockfile. Phase 3 probe graph compiles **without** a Postgres checkpointer (in-memory compile only); Phase 2 `langgraph` schema placeholders remain migration-seeded with **no runtime auto-migrate**.

### Commands and results

| Command | Exit |
| --- | --- |
| `uv lock` + `uv sync --all-packages` | 0 |
| `pnpm exec supabase db reset --yes` | 0 |
| `uv run ruff format` / `ruff check` (touched Python) | 0 |
| `uv run pyright packages/core/src/smart_rag_core/jobs apps/worker/src apps/agents/.../ingestion/graph.py` | 0 |
| `uv run pytest tests/unit/test_job_backoff_admission.py tests/contract/test_job_leases.py tests/contract/test_langgraph_config.py -q` | 0 (16 passed) |
| `uv run python scripts/check.py --tier docs` | 0 |

### Crash / concurrency notes

- **SKIP LOCKED**: `test_skip_locked_claim_is_exclusive` uses two worker threads; only one receives a lease token.
- **Duplicate enqueue**: idempotency key returns existing row without duplicate budget reservation.
- **Ledger replay**: `ON CONFLICT` on `(job_table, job_id, operation_key)` prevents duplicate side effects.
- **Heartbeat/cancel**: cancellation clears processing lease; ledger RPC rejects stale tokens.
- **Dead-letter replay**: new `idempotency_key` with `replay_of_dead_letter_id` payload link; original DL row retained.
- **Graph-handoff pause**: claim RPC skips new `index` ops when pending index count > 50; `remove` still claims.

### Next-packet handoff

Packet 3 owns quarantine, ClamAV, category gate, Storage promotion saga, and admin alerts. Do not parse, scan, or embed in Packet 3 until quarantine promotion boundaries are proven.

## Packet checklist

1. [x] External-processing governance sign-off (this section)
2. [x] Durable leased jobs, checkpoints, admission, dead letters (this section)
3. [ ] Quarantine, ClamAV, governance hold, promotion saga, alerts
4. [ ] Approved bounded crawling through restricted proxy
5. [ ] Parser/OCR sandbox and typed format adapters
6. [ ] Chunking, deduplication, typed Parquet artifacts
7. [ ] Embeddings, BM25 projection, lifecycle, graph handoff
8. [ ] Adversarial, crash, throughput, and exit proof
