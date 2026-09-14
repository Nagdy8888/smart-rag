"""Exam HTTP contract: 202 start, poll, cancel, split-isolated latest (P06-32)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from smart_rag_api.dependencies.services import get_postgres_url
from smart_rag_api.main import create_app
from smart_rag_api.routers.pdf_eval import get_exam_repository, get_pdf_eval_service
from smart_rag_api.services.pdf_eval_workspace import PdfEvalWorkspaceService
from smart_rag_core.evaluation.private_pdf.exam_repository import (
    ExamEnqueueResult,
    ExamLatestReport,
    ExamReportCase,
    ExamRepositoryError,
    ExamRunStatus,
)
from smart_rag_core.evaluation.private_pdf.quiz_repository import QuizStatusCounts
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext

from tests.unit.typed_openapi import (
    as_openapi_client,
    json_object,
    permit_test_identity,
)

_OWNER = "00000000-0000-4000-8000-000000000001"
_MEMBER = "00000000-0000-4000-8000-000000000002"
_EXAM = UUID("bbbbbbbb-0000-4000-8000-000000000001")
_CASE = UUID("cccccccc-0000-4000-8000-000000000001")
_CANARY = "CANARY_EXPECTED_ANSWER_SECRET"
_PRIVATE_NAMES = frozenset(
    {
        "question",
        "expected_answer",
        "atomic_facts",
        "ranked_ids",
        "excerpt",
        "gold",
        "conversation_id",
    }
)


def _noop_rate_limit(*args: object, **kwargs: object) -> None:
    """Skip FastAPI-owned limiter in isolated HTTP tests.

    Args:
        *args: Ignored.
        **kwargs: Ignored.
    """

    del args, kwargs


def _identity(user_id: str, role: str) -> dict[str, str]:
    """Return test identity headers.

    Args:
        user_id: Subject UUID.
        role: Role label.

    Returns:
        Header mapping.
    """

    return {
        "X-Test-User-Id": user_id,
        "X-Test-Role": role,
        "X-Test-Authorization-Version": "1",
    }


def _assert_public(payload: object) -> None:
    """Fail when a private field name appears in JSON.

    Args:
        payload: Parsed JSON.

    Raises:
        AssertionError: Private name present.
    """

    if isinstance(payload, dict):
        typed = cast(dict[str, object], payload)
        assert set(typed).isdisjoint(_PRIVATE_NAMES)
        assert _CANARY not in str(typed)
        for value in typed.values():
            _assert_public(value)
        return
    if isinstance(payload, list):
        for item in cast(list[object], payload):
            _assert_public(item)


class _FakeExams:
    """In-memory exam RPC stand-in."""

    def __init__(self) -> None:
        """Bind empty state."""

        self.enqueued: list[str] = []
        self.error: str | None = None
        self.replayed = False
        self.status = "queued"
        self.split = "development"
        self.reports: dict[str, ExamLatestReport] = {}
        self.cases: tuple[ExamReportCase, ...] = ()

    def enqueue(
        self,
        caller: CallerContext,
        *,
        split: str,
        idempotency_key: str,
        candidate_fingerprint: str,
        expected_dataset_hash: str | None = None,
    ) -> ExamEnqueueResult:
        """Queue or reconnect.

        Args:
            caller: Examiner.
            split: Split.
            idempotency_key: Key.
            candidate_fingerprint: Digest.
            expected_dataset_hash: Optional CAS.

        Returns:
            Enqueue row.

        Raises:
            ExamRepositoryError: Mapped failure.
        """

        del caller, expected_dataset_hash
        assert len(candidate_fingerprint) == 64
        if self.error is not None:
            raise ExamRepositoryError(self.error)
        self.enqueued.append(idempotency_key)
        self.split = split
        return ExamEnqueueResult(
            exam_run_id=_EXAM,
            status=self.status,
            dataset_hash="d" * 64,
            conversation_id=uuid4(),
            replayed=self.replayed,
        )

    def get(self, caller: CallerContext, *, exam_run_id: UUID) -> ExamRunStatus | None:
        """Return poll status.

        Args:
            caller: Examiner.
            exam_run_id: Exam id.

        Returns:
            Status or None.
        """

        del caller
        if exam_run_id != _EXAM:
            return None
        return ExamRunStatus(
            exam_run_id=_EXAM,
            split=self.split,
            status=self.status,
            dataset_hash="d" * 64,
            candidate_fingerprint="f" * 64,
            case_count=2,
            completed_case_count=1 if self.status != "queued" else 0,
            holdout_opened=False,
            conversation_id=uuid4(),
        )

    def cancel(self, caller: CallerContext, *, exam_run_id: UUID) -> str:
        """Cancel.

        Args:
            caller: Examiner.
            exam_run_id: Exam id.

        Returns:
            Status.

        Raises:
            ExamRepositoryError: Missing exam.
        """

        del caller
        if exam_run_id != _EXAM:
            raise ExamRepositoryError("not_found")
        self.status = "cancelled"
        return self.status

    def latest_report(
        self,
        caller: CallerContext,
        *,
        split: str,
    ) -> ExamLatestReport | None:
        """Return a split-isolated report.

        Args:
            caller: Examiner.
            split: Split.

        Returns:
            Report or None.
        """

        del caller
        return self.reports.get(split)

    def list_report_cases(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
    ) -> tuple[ExamReportCase, ...]:
        """Return report cases.

        Args:
            caller: Examiner.
            exam_run_id: Exam id.

        Returns:
            Case rows.
        """

        del caller
        if exam_run_id != _EXAM:
            return ()
        return self.cases


class _StatusQuiz:
    """Quiz status stand-in for empty-dataset 422 counts."""

    def status_counts(self, caller: CallerContext) -> QuizStatusCounts:
        """Return zeros.

        Args:
            caller: Examiner.

        Returns:
            Counts.
        """

        del caller
        return QuizStatusCounts(
            draft_count=0,
            approved_count=0,
            rejected_count=0,
            stale_gold_count=0,
            live_count=0,
            remaining_capacity=60,
        )


def _client(
    monkeypatch: pytest.MonkeyPatch,
    exams: _FakeExams,
) -> TestClient:
    """Create an app client with a fake exam repository.

    Args:
        monkeypatch: Pytest monkeypatch.
        exams: Fake exam RPCs.

    Returns:
        Test client.
    """

    permit_test_identity(monkeypatch)
    monkeypatch.setenv("PDF_EVAL_WORKSPACE_ENABLED", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.pdf_eval.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_exam_repository] = lambda: exams

    def _service() -> PdfEvalWorkspaceService:
        """Bind a stub run service that never finds Ask runs.

        Returns:
            Workspace service for exam HTTP tests.
        """

        class _Runs:
            """Reject run lookups during exam HTTP tests."""

            def get(self, caller: CallerContext, *, run_id: UUID) -> object:
                """Reject every run lookup.

                Args:
                    caller: Unused identity.
                    run_id: Requested run.

                Returns:
                    Never. Raises not_found.

                Raises:
                    QueryAdmissionError: Always ``not_found``.
                """

                raise QueryAdmissionError("not_found")

        return PdfEvalWorkspaceService(
            repository=_StatusQuiz(),  # type: ignore[arg-type]
            postgres_url="postgresql://unused",
            query_runs=_Runs(),  # type: ignore[arg-type]
        )

    application.dependency_overrides[get_pdf_eval_service] = _service
    return TestClient(application)


def test_exam_start_returns_202_without_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Start is 202 and does not persist case scores in HTTP."""

    exams = _FakeExams()
    with _client(monkeypatch, exams) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            "/admin/pdf-eval/exams",
            headers=_identity(_OWNER, "owner"),
            json={"split": "development", "idempotency_key": "exam-key-01"},
        )
        assert response.status_code == 202
        payload = json_object(response.json())
        _assert_public(payload)
        assert payload["exam_run_id"] == str(_EXAM)
        assert payload["replayed"] is False
        assert payload["holdout_opened"] is False
        assert exams.enqueued == ["exam-key-01"]
        assert exams.cases == ()


