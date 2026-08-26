# Packet 7 — checkpoints, store, reaper, governance, deletion

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

## Quoted requirement

> Implement Supabase checkpoints/store memory, idempotency/run-event GC,
> full governance enforcement, trace redaction, prompt versions, usage
> accounting, feedback, and immediate conversation deletion.

## Acceptance checks restated

- Checkpoint/resume/history is Supabase-durable and ownership-safe; store
  content is compact memory only; summary calls are budgeted; deleted-source
  citations are marked unavailable.
- Seven-day key and 30-day event defaults reap only completed data, preserve
  active/retryable and expiry-boundary one-paid-run semantics, and remain
  independent of budget reconciliation.
- Prompts/traces/usage are versioned, costed, redacted, and permitted by
  signed governance; prohibited or unknown external flows block.
- CI/nightly suites map every listed category on frozen/disjoint data,
  preserve holdout isolation, enforce bounded online cost, and include
  route/fusion/tool/cache/reaper/API/SSE/privacy outcomes.
- Conversation deletion immediately denies reads and leaves no
  conversation-scoped application/checkpoint/store/private-feedback/event/
  citation state; LangSmith deletion is durably requested within 24 hours
  with only content-free audit and pseudonymized aggregate usage retained.
- Feedback tags stay unmerged; curation schedule and release evaluation
  controls do not open the launch holdout.

## Inspected schema / APIs

| Item | Found |
| --- | --- |
| Pinned LangGraph | `langgraph==1.2.11`, `langgraph-checkpoint-postgres==3.1.2` |
| `PostgresStore.MIGRATIONS` | length 4 (versions 0–3); runtime never calls `setup()` |
| `PostgresStore(conn=pool)` | pinned constructor used by `open_query_memory_store` |
| Prior DELETE | packet 5/6 HTTP 501; replaced by 204 |
| `app.submit_run_feedback` | packet 5 six-arg RPC dropped; seven-arg tag required |
| Signed governance | `docs/security/OPENAI_DATA_GOVERNANCE.md`, `SUBPROCESSOR_GOVERNANCE.md` |
| Holdout | `HoldoutAccess.denied()`; QT-EVAL-009 stays `unverified` |

## Migration

`supabase/migrations/20260816210000_query_memory_store_reaper_v1.sql`
applied with `npx supabase migration up --db-url postgresql://postgres:postgres@127.0.0.1:54322/postgres` (no `db reset`).

Expand-only contents:

- `langgraph.store` + `langgraph.store_migrations` versions 0–3 copied from
  the pinned library. `CREATE INDEX CONCURRENTLY` omitted (transactional
  migrations). Runtime must not call `PostgresStore.setup()`.
- `app.runs.idempotency_key_hash` plus unique
  `(creator_user_id, conversation_id, idempotency_key_hash)` so a 7-day
  NULL of the plaintext key cannot double-admit. A trigger preserves the
  hash when the key is NULLed.
- `app.find_run_for_idempotency` / `app.admit_query_run` match live key
  **or** retained hash.
- `app.user_feedback.tag` CHECK of the ten exact unmerged tags;
  `app.citations.source_unavailable`.
- `app.langsmith_deletion_requests` (hashed keys only; statuses
  `pending` / `retrying` / `request_recorded` / `sla_expired`).
- `app.delete_conversation`, `app.reap_query_run_retention` (7d keys /
  30d events, `true_up_invoked` always false),
  `app.enqueue_query_maintenance_jobs`,
  `app.search_conversation_lingering_ids`.

## Checkpoints and store

- Query SSE compiles `compile_query_graph(checkpointer=...)` with
  `thread_id=str(conversation_id)`. Module-level Studio `graph` stays
  checkpointer-free.
- `CompactPostgresSaver` hashes `citation_text` / `passage` / `snippet` /
  `html` / `source` before durable writes.
- Store namespace is `(company_id or "company", user_id, conversation_id)`.
  `validate_memory_store_payload` rejects source-document keys.
- Summary is `usage_kind=summary` through `execute_counted_model_call`.
  Envelope shortfall records `summary_deferred` and skips the write.

## Reaper boundary table

| Case | Result | Proof |
| --- | --- | --- |
| Completed key age ≥ 7d | plaintext key NULLed; hash retained | `test_reaper_nulls_completed_keys_at_seven_days` |
| `pending` / `running` key | not reaped | `test_reaper_does_not_touch_pending_keys` |
| Reaper vs true-up | `true_up_invoked` false; reservation unchanged | `test_reaper_does_not_call_budget_true_up` |
| Same client key after expiry | reconnects the original paid run | `test_reaped_key_still_reconnects_same_paid_run` |
| Completed events age ≥ 30d | deleted | `test_events_reaped_after_thirty_days` |
| Conversation DELETE | keys/events purged immediately | `test_delete_leaves_no_lingering_conversation_ids` |

## Immediate deletion

`DELETE /conversations/{id}` is HTTP **204** for creator or owner/admin.
Foreign and tombstoned ids are **404** (not 403). One transaction
tombstones, then purges messages, runs, events, citations, private
feedback, `langgraph.checkpoints*`, and `langgraph.store` prefixes.
`app.search_conversation_lingering_ids` returns zero application /
checkpoint / store / feedback / event / citation matches. Tombstone,
content-free `conversation_deleted` audit, hashed LangSmith request
rows, and pseudonymized `llm_usage` may remain.

