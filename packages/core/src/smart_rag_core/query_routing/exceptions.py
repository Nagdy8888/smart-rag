"""Typed failures for query preparation, routing, and correction."""

from __future__ import annotations


class QueryRoutingError(RuntimeError):
    """Raised when preparation, routing, or correction fails closed.

    Attributes:
        reason: Stable machine-readable code. Never a secret or answer claim.
    """

    def __init__(self, reason: str) -> None:
        """Store one routing reason code.

        Args:
            reason: Short identifier returned to graph state and tests.
        """

        super().__init__(reason)
        self.reason = reason
