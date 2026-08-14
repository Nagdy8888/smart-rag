"""Typed exceptions for durable job repositories."""

from __future__ import annotations


class JobRepositoryError(RuntimeError):
    """Base error for job persistence failures."""


class JobNotFoundError(JobRepositoryError):
    """Raised when a referenced job row does not exist."""


class JobLeaseError(JobRepositoryError):
    """Raised when lease ownership or token validation fails."""


class JobAdmissionError(JobRepositoryError):
    """Raised when enqueue is blocked by backpressure or budget admission."""

    def __init__(self, reason: str) -> None:
        """Initialize with a stable machine-readable reason code.

        Args:
            reason: Short reason identifier such as ``pending_cap`` or
                ``budget_exhausted``.
        """

        super().__init__(reason)
        self.reason = reason


class JobRetryNotAllowedError(JobRepositoryError):
    """Raised when a job is not in a retryable dead-letter, failed, or backoff state."""
