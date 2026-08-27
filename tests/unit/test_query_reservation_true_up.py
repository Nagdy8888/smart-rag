"""Unit tests for scheduled query reservation true-up enqueue."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from smart_rag_core.query_admission.service import (
    enqueue_query_reservation_true_up_job,
)


def test_enqueue_query_reservation_true_up_job_uses_hourly_key() -> None:
    """Hourly idempotency keys isolate true-up from the memory reaper."""

    captured: dict[str, Any] = {}
    job_id = uuid4()

    class _Cursor:
        """Capture INSERT parameters for the true-up job."""

        def __enter__(self) -> _Cursor:
            """Return this cursor.

            Returns:
                The same cursor instance.
            """

            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the context without suppressing exceptions."""

            return None

        def execute(self, sql: str, params: object = None) -> None:
            """Record SQL and bind parameters.

            Args:
                sql: Statement text.
                params: Positional bind values.
            """

            captured["sql"] = sql
            captured["params"] = params

        def fetchone(self) -> tuple[object, ...]:
            """Return a new job id.

            Returns:
                One-column identifier tuple.
            """

            return (job_id,)

    class _Connection:
        """Connection double that yields the capturing cursor."""

        def cursor(self) -> _Cursor:
            """Return the capturing cursor.

            Returns:
                Stub cursor.
            """

            return _Cursor()

    clock = datetime(2026, 8, 19, 14, 22, tzinfo=UTC)
    inserted = enqueue_query_reservation_true_up_job(
        _Connection(),  # type: ignore[arg-type]
        now=clock,
    )
    assert inserted == job_id
    params = captured["params"]
    assert isinstance(params, tuple)
    typed_params = cast(tuple[object, ...], params)
    assert typed_params[0] == "query_reservation_true_up:2026-08-19T14"
    assert "query_reservation_true_up" in str(captured["sql"])
    assert '"kind": "query_reservation_true_up"' in str(typed_params[1]) or (
        "query_reservation_true_up" in str(typed_params[1])
    )
