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


class GraphMappingError(JobRepositoryError):
    """Raised when canonical graph mapping cannot become Graph Ready."""

    def __init__(self, reason: str) -> None:
        """Initialize with a stable machine-readable mapping reason.

        Args:
            reason: Short reason such as ``vendor_not_processed`` or
                ``language_gate``.
        """

        super().__init__(reason)
        self.reason = reason


class GraphResolverError(JobRepositoryError):
    """Raised when query-time graph resolution cannot complete safely."""

    def __init__(self, reason: str) -> None:
        """Initialize with a stable machine-readable resolver reason.

        Args:
            reason: Short reason such as ``graph_deadline`` or
                ``hidden_keyword_or_answer_call``.
        """

        super().__init__(reason)
        self.reason = reason


class GraphWriterLostError(JobLeaseError):
    """Raised when the graph writer lease or session advisory lock is lost."""

    def __init__(self, reason: str) -> None:
        """Initialize with a stable machine-readable reason.

        Args:
            reason: Short reason such as ``advisory_lock_lost`` or
                ``writer_lease_lost``.
        """

        super().__init__(reason)
        self.reason = reason
