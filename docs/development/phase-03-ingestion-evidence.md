---
title: Phase 3 ingestion evidence
owner: engineering-lead
status: pending
last-reviewed: 2026-08-14
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
| `uv run ruff check packages/core/src/smart_rag_core/ingestion/crawl infra/crawl-proxy/server.py tests/unit/test_crawl_policy.py tests/unit/test_crawl_proxy.py tests/contract/test_crawl_ssrf.py` | 0 |
| `uv run pytest tests/unit/test_crawl_policy.py tests/unit/test_crawl_proxy.py tests/contract/test_crawl_ssrf.py tests/contract/test_compose_topology.py -q` | 0 (40 passed) |
| `uv run python scripts/check.py --tier docs` | 0 |

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

## Packet 5 — parser/OCR sandbox and typed format adapters

### Quoted requirement

> Implement no-network parser/OCR isolation and typed format adapters with deterministic cleaning, format-specific source locators, and explicit media-only figure/chart diagnostics.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `packages/core/src/smart_rag_core/ingestion/parser/` | typed contracts, adapters, cleaning, sandbox launcher |
| `packages/core/src/smart_rag_core/ingestion/governance.py` | extracted-text detectors + `decide_external_processing` |
| `apps/agents/.../ingestion/parse_graph.py` | parse + govern graph nodes |
| `infra/parser-sandbox/` | immutable no-network parser image + runner |
| `docs/adr/ADR-parser-isolation.md` | shared-kernel blast radius + upgrade triggers |
| `docs/ingestion/INGESTION_LIMITS.md` | parser/OCR resource bounds + license matrix |

### Library / license matrix

| Library | Pin | License | Selected for |
| --- | --- | --- | --- |
| PyMuPDF | 1.25.5 | AGPL-3.0 | PDF text/boxes + scanned render |
| python-docx | 1.1.2 | MIT | DOCX logical block/table paths |
| python-pptx | 1.0.2 | MIT | PPTX slides/shapes/reading-order |
| openpyxl | 3.1.5 | MIT | XLSX typed cells/formulas/cache state |
| beautifulsoup4 + lxml | 4.13.3 / 5.3.1 | MIT / BSD | HTML boilerplate cleaning |
| markdown-it-py | 3.0.0 | MIT | Markdown token/line spans |
| pytesseract + Tesseract | 0.3.13 / distro | Apache-2.0 | OCR boxes/confidence |
| Pillow | 11.1.0 | HPND | OCR image buffers |

Adversarial comparison rejected ad-hoc `pdfplumber`/unpinned OCR stacks due to weaker box fidelity (PDF), non-deterministic HTML recovery, and missing OOXML structure coverage relative to the pinned set above.

### Commands and results

| Command | Exit |
| --- | --- |
| `uv lock` + `uv sync --all-packages` | 0 |
| `uv run ruff check packages/core/src/smart_rag_core/ingestion/parser apps/agents/src/smart_rag_agents/ingestion/parse_graph.py tests/unit/test_parser_*.py tests/contract/test_parser_sandbox.py tests/fixtures/parser` | 0 |
| `uv run pyright packages/core/src/smart_rag_core/ingestion/parser/types.py packages/core/src/smart_rag_core/ingestion/parser/service.py packages/core/src/smart_rag_core/ingestion/parser/sandbox/launcher.py packages/core/src/smart_rag_core/ingestion/governance.py apps/agents/src/smart_rag_agents/ingestion/parse_graph.py` | 0 |
| `uv run pytest tests/unit/test_parser_adapters.py tests/unit/test_parser_governance.py tests/unit/test_parser_sandbox.py tests/contract/test_parser_sandbox.py -q` | 0 (20 passed, 1 skipped — parser image not built) |
| `uv run python scripts/check.py --tier docs` | 0 |
| `docker compose --profile parser-build build parser-sandbox` | not run (optional local proof) |

### Negative / bounded fixtures

| Fixture | Expected |
| --- | --- |
| Oversize input bytes | `failed`, zero elements |
| Hash mismatch | `failed`, no promotion |
| Positive extracted secret detector | promotion denied |
| PDF repeated header/footer | removal diagnostics |
| HTML nav/cookie boilerplate | removed + diagnostics |
| XLSX formula cell | formula text preserved, not recalculated |
| PPTX slide/text | slide break + reading-order locator |
| Encrypted PDF/workbook | `encrypted` / `failed` bounded |
| Docker `--network none` proof | contract skip when image not built |

### Unverified assumptions

- End-to-end `parse` job through worker + Storage download on live Compose stack.
- Real Docker Desktop `--network none` run with built `smart-rag-parser-sandbox:local` image (contract test skips when image absent).
- Full OCR Arabic/English quality on scanned PDF production fixtures (Tesseract present in image; local unit tests tolerate missing binary).

