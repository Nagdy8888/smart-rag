"""Run-local reservation consume and true-up RPCs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.query_admission.exceptions import (
    QueryAdmissionError,
    QueryBudgetError,
)
from smart_rag_core.query_admission.repository.errors import raise_admission
from smart_rag_core.security.identity import CallerContext


@dataclass(frozen=True, slots=True)
class ReservationConsumeResult:
    """Optimistic consume outcome for one counted gateway call."""

    reservation_id: UUID
    optimistic_version: int
    remaining_usd: Decimal
    remaining_prompt_tokens: int
    remaining_completion_tokens: int


@dataclass(frozen=True, slots=True)
class TrueUpResult:
    """Idempotent settlement of one query reservation."""

    reservation_id: UUID
    status: str
    committed_amount_usd: Decimal
    already_settled: bool


def consume_query_reservation(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    reservation_id: UUID,
    expected_version: int,
    amount_usd: Decimal,
    prompt_tokens: int,
    completion_tokens: int,
) -> ReservationConsumeResult:
    """Atomically consume run-local remaining USD and tokens.

    The SQL updates only ``app.budget_reservations`` by id and optimistic
    version. It does not lock ``company_settings`` or ``profiles``.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner of the run.
        reservation_id: Run-local reservation.
        expected_version: Optimistic version from the previous consume/admit.
        amount_usd: USD to deduct (estimated/max cap).
        prompt_tokens: Prompt tokens to deduct.
        completion_tokens: Completion tokens to deduct.

    Returns:
        New optimistic version and remaining holds.

    Raises:
        QueryBudgetError: On version conflict or insufficient remaining.

    Side Effects:
        Decrements remaining holds and increments ``optimistic_version``.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.consume_query_reservation(
                  %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    reservation_id,
                    expected_version,
                    amount_usd,
                    prompt_tokens,
                    completion_tokens,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        raise_admission(exc)
    if row is None:
        raise QueryBudgetError("consume_returned_no_row")
    return ReservationConsumeResult(
        reservation_id=row["reservation_id"],
        optimistic_version=int(row["optimistic_version"]),
        remaining_usd=Decimal(str(row["remaining_usd"])),
        remaining_prompt_tokens=int(row["remaining_prompt_tokens"]),
        remaining_completion_tokens=int(row["remaining_completion_tokens"]),
    )


def true_up_query_reservation(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    reservation_id: UUID,
) -> TrueUpResult:
    """Settle one reservation to the sum of immutable usage.

    A second call is an idempotent no-op.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner of the run.
        reservation_id: Reservation to settle.

    Returns:
        Committed amount and whether this call was already settled.

    Raises:
        QueryAdmissionError: When authorization fails.

    Side Effects:
        Sets reservation status to ``committed`` or ``released`` and stores
        ``committed_amount_usd``. Does not relock company/user budget rows.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.true_up_query_reservation(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    reservation_id,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("true_up_returned_no_row")
    return TrueUpResult(
        reservation_id=row["reservation_id"],
        status=str(row["status"]),
        committed_amount_usd=Decimal(str(row["committed_amount_usd"])),
        already_settled=bool(row["already_settled"]),
    )
