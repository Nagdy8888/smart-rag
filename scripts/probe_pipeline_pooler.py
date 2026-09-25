"""Probe psycopg pipeline mode through the API's Supabase pooler DSN.

Run inside the rebuilt ``api`` container by piping this file to
``python -``. Prints millisecond timings and one PASS/FAIL line per check.
Never prints the DSN, row values other than the checked ones, or exception
text. Exits 1 when any check fails.
"""

from __future__ import annotations

import statistics
import sys
import time

import psycopg
from smart_rag_core.settings.backend import BackendSettings
from smart_rag_core.settings.base import load_settings

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

    dsn = load_settings(BackendSettings).supabase_db_url
    if dsn is None:
        print("blocked=missing_dsn")
        return 1
    connection = psycopg.connect(
        dsn.get_secret_value(), prepare_threshold=None, connect_timeout=10
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
