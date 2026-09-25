# L4 - One round trip per event-store write (conditional)

Read `00-rules-and-commands.md` first (especially **How to apply an edit**).
Every `Find (exactly once):` block must match exactly one place in the
named file. If it matches zero or two places, stop and report.

## Goal (why)

After L2, each event-store transaction is 3 network round trips
(`SET LOCAL ROLE app_api; SET LOCAL lock_timeout` -> RPC -> `COMMIT`),
about 254 ms at 85-95 ms per trip. After L3 only terminal flushes and a
full writer queue wait for writes, so this packet runs only if the L3
writer summaries show that writes still cost visible time. With psycopg
pipeline mode the steps go out together and come back in about one round
trip.

Scope: `PostgresRunEventStore.append` and `_list_after_once`.
`get_authorized_run`, `mark_running`, and `probe` keep `_transaction()`.

## Step 0 - trigger (check first; no code before this)

Open `docs/evaluation/QUERY_LATENCY_REPAIR_EVIDENCE.md`, section
`L3 writer summaries`. Run L4 only if `append_ms_p50` median is above 150
**or** `flush_ms_max` median is above 1000.

If the trigger is not met:

1. In the `Per-packet timing log` table, in the row whose first cell is
   `L4`, replace the first `pending` cell with `skipped` and every other
   `pending` cell with `-`.
2. In `.cursor/plans/query_latency_repair_3f9c2a61.plan.md`, under the
   todo `id: l4-pipelined-append`, change `status: pending` to
   `status: cancelled`.
3. Commit only those two files as
   `docs(plan): L4 skipped, trigger not met`, push, and stop.

## Step 1 - gate probe (new file, then run it)

The API DSN goes through the Supavisor transaction pooler (port 6543).
Contract tests run on local Postgres in CI, so they cannot prove pooler
behavior. This probe runs **inside the rebuilt `api` container**, where
`SUPABASE_DB_URL` is the pooler DSN.

File: `scripts/probe_pipeline_pooler.py`

Full contents:

