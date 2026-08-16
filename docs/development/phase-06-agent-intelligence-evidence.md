---
title: Phase 6 Agent intelligence evidence
owner: engineering-lead
status: pending
last-reviewed: 2026-08-16
audience: engineering, reviewers
phase: 6
---

# Phase 6 — Agent intelligence evidence

Canonical packet evidence for
[Phase 6](../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md).
Packet 1 created this file. Phase status remains `pending` until the wrapper
gate is proven and accepted. Packet 1 does not mark the phase complete.

Related: [QUERY_ADMISSION.md](../agent/QUERY_ADMISSION.md) ·
[QUERY_BUDGETS.md](../agent/QUERY_BUDGETS.md) ·
[QUALITY_TARGETS.md](../QUALITY_TARGETS.md) ·
[AUDIT_CHAIN.md](../security/AUDIT_CHAIN.md) ·
[docs index](../README.md)

## Prerequisites

| Prerequisite | Evidence |
| --- | --- |
| Phases 1–5 accepted | [phase-05-graphrag-evidence.md](./phase-05-graphrag-evidence.md) status `accepted` |
| JWT/profile `CallerContext` | `smart_rag_core.security.identity` plus FastAPI JWKS loader |
| Durable budgets | `app.budget_reservations` kinds were `ingestion_daily` / `graph_index` / `graph_maintenance` |
| Audit chain | `app.append_audit_event` / `app.authorize_restricted_read` |
| `Phase6RouteFamily` | `smart_rag_core.query_profile.phase6_map` |

## Packet 1 — authenticated idempotent run admission

### Quoted requirement

> Implement authenticated, idempotent run admission with server-derived
> database authorization, deadlines, recursion/model/tool ceilings, durable
> reservations, read-access auditing, and authorized runtime context.

### Acceptance checks restated

- Unauthorized, stale-role, revoked-session, cross-user run, deleted
  conversation, and over-budget requests create no paid run and receive no
  authorized runtime context.
- Concurrent sends with the same user/conversation/key converge on one run,
  one reservation, and one paid execution; authorized retries reconnect.
- Every route enforces its exact deadline, recursion, correction, subquestion,
  model-call, tool, discovery, manifest, and side-effect ceilings and
  terminates safely on exhaustion.
- All gateway calls consume one durable run reservation; immutable usage
  matches provider attempts including timeout-after-send; completion/crash
  reconciliation cannot overspend; consume SQL does not hot-relock shared
  budget rows.
- Restricted preview/download/evidence events are append-only, chained,
  content-minimized, and correlated to actor/version/run/citation/purpose.

### Inspected schema / APIs

| Item | Found |
| --- | --- |
| Latest prior migration | `20260816160000_bm25_reconcile_and_ineligible_pointer_v1.sql` |
| `runs_idempotency_key_uq` | global unique on `idempotency_key` where not null; retained |
| `budget_reservations_kind_allowed` | CHECK `ingestion_daily\|graph_index\|graph_maintenance` before this packet |
| `app_api` grants | SELECT on `conversations`; no runs/llm_usage DML |
| `validate_caller_context` | live role, disabled, `authorization_version` |
| Ingestion admission | `JobAdmissionService` uses `ingestion_daily` only; not mixed |
| Query graph | Phase 1 `unconfigured` scaffold, replaced by `enforce_admission` |
| `test_langgraph_config.py` | previously asserted `unconfigured`; updated |
| Pinned psycopg | `psycopg[binary]==3.3.3` |
| LangGraph | existing `langgraph` pin used by ingestion graph |

### Authorization matrix (admit)

| Case | Result |
| --- | --- |
| Disabled profile | `authorization_rejected`; no reservation |
| Forged/stale role vs `app.profiles.role` | `authorization_rejected` |
| Stale `authorization_version` | `authorization_rejected` |
| `revoked_sessions` row or profile-wide revoke | `session_revoked` |
| Foreign conversation | `conversation_forbidden` (creator-only send) |
| Deleted conversation | `conversation_deleted` |
| Monthly cap below envelope | `budget_exhausted` |
| Five pending/running unexpired runs | `concurrency_cap` |
| Same key, same payload hash | reconnect, no second reservation |
| Same key, different hash | `key_collision` |
| Client USD / Valkey / BM25 / cache | not RPC inputs; cannot enlarge or skip |

