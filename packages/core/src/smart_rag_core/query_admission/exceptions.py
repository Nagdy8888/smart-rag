"""Typed failures for query admission, ceilings, and reservation consume."""

from __future__ import annotations


class QueryAdmissionError(RuntimeError):
    """Raised when authenticated query-run admission fails closed.

    Attributes:
        reason: Stable machine-readable code such as ``authorization_rejected``.
    """

    def __init__(self, reason: str) -> None:
        """Store one admission reason code.

        Args:
            reason: Short identifier returned to FastAPI/tests. Never a secret.
        """

        super().__init__(reason)
        self.reason = reason


class QueryBudgetError(QueryAdmissionError):
    """Raised when run-local reservation consume or settlement fails closed."""


class QueryCeilingError(QueryAdmissionError):
    """Raised when a deadline, recursion, model, or tool ceiling is exhausted."""


class TimeoutAfterSendError(RuntimeError):
    """Raised when a provider HTTP request was sent but the response was lost.

    Callers must still write immutable ``llm_usage`` using the estimated cap so
    timeout-after-send cannot under-count a billed attempt.
    """
