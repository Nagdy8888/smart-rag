"""Citation page PNG stays private: owned pages render, others return no bytes."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from smart_rag_api.dependencies.identity import resolve_caller_context
from smart_rag_api.routers import query_runs as query_runs_router
from smart_rag_api.services.citation_page_http import CitationPageReadError
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20261015163000_citation_page_object_v2.sql"
)
_OWNED = UUID("22222222-2222-4222-8222-222222222222")
_FOREIGN = UUID("33333333-3333-4333-8333-333333333333")
_RUN = UUID("44444444-4444-4444-8444-444444444444")


def test_citation_page_migration_has_no_signed_url() -> None:
    """The locator function is app_api-only and does not mint a signed URL."""

    sql = _MIGRATION.read_text(encoding="utf-8")
    assert "get_citation_page_object_v1" in sql
    assert "get_run_citation_detail_v1" in sql
    assert "query_admission:not_found" in sql
    assert "GRANT EXECUTE" in sql
    assert "app_api" in sql
    assert "signed_url" not in sql.lower()
    assert "create_signed" not in sql.lower()
    assert "application/pdf" not in sql
    assert "%.pdf" not in sql


def test_citation_page_route_returns_png_only_for_an_owned_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An owned page is image/png. Foreign and unavailable citations are 404."""

    def allow_fixture_read(*_args: object, **_kwargs: object) -> None:
        """Leave rate-limit behavior to its dedicated contract tests."""

    monkeypatch.setattr(query_runs_router, "enforce_rate_limit", allow_fixture_read)

    class _Pages:
        """Serve fixture bytes with explicit authorization outcomes."""

        def read_png(
            self,
            caller: CallerContext,
            *,
            run_id: UUID,
            citation_id: UUID,
        ) -> bytes:
            """Read only an owned fixture page."""
            assert caller.role is UserRole.MEMBER
            assert run_id == _RUN
            if citation_id == _OWNED:
                return b"\x89PNG\r\n"
            if citation_id == _FOREIGN:
                raise QueryAdmissionError("not_found")
            raise CitationPageReadError("citation_page_unavailable")

    application = FastAPI()
    application.include_router(query_runs_router.router)
    application.dependency_overrides[query_runs_router.get_citation_page_service] = (
        lambda: _Pages()
    )
    application.dependency_overrides[resolve_caller_context] = lambda: CallerContext(
        user_id="11111111-1111-4111-8111-111111111111",
        role=UserRole.MEMBER,
        authorization_version=1,
    )
    client = cast(httpx.Client, TestClient(application))
    ok = client.get(f"/runs/{_RUN}/citations/{_OWNED}/page")
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("image/png")
    assert ok.content.startswith(b"\x89PNG")
    assert ok.headers["cache-control"] == "private, no-store"
    assert "http" not in ok.text.lower()
    foreign = client.get(f"/runs/{_RUN}/citations/{_FOREIGN}/page")
    assert foreign.status_code == 404
    assert foreign.content == b"" or b"PNG" not in foreign.content
    unavailable = client.get(
        f"/runs/{_RUN}/citations/55555555-5555-4555-8555-555555555555/page"
    )
    assert unavailable.status_code == 404
    assert b"\x89PNG" not in unavailable.content
