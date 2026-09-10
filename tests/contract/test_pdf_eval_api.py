"""Local PDF evaluation workspace HTTP contract: auth, holdout, revision."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from smart_rag_api.dependencies.services import get_postgres_url
from smart_rag_api.main import create_app
from smart_rag_api.routers.query_runs import get_query_run_service
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord, RunCitationRecord
from smart_rag_core.security.identity import CallerContext

from tests.unit.typed_openapi import (
    as_openapi_client,
    json_object,
    json_object_list,
    permit_test_identity,
)

_OWNER = "00000000-0000-4000-8000-000000000001"
_MEMBER = "00000000-0000-4000-8000-000000000002"
_CASE = "aaaaaaaaaaaaaaaaaaaaaaaa"
_CHUNK = UUID("00000000-0000-0000-0000-000000000001")


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


def _envelope() -> dict[str, object]:
    """Return one v1 workspace envelope.

    Returns:
        JSON mapping. Tests must not print questions.
    """

    return {
        "schema_version": "private-pdf-eval-v1",
        "generated_only": True,
        "human_sealed": False,
        "holdout_opened": False,
        "version_id": str(uuid4()),
        "document_id": str(uuid4()),
        "content_hash": "aa" * 32,
        "openai_calls": 0,
        "cases": [
            {
                "case_id": _CASE,
                "split": "development",
                "source_family_id": "bbbbbbbbbbbbbbbbbbbbbbbb",
                "query_class": "factual_definition",
                "chunk_ids": [str(_CHUNK)],
                "page_numbers": [1],
                "heading_paths": ["Chapter 1"],
                "required_terms": ["Hybrid"],
                "expected_profile_id": "hybrid_default_v1",
                "expected_scope": "unscoped",
                "expected_refusal": False,
                "acl_actor_id": _OWNER,
                "human_approved": False,
                "generated_only": True,
                "reviewer": None,
                "question": "What is stated about Hybrid?",
                "expected_answer": "Agents coordinate tools.",
                "atomic_facts": ["Agents coordinate tools."],
            }
        ],
    }


def _enable_workspace(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Enable the local workspace against ``root``.

    Args:
        monkeypatch: Pytest monkeypatch.
        root: Temporary workspace directory.
    """

    permit_test_identity(monkeypatch)
    monkeypatch.setenv("PDF_EVAL_WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("PDF_EVAL_WORKSPACE_ROOT", str(root))


def _client(monkeypatch: pytest.MonkeyPatch, root: Path) -> TestClient:
    """Create an app client with the workspace flag on.

    Args:
        monkeypatch: Pytest monkeypatch.
        root: Workspace directory.

    Returns:
        Test client.
    """

    _enable_workspace(monkeypatch, root)
    monkeypatch.setattr(
        "smart_rag_api.routers.pdf_eval.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    return TestClient(application)


def test_disabled_workspace_discloses_no_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Disabled mode is 404, not an empty dataset."""

    permit_test_identity(monkeypatch)
    monkeypatch.setenv("PDF_EVAL_WORKSPACE_ENABLED", "false")
    monkeypatch.setenv("PDF_EVAL_WORKSPACE_ROOT", str(tmp_path))
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


def test_member_is_forbidden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Members and viewers cannot read the workspace."""

    (tmp_path / "eval-draft").mkdir()
    (tmp_path / "eval-draft" / "draft.json").write_text(
        json.dumps(_envelope()), encoding="utf-8"
    )
    with _client(monkeypatch, tmp_path) as raw:
        client = as_openapi_client(raw)
        response = client.get(
            "/admin/pdf-eval/status",
            headers=_identity(_MEMBER, "member"),
        )
        assert response.status_code == 403
        assert json_object(response.json())["detail"] == "forbidden"


def test_owner_can_list_without_bulk_questions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """List OpenAPI and JSON omit bulk question fields."""

    (tmp_path / "eval-draft").mkdir()
    (tmp_path / "eval-draft" / "draft.json").write_text(
        json.dumps(_envelope()), encoding="utf-8"
    )
    with _client(monkeypatch, tmp_path) as raw:
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
        assert first["case_id"] == _CASE
        holdout = client.get(
            "/admin/pdf-eval/cases",
            params={"split": "holdout"},
            headers=_identity(_OWNER, "owner"),
        )
        assert holdout.status_code == 400


def test_stale_revision_conflicts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Stale compare-and-swap returns 409."""

    (tmp_path / "eval-draft").mkdir()
    (tmp_path / "eval-draft" / "draft.json").write_text(
        json.dumps(_envelope()), encoding="utf-8"
    )
    with _client(monkeypatch, tmp_path) as raw:
        client = as_openapi_client(raw)
        headers = _identity(_OWNER, "owner")
        detail = json_object(
            client.get(f"/admin/pdf-eval/cases/{_CASE}", headers=headers).json()
        )
        conflict = client.patch(
            f"/admin/pdf-eval/cases/{_CASE}",
            headers=headers,
            json={
                "expected_revision": "0" * 64,
                "question": "According to Chapter 1, what is Hybrid?",
            },
        )
        assert conflict.status_code == 409
        ok = client.patch(
            f"/admin/pdf-eval/cases/{_CASE}",
            headers=headers,
            json={
                "expected_revision": detail["revision"],
                "question": "According to Chapter 1, what is Hybrid?",
            },
        )
        assert ok.status_code == 200
        approved = client.post(
            f"/admin/pdf-eval/cases/{_CASE}/approve",
            headers=headers,
            json={"expected_revision": json_object(ok.json())["revision"]},
        )
        assert approved.status_code == 200
        body = json_object(
            client.get(f"/admin/pdf-eval/cases/{_CASE}", headers=headers).json()
        )
        assert body["reviewer"] == _OWNER
        assert body["human_approved"] is True


def test_holdout_path_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A holdout relative path cannot be used as the workspace dataset."""

    (tmp_path / "holdout").mkdir()
    (tmp_path / "holdout" / "labels.json").write_text("{}", encoding="utf-8")
    with _client(monkeypatch, tmp_path / "holdout") as raw:
        client = as_openapi_client(raw)
        response = client.get(
            "/admin/pdf-eval/status",
            headers=_identity(_OWNER, "owner"),
        )
        assert response.status_code == 404


def test_compare_run_uses_owned_citations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Compare-run scores ACL-rechecked citation IDs in core code."""

    (tmp_path / "eval-draft").mkdir()
    (tmp_path / "eval-draft" / "draft.json").write_text(
        json.dumps(_envelope()), encoding="utf-8"
    )
    run_id = uuid4()

    class _FakeRuns:
        def get(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
            if str(caller.user_id) != _OWNER:
                raise QueryAdmissionError("not_found")
            return QueryRunRecord(
                run_id=run_id,
                conversation_id=uuid4(),
                creator_user_id=UUID(_OWNER),
                status="succeeded",
                reservation_id=uuid4(),
            )

        def citations(
            self, caller: CallerContext, *, run_id: UUID
        ) -> tuple[RunCitationRecord, ...]:
            return (
                RunCitationRecord(
                    citation_id=uuid4(),
                    citation_index=1,
                    chunk_id=_CHUNK,
                    provenance={},
                    source_unavailable=False,
                ),
            )

    _enable_workspace(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "smart_rag_api.routers.pdf_eval.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_query_run_service] = lambda: _FakeRuns()
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        headers = _identity(_OWNER, "owner")
        response = client.post(
            f"/admin/pdf-eval/cases/{_CASE}/compare-run",
            headers=headers,
            json={"run_id": str(run_id)},
        )
        assert response.status_code == 200
        payload = json_object(response.json())
        assert payload["intersection"] == 1
        assert payload["manual_ai_test"] is True
        foreign = client.post(
            f"/admin/pdf-eval/cases/{_CASE}/compare-run",
            headers=_identity(_MEMBER, "member"),
            json={"run_id": str(run_id)},
        )
        assert foreign.status_code == 403
