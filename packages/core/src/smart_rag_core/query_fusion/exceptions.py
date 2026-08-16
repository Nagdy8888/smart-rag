"""Typed failures for Combined fusion and ablation."""

from __future__ import annotations


class FusionError(RuntimeError):
    """Raised when Combined fusion fails closed.

    Attributes:
        reason: Stable machine-readable code. Never a secret or answer claim.
    """

    def __init__(self, reason: str) -> None:
        """Store one fusion reason code.

        Args:
            reason: Short identifier returned to graph state and tests.
        """

        super().__init__(reason)
        self.reason = reason
