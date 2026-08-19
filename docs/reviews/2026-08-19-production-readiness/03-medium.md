---
title: Medium production-readiness findings
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: engineering, security, frontend
reviewed_commit: 09a102a
---

# Medium findings

Fix these in the hardening window. Unowned Medium is a Phase 10 stop per the external-assessment disposition rule; name an owner even if you defer.

Related: [high](./02-high.md) · [low](./04-low.md)

## PRD-M-001 — API binds `0.0.0.0` by default

- **Location:** `packages/core/src/smart_rag_core/settings/backend.py:54-55`, `apps/backend/Dockerfile:54`
- **Evidence:** `API_BIND_HOST` default `0.0.0.0`. Container CMD repeats it.
- **Impact:** Correct inside Docker. Dangerous if someone runs uvicorn on a laptop/EC2 public interface without Caddy. Rely on security groups, not bind address.
- **Remediation:** Staging user-data/Caddy only; document that host firewall must drop 8000. Optional: default bind `127.0.0.1` for non-container `APP_ENV=local`.

## PRD-M-002 — CORS defaults to local Next ports

- **Location:** `packages/core/src/smart_rag_core/settings/backend.py:111-115`
- **Evidence:** Default `CORS_ALLOW_ORIGINS` is `:3000` and `:3010` loopback. Wildcards are rejected (good).
- **Impact:** Forgetting to set the Vercel origin in production means the browser CORS-fails (fail closed for credentialed calls). Easy operational miss, not an open wildcard.
- **Remediation:** Production settings validator: `APP_ENV=production` requires HTTPS origins and rejects loopback.

## PRD-M-003 — `filter_invented_ids` keeps citations with `chunk_id is None`

- **Location:** `packages/core/src/smart_rag_core/query_answer/generate.py:100-104`
- **Evidence:** A citation survives if `chunk_id is None or chunk_id in chunks`. Deterministic check later requires a source (`deterministic.py` `_citation_ok`).
- **Impact:** Defense is layered, not single-point. If verify is skipped on a future branch, uncited IDs could stream.
- **Remediation:** Drop `chunk_id is None` unless `table_id` is in `table_ids`. Add a unit that fails if generate_answer_node is reordered.

## PRD-M-004 — Verifier covers at most six links; remainder omitted

- **Location:** `packages/core/src/smart_rag_core/query_answer/verifier.py:19-46`
- **Evidence:** By design, extra links are omitted from the model verifier. Deterministic filters still apply.
- **Impact:** Composite/multi-hop answers can have unverified tail links. Status may still be `complete` if those links were not marked unsupported.
- **Remediation:** If omitted IDs exist, force `partial` and surface `verifier_omitted_links` in SSE/UI.

## PRD-M-005 — Auth Admin CORS header list omits `X-Test-AAL`

- **Location:** `cors.py` vs `identity.py:23`
- **Evidence:** Identity accepts `X-Test-AAL`; CORS allow-headers does not list it.
- **Impact:** Test-only inconsistency. Production should remove all X-Test headers (H-003).

## PRD-M-006 — Graph neighborhood SVG is a grid of circles

- **Location:** `apps/frontend/src/components/graph-explorer.tsx:42-74`
- **Evidence:** Nodes placed on a 10-column grid; `title` is `object_id`. Caps at 80 nodes; list-first UX otherwise.
- **Impact:** Inspection works; users will not "see" relationships. Fine for a console, weak if GraphRAG is sold visually.
- **Remediation:** Keep list-first. If a real graph view is needed, bound hop/node caps (already 3 / 200) and render edges, not a circle grid.

## PRD-M-007 — Query cache TTL 30s still requires recheck (good) but visibility generation must move

- **Location:** `packages/core/src/smart_rag_core/retrieval/cache_store.py:34-35`, `cache_key.py:20-40`
- **Evidence:** Keys include `principal_scope_hash` and `visibility_generation`. Hits call recheck. TTL 30s.
- **Impact:** If visibility generation lags ACL downgrade, recheck is the real control. Confirm every ACL/delete increments generation; if not, 30s is residual risk mitigated by recheck.
- **Remediation:** Contract test: delete document, cache hit, recheck returns empty, no SSE citation.

## PRD-M-008 — Rate-limit skip when Valkey and Postgres are both unset

