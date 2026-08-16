"""Durable job queue repositories, admission, and lease helpers."""

from smart_rag_core.jobs.admission import JobAdmissionService
from smart_rag_core.jobs.backoff import compute_retry_delay_seconds
from smart_rag_core.jobs.dead_letter import DeadLetterService
from smart_rag_core.jobs.exceptions import (
    GraphWriterLostError,
    JobAdmissionError,
    JobLeaseError,
    JobNotFoundError,
    JobRepositoryError,
    JobRetryNotAllowedError,
)
from smart_rag_core.jobs.graph_metrics import GraphMetricsService, GraphQueueMetrics
from smart_rag_core.jobs.graph_writer import (
    GraphWriterGuard,
    graph_advisory_lock_keys,
)
from smart_rag_core.jobs.hybrid_enqueue import (
    enqueue_hybrid_index_job,
    hybrid_index_idempotency_key,
)
from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.jobs.ledger import JobOperationLedger
from smart_rag_core.jobs.lightrag_repository import LightragIndexJobRepository
from smart_rag_core.jobs.limits import (
    DEFAULT_DAILY_INGESTION_BUDGET_USD,
    GRAPH_HANDOFF_PAUSE_PENDING_INDEX,
    MAX_ESTIMATED_JOB_SIZE_BYTES,
    MAX_PENDING_INGESTION_JOBS,
)

__all__ = [
    "DEFAULT_DAILY_INGESTION_BUDGET_USD",
    "GRAPH_HANDOFF_PAUSE_PENDING_INDEX",
    "MAX_ESTIMATED_JOB_SIZE_BYTES",
    "MAX_PENDING_INGESTION_JOBS",
    "DeadLetterService",
    "GraphMetricsService",
    "GraphQueueMetrics",
    "GraphWriterGuard",
    "GraphWriterLostError",
    "IngestionJobRepository",
    "JobAdmissionError",
    "JobAdmissionService",
    "JobLeaseError",
    "JobNotFoundError",
    "JobOperationLedger",
    "JobRepositoryError",
    "JobRetryNotAllowedError",
    "LightragIndexJobRepository",
    "compute_retry_delay_seconds",
    "enqueue_hybrid_index_job",
    "graph_advisory_lock_keys",
    "hybrid_index_idempotency_key",
]