Concurrent readers wait on `FOR UPDATE` then see the tombstone
(`test_concurrent_read_during_delete_is_denied`).

## LangSmith deletion request

Durable `app.langsmith_deletion_requests` retries HTTP *requests* of
hashed keys. `request_recorded` means the request was sent, **not** that
cloud traces were deleted. After 24 hours the row is `sla_expired` and
no further HTTP is sent for that expired claim
(`test_langsmith_deletion_request_retries_within_sla`).

## Governance, prompts, traces, usage, feedback

- `assert_langsmith_export_permitted` blocks real-company tracing until
  `subprocessor_matrix_verified`.
- `assert_vercel_metadata_has_no_private_payload` rejects source/secret
  keys.
- Prompt registry: immutable ids, SHA-256, `SMART_RAG_PROMPT_ENV`
  promotion. `summary_v1` added to
  `apps/agents/src/smart_rag_agents/prompts/`.
- `query_run_trace_metadata` carries hashed user id, run id, requested /
  effective / corrected route, model/prompt versions, disclosed tools,
  candidate counts, BM25 index/version/lag/recheck/fallback, latency,
  tokens, cache, cost. Production payloads stay redacted.
- Usage JSON (`UsageResponse`) has no `prompt` / `query` / `passage` /
  `snippet` / `html` / `source` / `message` fields.
- Feedback requires one of the ten exact tags. Merged strings fail
  `feedback:invalid_tag`.

## Evaluation registry

`packages/core/src/smart_rag_core/evaluation/phase6_registry.py` maps
every packet-7 category to an existing Phase 4/5/6 command. CI:
`scripts/ci/check_phase6_eval_registry.py` (unit tier via
`scripts/check.py`). Online eval: mock default, max 20 cases, USD 2.00,
`HoldoutAccess.denied()`. Bounded LangSmith agent eval
(`scripts/eval_query_agent_langsmith.py`) is a **follow-up tool** on the
synthetic development split; it does not complete Phase 6, retune Hybrid,
or open holdout. Hosted online evaluators on
`smart-rag-agent-eval-online` are the same class of tool: synthetic
development only, holdout sealed, ≤20 traces, USD 2 weekly judge cap, no
attachment to `smart-rag`. `qt_eval_009_combined_plus_10pp` status is
**`unverified`**. Frontend XSS of entity/relation/crawl HTML is packet 8.

Curation schedule (weekly through pilot + first eight production weeks,
then monthly) is documented in
[PHASE6_EVAL_REGISTRY.md](../../evaluation/PHASE6_EVAL_REGISTRY.md).
Post-launch regression sets are not the immutable holdout.

## Commands and exit codes

| Command | Exit |
| --- | --- |
| `uv run ruff check` (packet 7 Python) | 0 |
| `uv run python -m pyright` (packet 7 Python) | 0 |
| `uv run python scripts/ci/check_migrations.py` | 0 (51 reviewed files) |
| `uv run python scripts/ci/check_openapi.py` | 0 (snapshot matches after DELETE 204 regenerate) |
| `uv run python scripts/ci/check_phase6_eval_registry.py` | 0 |
| `uv run python -m pytest tests/unit/test_conversation_deletion.py tests/contract/test_query_memory_reaper.py tests/unit/test_phase6_eval_registry.py tests/unit/test_agent_eval.py tests/unit/test_langsmith_agent_runner.py tests/unit/test_query_agent_eval_trace.py tests/unit/test_prompt_registry.py tests/unit/test_langsmith_tracing.py tests/unit/test_fastapi_security.py tests/unit/test_package_imports.py tests/contract/test_import_boundaries.py -q` | 0 |
| `uv run python scripts/eval_query_agent_langsmith.py --dry-run --limit 3` | 0 |

## Deviations

- LangGraph store schema is applied by Supabase migration, not
  `PostgresStore.setup()`, because `CREATE INDEX CONCURRENTLY` cannot run
  inside a transaction. Matches the ingestion checkpointer pattern.
- FastAPI 0.141.1 still has no `EventSourceResponse` (packet 6 deviation).
- QT-EVAL-009 Combined +10pp vs Hybrid on **live** mapping/extraction is
  explicitly unverified. Do not claim it.
- Hosted Auth throttling and live OpenAI answer/verifier remain mock /
  local-only as recorded in earlier packets.

## Rollback

- Revert `20260816210000_query_memory_store_reaper_v1.sql` only with a
  later expand/contract migration (do not `DROP TABLE` store in place).
- DELETE would return 501 again; do not ship that without a replacement
  purge path.
- Keep `idempotency_key_hash` if plaintext keys are still being NULLed.

## Packet 8 handoff

- Thin authenticated developer UI only (not Stitch / production frontend).
- Prove route/fallback/injection/idempotency/budget/outage/event-loop/
  privacy gates through the UI against real local boundaries.
- Five live Composite heartbeat proofs deferred from packets 5–6 belong
  here.
- Do **not** mark Phase 6 complete until the wrapper `Done when` gate is
  proven and the user accepts it.
