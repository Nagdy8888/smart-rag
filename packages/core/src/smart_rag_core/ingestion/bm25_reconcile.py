"""Pure BM25 outbox reconcile decisions.

A verified ParadeDB projection must not sit in ``processing`` forever after a
worker crash between upsert and ``complete()``. Hybrid Ready is only finalized
when verify still holds and the version has not yet left a pre-hybrid status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from smart_rag_core.schema.enums import DocumentStatus, JobStatus

Bm25ReconcileAction = Literal["complete", "finalize_then_complete", "fail", "noop"]

_PRE_HYBRID_STATUSES = frozenset(
    {
        DocumentStatus.UPLOADING,
        DocumentStatus.UPLOADED,
        DocumentStatus.SCANNING,
        DocumentStatus.PARSING,
    }
)


@dataclass(frozen=True, slots=True)
class Bm25ReconcileDecision:
    """Closed reconcile action for one leased BM25 outbox row.

    Attributes:
        action: Worker-facing next step. ``complete`` never implies Hybrid Ready.
        reason: Stable machine-readable detail for logs and tests.
    """

    action: Bm25ReconcileAction
    reason: str


def decide_bm25_reconcile(
    *,
    job_status: str,
    job_operation: str,
    verify_passed: bool,
    version_status: str | None,
) -> Bm25ReconcileDecision:
    """Decide how to repair one leased BM25 outbox row.

    Args:
        job_status: Current ``app.job_status`` value.
        job_operation: ``upsert`` or ``delete``.
        verify_passed: True only when the Hybrid Ready ParadeDB contract still
            holds (ID/hash/index version / sample query, or delete absence).
        version_status: Public ``app.document_status`` when known.

    Returns:
        Decision. ``fail`` never finalizes Hybrid Ready. ``complete`` is a
        no-op relative to document status when the version is already past
        parsing. ``finalize_then_complete`` is the only path that may call
        ``finalize_hybrid_ready``.
    """

    if job_status == JobStatus.COMPLETED.value:
        return Bm25ReconcileDecision(action="noop", reason="already_completed")
    if job_status != JobStatus.PROCESSING.value:
        return Bm25ReconcileDecision(action="noop", reason="not_processing")
    if not verify_passed:
        return Bm25ReconcileDecision(action="fail", reason="verification_failed")
    if job_operation == "delete":
        return Bm25ReconcileDecision(action="complete", reason="delete_verified")
    if version_status is None:
        return Bm25ReconcileDecision(action="fail", reason="version_missing")
    if version_status in {item.value for item in _PRE_HYBRID_STATUSES}:
        return Bm25ReconcileDecision(
            action="finalize_then_complete",
            reason="verify_passed_needs_finalize",
        )
    return Bm25ReconcileDecision(
        action="complete", reason="verify_passed_already_final"
    )
