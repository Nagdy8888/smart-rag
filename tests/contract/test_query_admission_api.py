"""Contract tests for Auto chat admission HTTP (no SSE bodies)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from smart_rag_api.dependencies.services import get_postgres_url
from smart_rag_api.main import create_app
from smart_rag_api.routers.conversations import get_query_run_service
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import CallerContext, UserRole

from tests.unit.typed_openapi import as_openapi_client, json_object

_OWNER = "00000000-0000-4000-8000-000000000001"


def _identity() -> dict[str, str]:
    """Return test identity headers.

    Returns:
        Header mapping for ``APP_ENV=test``.
    """

    return {
        "X-Test-User-Id": _OWNER,
        "X-Test-Role": "owner",
        "X-Test-Authorization-Version": "1",
    }


class _AdmitService:
    """Canned Composite admit used by the HTTP contract."""

    def __init__(self, context: AuthorizedRuntimeContext, stream_path: str) -> None:
        """Store the admit result.

        Args:
            context: Authorized context.
            stream_path: Packet 6 path.
        """

        self._context = context
        self._stream_path = stream_path

    def submit_auto_message(
        self,
        caller: CallerContext,
        *,
        conversation_id: UUID,
        idempotency_key: UUID,
        message: str,
    ) -> tuple[AuthorizedRuntimeContext, str]:
        """Return the canned admit.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation.
            idempotency_key: Client key.
            message: User text.

        Returns:
            Context and stream path.
        """

        del caller, conversation_id, idempotency_key, message
        return self._context, self._stream_path


def _noop_rate_limit(*args: object, **kwargs: object) -> None:
    """Skip FastAPI-owned limiter in isolated HTTP tests.

    Args:
        *args: Ignored.
        **kwargs: Ignored.
    """

    del args, kwargs


def test_query_admission_route_is_registered() -> None:
    """``POST /conversations/{id}/messages`` is in OpenAPI."""

    with TestClient(create_app()) as raw:
        client = as_openapi_client(raw)
        schema = json_object(client.get("/openapi.json").json())
    paths = json_object(schema.get("paths", {}))
    assert "/conversations/{conversation_id}/messages" in paths
    methods = json_object(paths["/conversations/{conversation_id}/messages"])
    assert "post" in methods


def test_unauthenticated_message_submit_is_unauthorized() -> None:
    """Chat submit requires a bearer token or test identity."""

    with TestClient(create_app()) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            f"/conversations/{uuid4()}/messages",
            json={"message": "hello"},
        )
    assert response.status_code == 401


def test_auto_submit_admits_composite_and_returns_stream_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto chat uses the Composite envelope and does not invent SSE events."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(
        "smart_rag_api.routers.conversations.enforce_rate_limit",
        _noop_rate_limit,
    )
    run_id = uuid4()
    conversation_id = uuid4()
    reservation_id = uuid4()
    now = datetime.now(tz=UTC)
    context = AuthorizedRuntimeContext(
        user_id=UUID(_OWNER),
        role=UserRole.OWNER,
        authorization_version=1,
        conversation_id=conversation_id,
        run_id=run_id,
        reservation_id=reservation_id,
        reconnect=False,
        route_family=Phase6RouteFamily.COMPOSITE,
        deadline_at=now,
        recursion_limit=8,
        correction_ceiling=1,
        subquestion_ceiling=0,
        model_call_ceiling=8,
        tool_ceiling=3,
        discovery_ceiling=0,
        manifest_ceiling=2,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("0.50"),
        remaining_usd=Decimal("0.50"),
        remaining_prompt_tokens=8000,
        remaining_completion_tokens=2000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="c" * 64,
        status="pending",
    )
    stream_path = f"/runs/{run_id}/events"
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_query_run_service] = lambda: _AdmitService(
        context, stream_path
    )
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            f"/conversations/{conversation_id}/messages",
            json={
                "message": "Compare the two invoices",
                "idempotency_key": str(uuid4()),
            },
            headers=_identity(),
        )
    assert response.status_code == 202
    payload = json_object(response.json())
    assert payload["run_id"] == str(run_id)
    assert payload["reservation_id"] == str(reservation_id)
    assert payload["stream_path"] == stream_path
    assert payload["route_family"] == Phase6RouteFamily.COMPOSITE.value
    assert payload["reconnect"] is False
    assert "event" not in payload
    assert "sse" not in payload
