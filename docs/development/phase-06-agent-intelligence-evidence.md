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
[QUERY_ROUTING.md](../agent/QUERY_ROUTING.md) ·
[COMBINED_FUSION.md](../agent/COMBINED_FUSION.md) ·
[ANSWER_VERIFICATION.md](../agent/ANSWER_VERIFICATION.md) ·
[OPTIONAL_TOOLS.md](../agent/OPTIONAL_TOOLS.md) ·
[SSE.md](../api/SSE.md) ·
[STREAMING_TIMEOUTS.md](../deployment/STREAMING_TIMEOUTS.md) ·
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

## Packet 2 — memory, rewrite, profiling, route matrix, one correction

### Quoted requirement

> Implement memory rewrite, extended typed profiling, the complete
> deterministic route/limitation matrix, one global correction, and bounded
> parallel branches.

Packet 1 (`54f70c5`) is the input authority. This packet does not mark
Phase 6 complete and does not check the wrapper packet checkbox.

### Acceptance checks restated

- One typed `QueryPreparation` contains every required field. Model-assisted
  rewrite plus profile uses at most one counted `usage_kind=profile` call
  and preserves intent/entities against the original.
- Every listed route, limitation, refusal, comparison, mixed, and Composite
  case is deterministic, authorization-preserving, and clamped to the
  reserved packet 1 envelope (`requested_route` vs `effective_route` vs
  `corrected_route`).
- Whole-document claims require `section_coverage_ratio=1.0`. Provisional
  coverage remains frozen `0.65`. Phase 6 does not retune either.
- Multi-part work is at most three subquestions/rewrites, branch concurrency
  2, one global correction total, no hidden catalog or LightRAG keyword
  call, and verified partial/insufficient evidence on exhaustion.
- Historical relationships stay Hybrid with `temporal_graph_limitation`.
  Graph-only remains inspection. Negation/media/`NoRetrieval` cannot escape
  their evidence/limitation boundaries.

### Inspected schema / APIs consumed (not retuned)

| Item | Found |
| --- | --- |
| Latest prior migration | `20260816170000_query_run_admission_v1.sql` |
| This packet migration | `20260816180000_query_memory_routing_v1.sql` |
| Summary store / LangGraph store | none; packet 7 owns store |
| `conversations` summary column | none; last **12** messages only |
| `profile_query` / `extract_deterministic` | Phase 4; reused |
| `map_query_type_to_phase6_family` | Phase 4/5; extended by packet 2 matrix |
| `COVERAGE_SCORE_BASELINE` | `0.65` in `frozen_profile.py`; all `QueryClass` thresholds 0.65 |
| `HybridRetriever.retrieve` | sync; profile + caller + deadline |
| `GraphRetriever.retrieve_*` | async; **precomputed** keywords required |
| `structured_table_query` / `TableQueryPlan` | Phase 4; invoked directly |
| `execute_counted_model_call` | packet 1; prep uses `usage_kind=profile` |
| Timezone | UTC (`QT-TZ-001`); no signed company TZ |
| `QueryType` | not extended; `graph_inspection` / `no_retrieval` are `Phase6Extension` |

### Schema added

`app.load_query_memory(caller_user_id, caller_role, caller_authorization_version, p_conversation_id, p_limit default 12)`:

- `SECURITY DEFINER`, `search_path = pg_catalog, app`
- `validate_caller_context` first
- creator-only (owner/admin audit SELECT does not authorize another thread)
- deleted conversation raises `query_memory:conversation_deleted`
- `left(content, 1500)`, newest-first, limit 1–12
- `REVOKE` from `PUBLIC`/`anon`/`authenticated`; `GRANT EXECUTE` to `app_api` only
- never joins source documents

No new `runs` routing columns. Routing diagnostics live on graph state for
packet 3.

### Graph wiring

`enforce_admission` → `load_memory` → `prepare_query` → `compile_plan` →
`execute_branches` → `apply_correction` → END. No answer node. No Combined
fusion, ablation, or verifier.

Envelope vs Auto: packet 1 reserves the family envelope before profiling.
The planner never enlarges remaining ceilings. A client Combined request
cannot expand a Hybrid reservation (`envelope_cannot_enlarge`). Normal Auto
chat **should** reserve `composite` (50s / 9 calls / 5 tools); that wiring
is documented for packet 5 routers, not implemented here.

### Preparation

1. Untrusted input safety (NUL strip, 2000-character bound).
2. Deterministic extract via `extract_deterministic` / `profile_query_sync`
   — **zero** model calls for simple profiles.
3. When rewrite+profile need a model: **one** `execute_counted_model_call`
   with `usage_kind=profile`. `forbid_separate_rewrite_call` always fails.
4. Intent/entity fidelity vs original; original remains fallback variant.
5. `QueryPreparation` includes original, optional rewrite, `ExpectedProfile`,
   language, UTC temporal intent, hl/ll keywords, entities/aliases, exact
   terms, dates/numbers/filters, negation, document/section/page scope, media
   intent, historical and low-confidence relationship signals, decomposition
   (≤3), confidence, `model_calls` 0|1, fallback reason.

JSON graph-state round-trip coerces strict Phase 4 `ProfileField.provenance`
strings back to `FieldProvenance` without changing the Phase 4 schema.

### Route matrix fixtures (unit)

| Query | Effective family | Required kinds | Limitations |
| --- | --- | --- | --- |
| `What is the status of INV-SR-1001?` | Hybrid | hybrid | — |
| `Define the Orion widget alias policy date.` | Hybrid | hybrid | — |
| `Which team owns INV-SR-1001 related to procurement?` | Combined | hybrid + graph_local | — |
| `Which team owns the widget after the handoff as of 2020-01-01?` | Hybrid | hybrid | `temporal_graph_limitation` |
| `Summarize ordinary safety themes.` | Hybrid | hybrid | — |
| `What is the corpus-wide landscape of safety themes?` | Combined | hybrid + graph_global_steering | `global_steering_only` |
| `Summarize document p4-src-0001` | Hybrid | hybrid | `whole_document_section_coverage` |
| same with `section_coverage_ratio=0.5` | ScopedRefusal | scoped_refusal | `section_coverage_below_1` |
| `What is not allowed for INV-SR-1001?` | Hybrid | hybrid | `negation_unscoped`; `prove_complement=false` |
| `Describe the unlabeled chart in the figure` | ScopedRefusal | scoped_refusal | `media_limitation` |
| caption/OCR media language | Hybrid | hybrid | media answer allowed |
| `Compare PRJ-ALPHA leave days and notice period.` | Hybrid | hybrid | — |
| `Compare INV-SR-1001 policy and sum the Q1 sheet` | Composite | hybrid + structured_table | — |
| `sum the Q1 sheet totals` | StructuredTable | structured_table | — |
| `Inspect the current graph workspace` | GraphInspection | graph_inspection | `graph_inspection_only` |
| `Hello` / rewrite-this-paragraph | NoRetrieval | no_retrieval | `no_retrieval`; company claim forbidden |
| `maybe related to INV-SR-1001` | Hybrid | hybrid | `low_confidence_relationship` (signal retained) |