```python
"""Probe psycopg pipeline mode through the API's Supabase pooler DSN.

Run inside the rebuilt ``api`` container by piping this file to
``python -``. Prints millisecond timings and one PASS/FAIL line per check.
Never prints the DSN, row values other than the checked ones, or exception
text. Exits 1 when any check fails.
"""

from __future__ import annotations

import os
import statistics
import sys
import time

import psycopg

ITERATIONS = 10
PROBE_SQL = "SELECT current_user, current_setting('lock_timeout'), %s::int"


def _elapsed_ms(started: float) -> float:
    """Return milliseconds since ``started``.

    Args:
        started: A ``time.perf_counter()`` value.

    Returns:
        Elapsed milliseconds.
    """

    return (time.perf_counter() - started) * 1000.0


def _sequential(connection: psycopg.Connection) -> list[float]:
    """Time the L2 three-round-trip transaction ``ITERATIONS`` times.

    Args:
        connection: Open login-role connection with autocommit off.

    Returns:
        Milliseconds per transaction.
    """

    timings: list[float] = []
    for _ in range(ITERATIONS):
        started = time.perf_counter()
        connection.execute("SET LOCAL ROLE app_api; SET LOCAL lock_timeout TO '2s'")
        connection.execute(PROBE_SQL, (1,)).fetchone()
        connection.commit()
        timings.append(_elapsed_ms(started))
    return timings


def _pipelined(connection: psycopg.Connection) -> tuple[list[float], bool]:
    """Time the pipelined transaction and check its role and timeout.

    Args:
        connection: Open login-role connection with autocommit off.

    Returns:
        Milliseconds per transaction, and whether every row was
        ``("app_api", "2s", 1)``.
    """

    timings: list[float] = []
    rows_ok = True
    for _ in range(ITERATIONS):
        started = time.perf_counter()
        with connection.pipeline():
            connection.execute("SET LOCAL ROLE app_api")
            connection.execute("SET LOCAL lock_timeout TO '2s'")
            cursor = connection.execute(PROBE_SQL, (1,))
            connection.commit()
        row = cursor.fetchone()
        timings.append(_elapsed_ms(started))
        rows_ok = rows_ok and row == ("app_api", "2s", 1)
    return timings, rows_ok


def _scope_ends_at_commit(connection: psycopg.Connection) -> bool:
    """Check that role and lock timeout do not survive the commit.

    Args:
        connection: Connection whose last transaction was pipelined.

    Returns:
        True when the next transaction runs as the login role without the
        two-second lock timeout.
    """

    row = connection.execute(
        "SELECT current_user, current_setting('lock_timeout')"
    ).fetchone()
    connection.commit()
    return row is not None and row[0] != "app_api" and row[1] != "2s"


def _error_path(connection: psycopg.Connection) -> bool:
    """Check that a failing pipelined statement raises and can be rolled back.

    Args:
        connection: Open login-role connection with autocommit off.

    Returns:
        True when ``DivisionByZero`` is raised and ``SELECT 1`` works after
        rollback.
    """

    raised = False
    try:
        with connection.pipeline():
            connection.execute("SET LOCAL ROLE app_api")
            connection.execute("SET LOCAL lock_timeout TO '2s'")
            connection.execute("SELECT 1/0")
            connection.commit()
    except psycopg.errors.DivisionByZero:
        raised = True
    connection.rollback()
    recovered = connection.execute("SELECT 1").fetchone() == (1,)
    connection.commit()
    return raised and recovered


def main() -> int:
    """Run every check and print the results.

    Returns:
        Process exit code: 0 when every check passes, else 1.
    """

    connection = psycopg.connect(
        os.environ["SUPABASE_DB_URL"], prepare_threshold=None, connect_timeout=10
    )
    try:
        connection.execute("SELECT 1").fetchone()
        connection.commit()
        sequential = statistics.median(_sequential(connection))
        pipelined_times, rows_ok = _pipelined(connection)
        pipelined = statistics.median(pipelined_times)
        checks = {
            "pipelined_rows": rows_ok,
            "scope_ends_at_commit": _scope_ends_at_commit(connection),
            "error_path": _error_path(connection),
            "pipelined_at_most_0_6_of_sequential": pipelined <= 0.6 * sequential,
        }
    finally:
        connection.close()
    print(f"sequential_ms_median={sequential:.1f}")
    print(f"pipelined_ms_median={pipelined:.1f}")
    print(f"ratio={pipelined / sequential:.2f}")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
```

Run it:

```powershell
uv run python -m ruff format scripts/probe_pipeline_pooler.py
uv run python scripts/check.py --tier lint
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --build --wait api
Get-Content scripts/probe_pipeline_pooler.py -Raw | docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml exec -T api python -
```

Expected: 3 number lines, then 4 lines that all start with `PASS`, exit
code 0.

If any line starts with `FAIL`, or the command exits non-zero:

1. Append to the end of `docs/evaluation/QUERY_LATENCY_REPAIR_EVIDENCE.md`
   a section `## L4 pooler probe` with the 7 printed lines in a `text`
   code block and the sentence `Gate failed; L4 code not applied.`
2. Replace the `pending` cells of the `L4` row as in Step 0 (first cell
   `gate failed`).
3. Commit only `scripts/probe_pipeline_pooler.py` and the evidence doc as
   `test(sse): pipeline pooler probe, gate failed (L4)`, push, report the
   7 lines to the user, and stop. Do not apply Edits 1-4.

## Files this packet edits (only after the gate passes)

| # | File |
| - | ---- |
| 0 | `scripts/probe_pipeline_pooler.py` (new, Step 1) |
| 1 | `packages/core/src/smart_rag_core/sse/store.py` |
| 2 | `tests/unit/test_query_sse_event_store.py` (one fixture) |
| 3 | `tests/unit/test_query_sse_event_store_pipeline.py` (new) |
| 4 | `docs/api/SSE.md` |
| 5 | `docs/evaluation/QUERY_LATENCY_REPAIR_EVIDENCE.md` (after the live proof) |