### Exact ceilings

See [QUERY_BUDGETS.md](../agent/QUERY_BUDGETS.md). Hybrid 25s/7/2.80;
Combined 45/8/3.20; StructuredTable 30/6/2.40; Composite 50/9/3.60;
inspection 10/3/0.75. `no_retrieval` / `scoped_refusal` use Hybrid 25s
(assumption: QUALITY_TARGETS has no sixth deadline).

### Constraint widening (not data-destructive)

`budget_reservations_kind_allowed` was replaced to add `query_run`.
`scripts/ci/check_migrations.py` now allows `ALTER TABLE ... DROP CONSTRAINT`
while still forbidding `DROP TABLE` / `DROP COLUMN`. Documented as additive
allowed-value widening.

### Files changed (Packet 1)

- `supabase/migrations/20260816170000_query_run_admission_v1.sql`
- `scripts/ci/check_migrations.py`
- `packages/core/src/smart_rag_core/query_admission/`
- `packages/core/src/smart_rag_core/generated/database.ts`
- `apps/backend/src/smart_rag_api/services/query_admission.py`
- `apps/agents/src/smart_rag_agents/query/graph.py`
- `tests/unit/test_query_admission_ceilings.py`
- `tests/unit/test_migration_policy.py`
- `tests/contract/test_query_run_admission.py`
- `tests/contract/test_langgraph_config.py`
- `docs/agent/QUERY_ADMISSION.md`
- `docs/agent/QUERY_BUDGETS.md`
- `docs/architecture/08-data-dictionary.md`
- `docs/architecture/03-components.md`
- `docs/QUALITY_TARGETS.md` (engineering-default subsection only)
- `docs/README.md`
- `docs/development/CONFIGURATION.md`
- `docs/security/AUDIT_CHAIN.md`
- `docs/security/AUTH_RATE_LIMIT_OWNERSHIP.md`
- `docs/development/phase-06-agent-intelligence-evidence.md`

No public chat/SSE router. No new environment variables. Wrapper packet
checkbox left unchecked. Phase status remains `pending`.

### Commands and results

Recorded after local apply on port **54322**. DSN passwords are not logged.
`pnpm exec supabase db reset` was **not** used.

| Command | Exit |
| --- | --- |
| `pnpm exec supabase status` | 0; DB URL `127.0.0.1:54322` (some sidecar services stopped) |
| `pnpm exec supabase migration up` | 0; applied `20260816160000_bm25_reconcile_and_ineligible_pointer_v1.sql` and `20260816170000_query_run_admission_v1.sql` |
| `pnpm exec supabase gen types typescript --db-url …54322… --schema app,public,storage,auth` written UTF-8 via Python (not PowerShell `>`) | 0; 202685 bytes; includes `admit_query_run`; `--local` still targets 5432 and was not used |
| `uv run ruff format` on changed Python paths | 0 |
| `uv run ruff check` on changed Python paths | 0 |
| `uv run python -m pyright` on changed Python paths | 0 errors |
| `uv run python scripts/ci/check_migrations.py` | 0 (47 reviewed files) |
| `uv run python -m pytest tests/unit/test_query_admission_ceilings.py tests/contract/test_query_run_admission.py tests/contract/test_langgraph_config.py tests/unit/test_package_imports.py tests/contract/test_import_boundaries.py tests/unit/test_migration_policy.py -q` | 0; **51 passed**, 0 failed, 0 skipped |

### Unique-key / concurrency traces