### Correction traces

| Case | Result |
| --- | --- |
| coverage 0.40 + retained current relationship + Composite envelope | one `hybrid_to_combined`; reuses Hybrid ranked IDs; remaining_corrections=0 |
| coverage 0.20 without relationship | one `same_route_retry` |
| already_applied | `correction_loop` |
| `refuse_second_correction(True)` | `second_correction` |
| remaining_corrections=0 and weak coverage | `insufficient_evidence` |
| historical relationship | never `hybrid_to_combined`; no graph branch added |
| holdout override 0.40 | `holdout_driven_threshold_change` |
| coverage 0.90 | no correction spent |
| Hybrid reservation + Combined matrix | clamp to Hybrid; `envelope_cannot_enlarge` |
| Hybrid reservation + relationship correction | escalation blocked (`escalation_envelope_blocked` → insufficient evidence) |

### Branch / limitation negatives

| Negative | Result |
| --- | --- |
| separate rewrite call | `separate_rewrite_call` |
| profile schema omission | `ValidationError` / `profile_schema_omission` |
| original-query loss | `original_query_loss` |
| production manual override | `production_manual_override` |
| fourth subquestion | `ValidationError` / `fourth_subquestion` |
| `branch_concurrency=8` | `branch_fan_out` |
| historical graph path at execute | `historical_graph_path` |
| empty hl or ll keywords on bound graph retrieve | `empty_keywords` (never extract) |
| hidden keyword extract counter | `hidden_keyword_call` |
| unauthorized ACL blindness | count suppressed (`None`) |
| graph-only as answer (`graph_as_answer_forbidden=False`) | `ValidationError` |
| NoRetrieval company claim | `ValidationError` |
| unproved complement | `ValidationError` |
| coverage_threshold 0.40 / section_coverage 0.65 | `holdout_driven_threshold_change` |
| unbound Combined | Hybrid degrade + `graph_unavailable`; `graph_prose_used=false` |
| BM25 snippets | `bm25_snippets_used=false` always |

### Call counts and counters

| Counter | Proven value |
| --- | --- |
| deterministic prep `model_calls` | 0 |
| force_model rewrite+profile | 1; `app.llm_usage.usage_kind=profile`; no `rewrite` kind |
| `keyword_extract_count` | 0 on every branch and LangGraph invoke |
| `catalog_llm_call_count` | 0 on every plan and invoke |
| query-graph import | no sockets / no OpenAI (`test_package_imports.py`) |

### Decomposition and parallelism

- `SUBQUESTION_CEILING=3` (`MAX_SUBQUESTIONS`)
- `BRANCH_CONCURRENCY=2`
- Independent required branches run via `ThreadPoolExecutor(max_workers=2)`
- Citation lookup is ID resolution only (after Hybrid IDs)
- Memory: last 12 creator messages as `<<untrusted-memory>>` records

### Contract traces (local Postgres 54322)

| Case | Result |
| --- | --- |
| creator memory load | 2 delimited records; no source documents |
| owner stranger on another user's thread | `conversation_forbidden` |
| deleted conversation | `conversation_deleted` |
| counted prep | one `profile` usage row for the admitted run |
| `Hello` branches | inherit `run_id` and `reservation_id`; keyword/catalog counters 0; `company_claim=false` |
| LangGraph empty query | `routing_rejected` / `empty_query` |
| LangGraph `INV-SR-1001` with Hybrid envelope | `correction_applied` or `insufficient_evidence`; `effective_route=hybrid`; no answer key |

### Commands and results

Recorded after local apply on port **54322**. DSN passwords are not logged.
`pnpm exec supabase db reset` was **not** used.

| Command | Exit |
| --- | --- |
| `pnpm exec supabase status` | 0; DB URL `127.0.0.1:54322` (some sidecar services stopped) |
| `pnpm exec supabase migration up` | 0; applied `20260816180000_query_memory_routing_v1.sql` |
| `pnpm.cmd exec supabase gen types typescript --db-url …54322… --schema app,public,storage,auth` written UTF-8 via Python (not PowerShell `>`) | 0; 203057 bytes; includes `load_query_memory`; `--local` still targets 5432 and was not used |
| `uv run ruff format` on changed Python paths | 0 |
| `uv run ruff check` on changed Python paths | 0 |
| `uv run python -m pyright` on changed Python paths | 0 errors |
| `uv run python scripts/ci/check_migrations.py` | 0 (48 reviewed files) |
| `uv run python -m pytest tests/unit/test_query_routing_matrix.py tests/unit/test_query_correction.py tests/contract/test_query_preparation.py tests/contract/test_langgraph_config.py tests/unit/test_package_imports.py tests/contract/test_import_boundaries.py -q` | 0; **66 passed**, 0 failed, 0 skipped |

### Deviations

- Auto composite reservation is documented, not wired in FastAPI (packet 5
  owns routers). The planner clamps to the reserved envelope.
- `no_retrieval` / `scoped_refusal` still use the Hybrid 25s envelope
  (packet 1). Not a signed sixth deadline.
- Prep uses existing SQL CHECK value `profile`, not a new combined usage
  kind.
- Routing diagnostics are graph-state-only; no new `runs` columns.
- Memory is last 12 messages; no summary store (packet 7).
- Unbound retrievers degrade (`retrievers_unbound` / `graph_unavailable`);
  not fake success. LangGraph compile/invoke tests run without Hybrid/graph
  bindings, so coverage is `None` and the one correction is not spent.