## Edit 1 - `store.py`

File: `packages/core/src/smart_rag_core/sse/store.py`

1a. Find (exactly once):

```python
from typing import NoReturn, Protocol
```

Replace with:

```python
from typing import Any, LiteralString, NoReturn, Protocol
```

1b. Find (exactly once):

```python
EVENT_STORE_LOCK_TIMEOUT_SQL = "SET LOCAL lock_timeout TO '2s'"
```

Replace with:

```python
EVENT_STORE_LOCK_TIMEOUT_SQL: LiteralString = "SET LOCAL lock_timeout TO '2s'"
```

1c. Find (exactly once):

```python
multi-statement strings with the simple query protocol."""
EVENT_STORE_IDLE_SECONDS = 60.0
```

Replace with:

```python
multi-statement strings with the simple query protocol."""
EVENT_STORE_ROLE_SQL: LiteralString = "SET LOCAL ROLE app_api"
"""Role step as its own statement; pipeline mode rejects multi-statement strings."""
EVENT_STORE_APPEND_PIPELINED = True
"""Send role, lock timeout, RPC, and commit of ``append`` and replay as one
psycopg pipeline (about one network round trip instead of three). False
restores the ``_transaction`` path."""
APPEND_RUN_EVENT_SQL: LiteralString = """
SELECT run_id, sequence, event_type, payload, created_at
FROM app.append_run_event(
    %s::uuid, %s::text, %s::bigint, %s::uuid, %s::text, %s::jsonb
)
"""
LIST_RUN_EVENTS_AFTER_SQL: LiteralString = """
SELECT run_id, sequence, event_type, payload, created_at
FROM app.list_run_events_after(
    %s::uuid, %s::text, %s::bigint, %s::uuid, %s::bigint
)
"""
EVENT_STORE_IDLE_SECONDS = 60.0
```

1d. Add the pipelined helper. Find (exactly once):

```python
        finally:
            self._pool.release(connection, reusable=reusable)

    def probe(self) -> None:
```

Replace with:

```python
        finally:
            self._pool.release(connection, reusable=reusable)

    def _pipelined_rows(
        self, sql: LiteralString, params: tuple[object, ...]
    ) -> list[tuple[Any, ...]]:
        """Run one RPC in its own transaction as a single psycopg pipeline.

        Role, lock timeout, the RPC, and ``COMMIT`` are sent together, so
        the transaction costs about one network round trip. Role and lock
        timeout are ``SET LOCAL`` exactly as in ``_transaction``. Errors
        surface at the commit sync; any error rolls back best-effort,
        closes that session, and re-raises. Callers must not replay an
        append.

        Args:
            sql: Parameterized RPC statement.
            params: Bound parameters for ``sql``.

        Returns:
            Rows returned by the RPC, read after the pipeline synced.

        Raises:
            QueryAdmissionError: ``event_store_busy`` when no pooled session
                frees up within ``EVENT_STORE_POOL_WAIT_SECONDS``.
            psycopg.Error: Connection, role, RPC, commit, or rollback failure.
        """

        try:
            connection = self._pool.acquire()
        except PoolBusyError as exc:
            raise QueryAdmissionError("event_store_busy") from exc
        reusable = False
        try:
            with connection.pipeline():
                connection.execute(EVENT_STORE_ROLE_SQL)
                connection.execute(EVENT_STORE_LOCK_TIMEOUT_SQL)
                cursor = connection.execute(sql, params)
                connection.commit()
            rows = cursor.fetchall()
            reusable = True
            return rows
        except BaseException:
            try:
                connection.rollback()
            except Exception:
                LOGGER.info(
                    "event store rollback failed",
                    extra={
                        "operation": "event_store_rollback",
                        "attempt": 1,
                        "reason": "rollback_failed",
                    },
                )
            raise
        finally:
            self._pool.release(connection, reusable=reusable)

    def probe(self) -> None:
```