def test_exam_idempotent_reconnect_and_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same key reconnects; payload collision is 409."""

    exams = _FakeExams()
    exams.replayed = True
    with _client(monkeypatch, exams) as raw:
        client = as_openapi_client(raw)
        replay = client.post(
            "/admin/pdf-eval/exams",
            headers=_identity(_OWNER, "owner"),
            json={"split": "development", "idempotency_key": "exam-key-01"},
        )
        assert replay.status_code == 202
        assert json_object(replay.json())["replayed"] is True
        exams.error = "idempotency_collision"
        collided = client.post(
            "/admin/pdf-eval/exams",
            headers=_identity(_OWNER, "owner"),
            json={"split": "development", "idempotency_key": "exam-key-01"},
        )
        assert collided.status_code == 409
        assert json_object(collided.json())["detail"] == "idempotency_collision"


def test_exam_one_active_and_qualification_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One-active and consumed qualification are 409."""

    exams = _FakeExams()
    exams.error = "already_running"
    with _client(monkeypatch, exams) as raw:
        client = as_openapi_client(raw)
        active = client.post(
            "/admin/pdf-eval/exams",
            headers=_identity(_OWNER, "owner"),
            json={"split": "development", "idempotency_key": "exam-key-02"},
        )
        assert active.status_code == 409
        exams.error = "qualification_consumed"
        consumed = client.post(
            "/admin/pdf-eval/exams",
            headers=_identity(_OWNER, "owner"),
            json={"split": "qualification", "idempotency_key": "exam-key-03"},
        )
        assert consumed.status_code == 409