- Frozen `ProfileField` is `strict=True`; packet 2 adds JSON coerce helpers
  rather than loosening Phase 4 types.

### Rollback

Forward-fix: stop calling `app.load_query_memory` and skip the new graph
nodes. Do not `DROP FUNCTION` in the same release. Local-only
`supabase db reset` is destructive.

### Packet 3 handoff (from packet 2)

Packet 3 implemented fusion, tables, one answer, and the verifier below.
SSE, optional catalog, and UI remain later packets.

### Unverified (packet 2 residual)

- Hosted Supabase Auth throttling remains unproven.
- Live Hybrid/LightRAG/table retrieve against populated corpora (branches
  used fakes or unbound adapters in unit tests).
- FastAPI Auto→composite reservation wiring (packet 5).

## Packet 3 — Combined fusion, table composition, answer, verifier

### Quoted requirement

> Implement resolved-path Combined fusion and ablation, deterministic table
> composition, canonical answer evidence, inference-link citations, and
> layered verification.

### Acceptance checks restated

- Resolved paths contribute only authorized current canonical passages;
  table outputs identify exact deterministic source cells/ranges; graph
  prose/BM25 snippets never reach answer evidence.
- Formulas, `0.25` hop penalty, `1.20` edge-support multiplier cap, RRF
  denominator `60`, graph weight `0.50`, agreement cap `1.10`, and 40%
  graph-discovered-only cap are exact, deterministic, and fixture-tested.
- Fusion beats naive union on answer/path success and citation
  completeness within gates **or is removed** in favor of documented union.
- On disjoint relationship/multi-hop evaluation, Combined answer path
  improves success by ≥10 percentage points over Hybrid alone while
  preserving citation correctness/completeness, faithfulness, cost
  ceilings; first token ≤10s and completion ≤35s p95 **if measurable**.
- One answer call and at most one small verifier call covering ≤6 material
  links; unsupported links omitted/refused, not softened.

### Inspected schema / APIs

| Item | Found |
| --- | --- |
| Latest migration | `20260816180000_query_memory_routing_v1.sql` (no Packet 3 SQL) |
| `app.citations.provenance` | jsonb already present; expand-only payload, no new column |
| `GRAPH_SURVIVAL_FALLBACK_THRESHOLD` | `0.50` in `retrieval/graph.py` |
| `FINAL_EVIDENCE_MAX` / `DOCUMENT_QUOTA` | `12` / `2` from Phase 4 Hybrid |
| `RRF_K` | `60` |
| Usage kinds `answer` / `verifier` | already in `query_admission.ceilings` |
| Pinned OpenAI | `openai==2.26.0`; Responses `json_schema`, `store=False`, `max_retries=0` |
| Prompt hashes | LF-normalized SHA-256 of `answer_v1.md` / `verifier_v1.md` |

### Fusion vs union decision

Selected algorithm: **`resolved_path_fusion`**.

Development/qualification fixtures (synthetic authorized IDs, holdout
sealed):

| Case | Hybrid success | Union success | Fusion success |
| --- | --- | --- | --- |
| refund-period | true | true | true |
| project-atlas-product | false | false | true |
| atlas-to-supplier-multihop | false | false | true |

| Metric | Value |
| --- | --- |
| Hybrid success rate | `1/3` |
| Union success rate | `1/3` |
| Fusion success rate | `1` |
| Fusion citation completeness | `1` |
| Union citation completeness | `1/3` |
| Combined minus Hybrid (synthetic pp) | `66.67` |
| `fusion_beats_union` | true |
| Live QT-EVAL-009 +10pp | **unverified** |
| First token ≤10s / completion ≤35s p95 | **unverified** |

Fusion beat naive union because gold relationship/multi-hop chunks sat at
Hybrid ranks 15–20 (outside the frozen 12-unit cap) and resolved graph
support promoted them via Combined RRF plus the `1.10` agreement
multiplier. Union kept Hybrid-first order and dropped those gold IDs.
This synthetic gain is **not** QT-EVAL-009. It does not use CoverageSlice
floors, Phase 4 identity-rerank percents, or holdout labels.

Config hash is `6fadc2a7b98e47cc00c09590d8a6d196e2554fe3eb971052d058e08d0128164f`
(`fusion_config_hash(resolved_path_fusion)`). Tests assert it matches
`SELECTED_FUSION_ALGORITHM`.

### Representative contracts

| Contract | Result |
| --- | --- |
| Refund-period fact | Hybrid evidence only |
| Project Atlas product relationships | Combined with resolved canonical support |
| Atlas-to-Supplier multi-hop | Combined inference citations; conclusion need not be verbatim |
| LightRAG timeout | `requested_route=combined`, `effective_route=hybrid`, `graph_timeout` |
| Numeric comparison | Deterministic table ranges; prose math fails closed |
| Unsupported link | Removed/refused, chain dropped |

### Negative tests

Unmapped/stale/deleted/unauthorized path, missing edge support, native
prose, BM25 snippet, graph-only answer, hidden keyword call, hidden
LightRAG `answer_generate`, model fusion weight, agreement multiplier
above `1.10`, graph-only share above 40%, table arithmetic from prose,
seventh verifier link, verifier loop, second answer generation, unsupported
chain, conclusion-verbatim not required, LightRAG timeout mislabeled
Combined, and holdout-tuned configuration all fail closed.

### Graph wiring

`apply_correction` → `fuse_evidence` → `compose_tables` →
`generate_answer` → `verify_answer` → END.

Unbound Hybrid `INV-SR-1001` invoke: empty evidence, one refused/partial
answer payload, `answer_call_count=0`, `verifier_call_count=0`,
`keyword_extract_count=0`, `catalog_llm_call_count=0`. Compile constructs
no sockets or OpenAI.

### Commands and results

Recorded on Windows PowerShell. DSN passwords are not logged.

| Command | Exit |
| --- | --- |
| `uv run ruff format` on changed Python paths | 0 |
| `uv run ruff check` on changed Python paths | 0 |
| `uv run python -m pyright` on changed Python paths | 0 errors |
| `uv run python -m pytest tests/unit/test_combined_fusion.py tests/unit/test_answer_verifier.py tests/contract/test_langgraph_config.py tests/unit/test_package_imports.py tests/contract/test_import_boundaries.py` | 0; **48 passed**, 5 warnings (SwigPy worker import), 0 failed |
| `uv run python scripts/ci/check_migrations.py` | 0 (48 reviewed files; no Packet 3 SQL) |

