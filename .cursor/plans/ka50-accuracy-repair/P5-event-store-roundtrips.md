# P5 - One fewer round trip per SSE event

## Goal

`PostgresRunEventStore._transaction` runs, per persisted SSE event:
`SET ROLE app_api` -> `SET LOCAL lock_timeout TO '2s'` ->
`SELECT ... app.append_run_event(...)` -> `COMMIT`. Against remote
Supabase that is about 0.65 s per event and a run emits 20-30 events, so
10-20 s of bookkeeping competes with the Hybrid envelope
(`FAMILY_DEADLINE_SECONDS[HYBRID] = 25` in
`packages/core/src/smart_rag_core/query_admission/envelopes.py`; the
retrieve slice inside it is `RETRIEVAL_SLICE_SECONDS = 10.0` and the
answer stage needs `ANSWER_STAGE_MIN_SECONDS = 8.0`). Merging the two `SET`
statements into one `execute()` removes one round trip per event. Psycopg
3 allows several statements in one `execute()` when **no parameters** are
passed (server-side binding is only used with parameters; see "Multiple
statements in the same query" in the psycopg 3 "Differences from
psycopg2" page). Both statements here are parameter-free literals.

This is a latency packet. It does not change what is persisted, the
role, the lock timeout, or commit semantics.

## Read first

- `packages/core/src/smart_rag_core/sse/store.py` lines ~29-33
  (`EVENT_STORE_LOCK_TIMEOUT`, `EVENT_STORE_LOCK_TIMEOUT_SQL`) and
  `_transaction` (line ~478).
- `tests/unit/test_query_sse_event_store.py`
  `test_postgres_event_store_reuses_and_closes_session` (asserts the
  statement sequence) and any other test referencing
  `EVENT_STORE_LOCK_TIMEOUT_SQL` (`rg EVENT_STORE_LOCK_TIMEOUT_SQL`).
- `docs/api/SSE.md` or the runbook that documents the event store
  transaction (`rg "SET ROLE app_api" docs`).

## Steps

### 1. Constant

In `store.py` add after `EVENT_STORE_LOCK_TIMEOUT_SQL` (exact code):

```python
EVENT_STORE_SESSION_SQL = f"SET ROLE app_api; {EVENT_STORE_LOCK_TIMEOUT_SQL}"
"""One parameter-free round trip that selects the API role and bounds lock
waits for the transaction. Psycopg 3 sends parameter-free multi-statement
strings with the simple query protocol."""
```

Keep `EVENT_STORE_LOCK_TIMEOUT_SQL` exported; other modules may use it.

### 2. `_transaction`

Replace

```python
                connection.execute("SET ROLE app_api")
                connection.execute(EVENT_STORE_LOCK_TIMEOUT_SQL)
```

with

```python
                connection.execute(EVENT_STORE_SESSION_SQL)
```

Update the docstring sentence to "Each transaction runs one
parameter-free statement that does ``SET ROLE app_api`` and sets
``lock_timeout`` to two seconds ...".

### 3. Measure

Add an `INFO` log with the elapsed milliseconds per append in
`PostgresRunEventStore.append` **only if** the module already has a
timing pattern (search for `perf_counter` in `store.py`). If it does not,
skip logging; the live proof below measures externally.

## Tests

`tests/unit/test_query_sse_event_store.py`
`test_postgres_event_store_reuses_and_closes_session`: replace the three
assertions on `SET ROLE app_api` and `EVENT_STORE_LOCK_TIMEOUT_SQL` with

```python
    assert calls.count(EVENT_STORE_SESSION_SQL) == 2
    assert "SET ROLE app_api" in EVENT_STORE_SESSION_SQL
    assert EVENT_STORE_LOCK_TIMEOUT_SQL in EVENT_STORE_SESSION_SQL
    assert calls.index(EVENT_STORE_SESSION_SQL) < calls.index("COMMIT")
```

and import `EVENT_STORE_SESSION_SQL`. Check the other tests in the file
that count statements (`test_postgres_event_store_discards_on_error_without_append_replay`,
`test_postgres_event_store_list_after_retries_before_rows`) and update
counts the same way; do not weaken any assertion about rollback,
discard, or no-replay.

Contract test (runs only with a database URL; see how
`tests/contract` gates on `require_supabase_db_url`): add one test that
opens `PostgresRunEventStore` against the test database, appends one
event, and asserts `SELECT current_setting('lock_timeout')` inside a
`_transaction()` returns `2s` and `SELECT current_user` returns
`app_api`. This proves the merged statement applied both settings.

## Docs

- Update the event-store paragraph in the doc found by
  `rg "SET ROLE app_api" docs` to describe the single statement.

## Commands

```powershell
uv run python -m pytest tests/unit/test_query_sse_event_store.py -q
uv run python -m pytest tests/contract -k event_store -q
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier docs
```

Live proof: run the KA50 subset `k06 k10 k16` (three fast passes) into
`.private-eval/runs/p5-before/` against the image as it is **before** this
packet's edit, then rebuild the `api` image (`00-rules-and-commands.md`,
"Docker rebuild before any live run"; probe must print `P5 present`) and
run the same subset into `.private-eval/runs/p5-after/`. Compare wall time
per question printed by the runner. Expect 10-25% lower per-question
time; record both numbers in the P7 evidence doc.

## Done when

- [ ] `_transaction` issues exactly one `SET` statement per transaction.
- [ ] Unit tests updated as specified; contract test proves both settings
      applied.
- [ ] Lint, types, docs pass.
- [ ] Committed and pushed; `gh pr checks --watch --fail-fast` exit 0.

## Commit

Follow "At the end of every packet" in `00-rules-and-commands.md`.
Message:

```text
perf(sse): one round trip for SET ROLE and lock_timeout in the event store (P5)
```

## Do not

- Do not enable autocommit, pipeline mode, or a `ClientCursor`.
- Do not change `lock_timeout` value, the role, or the commit/rollback
  order.
- Do not batch `app.append_run_event` itself into the same statement (it
  has parameters).
