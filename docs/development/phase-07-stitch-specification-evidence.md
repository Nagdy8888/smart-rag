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

## Packet 2 — Write copy-ready Stitch prompts, responsive LTR/RTL frames, Arabic/bidirectional behavior, information hierarchy, component inventory, localization decision, and design tokens

### Requirement (quoted)

> Write copy-ready Stitch prompts, responsive LTR/RTL frames,
> Arabic/bidirectional behavior, information hierarchy, component inventory,
> localization decision, and design tokens.

### Concrete acceptance checks

- Prompts are copy-ready and cover every canonical surface without mock
  behavior.
- LTR/RTL and mobile/desktop frames show equivalent task completion.
- Localization, direction, logical text-offset, typography, and overflow
  decisions are unambiguous.
- Components and tokens are reusable by Stitch references and the fallback
  system.
- Blur, Tailwind CDN, invented API fields, and graph-only answering are
  rejected.

### Files changed

| File | Action |
| --- | --- |
| `docs/frontend/STITCH_BRIEF.md` | Created — localization, tokens, prompts, frames, fixtures |
| `tests/unit/test_phase07_stitch_brief.py` | Created — brief honesty checks |
| `docs/frontend/API_UI_MAPPING.md` | Linked the brief |
| `docs/README.md` | Indexed the brief |
| `.cursor/plans/hybrid-graph-rag/07-phase-stitch-specification.md` | Packet 2 checkbox |

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_phase07_stitch_brief.py tests/unit/test_phase07_api_ui_mapping.py -q` | 0 (8 passed) |
| `uv run ruff check tests/unit/test_phase07_stitch_brief.py` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

### Localization / token decision

- Chrome: English. Content: `dir="auto"` + bidi isolate. Codes/URLs: `dir="ltr"`.
- One palette/radius/elevation/type/spacing set. Blur rejected.
- Arabic chrome blocked on GAP-07-19 (no locale on `GET /me`).

### Negative findings

- Prompts forbid posting a client route (GAP-07-01).
- XSS filename fixture is specified as escaped text.
- No DESIGN.md existed; tokens are defined here rather than silently mixed.

### Rollback

Delete `STITCH_BRIEF.md` and the brief unit test; unlink from the index.

## Packet 3 — Specify every loading, empty, error, permission, quarantine, quota, compatibility, limitation, fallback, partial-readiness, budget, and degraded state

### Requirement (quoted)

> Specify every loading, empty, error, permission, quarantine, quota,
> compatibility, limitation, fallback, partial-readiness, budget, and
> degraded state.

### Files changed

| File | Action |
| --- | --- |
| `docs/frontend/STITCH_STATES.md` | Created — per-surface matrix |
| `docs/frontend/STITCH_BRIEF.md` | Linked states as part of the brief |
| `tests/unit/test_phase07_stitch_states.py` | Coverage + negative leak checks |
| `docs/README.md` | Indexed states |
| Phase 7 wrapper | Packet 3 checkbox |

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_phase07_stitch_states.py tests/unit/test_phase07_stitch_brief.py -q` | 0 (7 passed) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

### Negative findings

- Graph-only answering is not a success state.
- ACL blindness reveals no unauthorized titles/counts.
- Auth-direct login is not FastAPI-throttled.
- Source preview, audit, budgets, settings, document delete remain GAPs.

### Rollback

Delete `STITCH_STATES.md` and its unit test; unlink from the brief.

## Packet 4 — Map each visible action and field to a real typed API/Auth contract; identify gaps instead of inventing mock behavior

### Requirement (quoted)

> Map each visible action and field to a real typed API/Auth contract;
> identify gaps instead of inventing mock behavior.

### Files changed

| File | Action |
| --- | --- |
| `docs/frontend/API_UI_MAPPING.md` | P07-04 visible control tables |
| `tests/unit/test_phase07_api_ui_mapping.py` | Bidirectional coverage assertions |
| Phase 7 wrapper | Packet 4 checkbox |

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_phase07_api_ui_mapping.py -q` | 0 (5 passed) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

### Negative mapping tests

Duplicate submit, resume after sequence, unknown SSE, 426, forged role,
unauthorized source, privileged keys, and internal traces are mapped to
denial or GAP rows. No mock endpoints added.

### Rollback

Revert the P07-04 section of `API_UI_MAPPING.md`.