1e. `append`. Find (exactly once):

```python
        validated = validate_sse_payload(event_type, payload)
        try:
            with self._transaction() as connection:
                row = connection.execute(
                    """
                    SELECT run_id, sequence, event_type, payload, created_at
                    FROM app.append_run_event(
                        %s::uuid, %s::text, %s::bigint, %s::uuid, %s::text, %s::jsonb
                    )
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        run_id,
                        event_type,
                        Json(validated),
                    ),
                ).fetchone()
        except psycopg.Error as exc:
```

Replace with:

```python
        validated = validate_sse_payload(event_type, payload)
        params: tuple[object, ...] = (
            caller.user_id,
            caller.rpc_role(),
            caller.rpc_authorization_version(),
            run_id,
            event_type,
            Json(validated),
        )
        try:
            if EVENT_STORE_APPEND_PIPELINED:
                rows = self._pipelined_rows(APPEND_RUN_EVENT_SQL, params)
                row = rows[0] if len(rows) == 1 else None
            else:
                with self._transaction() as connection:
                    row = connection.execute(APPEND_RUN_EVENT_SQL, params).fetchone()
        except psycopg.Error as exc:
```

1f. `append` docstring. Find (exactly once):

```python
        """Persist through ``app.append_run_event``.

        Args:
```

Replace with:

```python
        """Persist through ``app.append_run_event``.

        With ``EVENT_STORE_APPEND_PIPELINED`` the transaction is one psycopg
        pipeline (about one round trip). Never replayed after an error.

        Args:
```

1g. `_list_after_once`. Find (exactly once):

```python
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT run_id, sequence, event_type, payload, created_at
                FROM app.list_run_events_after(
                    %s::uuid, %s::text, %s::bigint, %s::uuid, %s::bigint
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                    after,
                ),
            ).fetchall()
```

Replace with:

```python
        params: tuple[object, ...] = (
            caller.user_id,
            caller.rpc_role(),
            caller.rpc_authorization_version(),
            run_id,
            after,
        )
        if EVENT_STORE_APPEND_PIPELINED:
            rows = self._pipelined_rows(LIST_RUN_EVENTS_AFTER_SQL, params)
        else:
            with self._transaction() as connection:
                rows = connection.execute(LIST_RUN_EVENTS_AFTER_SQL, params).fetchall()
```

1h. `_list_after_once` docstring. Find (exactly once):

```python
        """Run one read-only replay RPC.

        Args:
```

Replace with:

```python
        """Run one read-only replay RPC.

        Uses one psycopg pipeline when ``EVENT_STORE_APPEND_PIPELINED``.

        Args:
```

After Edit 1: `rg -n "FROM app.append_run_event\(" packages/core/src/smart_rag_core/sse/store.py`
prints exactly one line (inside `APPEND_RUN_EVENT_SQL`).

## Edit 2 - keep the L2 fakes on the old path

File: `tests/unit/test_query_sse_event_store.py`

The L2 tests use fake connections without `pipeline()`. They keep testing
the `_transaction` path; the new file in Edit 3 tests the pipeline path.

Find (exactly once):

```python
from tests.unit.typed_attrs import typed_attr


def test_postgres_event_store_reuses_and_closes_session(monkeypatch: Any) -> None:
```

Replace with:

```python
from tests.unit.typed_attrs import typed_attr


@pytest.fixture(autouse=True)
def use_transaction_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run this module's fakes on the ``_transaction`` path.

    Pipeline-mode behavior is tested in
    ``test_query_sse_event_store_pipeline.py``.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """

    monkeypatch.setattr(sse_store_mod, "EVENT_STORE_APPEND_PIPELINED", False)


def test_postgres_event_store_reuses_and_closes_session(monkeypatch: Any) -> None:
```

## Edit 3 - new file `tests/unit/test_query_sse_event_store_pipeline.py`

