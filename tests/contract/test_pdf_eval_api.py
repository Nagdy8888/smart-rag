"""Hosted PDF evaluation case HTTP contract: auth, holdout, CAS, 503."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from smart_rag_api.dependencies.services import get_postgres_url
from smart_rag_api.main import create_app
from smart_rag_api.routers.pdf_eval import get_pdf_eval_service
from smart_rag_api.services.pdf_eval_workspace import PdfEvalWorkspaceService
from smart_rag_core.evaluation.private_pdf.quiz_repository import (
    QuizCaseDetail,
    QuizCaseSummary,
    QuizCreateResult,
    QuizGoldLocator,
    QuizMigrationMissingError,
    QuizRepositoryError,
    QuizStatusCounts,
)
from smart_rag_core.evaluation.private_pdf.schema import WORKSPACE_MAX_QUESTION_CHARS
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord, RunCitationRecord
from smart_rag_core.security.identity import CallerContext

from tests.unit.typed_openapi import (
    JsonResponse,
    as_openapi_client,
    json_object,
    json_object_list,
    permit_test_identity,
)

_OWNER = "00000000-0000-4000-8000-000000000001"
_MEMBER = "00000000-0000-4000-8000-000000000002"
_CASE = UUID("aaaaaaaa-0000-4000-8000-000000000001")
_CHUNK = UUID("00000000-0000-0000-0000-000000000001")
_RUN = UUID("00000000-0000-4000-8000-000000000099")


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


class _FakeQuizRepo:
    """In-memory quiz RPC stand-in. Never logs question text."""

    missing_schema: bool
    detail: QuizCaseDetail

    def __init__(self) -> None:
        """Seed one development draft."""

        self.missing_schema = False
        self.detail = QuizCaseDetail(
            case_id=_CASE,
            split="development",
            query_class="factual_definition",
            review_status="draft",
            generated_only=True,
            source_family_id="bbbbbbbbbbbbbbbbbbbbbbbb",
            question="What is stated about Hybrid?",
            expected_answer="Agents coordinate tools.",
            atomic_facts=("Agents coordinate tools.",),
            required_terms=("Hybrid",),
            expected_scope="unscoped",
            source_run_id=_RUN,
            document_id=None,
            version_id=None,
            gold=(
                QuizGoldLocator(
                    ordinal=1,
                    chunk_id=_CHUNK,
                    document_id=uuid4(),
                    version_id=uuid4(),
                    page_number=1,
                    page_label="1",
                    section_path=("Chapter 1",),
                    stale=False,
                ),
            ),
            gold_stale=False,
            reviewer_user_id=None,
            row_version=1,
        )

    def _guard(self) -> None:
        """Raise when the hosted schema is absent."""

        if self.missing_schema:
            raise QuizMigrationMissingError()

    def create(
        self,
        caller: CallerContext,
        *,
        source_run_id: UUID | None,
        question: str | None,
        expected_answer: str,
        atomic_facts: Sequence[str],
        query_class: str,
        required_terms: Sequence[str],
        split: str,
        source_family_id: str | None,
        generated_only: bool,
        chunk_ids: Sequence[UUID],
        idempotency_key: str,
        request_payload_hash: str,
    ) -> QuizCreateResult:
        """Record a create without persisting private fields."""

        del caller, question, expected_answer, atomic_facts, required_terms
        del generated_only, chunk_ids, idempotency_key, request_payload_hash
        self._guard()
        if split == "holdout":
            raise QuizRepositoryError("holdout_rejected")
        del query_class, source_family_id, source_run_id
        return QuizCreateResult(case_id=_CASE, row_version=1, replayed=False)

    def list_summaries(
        self,
        caller: CallerContext,
        *,
        split: str | None,
        review_status: str | None,
        limit: int,
        after_id: UUID | None,
    ) -> tuple[QuizCaseSummary, ...]:
        """Return one summary without private fields."""

        del caller, review_status, limit, after_id
        self._guard()
        if split == "holdout":
            raise QuizRepositoryError("holdout_rejected")
        return (
            QuizCaseSummary(
                case_id=self.detail.case_id,
                split=self.detail.split,
                query_class=self.detail.query_class,
                review_status=self.detail.review_status,
                generated_only=self.detail.generated_only,
                source_family_id=self.detail.source_family_id,
                gold_chunk_count=len(self.detail.gold),
                gold_stale=self.detail.gold_stale,
                row_version=self.detail.row_version,
            ),
        )

    def get(self, caller: CallerContext, *, case_id: UUID) -> QuizCaseDetail:
        """Return the seeded detail."""

        del caller
        self._guard()
        if case_id != self.detail.case_id:
            raise QuizRepositoryError("not_found")
        return self.detail

    def patch(
        self,
        caller: CallerContext,
        *,
        case_id: UUID,
        row_version: int,
        question: str | None,
        expected_answer: str | None,
        atomic_facts: Sequence[str] | None,
        query_class: str | None,
        required_terms: Sequence[str] | None,
        source_family_id: str | None,
        expected_scope: str | None,
    ) -> tuple[UUID, int]:
        """CAS patch. Stale versions raise."""

        del caller, question, atomic_facts, query_class, required_terms
        del source_family_id, expected_scope
        self._guard()
        if case_id != self.detail.case_id:
            raise QuizRepositoryError("not_found")
        if row_version != self.detail.row_version:
            raise QuizRepositoryError("stale_row_version")
        current = self.detail
        if expected_answer is not None:
            patched: QuizCaseDetail = replace(
                current,
                expected_answer=expected_answer,
                review_status="draft",
                reviewer_user_id=None,
                row_version=row_version + 1,
            )
        else:
            patched = replace(
                current,
                review_status="draft",
                reviewer_user_id=None,
                row_version=row_version + 1,
            )
        self.detail = patched
        return self.detail.case_id, self.detail.row_version

    def replace_gold(
        self,
        caller: CallerContext,
        *,
        case_id: UUID,
        row_version: int,
        chunk_ids: Sequence[UUID],
    ) -> tuple[UUID, int, int]:
        """Replace gold IDs."""

        del caller
        self._guard()
        if case_id != self.detail.case_id:
            raise QuizRepositoryError("not_found")
        if row_version != self.detail.row_version:
            raise QuizRepositoryError("stale_row_version")
        current = self.detail
        self.detail = replace(
            current,
            review_status="draft",
            reviewer_user_id=None,
            row_version=row_version + 1,
        )
        return self.detail.case_id, self.detail.row_version, len(chunk_ids)

    def approve(
        self, caller: CallerContext, *, case_id: UUID, row_version: int
    ) -> tuple[UUID, int]:
        """Approve the seeded case."""

        self._guard()
        if case_id != self.detail.case_id:
            raise QuizRepositoryError("not_found")
        if row_version != self.detail.row_version:
            raise QuizRepositoryError("stale_row_version")
        current = self.detail
        self.detail = replace(
            current,
            review_status="approved",
            generated_only=False,
            reviewer_user_id=UUID(caller.user_id),
            row_version=row_version + 1,
        )
        return self.detail.case_id, self.detail.row_version

    def reject(
        self, caller: CallerContext, *, case_id: UUID, row_version: int
    ) -> tuple[UUID, int]:
        """Reject the seeded case."""

        del caller
        self._guard()
        if case_id != self.detail.case_id:
            raise QuizRepositoryError("not_found")
        if row_version != self.detail.row_version:
            raise QuizRepositoryError("stale_row_version")
        current = self.detail
        self.detail = replace(
            current,
            review_status="rejected",
            row_version=row_version + 1,
        )
        return self.detail.case_id, self.detail.row_version

    def delete(self, caller: CallerContext, *, case_id: UUID, row_version: int) -> None:
        """Delete the seeded case."""

        del caller
        self._guard()
        if case_id != self.detail.case_id:
            raise QuizRepositoryError("not_found")
        if row_version != self.detail.row_version:
            raise QuizRepositoryError("stale_row_version")
        current = self.detail
        self.detail = replace(current, case_id=uuid4())

    def status_counts(self, caller: CallerContext) -> QuizStatusCounts:
        """Return live counts."""

        del caller
        self._guard()
        return QuizStatusCounts(
            draft_count=1,
            approved_count=0,
            rejected_count=0,
            stale_gold_count=0,
            live_count=1,
            remaining_capacity=59,
        )


def _enable_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable the local workspace flag.

    Args:
        monkeypatch: Pytest monkeypatch.
    """

    permit_test_identity(monkeypatch)
    monkeypatch.setenv("PDF_EVAL_WORKSPACE_ENABLED", "true")