### Next-packet handoff (Packet 6)

- Consume `ParseResult.elements` with stable `element_id`, format-specific locators, `media_only`, removal/coverage diagnostics, and version hashes (`parser_v1`, `cleaning_v1`).
- Do not re-parse from raw bytes in Packet 6; chunking reads typed element trees only.
- Parquet/table artifact schema must preserve XLSX/CSV typed metadata already emitted by parser adapters.

## Packet 6 — chunking, deduplication, and typed Parquet artifacts

### Implemented

- `packages/core/src/smart_rag_core/ingestion/chunking/` — hierarchical builder, tokenizer (`cl100k_base_v1`), stable UUID5 IDs, exact/near dedup (`dedup_v1`), metrics.
- `packages/core/src/smart_rag_core/ingestion/tables/` — Arrow schema (`table_parquet_v1`), Parquet I/O, manifests, Storage path helper, DuckDB read-only sandbox contract.
- Final [CHUNKING_CONTRACT.md](../ingestion/CHUNKING_CONTRACT.md) and Arrow/Parquet pins in [INGESTION_LIMITS.md](../ingestion/INGESTION_LIMITS.md).

### Policy versions

| Component | Version |
| --- | --- |
| Chunking | `chunking_v1` |
| Tokenizer | `cl100k_base_v1` |
| Dedup | `dedup_v1` |
| Table schema | `table_parquet_v1` |

### Measured fuzzy dedup (fixtures)

| Metric | Value | Gate |
| --- | --- | --- |
| Precision | 1.000 | ≥ 0.99 |
| Recall | 0.500 | ≥ 0.85 |
| Mode | `exact_only` | fuzzy disabled; exact SHA-256 only |

### Commands and results

| Command | Exit |
| --- | --- |
| `uv lock` + `uv sync --all-packages` | 0 |
| `uv run ruff check packages/core/src/smart_rag_core/ingestion/chunking packages/core/src/smart_rag_core/ingestion/tables tests/unit/test_chunking_*.py tests/unit/test_table_parquet.py tests/contract/test_duckdb_parquet_sandbox.py` | 0 |
| `uv run pytest tests/unit/test_chunking_service.py tests/unit/test_chunking_dedup.py tests/unit/test_table_parquet.py tests/contract/test_duckdb_parquet_sandbox.py -q` | 0 (17 passed) |

### Negative / bounded fixtures

| Fixture | Expected |
| --- | --- |
| Mid-row/code split without exception | code atomic; table row chunks |
| Duplicate prose separated by code | representative + `duplicate_of_chunk_id` |
| XLSX formula cell | formula string preserved in Parquet |
| CSV duplicate headers | unique column names + original header manifest |
| DuckDB ATTACH/COPY/URL/traversal | blocked by sandbox validator |

### Unverified assumptions

- Live Supabase `table-artifacts` upload/hash verify through worker graph node (Storage gateway helper implemented; end-to-end job not run).
- Production-scale fuzzy dedup corpus beyond labeled fixture pairs.

### Next-packet handoff (Packet 7)

- Consume `ChunkingResult.chunks` with stable IDs, provenance, parent links, and dedup representatives.
- Use `table_artifacts` manifests/paths for canonical `document_tables` rows; no re-chunking from raw bytes.
- Wire governed embeddings + BM25 projection only after external-processing approval and budget reservation (Packet 7 scope).

## Packet checklist

1. [x] External-processing governance sign-off (this section)
2. [x] Durable leased jobs, checkpoints, admission, dead letters (this section)
3. [x] Quarantine, ClamAV, governance hold, promotion saga, alerts
4. [x] Approved bounded crawling through restricted proxy
5. [x] Parser/OCR sandbox and typed format adapters
6. [x] Chunking, deduplication, typed Parquet artifacts
7. [x] Embeddings, BM25 projection, lifecycle, graph handoff
8. [x] Adversarial, crash, throughput, and exit proof

## Packet 7 — embeddings, BM25 projection, Hybrid lifecycle, graph handoff, status APIs

### Implemented