- **Location:** `apps/backend/src/smart_rag_api/middleware/preauth.py:75-77`
- **Evidence:** Documented as "unconfigured, not dual outage." Dual outage of **bound** backends fail-closes inside `check_auth_rate_limit`.
- **Impact:** A production process that failed settings load oddly could skip limits. Unlikely if startup validates DSNs.
- **Remediation:** Production settings require Valkey limits URL. Unconfigured must not listen on a public port.

## PRD-M-009 — Phase 6 evidence and plan index disagree with packet checkboxes

- **Location:** plan index todos vs `06-phase-agent-intelligence.md` packets `[x]` vs evidence `status: pending`
- **Impact:** Next model run may reload Phase 6 as unfinished and duplicate work, or skip remaining `Done when` items.
- **Remediation:** Close or explicitly uncheck. Same class as PRD-C-007, tracked here as the documentation half.

## PRD-M-010 — Stitch is a template; density/chrome may still feel like a developer console

- **Location:** `docs/frontend/PHASE8_JOURNEY_MATRIX.md:13-15`, chat-app module CSS `developer-app.module.css`
- **Impact:** Fine for an internal RAG tester. External users may read it as unfinished.
- **Remediation:** If the client is internal SMEs, accept. If external, budget a visual pass after RTL.

## PRD-M-011 — Backup restore + BM25 rebuild drill not proven on managed topology

- **Location:** runbooks `storage-db-reconciliation.md`, `bm25-rebuild.md`; Phase 9 local only
- **Impact:** RPO 24h / RTO 4h are unsigned operational hopes on `t3.micro`.
- **Remediation:** Staging drill: restore Supabase + Storage, rebuild ParadeDB, parity check, time the clock.

## PRD-M-012 — Cost ceilings USD 200 / USD 20 are signed but live OpenAI spend is mock

- **Location:** QT-COST-001/002; `MOCK_MODEL_MODE` default true
- **Impact:** Reserve-once accounting can be correct in SQL and still uncalibrated in dollars per query.
- **Remediation:** After live models, compare gateway usage rows to OpenAI dashboard for a week before raising traffic.

## PRD-M-013 — Historical citation reads skip ACL and current-version recheck

- **Location:** `supabase/migrations/20260816210000_query_memory_store_reaper_v1.sql:1129-1144`
- **Evidence:** `source_unavailable` is deleted-document or missing chunk only. No `caller_can_read_document`, no `current_version_id` match.
- **Impact:** After ACL downgrade or version flip, `GET /runs/{id}/citations` can still return `chunk_id` as available (no passage text).
- **Remediation:** Same recheck RPC as live evidence. Do not return `chunk_id` when recheck fails.
- **Production blocker:** no for a demo; yes for the “downgrade immediately exclude” invariant on this read path

## PRD-M-014 — Unauthenticated readiness names ParadeDB, Valkey, LightRAG

- **Location:** `apps/backend/src/smart_rag_api/services/readiness.py`; `apps/frontend/src/components/readiness-panel.tsx`
- **Impact:** Attackers learn private topology. No DSN leak.
- **Remediation:** Public probe `{status, query_ready}` only. Operator names behind auth.

## PRD-M-015 — ZIP declared-size bomb check; parser filename used as a path

- **Location:** `packages/core/src/smart_rag_core/ingestion/parser/archive.py`; `parser/sandbox/launcher.py`
- **Impact:** Lying ZIP headers and `filename=../…` assist sandbox escape if C-012 stays fail-open.
- **Remediation:** Stream-extract with a hard byte cap; fixed `input.bin` name; `docker kill` on timeout.

## PRD-M-016 — Invitation create returns `raw_token` in JSON

- **Location:** `apps/backend/src/smart_rag_api/routers/auth_team.py`
- **Impact:** Browser history, APM, and XSS can steal a 24h join token.
- **Remediation:** Deliver only via mail. Stop stuffing the token into Auth `data`.

## PRD-M-017 — Maintained docs exceed the 300-line split rule

- **Location:** `.cursor/rules/70-documentation-standards.mdc`; `docs/development/phase-06-agent-intelligence-evidence.md` (1259 lines); phase-05 (1154); phase-09 (1038); phase-04 (1035); phase-10 (935); `docs/frontend/API_UI_MAPPING.md` (400)
- **Evidence:** Eleven Markdown files under `docs/` (excluding `prev_review`) are ≥300 lines. Five are ≥800. They mix packets, quality, latency, and ops into one ledger per phase.
- **Impact:** Reviewers cannot verify a single `Done when` without reading a catch-all file. The rule forbids exactly this shape.
- **Remediation:** Split evidence by packet into `docs/development/phase-NN/` with a short index. Keep `API_UI_MAPPING.md` as generated tables or split by surface.