def _client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    repository: _FakeQuizRepo | None = None,
    query_runs: object | None = None,
) -> TestClient:
    """Create an app client with a fake quiz repository.

    Args:
        monkeypatch: Pytest monkeypatch.
        repository: Optional fake repository.
        query_runs: Optional run service.

    Returns:
        Test client.
    """

    _enable_workspace(monkeypatch)
    monkeypatch.setattr(
        "smart_rag_api.routers.pdf_eval.enforce_rate_limit",
        _noop_rate_limit,
    )
    repo = repository or _FakeQuizRepo()
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"

    def _service() -> PdfEvalWorkspaceService:
        """Build a workspace service with optional run doubles.

        Returns:
            Service bound to the fake quiz repository.
        """

        runs = query_runs
        if runs is None:

            class _UnusedRuns:
                """Reject run lookups when Ask capture is unused."""

                def get(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
                    """Reject unknown runs.

                    Args:
                        caller: Unused identity.
                        run_id: Requested run.

                    Returns:
                        Never. Raises not_found.

                    Raises:
                        QueryAdmissionError: Always ``not_found``.
                    """

                    raise QueryAdmissionError("not_found")

                def citations(
                    self, caller: CallerContext, *, run_id: UUID
                ) -> tuple[RunCitationRecord, ...]:
                    """Return no citations.

                    Args:
                        caller: Unused identity.
                        run_id: Requested run.

                    Returns:
                        Empty citation tuple.
                    """

                    del caller, run_id
                    return ()

            runs = _UnusedRuns()
        return PdfEvalWorkspaceService(
            repository=repo,
            postgres_url="postgresql://unused",
            query_runs=runs,  # type: ignore[arg-type]
        )

    application.dependency_overrides[get_pdf_eval_service] = _service
    return TestClient(application)


def test_disabled_workspace_discloses_no_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled mode is 404, not an empty dataset."""

    permit_test_identity(monkeypatch)
    monkeypatch.setenv("PDF_EVAL_WORKSPACE_ENABLED", "false")
    application = create_app()
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        meta = json_object(client.get("/api/meta").json())
        assert meta["pdf_eval_workspace"] is False
        denied = client.get(
            "/admin/pdf-eval/status", headers=_identity(_OWNER, "owner")
        )
        assert denied.status_code == 404
        paths = json_object(client.get("/openapi.json").json()).get("paths", {})
        assert isinstance(paths, dict)
        assert "/admin/pdf-eval/status" not in paths


def test_member_is_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """Members and viewers cannot read the workspace."""

    with _client(monkeypatch) as raw:
        client = as_openapi_client(raw)
        response = client.get(
            "/admin/pdf-eval/status",
            headers=_identity(_MEMBER, "member"),
        )
        assert response.status_code == 403
        assert json_object(response.json())["detail"] == "forbidden"


def test_owner_can_list_without_bulk_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """List OpenAPI and JSON omit bulk question fields."""

    with _client(monkeypatch) as raw:
        client = as_openapi_client(raw)
        schema = json_object(client.get("/openapi.json").json())
        paths = json_object(schema.get("paths", {}))
        assert "/admin/pdf-eval/cases" in paths
        listed = json_object(
            client.get(
                "/admin/pdf-eval/cases", headers=_identity(_OWNER, "owner")
            ).json()
        )
        assert "question" not in listed
        items = json_object_list(listed["items"])
        first = items[0]
        assert "question" not in first
        assert first["case_id"] == str(_CASE)
        holdout = client.get(
            "/admin/pdf-eval/cases",
            params={"split": "holdout"},
            headers=_identity(_OWNER, "owner"),
        )
        assert holdout.status_code == 400
        approved = json_object(
            client.get(
                "/admin/pdf-eval/cases",
                params={"review_status": "approved"},
                headers=_identity(_OWNER, "owner"),
            ).json()
        )
        assert "question" not in approved
        invalid_review = client.get(
            "/admin/pdf-eval/cases",
            params={"review_status": "holdout"},
            headers=_identity(_OWNER, "owner"),
        )
        assert invalid_review.status_code == 422


def test_stale_row_version_conflicts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stale compare-and-swap returns 409."""

    with _client(monkeypatch) as raw:
        client = as_openapi_client(raw)
        headers = _identity(_OWNER, "owner")
        detail = json_object(
            client.get(f"/admin/pdf-eval/cases/{_CASE}", headers=headers).json()
        )
        conflict = client.patch(
            f"/admin/pdf-eval/cases/{_CASE}",
            headers=headers,
            json={
                "expected_row_version": 99,
                "question": "According to Chapter 1, what is Hybrid?",
            },
        )
        assert conflict.status_code == 409
        assert json_object(conflict.json())["detail"] == "stale_row_version"
        ok = client.patch(
            f"/admin/pdf-eval/cases/{_CASE}",
            headers=headers,
            json={
                "expected_row_version": detail["row_version"],
                "question": "According to Chapter 1, what is Hybrid?",
            },
        )
        assert ok.status_code == 200
        approved = client.post(
            f"/admin/pdf-eval/cases/{_CASE}/approve",
            headers=headers,
            json={"expected_row_version": json_object(ok.json())["row_version"]},
        )
        assert approved.status_code == 200
        body = json_object(
            client.get(f"/admin/pdf-eval/cases/{_CASE}", headers=headers).json()
        )
        assert body["reviewer_user_id"] == _OWNER
        assert body["human_approved"] is True
        assert "question" in body


def test_missing_schema_is_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing quiz RPCs are 503, not an empty workspace."""

    repo = _FakeQuizRepo()
    repo.missing_schema = True
    with _client(monkeypatch, repository=repo) as raw:
        client = as_openapi_client(raw)
        response = client.get(
            "/admin/pdf-eval/status", headers=_identity(_OWNER, "owner")
        )
        assert response.status_code == 503
        assert json_object(response.json())["detail"] == "quiz_schema_missing"


def test_create_rejects_holdout_and_browser_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create requires a source run and rejects holdout."""

    with _client(monkeypatch) as raw:
        client = as_openapi_client(raw)
        headers = _identity(_OWNER, "owner")
        rejected = client.post(
            "/admin/pdf-eval/cases",
            headers=headers,
            json={
                "source_run_id": str(_RUN),
                "query_class": "factual_definition",
                "split": "holdout",
                "idempotency_key": "idem-key-01",
            },
        )
        assert rejected.status_code == 400
        created = client.post(
            "/admin/pdf-eval/cases",
            headers=headers,
            json={
                "source_run_id": str(_RUN),
                "query_class": "factual_definition",
                "idempotency_key": "idem-key-02",
                "question": "browser question must be ignored",
            },
        )
        assert created.status_code == 422


def test_compare_run_uses_owned_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compare-run scores ACL-rechecked citation IDs in core code."""

    class _FakeRuns:
        """Completed owned run plus one citation for compare-run."""

        def get(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
            """Return the owned completed run.

            Args:
                caller: Authenticated identity.
                run_id: Requested run.

            Returns:
                Completed run row.

            Raises:
                QueryAdmissionError: When the caller is not the owner.
            """

            if str(caller.user_id) != _OWNER:
                raise QueryAdmissionError("not_found")
            return QueryRunRecord(
                run_id=run_id,
                conversation_id=uuid4(),
                creator_user_id=UUID(_OWNER),
                status="completed",
                reservation_id=uuid4(),
            )

        def citations(
            self, caller: CallerContext, *, run_id: UUID
        ) -> tuple[RunCitationRecord, ...]:
            """Return one ACL-safe citation.

            Args:
                caller: Unused identity.
                run_id: Requested run.

            Returns:
                One citation for the gold chunk.
            """

            del caller, run_id
            return (
                RunCitationRecord(
                    citation_id=uuid4(),
                    citation_index=1,
                    chunk_id=_CHUNK,
                    provenance={},
                    source_unavailable=False,
                ),
            )

    with _client(monkeypatch, query_runs=_FakeRuns()) as raw:
        client = as_openapi_client(raw)
        headers = _identity(_OWNER, "owner")
        response = client.post(
            f"/admin/pdf-eval/cases/{_CASE}/compare-run",
            headers=headers,
            json={"run_id": str(_RUN)},
        )
        assert response.status_code == 200
        payload = json_object(response.json())
        assert payload["intersection"] == 1
        assert payload["manual_ai_test"] is True
        foreign = client.post(
            f"/admin/pdf-eval/cases/{_CASE}/compare-run",
            headers=_identity(_MEMBER, "member"),
            json={"run_id": str(_RUN)},
        )
        assert foreign.status_code == 403


def test_incomplete_compare_run_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compare-run before a completed owned run is rejected."""

    class _Incomplete:
        """Running run that cannot be compared."""

        def get(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
            """Return a non-terminal run.

            Args:
                caller: Unused identity.
                run_id: Requested run.

            Returns:
                Running run row.
            """

            del caller
            return QueryRunRecord(
                run_id=run_id,
                conversation_id=uuid4(),
                creator_user_id=UUID(_OWNER),
                status="running",
                reservation_id=uuid4(),
            )

        def citations(
            self, caller: CallerContext, *, run_id: UUID
        ) -> tuple[RunCitationRecord, ...]:
            """Return no citations for an incomplete run.

            Args:
                caller: Unused identity.
                run_id: Requested run.

            Returns:
                Empty tuple.
            """

            del caller, run_id
            return ()

    with _client(monkeypatch, query_runs=_Incomplete()) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            f"/admin/pdf-eval/cases/{_CASE}/compare-run",
            headers=_identity(_OWNER, "owner"),
            json={"run_id": str(_RUN)},
        )
        assert response.status_code == 404


def test_status_omits_filesystem_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Status is aggregate DB counts with no workspace paths."""

    with _client(monkeypatch) as raw:
        client = as_openapi_client(raw)
        payload = json_object(
            client.get(
                "/admin/pdf-eval/status", headers=_identity(_OWNER, "owner")
            ).json()
        )
        assert payload["enabled"] is True
        assert payload["live_count"] == 1
        assert payload["holdout_opened"] is False
        assert "revision" not in payload
        assert "question" not in payload
        dumped = str(payload)
        assert ".private-eval" not in dumped
        assert "question" not in dumped


def test_inaccessible_case_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown case IDs are 404, not empty detail."""

    with _client(monkeypatch) as raw:
        client = as_openapi_client(raw)
        missing = uuid4()
        response = client.get(
            f"/admin/pdf-eval/cases/{missing}",
            headers=_identity(_OWNER, "owner"),
        )
        assert response.status_code == 404
        assert json_object(response.json())["detail"] == "not_found"


def test_question_html_is_escaped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Detail JSON HTML-escapes question and answer text."""

    repo = _FakeQuizRepo()
    current = repo.detail
    repo.detail = replace(
        current,
        question='<script>alert("xss")</script>',
        expected_answer="<img src=x onerror=alert(1)>",
    )
    with _client(monkeypatch, repository=repo) as raw:
        client = as_openapi_client(raw)
        body = json_object(
            client.get(
                f"/admin/pdf-eval/cases/{_CASE}",
                headers=_identity(_OWNER, "owner"),
            ).json()
        )
        assert "<script>" not in str(body["question"])
        assert "&lt;script&gt;" in str(body["question"])
        assert "<img" not in str(body["expected_answer"])


def test_oversized_question_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch payload bounds are enforced before repository writes."""

    with _client(monkeypatch) as raw:
        client = as_openapi_client(raw)
        response = client.patch(
            f"/admin/pdf-eval/cases/{_CASE}",
            headers=_identity(_OWNER, "owner"),
            json={
                "expected_row_version": 1,
                "question": "q" * (WORKSPACE_MAX_QUESTION_CHARS + 1),
            },
        )
        assert response.status_code == 422


def test_delete_uses_cas_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """DELETE with a CAS body succeeds for the current row version."""

    with _client(monkeypatch) as raw:
        client = as_openapi_client(raw)
        headers = _identity(_OWNER, "owner")
        deleted = cast(
            JsonResponse,
            raw.request(  # pyright: ignore[reportUnknownMemberType]
                "DELETE",
                f"/admin/pdf-eval/cases/{_CASE}",
                headers=headers,
                json={"expected_row_version": 1},
            ),
        )
        assert deleted.status_code == 200
        missing = client.get(f"/admin/pdf-eval/cases/{_CASE}", headers=headers)
        assert missing.status_code == 404


def test_regenerate_capacity_is_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regenerate stops at remaining capacity instead of self-approving."""

    class _Full(_FakeQuizRepo):
        """Quiz repository already at capacity."""

        def status_counts(self, caller: CallerContext) -> QuizStatusCounts:
            """Return a full live count.

            Args:
                caller: Unused identity.

            Returns:
                Counts that exhaust remaining capacity.
            """

            del caller
            self._guard()
            return QuizStatusCounts(
                draft_count=60,
                approved_count=0,
                rejected_count=0,
                stale_gold_count=0,
                live_count=60,
                remaining_capacity=0,
            )

    with _client(monkeypatch, repository=_Full()) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            "/admin/pdf-eval/drafts/regenerate",
            headers=_identity(_OWNER, "owner"),
            json={"document_id": str(uuid4())},
        )
        assert response.status_code == 409
        assert json_object(response.json())["detail"] == "capacity_exceeded"


def test_local_compose_defaults_eval_workspace_on() -> None:
    """Local Compose interpolates the kill switch as true."""

    text = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "PDF_EVAL_WORKSPACE_ENABLED:-true" in text
    staging = (
        Path(__file__).resolve().parents[2]
        / "infra"
        / "ec2"
        / "docker-compose.staging.yml"
    ).read_text(encoding="utf-8")
    assert "PDF_EVAL_WORKSPACE_ENABLED:-true" not in staging
