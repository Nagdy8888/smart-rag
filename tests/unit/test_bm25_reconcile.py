"""Unit tests for BM25 outbox reconcile decisions and verify-fail safety."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
from smart_rag_core.ingestion.bm25_reconcile import decide_bm25_reconcile
from smart_rag_core.schema.enums import DocumentStatus, JobStatus


def test_decide_completed_is_noop() -> None:
    """A second reconcile against a completed outbox row is a no-op."""

    decision = decide_bm25_reconcile(
        job_status=JobStatus.COMPLETED.value,
        job_operation="upsert",
        verify_passed=True,
        version_status=DocumentStatus.GRAPH_INELIGIBLE.value,
    )
    assert decision.action == "noop"
    assert decision.reason == "already_completed"


def test_decide_verify_fail_does_not_complete() -> None:
    """Failed ParadeDB verify must fail/retry, never complete or finalize."""

    decision = decide_bm25_reconcile(
        job_status=JobStatus.PROCESSING.value,
        job_operation="upsert",
        verify_passed=False,
        version_status=DocumentStatus.PARSING.value,
    )
    assert decision.action == "fail"
    assert decision.reason == "verification_failed"


def test_decide_parsing_after_verify_finalizes() -> None:
    """Crash before Hybrid Ready still finalizes only after verify holds."""

    decision = decide_bm25_reconcile(
        job_status=JobStatus.PROCESSING.value,
        job_operation="upsert",
        verify_passed=True,
        version_status=DocumentStatus.PARSING.value,
    )
    assert decision.action == "finalize_then_complete"


def test_decide_already_hybrid_family_completes_without_finalize() -> None:
    """Verified stuck jobs after Hybrid Ready complete without re-finalizing."""

    decision = decide_bm25_reconcile(
        job_status=JobStatus.PROCESSING.value,
        job_operation="upsert",
        verify_passed=True,
        version_status=DocumentStatus.GRAPH_INELIGIBLE.value,
    )
    assert decision.action == "complete"
    assert decision.reason == "verify_passed_already_final"


def test_decide_delete_verified_completes() -> None:
    """Delete reconcile completes only when ParadeDB absence verified."""

    passed = decide_bm25_reconcile(
        job_status=JobStatus.PROCESSING.value,
        job_operation="delete",
        verify_passed=True,
        version_status=None,
    )
    failed = decide_bm25_reconcile(
        job_status=JobStatus.PROCESSING.value,
        job_operation="delete",
        verify_passed=False,
        version_status=None,
    )
    assert passed.action == "complete"
    assert failed.action == "fail"


def _service_with_verifier(
    *, passed: bool, status: str
) -> tuple[Bm25ProjectionService, MagicMock]:
    """Build a service whose verifier and version-status query are fakes.

    Args:
        passed: Whether ``verify_version`` reports success.
        status: Public document-version status returned by the status SELECT.

    Returns:
        Service plus the mocked cursor used to detect finalize SQL.
    """

    supabase = MagicMock()
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchone.return_value = (status,)
    supabase.cursor.return_value = cursor
    service = Bm25ProjectionService(supabase, MagicMock())

    class _Verifier:
        """Stub BM25 verifier that returns a fixed pass/fail result."""

        def verify_version(self, _version_id: object) -> object:
            """Return a MagicMock whose ``passed`` flag matches the fixture.

            Args:
                _version_id: Unused document version identifier.

            Returns:
                Stub verification result with ``passed`` set.
            """

            result = MagicMock()
            result.passed = passed
            return result

    service._verifier = _Verifier()  # type: ignore[method-assign]
    return service, cursor


def _finalize_sql(cursor: MagicMock) -> tuple[str, ...]:
    """Return SQL strings passed to ``cursor.execute``."""

    statements: list[str] = []
    for call in cursor.execute.call_args_list:
        if call.args:
            statements.append(str(call.args[0]))
    return tuple(statements)


def test_reconcile_upsert_verify_fail_does_not_finalize() -> None:
    """Service reconcile must not call finalize_hybrid_ready when verify fails."""

    service, cursor = _service_with_verifier(
        passed=False, status=DocumentStatus.PARSING.value
    )
    outcome = service.reconcile_upsert_job(version_id=uuid4(), job_id=uuid4())
    assert outcome.action == "fail"
    assert all("finalize_hybrid_ready" not in sql for sql in _finalize_sql(cursor))


def test_reconcile_upsert_already_final_does_not_finalize() -> None:
    """Verified Hybrid-family versions complete without a second finalize."""

    service, cursor = _service_with_verifier(
        passed=True, status=DocumentStatus.GRAPH_INELIGIBLE.value
    )
    first = service.reconcile_upsert_job(version_id=uuid4(), job_id=uuid4())
    second = decide_bm25_reconcile(
        job_status=JobStatus.COMPLETED.value,
        job_operation="upsert",
        verify_passed=True,
        version_status=DocumentStatus.GRAPH_INELIGIBLE.value,
    )
    assert first.action == "complete"
    assert all("finalize_hybrid_ready" not in sql for sql in _finalize_sql(cursor))
    assert second.action == "noop"
