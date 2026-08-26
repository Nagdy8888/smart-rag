# Packet 2 — memory, rewrite, profiling, route matrix, one correction

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

## Quoted requirement

> Implement memory rewrite, extended typed profiling, the complete
> deterministic route/limitation matrix, one global correction, and bounded
> parallel branches.

Packet 1 (`54f70c5`) is the input authority. This packet does not mark
Phase 6 complete and does not check the wrapper packet checkbox.

## Acceptance checks restated

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

## Inspected schema / APIs consumed (not retuned)

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

## Schema added

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

## Graph wiring

`enforce_admission` → `load_memory` → `prepare_query` → `compile_plan` →
`execute_branches` → `apply_correction` → END. No answer node. No Combined
fusion, ablation, or verifier.

Envelope vs Auto: packet 1 reserves the family envelope before profiling.
The planner never enlarges remaining ceilings. A client Combined request
cannot expand a Hybrid reservation (`envelope_cannot_enlarge`). Normal Auto
chat **should** reserve `composite` (50s / 9 calls / 5 tools); that wiring
is documented for packet 5 routers, not implemented here.

## Preparation

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

## Route matrix fixtures (unit)

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

## Correction traces

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

## Branch / limitation negatives

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

## Call counts and counters

| Counter | Proven value |
| --- | --- |
| deterministic prep `model_calls` | 0 |
| force_model rewrite+profile | 1; `app.llm_usage.usage_kind=profile`; no `rewrite` kind |
| `keyword_extract_count` | 0 on every branch and LangGraph invoke |
| `catalog_llm_call_count` | 0 on every plan and invoke |
| query-graph import | no sockets / no OpenAI (`test_package_imports.py`) |

## Decomposition and parallelism

- `SUBQUESTION_CEILING=3` (`MAX_SUBQUESTIONS`)
- `BRANCH_CONCURRENCY=2`
- Independent required branches run via `ThreadPoolExecutor(max_workers=2)`
- Citation lookup is ID resolution only (after Hybrid IDs)
- Memory: last 12 creator messages as `<<untrusted-memory>>` records

## Contract traces (local Postgres 54322)

| Case | Result |
| --- | --- |
| creator memory load | 2 delimited records; no source documents |
| owner stranger on another user's thread | `conversation_forbidden` |
| deleted conversation | `conversation_deleted` |
| counted prep | one `profile` usage row for the admitted run |
| `Hello` branches | inherit `run_id` and `reservation_id`; keyword/catalog counters 0; `company_claim=false` |
| LangGraph empty query | `routing_rejected` / `empty_query` |
| LangGraph `INV-SR-1001` with Hybrid envelope | `correction_applied` or `insufficient_evidence`; `effective_route=hybrid`; no answer key |

## Commands and results

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

## Deviations

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

## Rollback

Forward-fix: stop calling `app.load_query_memory` and skip the new graph
nodes. Do not `DROP FUNCTION` in the same release. Local-only
`supabase db reset` is destructive.

## Packet 3 handoff (from packet 2)

Packet 3 implemented fusion, tables, one answer, and the verifier below.
SSE, optional catalog, and UI remain later packets.

## Unverified (packet 2 residual)

- Hosted Supabase Auth throttling remains unproven.
- Live Hybrid/LightRAG/table retrieve against populated corpora (branches
  used fakes or unbound adapters in unit tests).
- FastAPI Auto→composite reservation wiring (packet 5).