- `packages/core/src/smart_rag_core/ingestion/embeddings/` — contextual input, mock/policy vectors, governed batch service with durable ledger.
- `packages/core/src/smart_rag_core/gateways/embedding.py` — shared `EmbeddingGateway` (mock-only until provider settings verified).
- `packages/core/src/smart_rag_core/ingestion/canonical/repository.py` — transactional canonical chunk/term/table writes + BM25 outbox enqueue.
- `packages/core/src/smart_rag_core/retrieval/bm25_indexer.py` — core `Bm25Indexer` ParadeDB writer adapter.
- `packages/core/src/smart_rag_core/retrieval/bm25_verifier.py` — cross-system row/hash/sample-query verification.
- `packages/core/src/smart_rag_core/ingestion/bm25_projection.py` — worker projection service + Hybrid Ready finalization RPC.
- `apps/agents/src/smart_rag_agents/ingestion/index_graph.py` — parse/chunk/embed/persist indexing graph (`hybrid_index` job kind).
- `apps/worker/src/smart_rag_worker/bm25_runner.py` — leased BM25 job loop with heartbeat.
- `apps/backend/src/smart_rag_api/routers/ingestion_status.py` — lifecycle/diagnostics + role-scoped retry.
- `supabase/migrations/20260813200000_hybrid_embedding_lifecycle_v1.sql` — embedding ledger, lifecycle RPCs, graph handoff idempotency.

### Policy pins