### Deviations

- No new SQL migration. Fusion scores and inference flags live in existing
  `app.citations.provenance` jsonb.
- Live Combined vs Hybrid +10pp on labeled relationship/multi-hop cases
  with live mapping/extraction was **not** measured. Residual gate for
  phase exit.
- Latency p95 (first token ≤10s, completion ≤35s) was **not** measured.
- Naive union was **not** shipped; resolved-path fusion beat union on the
  measurable development fixtures above.
- SSE, optional tool catalog, and UI are out of scope (packets 4–8).
- Persist-to-Postgres citation insert is implemented but not live-database
  tested in this packet.

### Rollback

Forward-fix: skip `fuse_evidence` / answer / verifier nodes and stop
writing fusion keys into `app.citations.provenance`. No DROP. No new
migration to revert.

### Packet 4 handoff

- Optional tool registry and progressive disclosure. Core Hybrid,
  LightRAG, StructuredTable, citation, answer, and verifier tools stay
  **outside** the catalog.
- Packet 3 already binds those core tools directly on the query graph.
- Discovery remains at most one round and three optional manifests.
- Unselected optional schemas must never enter prompts.
- SSE, reconnect, heartbeats, and UI remain later packets.
- Keep `keyword_extract_count=0` and `catalog_llm_call_count=0` on the
  core path. A catalog LLM is only for optional discovery after
  role/feature filtering.
- Auto admit should still reserve `composite` so Combined and
  Hybrid→Combined escalation fit the envelope.

### Unverified (packet 3)

- QT-EVAL-009 live Combined vs Hybrid +10pp on labeled
  relationship/multi-hop cases with live mapping/extraction.
- Combined first-token ≤10s and completion ≤35s p95.
- Live OpenAI answer/verifier Responses calls (mock mode only).
- Live `app.citations` insert against Postgres.
- Hosted Auth throttling (carried from packet 1).

## Packet 4 — optional-tool registry and progressive disclosure

### Quoted requirement

> Implement the optional-tool registry/disclosure contract while keeping
> core retrieval and verification outside catalog discovery.

### Acceptance checks restated

- Core retrieval/answer/verification call paths incur zero catalog-search
  model rounds and expose no optional schema unless the typed request
  requires it.
- Level 0–3 payloads are bounded and permission-filtered; only selected
  manifests/guidance enter the next call; executor reauthorization cannot
  be bypassed by the planner.
- One discovery round, three optional manifests, route tool ceilings
  (4, or 5 Composite), one side-effecting tool, and byte/token/chunk/
  summary/input budgets are enforced.
- ≥20-tool fixture proves zero unrelated schema leakage and either
  justified selection improvement **or** documented deterministic mapping
  fallback.
- Arbitrary MCP execution is absent; metadata import alone cannot
  authorize or bind a remote tool.

### Inspected pins / APIs

