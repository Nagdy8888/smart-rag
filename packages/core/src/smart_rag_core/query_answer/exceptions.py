"""Typed failures for answer generation and verification."""

from __future__ import annotations


class AnswerError(RuntimeError):
    """Raised when answer assembly, generation, or verification fails closed.

    Attributes:
        reason: Stable machine-readable code. Never a secret.
    """

    def __init__(self, reason: str) -> None:
        """Store one answer-path reason code.

        Args:
            reason: Short identifier returned to graph state and tests.
        """

        super().__init__(reason)
        self.reason = reason