File: `tests/unit/test_query_sse_event_store_pipeline.py`

Full contents:

```python
"""Pipelined event-store transactions: one round trip per append or replay."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.sse import store as sse_store_mod
from smart_rag_core.sse.store import (
    APPEND_RUN_EVENT_SQL,
    EVENT_STORE_LOCK_TIMEOUT_SQL,
    EVENT_STORE_ROLE_SQL,
    EVENT_STORE_SESSION_SQL,
    LIST_RUN_EVENTS_AFTER_SQL,
    PostgresRunEventStore,
)

from tests.unit.typed_attrs import typed_attr


class _LockTimeout(psycopg.OperationalError):
    """Driver error carrying the lock-timeout SQLSTATE."""

    @property
    def sqlstate(self) -> str:
        """Return the lock-not-available SQLSTATE.

        Returns:
            ``55P03``.
        """

        return "55P03"


class _Connection:
    """Fake psycopg connection that records statements and pipeline use."""

    def __init__(
        self,
        rows: list[tuple[Any, ...]],
        *,
        commit_error: Exception | None = None,
    ) -> None:
        """Configure the fake.

        Args:
            rows: Rows every cursor returns.
            commit_error: Raised by ``commit`` when set.
        """

        self.rows = rows
        self.commit_error = commit_error
        self.closed = False
        self.in_pipeline = False
        self.calls: list[str] = []

    @contextmanager
    def pipeline(self) -> Generator[None, None, None]:
        """Record pipeline entry and exit.

        Yields:
            None while the pipeline is open.
        """

        self.calls.append("PIPELINE")
        self.in_pipeline = True
        try:
            yield
        finally:
            self.in_pipeline = False
            self.calls.append("END_PIPELINE")

    def execute(self, statement: str, params: object = None) -> _Cursor:
        """Record one statement.

        Args:
            statement: SQL text.
            params: Bound parameters (unused).

        Returns:
            Cursor over the configured rows.
        """

        del params
        self.calls.append(statement)
        return _Cursor(self)

    def commit(self) -> None:
        """Record commit and raise the configured error, if any.

        Raises:
            Exception: ``commit_error`` when configured.
        """

        self.calls.append("COMMIT")
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        """Record rollback."""

        self.calls.append("ROLLBACK")

    def close(self) -> None:
        """Mark the connection closed."""

        self.closed = True
        self.calls.append("CLOSE")


class _Cursor:
    """Cursor stand-in that records whether rows are read inside a pipeline."""

    def __init__(self, connection: _Connection) -> None:
        """Keep the owning connection.

        Args:
            connection: Fake connection.
        """

        self._connection = connection

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Return all rows and record the read.

        Returns:
            Configured rows.
        """

        self._connection.calls.append(
            "FETCH_IN_PIPELINE" if self._connection.in_pipeline else "FETCH"
        )
        return self._connection.rows

    def fetchone(self) -> tuple[Any, ...] | None:
        """Return the first row and record the read.

        Returns:
            First configured row, or None.
        """

        rows = self.fetchall()
        return rows[0] if rows else None


def _row(sequence: int) -> tuple[Any, ...]:
    """Return one RPC result row.

    Args:
        sequence: Event sequence.

    Returns:
        ``(run_id, sequence, event_type, payload, created_at)``.
    """

    return (uuid4(), sequence, "schema", {"sse_schema_version": "1"}, datetime.now(UTC))


def _caller() -> CallerContext:
    """Return a member caller.

    Returns:
        Caller context.
    """

    return CallerContext(
        user_id=str(uuid4()), role=UserRole.MEMBER, authorization_version=1
    )


def _store(
    monkeypatch: pytest.MonkeyPatch, connection: _Connection
) -> PostgresRunEventStore:
    """Build a pipelined store whose pool always connects to ``connection``.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        connection: Fake connection to lend.

    Returns:
        Store with pipeline mode on.
    """

    monkeypatch.setattr(sse_store_mod, "EVENT_STORE_APPEND_PIPELINED", True)

    def _connect(url: str, **kwargs: object) -> object:
        """Return the fake connection.

        Args:
            url: DSN (unused).
            **kwargs: Driver kwargs (unused).

        Returns:
            Fake connection.
        """

        del url, kwargs
        connection.closed = False
        return connection

    monkeypatch.setattr(
        "smart_rag_core.settings.postgres_connect.psycopg.connect", _connect
    )
    return PostgresRunEventStore("postgresql://hosted")


def test_pipelined_append_sends_role_lock_rpc_commit_in_one_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Append sends four steps in one pipeline and reads the row afterwards."""

    connection = _Connection([_row(1)])
    store = _store(monkeypatch, connection)
    persisted = store.append(
        _caller(),
        run_id=uuid4(),
        event_type="schema",
        payload={"sse_schema_version": "1"},
    )
    assert connection.calls == [
        "PIPELINE",
        EVENT_STORE_ROLE_SQL,
        EVENT_STORE_LOCK_TIMEOUT_SQL,
        APPEND_RUN_EVENT_SQL,
        "COMMIT",
        "END_PIPELINE",
        "FETCH",
    ]
    assert persisted.sequence == 1
    assert typed_attr(store, "_pool").idle_count() == 1
    store.close()


def test_pipelined_list_after_same_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay uses the same pipelined sequence with the list RPC."""

    connection = _Connection([_row(1), _row(2)])
    store = _store(monkeypatch, connection)
    events = store.list_after(_caller(), run_id=uuid4(), after=0)
    assert connection.calls == [
        "PIPELINE",
        EVENT_STORE_ROLE_SQL,
        EVENT_STORE_LOCK_TIMEOUT_SQL,
        LIST_RUN_EVENTS_AFTER_SQL,
        "COMMIT",
        "END_PIPELINE",
        "FETCH",
    ]
    assert [event.sequence for event in events] == [1, 2]
    store.close()


def test_pipelined_append_error_discards_connection_without_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lock timeout at the commit sync maps, rolls back, and closes once."""

    connection = _Connection([_row(1)], commit_error=_LockTimeout())
    store = _store(monkeypatch, connection)
    with pytest.raises(QueryAdmissionError) as failure:
        store.append(
            _caller(),
            run_id=uuid4(),
            event_type="schema",
            payload={"sse_schema_version": "1"},
        )
    assert failure.value.reason == "lock_timeout"
    assert connection.calls.count(APPEND_RUN_EVENT_SQL) == 1
    assert "ROLLBACK" in connection.calls
    assert connection.closed is True
    assert typed_attr(store, "_pool").idle_count() == 0


def test_pipeline_flag_off_uses_transaction_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the flag off, append uses the L2 transaction without a pipeline."""

    connection = _Connection([_row(1)])
    store = _store(monkeypatch, connection)
    monkeypatch.setattr(sse_store_mod, "EVENT_STORE_APPEND_PIPELINED", False)
    store.append(
        _caller(),
        run_id=uuid4(),
        event_type="schema",
        payload={"sse_schema_version": "1"},
    )
    assert "PIPELINE" not in connection.calls
    assert connection.calls[:2] == [EVENT_STORE_SESSION_SQL, APPEND_RUN_EVENT_SQL]
    assert connection.calls[-1] == "COMMIT"
    store.close()
```

