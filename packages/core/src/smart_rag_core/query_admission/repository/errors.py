"""Map Postgres errors to typed query-admission failures."""

from __future__ import annotations

from typing import NoReturn

from smart_rag_core.query_admission.exceptions import (
    QueryAdmissionError,
    QueryBudgetError,
)

_REASON_PREFIX = "query_admission:"


def _raise_admission(exc: BaseException) -> NoReturn:
    """Map a Postgres exception to a typed admission/budget error.

    Args:
        exc: Driver or database error.

    Raises:
        QueryAdmissionError: Always, with a stable reason when the SQL
            message includes a ``query_admission:`` prefix.
    """

    message = str(exc)
    reason = "database_rejected"
    if _REASON_PREFIX in message:
        start = message.find(_REASON_PREFIX) + len(_REASON_PREFIX)
        tail = message[start:].split()[0].strip("\"'")
        reason = tail.split("\n")[0]
    if reason in {
        "optimistic_version_conflict",
        "reservation_exhausted",
        "reservation_not_active",
    }:
        raise QueryBudgetError(reason) from exc
    raise QueryAdmissionError(reason) from exc