| Trace | Result |
| --- | --- |
| Same `(creator_user_id, conversation_id, idempotency_key)` + same payload hash | reconnect; one `app.runs` row; one `query_run` reservation |
| Same key + different payload hash | `key_collision`; still one run / one reservation |
| Two connections, same key, barrier | both commits succeed; identical `run_id` and `reservation_id` |
| Global `runs_idempotency_key_uq` | retained; not dropped |

### Reservation / usage ledgers

| Case | Ledger |
| --- | --- |
| Hybrid admit | `amount_usd=2.80`, `optimistic_version=1`, status `reserved` |
| Consume USD 0.40 at v1 | v2; remaining 2.40 |
| Consume at stale v1 | `optimistic_version_conflict` |
| Consume USD 99 at v2 | `reservation_exhausted` |
| Crash before `send` | no `llm_usage`; true-up `released` / committed 0 |
| Timeout-after-send | `llm_usage.timeout_after_send=true`, `cost_usd=0.40`, `usage_kind=answer` |
| True-up after sent attempt | `committed` 0.40 ≤ envelope 2.80 |
| Second true-up | `already_settled=true`; committed unchanged |
| Expiry reconciler | run `partial`; reservation released/committed 0 |
| `pg_get_functiondef(consume_query_reservation)` | no `company_settings`; no `FOR UPDATE` |
| Rate-limit 429 / limiter unavailable | zero `query_run` reservations |
| Restricted evidence | `restricted_read.authorized`; payload has `run_id`/`citation_id`/`version_id`; no passage text; `verify_audit_chain` null (ok) |

### Negative tests

Forged/stale JWT role, stale `authorization_version` (captured after the
profile `disabled_at` trigger bump), disabled user, revoked session, foreign
conversation, deleted conversation, key collision, duplicate concurrent
request, monthly over-budget, concurrency cap 5, optimistic-version conflict,
reservation exhaustion, crash before/after provider send, double true-up,
deadline/recursion/call/tool overrun helpers, direct audit/usage
insert/update/delete, client route/role/cache/BM25/Valkey mapping on the
graph. All fail closed.

### Deviations

- `no_retrieval` / `scoped_refusal` use the Hybrid 25s envelope. Not a signed
  sixth deadline.
- Per-call USD caps are engineering defaults, not signed QT rows.
- FastAPI query-admission limiter is 20 attempts / 60 seconds (engineering
  default). Packet 5 owns signed rate policy and router breadth.
- CHECK widening used `DROP CONSTRAINT` of a CHECK; CI regex was narrowed
  accordingly. Not `DROP COLUMN` / `DROP TABLE`.
- Monthly `query_run` reserved+committed spend is summed **company-wide**
  and compared to the caller's effective cap
  (`COALESCE(profile, company, 200)`). This is fail-closed for QT-COST-001
  and does not let a personal override ignore other users' query holds.
  Graph maintenance reservations are excluded.

### Rollback

Restore the database from the pre-packet snapshot or `supabase db reset` on
local only (destructive). Forward-fix is to keep the additive columns and
stop calling the new RPCs. Do not DROP the new columns in the same release.

### Packet 2 handoff

- `AuthorizedRuntimeContext` is required input to the query graph.
- Ceilings and remaining counters live on graph state after
  `enforce_admission`.
- Gateway counted calls must use `execute_counted_model_call` (or the RPCs)
  against the run-local reservation.
- Do not implement profiling/routing in packet 1 leftovers. Packet 2 owns
  rewrite, typed profiling, and the route matrix. Admission already reserved
  the family envelope passed by FastAPI; packet 2 must not treat client route
  as authorization.
- Heartbeat/true-up RPCs exist. Packet 7 owns checkpoint/event reaping.

### Unverified

- Hosted Supabase Auth throttling remains unproven locally
  (`local_auth_throttling_proven=False`). Packet 1 does not claim to throttle
  hosted Auth.
- Full-repo Pyright outside this packet's changed paths.
- `pnpm exec supabase gen types --local` still connects to port 5432; types
  were generated with `--db-url` to `127.0.0.1:54322` instead.