## Edit 4 - `docs/api/SSE.md`

File: `docs/api/SSE.md`

Find (exactly once):

```markdown
free session gets `event_store_busy`, which the append path logs and
handles like `lock_timeout`.
```

Replace with:

```markdown
free session gets `event_store_busy`, which the append path logs and
handles like `lock_timeout`.

Since latency packet L4, `append` and replay send `SET LOCAL ROLE app_api`,
`SET LOCAL lock_timeout TO '2s'`, the RPC, and `COMMIT` as one psycopg
pipeline, so a transaction costs about one network round trip instead of
three. Role and timeout scope, error mapping, discard-on-error, and "never
replay an append" are unchanged. `get_authorized_run` and `mark_running`
keep the three-step transaction. `scripts/probe_pipeline_pooler.py`, run
inside the `api` container, proves the behavior through the Supavisor
transaction pooler. Set `EVENT_STORE_APPEND_PIPELINED = False` in
`smart_rag_core.sse.store` to switch back.
```

## Commands (run all; each must exit 0)

```powershell
uv run python -m ruff format packages/core/src/smart_rag_core/sse/store.py scripts/probe_pipeline_pooler.py tests/unit/test_query_sse_event_store.py tests/unit/test_query_sse_event_store_pipeline.py
uv run python -m ruff check --select I --fix packages/core/src/smart_rag_core/sse/store.py scripts/probe_pipeline_pooler.py tests/unit/test_query_sse_event_store.py tests/unit/test_query_sse_event_store_pipeline.py
uv run python -m pytest tests/unit/test_query_sse_event_store.py tests/unit/test_query_sse_event_store_pipeline.py tests/unit/test_query_sse_lifecycle.py tests/unit/test_query_sse_event_writer.py
uv run python -m pytest tests/contract/test_sse_run_lock.py tests/contract/test_sse_resume.py
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier format
uv run python scripts/check.py --tier docs
```

