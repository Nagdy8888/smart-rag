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

Packet 4 owns approved bounded crawling through the restricted proxy. Do not enable parser/OCR/chunking/graph indexing in Packet 4 scope beyond crawl handoff interfaces.

## Packet 3 — quarantine, ClamAV, governance hold, promotion saga, alerts

### Quoted requirement

> Implement quota-bounded quarantine, orphan TTL cleanup, fresh-signature malware scanning, category approval, safe promotion, append-only provenance, and durable local admin alerts.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `supabase/migrations/20260813180000_quarantine_scan_promotion_v1.sql` | promotion saga, finalize RPC, scan columns |
| `packages/core/src/smart_rag_core/gateways/clamav.py` | INSTREAM client; PING health-only |
| `packages/core/src/smart_rag_core/gateways/storage.py` | download/copy/verify/delete gateway |
| `packages/core/src/smart_rag_core/ingestion/*` | scan, governance, promotion |
| `apps/agents/.../ingestion/scan_graph.py` | scan/promote graph nodes |
| `apps/worker/.../lifecycle.py` | routes `scan_promote` jobs |
| `apps/backend/.../upload_finalize.py` | finalize RPC wrapper |
| `docker-compose.yml` | pinned ClamAV service |
| `docs/runbooks/CLAMAV_SCAN_AND_PROMOTION.md` | ops runbook |

### ClamAV pin

| Item | Value |
| --- | --- |
| Image | `clamav/clamav:stable@sha256:78810772a92b4a9168115bc6b2e0ffd702640893b9577f8c3d0432762d2655c4` |
| License | GPL-2.0 (upstream ClamAV) |
| Engine | `stable` track (Alpine-based official image) |
| Signatures | persistent volume `clamav_db:/var/lib/clamav` + container entrypoint `freshclam` |
| Health | `clamdcheck.sh` (not scan readiness) |

Primary docs: <https://docs.clamav.net/manual/Installing/Docker.html>

### Commands and results

| Command | Exit |
| --- | --- |
| `docker pull clamav/clamav:stable` + inspect RepoDigests | 0 |
| `pnpm exec supabase db reset --yes` | 0 |
| `uv run ruff check` (touched Python) | 0 |
| `uv run pyright apps/agents/src/smart_rag_agents/ingestion/scan_graph.py` | 0 |
| `uv run pytest tests/unit/test_clamav_client.py tests/contract/test_clamav_scan.py tests/contract/test_promotion_saga.py tests/contract/test_upload_finalize.py tests/contract/test_quarantine_cleanup.py -q` | 0 (9 passed, 2 skipped — ClamAV not on host `127.0.0.1:3310`) |
| `uv run python scripts/check.py --tier docs` | 0 |

### Negative / crash tests

| Fixture | Result |
| --- | --- |
| EICAR | `infected` (contract when ClamAV reachable) |
| Oversize scan payload | `over_limit` without INSTREAM |
| Fake clean via `app_api` | blocked (Phase 2 trigger retained) |
| Promotion crash after each saga step | replay completes once (contract) |
| Cross-user finalize | denied |
| Orphan cleanup retry | idempotent (`test_quarantine_cleanup`) |

### Unverified assumptions

- Full end-to-end scan/promote against live Storage + ClamAV in one worker invocation (requires local stack secrets).
- Inbucket email delivery hook for every admin notification (durable DB rows implemented; SMTP bridge deferred to existing Phase 2 mail helpers).
- Archive-bomb and encrypted fixtures at real ClamAV boundary (Packet 8 matrix).

### Next-packet handoff

Packet 4 implements approved URL crawling through the restricted proxy only. Parser/OCR nodes remain unavailable; promoted objects may reach `parsing` status but must not claim Hybrid/graph readiness.

## Packet 4 — approved bounded crawling through restricted proxy

### Quoted requirement