| Item | Found |
| --- | --- |
| `langgraph` | `1.2.11` in `apps/agents/pyproject.toml` |
| `langchain-core` | `1.5.4` transitive in `uv.lock` |
| `langchain.agents` middleware | **absent** (no top-level `langchain` agents package) |
| Query graph | `StateGraph` in `apps/agents/src/smart_rag_agents/query/graph.py`, not `create_agent` |
| Current docs | [Dynamic tool selection](https://docs.langchain.com/oss/python/langchain/tools#dynamic-tool-selection) (`wrap_model_call` + `request.override(tools=...)`) apply to unpinned `langchain.agents` |
| `BaseChatModel.bind_tools` | Raises `NotImplementedError` on the fake chat model; `Runnable.bind(tools=...)` returns a **new** runnable |
| Latest app migration | `20260816180000_query_memory_routing_v1.sql` (no Packet 4 SQL) |
| Existing catalog tables | `app.tool_catalog` / `tool_versions` / `tool_permissions` / `tool_usage_events` from `20260812135100_tools_catalog_v1.sql` |
| Registry version | `optional_tools_v1` in-code allow-list (runtime authority) |
| L0 prompt | `optional_catalog_v1.md` |

### Binding approach (pin-compatible equivalent)

Pinned middleware cannot use `langchain.agents` `wrap_model_call`. The
packet stop (“stop if pinned middleware cannot bind only the next call”)
does **not** fire: `langchain-core` `Runnable.bind(tools=...)` binds
selected schemas onto a **new** runnable for that invocation. The original
chat model is not mutated, so the following call does not receive
unselected schemas. Wrapper:
`smart_rag_agents.query.nodes.binding.bind_selected_tools_next_call`.
Contract: `test_bind_tools_next_call_does_not_leak_unselected_schemas`.

Core (`smart_rag_core`) defines no LangGraph nodes and does not import
langgraph/langchain.

### Registry / role matrix

23 allow-listed tools. Forbidden core keys are absent:
`hybrid_retrieve`, `lightrag_retrieve`, `graph_retrieve`,
`structured_table_query`, `citation_lookup`, `source_lookup`, `answer`,
`verifier`, `answer_generate`, `verify_answer`.

Catalog holds **export format** cards, member helpers, admin/owner
administration fixtures, disabled connectors, an MCP metadata fixture,
a stale ODS export, and an oversized-guidance admin fixture.

| Role | Visible count | Notes |
| --- | --- | --- |
| viewer | 1 (`viewer_help_card`) | No export/admin names or counts |
| member | 11 | export + feedback; no admin |
| admin | 18 | no owner-only `admin_budget_adjust` |
| owner | 19 | still hides disabled/undiscoverable MCP/connectors/stale ODS |

Hidden/disabled tools contribute **neither names nor counts**.

### Disclosure sizes (member, query `export this table`)

| Level | Bytes | Tokens (cl100k) | Content |
| --- | --- | --- | --- |
| L0 | 497 | 105 | capabilities + safety rules; no catalog names |
| L1 | 886 | 199 | top-5 export cards after role filter |
| L2 (`export_csv` only) | 1515 | 367 | selected schema/examples/policy |
| L3 (+ CSV guidance) | 1660 | 400 | bounded operational section |

Prompt capture: L2 for `export_csv` does **not** contain `invite_email`,
`admin_user_invite`, `structured_table_query`, or `"const":"xlsx"`.
`xlsx` may appear on L1 cards (visible export ranking) but the unselected
XLSX **schema** does not enter the selected manifest.

### ≥20-tool comparison (10 cases)

Measured by `compare_discovery_vs_mapping()` against the 23-tool catalog.

| Metric | Deterministic mapping | Catalog discovery |
| --- | --- | --- |
| Accuracy | `0.80` (8/10) | `0.70` (7/10) |
| Accuracy gain | — | **−10.0 pp** |
| Latency | `0.08 ms` | `9.04 ms` |
| Tokens in selection payload | `12` | `3099` (ratio ≫ 2.0) |

Thresholds: retain discovery only if gain ≥ **10 pp** and token ratio ≤
**2.0**. Discovery failed both. Runtime policy:
`SelectionPolicy.DETERMINISTIC_MAPPING`. Unjustified discovery retained
in runtime fails with `unjustified_discovery_retained`.

Discovery latency is recorded on `OptionalTelemetry.discovery_latency_ms`
and is **not** mixed with Hybrid/LightRAG retrieval latency. Core Hybrid
path skips optional selection (`optional_selection_mode=skipped`), so
catalog discovery latency is zero there.

### Graph wiring

`compose_tables` → `disclose_optional_tools` → `generate_answer` →
`verify_answer` → END.

Table-plus-export: `structured_table_query` remains packet 3 deterministic
composition; catalog loads one export manifest; executor rechecks table
IDs, format, live role, quotas, and idempotency. Viewers never see
member/admin cards.

Hybrid `INV-SR-1001` invoke: `catalog_llm_call_count=0`,
`keyword_extract_count=0`, `optional_selection_mode` skipped. Answer and
verifier nodes preserve the catalog counter (they do not call the
catalog).

### Negative tests

Unauthorized card/name/count leakage, core-tool catalog membership,
fourth manifest, second discovery, unselected schema in prompt, stale/
disabled manifest, role change after planning, argument/quota/table-id
violation, oversized guidance, over-budget model input, second side
effect, arbitrary MCP target, metadata-import-cannot-bind, and
unjustified discovery retained in runtime all fail closed. Core path
zero catalog rounds. Next-call bind does not leak unselected schemas
onto the original model.

### Commands and results

Recorded on Windows PowerShell. DSN passwords are not logged.

| Command | Exit |
| --- | --- |
| `uv run ruff format` on changed Python paths | 0 |
| `uv run ruff check` on changed Python paths | 0 |
| `uv run python -m pyright` on changed Python paths | 0 errors |
| `uv run python -m pytest tests/unit/test_optional_tools.py tests/unit/test_optional_tools_discovery.py tests/contract/test_langgraph_config.py tests/unit/test_package_imports.py tests/contract/test_import_boundaries.py -q` | 0; **40 passed**, 5 warnings (SwigPy worker import), 0 failed |
| `uv run python scripts/ci/check_migrations.py` | 0 (48 reviewed files; no Packet 4 SQL) |

### Deviations

- No new SQL migration. v1 authority is the in-code `optional_tools_v1`
  registry plus live role from `CallerContext` /
  `AuthorizedRuntimeContext`. Existing `app.tool_catalog` rows are
  expand-ready for a later admin UI seed, not runtime authorization.
- Catalog LLM is **not** a new `llm_usage` kind. Runtime mapping spends
  zero catalog model rounds. `force_discovery` is test-only.
- `langchain.agents` dynamic-tool middleware is **not** added. The
  StateGraph `Runnable.bind(tools=...)` equivalent is documented in
  [OPTIONAL_TOOLS.md](../agent/OPTIONAL_TOOLS.md).
- `smart_rag_core.gateways` model exports are lazy so
  `from smart_rag_core.gateways.storage import StorageGateway` does not
  import `query_answer` while `query_admission.ceilings` is still loading.
- SSE, FastAPI catalog admin UI, and the testing UI remain later packets.

### Rollback

Forward-fix: skip `disclose_optional_tools` (wire `compose_tables` →
`generate_answer`) and stop binding optional schemas. No DROP. No new
migration to revert. Restore eager `gateways` model imports only after
breaking the ceilings ↔ routing cycle another way.

### Packet 5 handoff

- Thin FastAPI routers/services, Supabase-Auth/FastAPI rate ownership,
  authorization-safe retrieval caching, endpoint-specific authorization,
  CPU offload, and prompt/data isolation.
- Tools endpoints (catalog search / admin create/version/enable/
  permission) must not treat DB seed as authority unless they recheck the
  same live role + in-code allow-list (or an additive catalog expansion
  that preserves executor reauthorization).
- Auto admit should still reserve `composite` so Combined and
  Hybrid→Combined escalation fit the envelope.
- Keep `keyword_extract_count=0` and `catalog_llm_call_count=0` on the
  core retrieve/answer/verify path.
- SSE, reconnect, heartbeats, and UI remain packets 6 and 8.
- Do **not** mark Phase 6 complete. Do **not** check the wrapper checkbox.

### Unverified (packet 4)

- Live FastAPI catalog search/admin routes (packet 5 HTTP unit tests now
  cover in-code registry + live role; live Postgres seed writes remain
  unverified).
- Live `app.tool_usage_events` inserts against Postgres.
- Hosted Auth throttling (carried from packet 1).
- QT-EVAL-009 and Combined p95 latency (carried from packet 3).

## Packet 5 — FastAPI security, rate ownership, cache, offload, isolation

### Quoted requirement

> Implement thin FastAPI routers/services, Supabase-Auth/FastAPI rate
> ownership, authorization-safe retrieval caching, endpoint-specific
> authorization, CPU offload, and prompt/data isolation.

### Acceptance checks restated

- Every listed endpoint has explicit role/ownership/current-version/
  deletion/ACL behavior; routers stay thin (`Depends` → service →
  factory-injected core/agent). No repository imports in packet 5 routers.
- Provider-owned Auth and FastAPI-owned rate controls are separately
  documented; FastAPI never claims to throttle browser-direct Auth
  (`local_auth_throttling_proven=False`).
- Valkey loss: AUTH_ADJACENT / COST_MUTATION / PRE_AUTH_IP use Valkey then
  Postgres and 503 + Retry-After if both fail. LOW_RISK_READ may use an
  emergency in-process limiter with `rate_limit_degraded`.
- Separate Valkey instances: limits `64mb` / `mem_limit 128m` /
  `noeviction`; cache `256mb` / `320m` / `allkeys-lru`; `requirepass`;
  private network; no host ports. 64mb is 50% of 128m (≤ 70%).
- Retrieval cache stores IDs/ranks only (TTL 30s / 300s). Every hit
  rechecks; ACL/delete/version mismatch and forbidden snippet/text/passage
  fields drop the entry. Events: `cache_hit`, `cache_miss`,
  `cache_invalidated`, `cache_recheck_failed`.
- CPU slices over 10 ms offload through a bounded cancellable process
  pool; blocking I/O uses a thread pool. Five live Composite heartbeat
  proofs remain packets 6 and 8.
- Extra JSON fields and untrusted HTML fail closed (422 / escaped JSON,
  never `text/html`). Local audit export detects mutation, gap, fork,
  signing failure, and passage-like keys without storing full source text.

### Inspected schema / APIs

| Item | Found |
| --- | --- |
| Latest additive migration | `20260816190000_fastapi_security_rpcs_v1.sql` |
| Conversation delete RPC | Not implemented; DELETE HTTP is 501 `conversation_deletion_not_implemented` |
| Auto admit envelope | HTTP maps Auto chat to `Phase6RouteFamily.COMPOSITE` |
| Stream path | `{run_id, stream_path}` with `/runs/{run_id}/events`; no EventSource body |
| OpenAPI snapshot | `docs/api/openapi.foundation.json` regenerated UTF-8 |
| Valkey Compose | `docker-compose.yml` `valkey-limits` / `valkey-cache` as above |
| CORS default | `http://127.0.0.1:3000,http://localhost:3000`; `*` rejected |

### Endpoint authorization matrix

| Method | Path | Authorization | Notes |
| --- | --- | --- | --- |
| GET | `/health/live` | public | Process up |
| GET | `/health/ready` | public | Dependency-aware; `query_ready` is false in mock/unconfigured |
| GET | `/api/meta` | public | Publishes `api_version`, `sse_schema_version`, `min_client_version` |
| GET | `/me` | authenticated | Server-derived role |
| POST | `/admin/invitations` | owner/admin | AUTH_ADJACENT |
| POST | `/invitations/accept` | authenticated | Email from token, not body |
| POST | `/admin/users/{user_id}/offboard` | owner/admin AAL2 | AUTH_ADJACENT |
| GET | `/documents` | authenticated | ACL list |
| GET | `/documents/{document_id}` | authenticated | 404 if missing/unauthorized |
| POST | `/documents/uploads` | member+ upload | COST_MUTATION; local `signed_url=null` |
| POST | `/documents/uploads/finalize` | member+ upload | COST_MUTATION |
| POST/GET | `/conversations` | authenticated | Creator insert / list |
| GET | `/conversations/{conversation_id}` | creator or owner/admin | 404 otherwise |
| DELETE | `/conversations/{conversation_id}` | authenticated | **501** packet 7 |
| POST | `/conversations/{conversation_id}/messages` | creator | Auto → COMPOSITE; `{run_id, stream_path}` |
| GET | `/runs/{run_id}` | creator only | IDOR → 404 |
| POST | `/runs/{run_id}/cancel` | creator | Not SSE cancel transport |
| GET | `/runs/{run_id}/citations` | creator | IDs/provenance; no passage |
| POST | `/runs/{run_id}/feedback` | creator | thumbs 1 or 5 |
| GET | `/graph/entities/search` | authenticated | Cheap SQL; 3s timeout |
| GET | `/tables` | authenticated | Current-version manifests; no paths |
| POST | `/tables/analyze` | authenticated | `TableQueryPlan` extra=forbid |
| GET | `/tools` | authenticated | In-code registry + live role; Postgres not required |
| POST | `/admin/tools` | owner/admin | Allow-listed keys only |
| POST | `/admin/tools/{tool_key}/enable` | owner/admin | Allow-list recheck |
| POST | `/admin/tools/{tool_key}/permissions` | owner/admin | Executor still rechecks live role |
| GET | `/usage/me` | authenticated | Caller totals |
| GET | `/usage/company` | owner/admin | Members/viewers 403 |

### Valkey / cache / offload proof

| Check | Result |
| --- | --- |
| Limits `maxmemory` / `mem_limit` / policy | `64mb` / `128m` / `noeviction` in `docker-compose.yml` |
| Cache `maxmemory` / `mem_limit` / policy | `256mb` / `320m` / `allkeys-lru` |
| Host ports / network | none / `private`; `requirepass`; named ACL users Phase 10 |
| Key prefixes | `limits:` and `cache:` in `smart_rag_core.runtime.valkey` |
| Cache TTLs | result 30s, profile 300s |
| Cache recheck | `test_retrieval_cache.py`: drop/flip/forbidden payload → miss; no stale IDs |
| Import-time sockets | `test_package_imports.py` still denies socket/OpenAI construction |
| Offload / cancel | `test_cpu_slice_budget_and_offload_cancel`: 10 ms budget, thread/process offload, `OffloadCancelledError` |
| Event-loop lag | `sample_event_loop_lag` unit-sampled; five live Composite runs are packet 8 |
| Lifespan OffloadExecutor | **Not** started in FastAPI lifespan (Windows TestClient/process-pool hang) |

### Rate ownership

| Check | Result |
| --- | --- |
| Browser-direct Auth | FastAPI does not claim it; flag false |
| Dual Valkey+Postgres outage on mutations | `AuthRateLimitUnavailableError` / HTTP 503 Retry-After |
| Unconfigured (both URLs unset) | Pre-auth middleware skips; not treated as dual outage |
| LOW_RISK_READ Valkey loss | Emergency limiter + `rate_limit_degraded` |
| Reserve-once vs limiter | Packet 1 admission reservations stay separate from FastAPI buckets |

### Isolation / audit

| Check | Result |
| --- | --- |
| Conversation title HTML | Escaped in JSON; content-type `application/json` |
| Extra JSON fields | 422 `validation_failed` |
| Oversized body | 413 `payload_too_large` |
| CORS | Exact origin reflected; evil origin omitted; `*` settings fail |
| Viewer tools | `admin_user_invite` omitted; core forbidden keys omitted |
| Foreign run fetch | 404 `not_found` |
| Local HMAC export | mutation / gap / fork / empty / passage key / empty secret fail closed |

### Commands and results

| Command | Exit |
| --- | --- |
| `uv run ruff format` on packet 5 Python paths | 0 |
| `uv run ruff check` on packet 5 Python paths | 0 |
| `uv run python -m pyright` on packet 5 changed Python paths | 0 errors |
| `uv run python scripts/ci/check_migrations.py` | 0 (49 reviewed files) |
| `uv run python scripts/ci/check_openapi.py` | 1 then 0 (snapshot rewritten UTF-8, then matches) |
| `uv run python -m pytest tests/unit/test_fastapi_security.py tests/contract/test_query_admission_api.py tests/contract/test_retrieval_cache.py tests/unit/test_package_imports.py tests/contract/test_import_boundaries.py tests/unit/test_backend_middleware.py tests/contract/test_auth_rate_limits.py tests/unit/test_settings.py` | 0; **57 passed**, 7 warnings, 0 failed |

### Deviations

- FastAPI lifespan does not construct `OffloadExecutor` because Windows
  `TestClient` plus a process pool hung import/readiness tests. Offload
  and cancellation are proven in unit tests; query nodes remain responsible
  for calling the executor when a slice exceeds 10 ms.
- Named Valkey ACL users and Secrets Manager rotation are Phase 10. Local
  Compose uses `requirepass` on the private network (ADR-private-service-tls
  omits TLS).
- Pre-auth IP limits skip when **neither** Valkey nor Postgres is configured
  so unconfigured processes are not treated as a dual outage.
- Local document upload `signed_url` is null (CloudFront is Phase 10).
- Conversation DELETE is 501 until packet 7.
- Five simultaneous Composite p95 lag / heartbeat proofs are packets 6 and 8.

### Rollback

Forward-fix: stop including the new routers and keep `/health` plus prior
ingestion/glossary/graph-inspect routes. Do not DROP the additive
`20260816190000` RPCs in the same release. Restore
`docs/api/openapi.foundation.json` from the prior commit if reverting the
snapshot.

### Phase 9 / 10 blockers

- Phase 9: reservation-lock wait at max concurrency (provisional p95 below 50 ms).
- Phase 10: KMS key unavailable to database roles; 15-minute chain-head
  anchors; signed daily batches to S3 Object Lock; named Valkey ACL +
  Secrets Manager; hosted Auth throttle proof; CloudFront signed URLs /
  WAF / origin restriction.

### Packet 6 handoff

- Implement `GET /runs/{run_id}/events` EventSource transport, SSE schema,
  15s heartbeat, resume, and cancel **without** inventing event names in
  packet 5.
- Enforce `min_client_version` / `sse_schema_version` handshake before paid
  work. Packet 5 only publishes those fields on `/api/meta`.
- Keep Auto admit on the Composite envelope and `stream_path`
  `/runs/{run_id}/events`.
- Do **not** mark Phase 6 complete. Do **not** check the wrapper checkbox.

### Unverified (packet 5)

- Live Postgres round-trips for the new conversation/run/document/table/
  tool-seed RPCs (HTTP tests inject services or unused DSNs).
- Live Valkey kill / restart / OOM / ACL recovery against Compose.
- Five live Composite runs (heartbeat jitter, missed 15s heartbeat).
  Packet 6 proved five **fixture** streams; live Composite LLM remains
  packet 8.
- Hosted Auth throttling (carried).
- QT-EVAL-009 and Combined p95 latency (carried).
- Phase 9 lock-wait measurement and Phase 10 AWS proof.

## Packet 6 — versioned additive SSE, handshake, resume, heartbeats

### Quoted requirement

> Implement versioned additive API/SSE contracts, compatibility handshake,
> resumable fetch SSE with persisted sequence IDs, heartbeats, cancellation,
> reconnect, sanitized errors, and deadline/partial events.

### Acceptance checks restated

- Incompatible clients fail with HTTP 426 `client_version_unsupported`
  **before** `admit_query_run_for_caller`. No reservation, no graph start.
  Resume GET of an already-admitted run requires Bearer + ownership only.
- Bearer POST fetch SSE (`Accept: text/event-stream`) admits then streams.
  JSON Accept stays HTTP 202 `{run_id, stream_path}` with
  `stream_path=/runs/{run_id}/events`. Duplicate idempotency keys reuse one
  run and do not start the executor twice.
- Every event (including heartbeat) is persisted with a monotonic run-local
  sequence **before** flush. `GET /runs/{run_id}/events?after=` and
  `Last-Event-ID` replay `sequence > after`. Foreign / missing / tombstoned
  conversations are 404.
- Reconnect never restarts paid execution. Process-local registry starts
  LangGraph (or the test fixture) at most once per `run_id`. A pending run
  with no live executor after process restart replays a sanitized
  `worker_unavailable` error.
- Heartbeats every **15 seconds** while a stream is open and the run is
  non-terminal. Cancel persists `cancelled` and stops the live generator.
- Local Caddy contract file uses `flush_interval -1` and **90s** timeouts.
  Docs name CloudFront `OriginReadTimeout` / `OriginKeepaliveTimeout` = 90s
  as Phase 10 IaC. This packet does not provision AWS or claim CDN proof.

### Event catalog (allow-list; extra=forbid)

`schema`, `status`, `heartbeat`, `route_correction`, `limitation`,
`deadline`, `partial`, `cache`, `coverage`, `optional_tool_disclosure`,
`citation_preview` (IDs/ranks only), `token_delta`, `usage`, `completed`,
`cancelled`, `error` (generic `{code}`; no traceback/secrets/HTML/passage).

Exactly one terminal among `completed` | `cancelled` | `error` | `partial`.
Deadline exhaustion emits `deadline` then `partial`. Clients log and ignore
unknown additive types.

Wire format (FastAPI 0.141 has no `EventSourceResponse`):

```
id: {sequence}
event: {allowlisted_type}
data: {json}

```

SSE headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
`Connection: keep-alive`, `X-Accel-Buffering: no`. Packet 5 security
middleware does not rewrite `text/event-stream` to JSON.

### Handshake versus reservation

| Case | Admit calls | Executor starts | HTTP |
| --- | --- | --- | --- |
| Missing `X-Client-Version` | 0 | 0 | 426 + published `min_client_version` / `sse_schema_version` |
| `X-Client-Version: 0.0.1` below min | 0 | 0 | 426 |
| Supported version + JSON Accept | 1 | 0 until GET resume | 202 |
| Supported version + EventSource Accept | 1 | 1 | 200 stream |
| Duplicate idempotency key | 2 (reconnect) | 1 | existing run |
| GET resume without client version | n/a | at most one | 200 replay |

Proven by `tests/unit/test_sse_protocol.py` and
`tests/contract/test_sse_resume.py`.

### Sequence / replay

- Memory and Postgres `app.append_run_event` allocate
  `COALESCE(MAX(sequence),0)+1` under a run lock after ownership and
  undeleted-conversation checks.
- Postgres contract: sequences `(1, 2, 3)`, `after=1` returns `(2, 3)`,
  foreign list and tombstoned `conversations.deleted_at` raise `not_found`,
  `app_api` cannot `INSERT` into `app.run_events` directly.
- Unique partial index enforces one terminal event per run.

### Heartbeat / event-loop (five held streams)

Five concurrent fixture SSE GETs were held while lag was sampled for ≥16 s
(`httpx.ASGITransport` + `asyncio.gather`). Production interval constant
`HEARTBEAT_INTERVAL_SECONDS == 15`. Cadence was measured from **persisted**
heartbeat rows (same append path as the socket) because ASGITransport
delivers the EventSource body when the generator completes.

Gates asserted in `tests/contract/test_sse_heartbeat.py`:

- p95 event-loop lag `< 50 ms` (`sample_event_loop_lag`)
- first persisted heartbeat jitter `< 2 s` around 15 s
- zero missed 15-second heartbeats (every held run persisted ≥1 heartbeat)

No OpenAI. Live Composite LLM streaming remains packet 8.

### Timeout contract (local files only)

| Input | Value | Proof |
| --- | --- | --- |
| Caddy `read_timeout` / `write_timeout` / upstream | 90s | `infra/caddy/Caddyfile` |
| Caddy buffering | `flush_interval -1` | same file |
| CloudFront `OriginReadTimeout` | 90s | `docs/deployment/STREAMING_TIMEOUTS.md` (Phase 10 IaC) |
| CloudFront `OriginKeepaliveTimeout` | 90s | same doc |
| Composite deadline | 50s | margin under 90s |

`tests/contract/test_streaming_timeout_contract.py` fails if any parsed
value ≠ 90. Caddy is **not** deployed. CloudFront is **not** provisioned.

### OpenAPI

Additive `GET /runs/{run_id}/events` (path param remains `run_id`).
POST `/conversations/{conversation_id}/messages` documents JSON 202 and
`text/event-stream` 200 plus 426 handshake. Snapshot
`docs/api/openapi.foundation.json` regenerated UTF-8.
`scripts/ci/check_openapi.py` allowlists `/runs/{run_id}/events`.

### Commands and exit codes

| Command | Exit |
| --- | --- |
| `uv run ruff format` (packet 6 Python) | 0 |
| `uv run ruff check` (packet 6 Python) | 0 |
| `uv run python -m pyright` (packet 6 Python) | 0 |
| `uv run python scripts/ci/check_migrations.py` | 0 (50 reviewed files) |
| `uv run python scripts/ci/check_openapi.py` | 0 (snapshot matches after UTF-8 regenerate) |
| `uv run python -m pytest tests/unit/test_sse_protocol.py tests/contract/test_sse_resume.py tests/contract/test_sse_heartbeat.py tests/contract/test_streaming_timeout_contract.py tests/unit/test_package_imports.py tests/contract/test_import_boundaries.py tests/unit/test_fastapi_security.py tests/contract/test_query_admission_api.py -q` | 0 (54 passed) |

`npx supabase migration up --db-url postgresql://postgres:postgres@127.0.0.1:54322/postgres`
applied `20260816200000_query_run_events_v1.sql` (no `db reset`). Backend
import still constructs no sockets/OpenAI (`test_package_imports`).

### Deviations

- FastAPI **0.141.1** has no `fastapi.sse.EventSourceResponse`. SSE uses
  Starlette `StreamingResponse` and manual framing (planned pin; no bump).
- JSON 202 is returned via `JSONResponse(status_code=202)` because
  `response_model=None` would default POST to 200 when the EventSource
  200 is also declared.
- Five-stream heartbeat jitter is measured from persisted rows, not
  `aiter_text` timestamps. Documented above.
- Production executor is `LangGraphQueryRunExecutor` (`graph.astream`
  once). HTTP tests inject `FixtureQueryRunExecutor`. Both persist through
  the same `RunEventStore.append` path.

### Rollback

- Drop/leave unused `app.run_events` / `app.append_run_event` /
  `app.list_run_events_after` via a later expand/contract migration
  (do not `DROP TABLE` in this packet).
- Revert `docs/api/openapi.foundation.json` and the FastAPI SSE routes.
- Clients without `X-Client-Version` would again reach admit; do not ship
  that rollback without a replacement handshake.

### Phase 10 blockers

- CloudFront/WAF/Caddy **IaC** asserting 90s `OriginReadTimeout` and
  `OriginKeepaliveTimeout` (this packet only has local contract files).
- Real staging 50-second Composite stream through managed CDN (no buffering,
  no premature origin close).
- Independent Vercel/API deploy skew and origin-restriction checks.
- Do not treat `infra/caddy/Caddyfile` as proof that Caddy is deployed.

### Packet 7 handoff

- Completed idempotency keys default to **seven days**; completed events
  to **30 days** through a dedicated reaper. This packet does **not** reap.
- Conversation deletion must purge keys/events immediately. DELETE remains
  HTTP 501 `conversation_deletion_not_implemented`. Tombstoned
  `conversations.deleted_at` already **denies resume immediately** (404).
- Do **not** implement packet 8 UI. Do **not** mark Phase 6 complete. Do
  **not** check the wrapper checkbox.