Expected (dry run 2026-09-24 with L0-L3 applied): the first pytest line
prints `39 passed`; types prints `0 errors`; the word `failed` does not
appear. The contract
line skips without a local database; the CI `contract` job must run it
(check its log for `test_sse_run_lock.py`). If CI skipped it too, write
"run-lock contract skipped in CI" in the report; do not claim it passed.

## Live proof

1. Before numbers: the `L3-after` report.
2. Rebuild, run the pooler probe again (all `PASS`), run the image probe
   (`L4 present`).
3. Timing run `L4-after`, then
   `uv run python scripts/eval_latency_report.py compare .private-eval/runs/L3-after/latency.json .private-eval/runs/L4-after/latency.json`.
4. Collect `sse.writer_summary` lines as in L3 step 5.
5. Expected: median `append_ms_p50` 150 or less; the targeted
   `metrics.event_spacing_median_s.median` lower than `L3-after`;
   `metrics.wall_seconds.median` not higher than `L3-after` by more than
   the noise band. Otherwise stop and report.
6. Evidence doc: fill the `L4` row as described in L3 Edit 8a (targeted
   metric `event_spacing_median_s`), and append to the end of the file:

   ```markdown
   ## L4 pooler probe and writer summaries

   | `sequential_ms_median` | `pipelined_ms_median` | `append_ms_p50` median | `flush_ms_max` median |
   | ---------------------: | --------------------: | ---------------------: | --------------------: |
   | pending | pending | pending | pending |
   ```

   then replace the four `pending` cells with the numbers (one decimal).

## Done when

- [ ] Trigger values recorded; the gate probe prints 4 `PASS` lines
      inside the container.
- [ ] Edits 1-4 applied exactly; the Edit 1 `rg` check prints one line.
- [ ] 4 new pipeline tests pass; every L2 event-store test passes
      unchanged apart from the Edit 2 fixture.
- [ ] Unit, lint, types, format, docs tiers pass; CI contract job ran
      `test_sse_run_lock.py` (or the skip is recorded).
- [ ] `L4-after` compare pasted; L4 row and probe table filled.
- [ ] Committed and pushed; `gh pr checks --watch --fail-fast` exit 0.

## Commit

```text
perf(sse): one pipelined round trip per event-store transaction (L4)
```

## Do not

- Do not pipeline more than one event per transaction.
- Do not use autocommit.
- Do not pipeline `get_authorized_run`, `mark_running`, or `probe`.
- Do not run the probe against the operator or session-pooler DSN; it
  must use the container's `SUPABASE_DB_URL`.