## PRD-M-018 — Docstring and TSDoc quality are not enforced, only Python presence

- **Location:** `tests/contract/docstring_scanner.py`; `apps/frontend/eslint.config.mjs`; `.cursor/rules/70-documentation-standards.mdc`
- **Evidence:** The AST scanner requires a non-empty docstring string. It does not require Args/Returns/Raises, LangGraph state sections, or side-effect notes. Frontend ESLint is `eslint-config-next` only — no TSDoc plugin, no exported-symbol scan.
- **Impact:** A one-word docstring satisfies CI. Ingestion graph nodes and new TS exports can drift from the written standard without a red build.
- **Remediation:** Extend the Python scanner for LangGraph node required headings. Add a TSDoc/AST check for exported functions in `apps/frontend/src/lib` and `components`. Do not weaken the presence gate.

## PRD-M-019 — Required-concern docs missing Mermaid

- **Location:** `docs/agent/QUERY_BUDGETS.md`; `docs/ingestion/CHUNKING_CONTRACT.md`; `docs/ingestion/INGESTION_LIMITS.md`; `docs/retrieval/BM25_PROJECTION_CONTRACT.md`; `docs/graph/GRAPH_MAPPING_CONTRACT.md`; `docs/security/OPENAI_DATA_GOVERNANCE.md`; `docs/deployment/STREAMING_TIMEOUTS.md`
- **Evidence:** `scripts/check_docs.py` validates Mermaid **kind** when a block exists; it does not require a block on architecture/auth/ingestion/retrieval/agent-routing/deployment docs. C4 files under `docs/architecture/` do have diagrams.
- **Impact:** Contracts that should show a flowchart or sequence are prose-only. Failure modes stay implicit.
- **Remediation:** Require one allowed Mermaid kind on those concern paths. Split dense diagrams; no theme colors.

## PRD-M-020 — Documentation index is a table, not a completeness gate

- **Location:** `docs/README.md`; `scripts/check_docs.py`
- **Evidence:** The index lists many documents with owner/status/last-reviewed. There is no test that every `docs/**/*.md` (except `prev_review`) appears, or that `status: draft` older than N days fails. Navigation is alphabetical, not C4 “read in this order.”
- **Impact:** New ADRs and packet evidence can land unlisted. Onboarding still starts at a 150-row table.
- **Remediation:** CI: fail if a maintained Markdown file is missing from `docs/README.md`. Add a short “read in this order” C4 section above the table. Keep the table.

## PRD-M-021 — `POST /graph/inspect` is unthrottled at FastAPI and pre-auth

- **Location:** `apps/backend/src/smart_rag_api/routers/graph_inspect.py:51-80`; `apps/backend/src/smart_rag_api/middleware/preauth.py:26-35`
- **Evidence:** Inspect depends on identity only. `GET /graph/entities/search` calls `enforce_rate_limit`. POST inspect does not. `_MUTATION_PREFIXES` omits `/graph`.
- **Impact:** Any member can hammer resolver/workspace SQL (10s deadline × concurrency) with no 429. Not an ACL bypass (resolver is ACL-filtered).
- **Remediation:** `enforce_rate_limit(..., COST_MUTATION or LOW_RISK_READ)` and add `/graph` to preauth mutations.

## PRD-M-022 — Document and conversation lists have no page bound

- **Location:** `apps/backend/src/smart_rag_api/services/documents_http.py:52-77`; `supabase/migrations/20260812135916_roles_rls_identity_v1.sql:163-226`
- **Evidence:** `list_visible_documents` and `list_user_conversations` return every visible row. HTTP wrappers `fetchall()` with no `LIMIT`.
- **Impact:** An owner/admin library or conversation rail can serialize the whole tenant on one GET. Fine at 8 docs; not at a real corpus.
- **Remediation:** Keyset pagination (`LIMIT` + `created_at, id`). Default page 50, max 200.

## PRD-M-023 — Query idempotency key is optional; the server mints a UUID

