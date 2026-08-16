---
title: Phase 7 Stitch specification evidence
owner: engineering-lead
status: draft
last-reviewed: 2026-08-17
audience: engineering, reviewers, client-approver
---

# Phase 7 — Stitch specification evidence

Canonical packet evidence for
[Phase 7](../../.cursor/plans/hybrid-graph-rag/07-phase-stitch-specification.md).
Do not check a packet from file presence alone.

## Packet 1 — Inventory real Phase 6 API, Auth, streaming, route-diagnostic, document, graph, tool, usage, and administration contracts

### Requirement (quoted)

> Inventory real Phase 6 API, Auth, streaming, route-diagnostic, document,
> graph, tool, usage, and administration contracts.

### Concrete acceptance checks

- Inventory is traceable to repository files or generated contracts, not plan
  inference.
- Auth-provider-direct operations are distinguished from FastAPI-owned
  operations.
- API compatibility, paid-work admission, ordered SSE resume, cancellation,
  diagnostics, source access, and role enforcement are covered.
- Every canonical screen family has verified inputs or an explicit gap.
- Reject UI fields without a typed owner; reject client-only authorization,
  privileged browser credentials, unverified BM25/graph text, raw internal
  errors, and claims that FastAPI throttles browser-direct Auth.

### Inspected sources

| Source | Version / proof |
| --- | --- |
| `docs/api/openapi.foundation.json` | 43 paths; `scripts/ci/check_openapi.py` allow-list |
| `apps/backend/src/smart_rag_api/main.py` | Router mount list |
| `apps/backend/src/smart_rag_api/schemas/fastapi_security.py` | HTTP models |
| `apps/backend/src/smart_rag_api/schemas/ingestion_status.py` | Status + BM25/graph handoff |
| `apps/backend/src/smart_rag_api/schemas/graph_inspect.py` | Inspect caps |
| `apps/backend/src/smart_rag_api/schemas/ingestion_crawl.py` | Crawl enqueue |
| `apps/backend/src/smart_rag_api/schemas/glossary.py` | Glossary import |
| `apps/backend/src/smart_rag_api/schemas/entity_rules.py` | Entity-rule CRUD |
| `packages/core/src/smart_rag_core/sse/catalog.py` | 16 event types, 15s heartbeat |
| `packages/core/src/smart_rag_core/feedback/tags.py` | 10 unmerged tags |
| `packages/core/src/smart_rag_core/schema/enums.py` | Document/job status |
| `packages/core/src/smart_rag_core/retrieval/graph.py` | `GraphLimitationCode` |
| `apps/frontend/src/lib/{types,api,limitations,client-version}.ts` | Thin UI types |
| `apps/frontend/src/components/developer-app.tsx` | Actual screens |
| `docs/frontend/THIN_DEVELOPER_UI.md` | Packet 8 console contract |
| `docs/api/{SSE,FASTAPI_SECURITY}.md` | Transport/security |
| `docs/security/AUTH_RATE_LIMIT_OWNERSHIP.md` | Auth vs FastAPI throttle |
| `supabase/config.toml` | signup, TOTP, Google `enabled=false` |
| `apps/backend/src/smart_rag_api/auth_admin/{mfa_recovery,bootstrap}.py` | Services, no routers |
| Phase 6 wrapper | Packets 1–8 checked; wrapper status still pending user accept |

### Files changed

| File | Action |
| --- | --- |
| `docs/frontend/API_UI_MAPPING.md` | Created — inventory, screen families, gap register |
| `docs/frontend/api-ui-inventory.json` | Created — machine lock of paths/SSE/gaps |
| `tests/unit/test_phase07_api_ui_mapping.py` | Created — snapshot/catalog/markdown coverage |
| `docs/development/phase-07-stitch-specification-evidence.md` | Created — this file |
| `docs/README.md` | Linked mapping + evidence |
| `docs/frontend/THIN_DEVELOPER_UI.md` | Reciprocal mapping link |
| `.cursor/plans/hybrid-graph-rag/07-phase-stitch-specification.md` | Packet 1 checkbox after proof |

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_phase07_api_ui_mapping.py -q` | 0 (4 passed) |
| `uv run python scripts/ci/check_openapi.py` | 0 (snapshot matches) |
| `uv run ruff check tests/unit/test_phase07_api_ui_mapping.py` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (107 markdown files) |

### Negative findings

- No invented FastAPI paths (`/budgets`, `/audit`, preview/download).
- FastAPI does not throttle `signInWithPassword` / OAuth / MFA / reset.
- Citations have no passage text; source drawer has no HTTP owner (GAP-07-09).
- Manual route override is absent from `SubmitMessageRequest` (GAP-07-01).
- SSE catalog has no profile/rewrite/candidate/BM25-byte/rerank/inference
  payloads (GAP-07-02).
- MFA recovery, owner bootstrap, company settings, audit list, document
  delete, and budget policy have no public HTTP routes.

### Unverified

- Phase 6 wrapper user acceptance (packets are checked; status pending).
- Hosted Auth throttling (Phase 10).
- CloudFront `signed_url` (Phase 10; local null).
- Live Stitch generation (packets 2–6).

### Phase 8 handoff impact

Phase 8 may implement UI for every inventoried FastAPI/Auth contract. Screens
tied to GAP-07-07, GAP-07-08, GAP-07-09, GAP-07-11, GAP-07-12, GAP-07-13,
GAP-07-14 remain blocked or honest-unavailable until the owning phase ships
HTTP. Do not mock them.

### Rollback

Delete the new frontend mapping/inventory/test/evidence rows and revert the
docs-index and thin-UI links.
