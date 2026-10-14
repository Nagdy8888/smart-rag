"""Figure storage stays private and the PNG route checks document ACL."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from smart_rag_api.dependencies.identity import resolve_caller_context
from smart_rag_api.routers import figures as figures_router
from smart_rag_api.services.figures_http import FIGURE_READ_SQL, FigureReadError
from smart_rag_core.security.identity import CallerContext, UserRole

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20261014143000_figure_artifacts_v1.sql"
)


def test_figure_migration_keeps_the_bucket_private() -> None:
    """The figure bucket is private and the table enables row security."""

    sql = _MIGRATION.read_text(encoding="utf-8")
    assert "figure-artifacts" in sql
    assert "public = false" in sql or ", false," in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "document_figures_api_read" in sql
    assert "caller_can_read_document" in FIGURE_READ_SQL


def test_figure_route_streams_png_only_for_an_authorized_key(
    monkeypatch,
) -> None:
    """The route returns image/png and hides missing or forbidden figures."""

    monkeypatch.setattr(figures_router, "enforce_rate_limit", lambda *_a, **_k: None)

    class _Figures:
        def read_png(self, caller: CallerContext, figure_key: str) -> bytes | None:
            assert caller.role is UserRole.MEMBER
            if figure_key == "abc123":
                return b"\x89PNG\r\n"
            if figure_key == "missing":
                return None
            raise FigureReadError("figure_object_unavailable")

    application = FastAPI()
    application.include_router(figures_router.router)
    application.dependency_overrides[figures_router.get_figure_service] = lambda: _Figures()
    application.dependency_overrides[resolve_caller_context] = lambda: CallerContext(
        user_id="11111111-1111-1111-1111-111111111111",
        role=UserRole.MEMBER,
        authorization_version=1,
    )
    client = TestClient(application)
    ok = client.get("/figures/abc123")
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("image/png")
    assert ok.content.startswith(b"\x89PNG")
    assert client.get("/figures/missing").status_code == 404
    assert client.get("/figures/broken").status_code == 404
    assert client.get("/figures/not-a-key").status_code == 404