| Component | Pin |
| --- | --- |
| Embedding model | `text-embedding-3-large` @ 1024 dims |
| Contextual policy | `contextual_v1` |
| BM25 schema | `bm25_v1` |
| Graph pipeline handoff | `graph_pipeline_v1` / `lightrag_v1` |

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run ruff check packages/core/src/smart_rag_core/ingestion/embeddings packages/core/src/smart_rag_core/retrieval apps/agents/src/smart_rag_agents/ingestion/index_graph.py apps/worker/src/smart_rag_worker/bm25_runner.py apps/backend/src/smart_rag_api/routers/ingestion_status.py tests/unit/test_embedding_service.py tests/unit/test_phase3_graph_scope_guard.py tests/unit/test_ingestion_status_openapi.py` | 0 |
| `uv run pytest tests/unit/test_embedding_service.py tests/unit/test_phase3_graph_scope_guard.py tests/unit/test_ingestion_status_openapi.py -q` | 0 (6 passed) |
| `uv run pytest tests/contract/test_hybrid_lifecycle.py -q` | 0 (3 passed, 1 skipped without PARADEDB_URL) |

### Negative / scope guards

| Fixture | Expected |
| --- | --- |
| Real company content without verified provider settings | embedding gate denies (`unverified_provider_settings`) |
| Duplicate graph handoff replay | one `lightrag_index_jobs` row |
| Phase 3 repo search for Graph Ready / mapping writes | fails guard test |
| Unauthorized retry | HTTP 403 for member role |

### Unverified assumptions

- End-to-end `hybrid_index` job on live Storage object through verified Hybrid Ready (requires local stack + synthetic fixture upload path).
- Real OpenAI embedding adapter (blocked until provider matrix verified; mock gateway only).

### Next-packet handoff (Packet 8)

- Full adversarial/crash matrix across scan→embed→BM25→handoff with real ClamAV/Storage/Postgres/ParadeDB boundaries.
- Throughput/lag measurement to signed 500 text / 100 OCR pages/hour gates.
- Apply migration on local Supabase before integration contracts.

## Packet 8 — adversarial, crash, throughput, and exit proof

### Quoted requirement

> Exercise positive, failure, authorization, idempotency, crash-recovery, resource-limit, malware, sensitive-data, and SSRF fixtures; complete Phase 3 exit proof without new product features.

### Acceptance checks restated

- Immutable fixture manifest covers required categories with source/license/hash (or explicit null hash), sensitivity, external-processing mode, and owning tests.
- Crash matrix maps plan crash points to owning evidence; live-stack crash injections remain explicit pending blockers.
- Owning unit/contract suite exits 0; real-boundary skips are named (Postgres/ClamAV/Docker/ParadeDB), not mocked as pass.
- Throughput report is honest: local parse→chunk→mock-embed measured; Hybrid Ready + OCR gates `not_run` / unmet without approved capacity change → phase remains `pending`.
- Every Phase 3 `Done when` clause mapped; managed/production-only gaps listed; explicit user acceptance requested before status `complete` or Phase 4.

### Implemented / corrected

| Path | Role |
| --- | --- |
| `tests/fixtures/phase3/FIXTURE_MANIFEST.json` | Immutable 35-row fixture registry (`manifest_sha256` pinned) |
| `tests/fixtures/phase3/__init__.py` | Load + canonical digest helpers |
| `tests/contract/test_phase3_fixture_manifest.py` | Manifest integrity, categories, AST owning-test resolve |
| `tests/contract/test_phase3_crash_matrix.py` | Proven vs pending E2E crash-point registry |
| `scripts/phase3_throughput_benchmark.py` | Bounded local throughput probe (exit `2` when Hybrid Ready not measured) |
| `tests/unit/test_ingestion_status_openapi.py` | Member retry forbidden (403) |
| `packages/core/.../tables/__init__.py`, `crawl/__init__.py` | Break circular imports for suite/benchmark importability |

### Fixture coverage

Categories present: `format`, `malware`, `governance`, `sensitive_data`, `ssrf`, `authorization`, `idempotency`, `crash_recovery`, `resource_limit` (35 fixtures). PDF/OOXML hashes may be `null` when generator metadata is non-deterministic; structure asserted in owning tests. EICAR digest pinned to canonical `275a021b…`.

### Crash matrix

- Proven (owning tests exist): SKIP LOCKED exclusivity, heartbeat/lease-loss cancel, invalid lease denial, dead-letter replay, promotion saga crash points, duplicate enqueue, graph handoff idempotency, deletion ACL exclusion, parser oversize fail-closed, governance detector block, embedding real-content deny.
- Pending live E2E (explicit): Storage mid-download crash, scan mid-crash, parser kill timeout, LangGraph checkpoint interrupt, canonical mid-batch rollback, embedding timeout after provider success, BM25 mid-batch before verify, Hybrid Ready flip before BM25 verify.

### Commands and results

| Command | Exit | Notes |
| --- | --- | --- |
| `uv run ruff check` (Packet 8 paths) | 0 | |
| `uv run pyright` (touched package inits) | 0 | |
| `uv run pytest` (manifest + crash matrix + all owning modules) | 0 | 131 passed, 18 skipped (local Supabase `54322`, ClamAV, Docker, or ParadeDB unavailable); 0 failed |
| `uv run python scripts/phase3_throughput_benchmark.py --iterations 10` | 2 | Local text parse→chunk→mock-embed ~1.26e6 pages/hour on host; `hybrid_ready_gate=not_run`; OCR gate `null` |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 | |

### Done when mapping (Phase 3)

| Done-when theme | Evidence | Posture |
| --- | --- | --- |
| Governance packet signed; real company content blocked | Packet 1 evidence; `OPENAI_DATA_GOVERNANCE.md` / `SUBPROCESSOR_GOVERNANCE.md`; external-processing tests | Proven (real content still prohibited) |
| RLS upload, MFA/category/URL approval, quarantine quota/TTL, promotion saga, provenance | Packets 2–3 owning tests + manifest auth/idempotency/crash rows | Proven in code/tests; live Postgres skips when stack down |
| Anomaly → local admin notifications | Packet 3 evidence | Proven in prior packet |
| Malware/stale/oversize/sensitive/SSRF/egress fail-closed | Manifest malware/sensitive/ssrf + ClamAV/crawl/governance owning tests | Proven unit/policy; live ClamAV/proxy skips when unavailable |
| Leased SKIP LOCKED, heartbeat, dead-letter, admission | Packet 2 + crash matrix | Proven; live DB skips when stack down |
| Parser sandbox + format/chunk matrix | Packets 5–6 + format fixtures | Proven inprocess; Docker sandbox skip when Docker unavailable |
| Hybrid Ready only after BM25 verify; Graph Pending/Ineligible only | Packet 7 + lifecycle/scope guards | Proven; no Graph Ready in Phase 3 |
| Deletion/ACL immediate exclusion + BM25 cleanup | Packet 7 hybrid lifecycle tests | Proven (ParadeDB delete may skip without URL) |
| Signed 500 text / 100 OCR pages/hour through Hybrid Ready | Throughput script | **Not proven** — Hybrid Ready E2E + OCR not measured; phase stays pending |
| Status APIs for ingestion/review/retry/BM25/handoff | Packet 7 OpenAPI + member 403 | Proven |

### Managed / production-only gaps

- Managed Supabase / Vercel / LangSmith / OpenAI provider matrix verification before real company content.
- Live Compose: ClamAV freshclam <24h, Storage promotion, worker leases, ParadeDB projection lag/cost on launch hardware.
- Full mid-pipeline crash injection on live stack (pending crash points above).
- OCR pages/hour on parser-sandbox + Tesseract path.

### Deviations / rollback

- Deviation: Packet 8 does not claim Hybrid Ready or OCR throughput gates; exits pending with blockers rather than inventing rates.
- Deviation: PDF fixture hash left `null` due to PyMuPDF metadata nondeterminism.
- Rollback: revert Packet 8 commit; restore prior package `__init__` imports if needed; no schema migrations in this packet.

### Phase status

- Phase wrapper `status`: remains `pending`.
- Packet 8 checkbox: checked after this evidence; **does not** mean phase complete.
- **User acceptance required** before marking Phase 3 `complete` or starting Phase 4.

### Explicit acceptance request

Please review this Packet 8 exit record and reply with acceptance or required blockers. Until accepted, Phase 3 stays pending and Phase 4 must not begin.
