"""Dashboard API validates periods and enforces role before database reads."""

from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Client
from smart_rag_api.dependencies.identity import resolve_caller_context
from smart_rag_api.dependencies.services import get_postgres_url
from smart_rag_api.routers import overview
from smart_rag_core.security.identity import CallerContext, UserRole


def test_overview_period_query_and_cache_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normal URL integers reach SQL; unexpected periods and members never do."""
    app = FastAPI()
    app.include_router(overview.router)
    caller = CallerContext(
        user_id=str(uuid4()), role=UserRole.OWNER, authorization_version=1
    )
    app.dependency_overrides[resolve_caller_context] = lambda: caller
    app.dependency_overrides[get_postgres_url] = lambda: "not-used"
    monkeypatch.setattr(overview, "enforce_rate_limit", MagicMock())
    connect = MagicMock()
    payload: dict[str, object] = {
        "generated_at": "2026-10-26T12:00:00Z",
        "period_start": "2026-10-20T00:00:00Z",
        "days": 7,
        "timezone": "UTC",
        "reliability_enabled": False,
        "summary": {
            "questions": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "measured": 0,
            "supported": 0,
            "not_measured": 0,
            "median_response_seconds": None,
            "latency_samples": 0,
            "cost_usd": "0",
        },
        "daily": [],
        "outcomes": {},
        "authority": {},
        "authority_unversioned": 0,
        "attention_counts": {},
        "attention_items": [],
    }
    connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (
        payload,
    )
    monkeypatch.setattr(overview.psycopg, "connect", connect)
    with TestClient(app) as raw_client:
        client = cast(Client, raw_client)
        response = client.get("/admin/overview?days=7")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        connect.reset_mock()
        assert client.get("/admin/overview?days=8").status_code == 422
        connect.assert_not_called()
        caller = caller.model_copy(update={"role": UserRole.MEMBER})
        assert client.get("/admin/overview?days=7").status_code == 403
        connect.assert_not_called()