> Implement approved-URL crawling only through the restricted proxy with redirect, DNS, peer-IP, scope, byte, page, and time bounds.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `infra/crawl-proxy/server.py` | POST `/fetch`, peer pin, bounded decode |
| `infra/crawl-proxy/requirements.txt` | `brotli==1.1.0` |
| `packages/core/src/smart_rag_core/ingestion/crawl/*` | policy, DNS, robots, adapter |
| `packages/core/src/smart_rag_core/gateways/crawl_proxy.py` | proxy client (httpx 0.28.1) |
| `packages/core/src/smart_rag_core/repositories/crawl.py` | runs/snapshots/events |
| `apps/agents/.../ingestion/crawl_graph.py` | crawl graph nodes |
| `apps/worker/.../lifecycle.py` | `website_crawl` job routing |
| `supabase/migrations/20260813190000_crawl_snapshots_provenance_v1.sql` | schema + approval RPC |
| `docker-compose.yml` | `egress` network; crawl-proxy dual-homed |
| `docs/ingestion/CRAWL_POLICY.md` | policy + sequence diagram |
| `docs/runbooks/CRAWL_EGRESS_AND_PROXY.md` | ops runbook |

### Library / RFC verification

| Capability | Pin / source |
| --- | --- |
| URL parsing | Python 3.11 `urllib.parse` |
| DNS | `socket.getaddrinfo` + `ipaddress` |
| HTTP client (core→proxy) | `httpx==0.28.1` (no auto-redirect to origin) |
| Proxy fetch | stdlib `socket`/`ssl` pinned connect |
| robots.txt | Python 3.11 `urllib.robotparser` (RFC 9309) |
| Decompression bounds | gzip/zlib/brotli 1.1.0 in proxy image |

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run ruff check packages/core/src/smart_rag_core/ingestion/crawl packages/core/src/smart_rag_core/gateways/crawl_proxy.py infra/crawl-proxy/server.py tests/unit/test_crawl_policy.py tests/unit/test_crawl_proxy.py tests/contract/test_crawl_ssrf.py` | pending |
| `uv run pytest tests/unit/test_crawl_policy.py tests/unit/test_crawl_proxy.py tests/contract/test_crawl_ssrf.py tests/contract/test_compose_topology.py -q` | pending |
| `uv run python scripts/check.py --tier docs` | pending |

### Negative fixture matrix (unit + contract)

| Fixture | Expected |
| --- | --- |
| localhost / 127.0.0.1 / ::1 | fail closed |
| private / link-local / metadata / CGNAT | fail closed |
| decimal / octal / hex IP literals | fail closed |
| mixed DNS answers | fail closed |
| userinfo / fragment / disallowed port | fail closed |
| redirect loop / redirect-to-private | fail closed |
| robots disallow | fail closed |
| decompression ratio bomb | fail closed |
| proxy bypass (non-/fetch POST) | 403 |
| worker on egress network | absent |
| missing peer_ip in proxy response | CrawlProxyError |

### Unverified assumptions

- End-to-end `website_crawl` job against live public fixture through Compose egress network (requires stack rebuild).
- Full Storage upload of snapshots in integrated worker run (gateway implemented; live secrets required).
- Parser sandbox egress denial (Packet 5 owns parser network namespace).

### Next-packet handoff

Packet 5 implements no-network parser/OCR isolation and typed format adapters. Crawl snapshots in `web-snapshots` are inputs; do not implement chunking, embeddings, or Hybrid readiness in Packet 5 until parser contracts pass.

## Packet checklist

1. [x] External-processing governance sign-off (this section)
2. [x] Durable leased jobs, checkpoints, admission, dead letters (this section)
3. [x] Quarantine, ClamAV, governance hold, promotion saga, alerts
4. [x] Approved bounded crawling through restricted proxy
5. [ ] Parser/OCR sandbox and typed format adapters
6. [ ] Chunking, deduplication, typed Parquet artifacts
7. [ ] Embeddings, BM25 projection, lifecycle, graph handoff
8. [ ] Adversarial, crash, throughput, and exit proof