def test_exam_empty_dataset_is_422_with_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No eligible cases returns counts only."""

    exams = _FakeExams()
    exams.error = "empty_dataset"
    with _client(monkeypatch, exams) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            "/admin/pdf-eval/exams",
            headers=_identity(_OWNER, "owner"),
            json={"split": "development", "idempotency_key": "exam-key-04"},
        )
        assert response.status_code == 422
        payload = json_object(response.json())
        _assert_public(payload)
        assert payload["detail"] == "empty_dataset"
        assert payload["approved_count"] == 0


def test_exam_holdout_rejected_by_body_enum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Holdout is not an allowed split in the request body."""

    exams = _FakeExams()
    with _client(monkeypatch, exams) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            "/admin/pdf-eval/exams",
            headers=_identity(_OWNER, "owner"),
            json={"split": "holdout", "idempotency_key": "exam-key-05"},
        )
        assert response.status_code == 422
        assert exams.enqueued == []


def test_exam_poll_cancel_and_latest_are_split_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Poll states, idempotent cancel, and split-isolated latest reports."""

    exams = _FakeExams()
    exams.status = "running"
    exams.reports["development"] = ExamLatestReport(
        exam_run_id=_EXAM,
        split="development",
        dataset_hash="d" * 64,
        case_count=2,
        hit_count=1,
        hybrid_recall_at_10=0.5,
        gates_pass=True,
        holdout_opened=False,
        created_at=datetime.now(UTC),
    )
    exams.cases = (
        ExamReportCase(
            exam_run_id=_EXAM,
            case_id=_CASE,
            ordinal=1,
            hit=False,
            gold_count=1,
            ranked_hit_count=0,
            latency_ms=12,
        ),
    )
    with _client(monkeypatch, exams) as raw:
        client = as_openapi_client(raw)
        polled = client.get(
            f"/admin/pdf-eval/exams/{_EXAM}",
            headers=_identity(_OWNER, "owner"),
        )
        assert polled.status_code == 200
        _assert_public(json_object(polled.json()))
        assert json_object(polled.json())["status"] == "running"
        missing = client.get(
            f"/admin/pdf-eval/exams/{uuid4()}",
            headers=_identity(_OWNER, "owner"),
        )
        assert missing.status_code == 404
        cancelled = client.post(
            f"/admin/pdf-eval/exams/{_EXAM}/cancel",
            headers=_identity(_OWNER, "owner"),
        )
        assert cancelled.status_code == 200
        assert json_object(cancelled.json())["status"] == "cancelled"
        again = client.post(
            f"/admin/pdf-eval/exams/{_EXAM}/cancel",
            headers=_identity(_OWNER, "owner"),
        )
        assert again.status_code == 200
        latest = client.get(
            "/admin/pdf-eval/reports/latest",
            headers=_identity(_OWNER, "owner"),
            params={"split": "development"},
        )
        assert latest.status_code == 200
        body = json_object(latest.json())
        _assert_public(body)
        assert body["present"] is True
        assert body["split"] == "development"
        empty = client.get(
            "/admin/pdf-eval/reports/latest",
            headers=_identity(_OWNER, "owner"),
            params={"split": "qualification"},
        )
        assert json_object(empty.json())["present"] is False
        cases = client.get(
            f"/admin/pdf-eval/reports/{_EXAM}/cases",
            headers=_identity(_OWNER, "owner"),
        )
        assert cases.status_code == 200
        listed = json_object(cases.json())
        _assert_public(listed)
        assert listed["missed_count"] == 1
        holdout_latest = client.get(
            "/admin/pdf-eval/reports/latest",
            headers=_identity(_OWNER, "owner"),
            params={"split": "holdout"},
        )
        assert holdout_latest.status_code == 422


def test_exam_member_forbidden_and_disabled_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Members are 403. Disabled workspace is 404 and omitted from OpenAPI."""

    exams = _FakeExams()
    with _client(monkeypatch, exams) as raw:
        client = as_openapi_client(raw)
        denied = client.post(
            "/admin/pdf-eval/exams",
            headers=_identity(_MEMBER, "member"),
            json={"split": "development", "idempotency_key": "exam-key-06"},
        )
        assert denied.status_code == 403
        schema = json_object(client.get("/openapi.json").json())
        paths = json_object(schema.get("paths", {}))
        assert "/admin/pdf-eval/exams" in paths
    permit_test_identity(monkeypatch)
    monkeypatch.setenv("PDF_EVAL_WORKSPACE_ENABLED", "false")
    application = create_app()
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        denied = client.post(
            "/admin/pdf-eval/exams",
            headers=_identity(_OWNER, "owner"),
            json={"split": "development", "idempotency_key": "exam-key-07"},
        )
        assert denied.status_code == 404
        paths = json_object(client.get("/openapi.json").json()).get("paths", {})
        assert isinstance(paths, dict)
        assert "/admin/pdf-eval/exams" not in paths
