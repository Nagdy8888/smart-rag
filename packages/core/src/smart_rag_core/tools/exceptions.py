"""Typed failures for optional-tool registry, disclosure, and execution."""

from __future__ import annotations


class ToolError(RuntimeError):
    """Raised when optional-tool disclosure or execution fails closed.

    Attributes:
        reason: Stable machine-readable code. Never a secret, catalog name
            of a hidden tool, or answer claim.
    """

    def __init__(self, reason: str) -> None:
        """Store one optional-tool reason code.

        Args:
            reason: Short identifier returned to graph state and tests.
        """

        super().__init__(reason)
        self.reason = reason