- **Location:** `apps/backend/src/smart_rag_api/routers/conversations.py:291-301`; `apps/backend/src/smart_rag_api/schemas/fastapi_security.py:93`
- **Evidence:** `SubmitMessageRequest.idempotency_key` may be `None`. Missing body and header keys become `uuid4()` per request.
- **Impact:** Double-submit without a client key admits two paid runs. Duplicate protection only works when the client remembers the key (the UI usually does).
- **Remediation:** Require `Idempotency-Key` or body key on paid POST. Reject missing keys with 400.

## PRD-M-024 — Crawl enqueue takes client `graph_eligible` and `content_class`

- **Location:** `apps/backend/src/smart_rag_api/services/crawl_enqueue.py:41-102`
- **Evidence:** Owner/admin RPC arguments include `content_class` and `graph_eligible` from the HTTP body after domain match. Members are rejected (good).
- **Impact:** An admin can mark a live host `synthetic` (weaker governance) or `graph_eligible=true` without a second reviewer. Matches single-step owner/admin approval, not dual-control.
- **Remediation:** Server-default `graph_eligible=false` and `content_class` from policy. Persist approval as a distinct admin action before enqueue.

## PRD-M-025 — Session JWT is stored in TanStack Query keys

- **Location:** `apps/frontend/src/lib/query-keys.ts:20-35`
- **Evidence:** `sessionQueryKeys(accessToken)` puts the Bearer token in `me`, `conversations`, `documents`, `usage`, and related keys.
- **Impact:** React Query persisters, DevTools, and error reporters can retain a live JWT. Cache isolation across users is the intended reason; a user id hash would suffice.
- **Remediation:** Key on `user_id` (or a hash of `sub`), never the raw access token. Keep Authorization on the fetch headers only.

## PRD-M-026 — Citation drawer always highlights the ACME fixture

- **Location:** `apps/frontend/src/components/chat-app.tsx:120-128`
- **Evidence:** Live `CitationDrawer` renders `CITATION_LOGICAL_FIXTURE_TEXT` (`الشركة ACME وقعت العقد.`) regardless of the selected citation. Copy admits the citations API has no offsets.
- **Impact:** Reviewers and users can believe the drawer shows the cited passage. It shows a synthetic highlight demo. Pairs with GAP-07-09 (no preview).
- **Remediation:** Remove the fixture from the production drawer, or gate it behind a “reviewer demo” flag. Show ids + provenance only until offsets exist.

## PRD-M-027 — `insufficient_evidence` from correction still fuses

- **Location:** `apps/agents/src/smart_rag_agents/query/graph.py:162-164`; `apps/agents/src/smart_rag_agents/query/nodes/pipeline.py:530-532`
- **Evidence:** After correction, `insufficient_evidence` sets detail `insufficient evidence; verified partial follows`. The correction→fuse router only ENDs on `admission_rejected` / `routing_rejected`. Docstring claims `insufficient_evidence` then END; the edge does not.
- **Impact:** Exhausted retrieval still spends fusion/answer/verifier budget. SSE can mislabel the terminal relative to the budget reason.
- **Remediation:** Route `insufficient_evidence` to END (or a scoped refuse node). Align the graph docstring with the edges.

## PRD-M-028 — API lifespan never starts the offload executor

- **Location:** `apps/backend/src/smart_rag_api/main.py:90`
- **Evidence:** `application.state.offload_executor = None`. Sync `psycopg.connect` and full-log rereads therefore run on the event loop (pairs with C-014).
- **Impact:** Under concurrent SSE, blocking DB calls stall heartbeats for every tenant on that process.
- **Remediation:** Start a bounded `ThreadPoolExecutor` in lifespan, or make the hot path async with asyncpg/psycopg async. Fail ready if the pool is required and missing.

## PRD-M-029 — Local worker Compose injects Storage Admin into the worker PID

- **Location:** `docker-compose.yml:234`; `tests/contract/test_privileged_secrets_absent.py`
- **Evidence:** Worker settings forbid a `storage_admin` field (good). Compose still sets `SUPABASE_STORAGE_ADMIN_SECRET` on the worker service for isolated loaders. Staging worker is the same pattern if that env is copied.
- **Impact:** Parser fail-open (C-012) then executes next to Storage Admin as well as the DB DSN.
- **Remediation:** Keep the secret off the worker task; pass it only into a dedicated scan/promote sidecar, or fail start if the parser sandbox is absent and this env is set.
