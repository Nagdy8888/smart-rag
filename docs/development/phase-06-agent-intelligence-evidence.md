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
