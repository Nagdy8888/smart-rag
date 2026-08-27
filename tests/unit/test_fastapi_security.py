"""Unit tests for Phase 6 packet 5 FastAPI security, offload, and isolation."""

from __future__ import annotations

import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from smart_rag_api.auth_admin.invitations import CreatedInvitation
from smart_rag_api.dependencies.services import get_model_gateway, get_postgres_url
from smart_rag_api.main import create_app
from smart_rag_api.routers.auth_team import get_auth_team_service
from smart_rag_api.routers.conversations import (
    get_conversation_service,
    get_query_run_service,
)
from smart_rag_api.routers.documents import get_document_service
from smart_rag_api.routers.query_runs import (
    get_query_run_service as get_run_fetch_service,
)
from smart_rag_api.routers.usage import get_usage_service
from smart_rag_api.services.documents_http import DocumentRecord
from smart_rag_core.conversations import ConversationRecord
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.runtime.offload import (
    CPU_SLICE_BUDGET_MS,
    OffloadCancelledError,
    OffloadExecutor,
    blocking_sleep_seconds,
    cpu_slice_over_budget,
    sample_event_loop_lag,
)
from smart_rag_core.security.audit_chain import (
    AUDIT_CHAIN_GENESIS_HASH,
    canonical_audit_material,
    redact_audit_payload,
    sha256_hex,
)
from smart_rag_core.security.audit_export import (
    AuditExportFault,
    AuditExportRow,
    LocalHmacAuditExporter,
    verify_audit_export_rows,
)
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.security.untrusted import isolate_untrusted_text
from smart_rag_core.settings import SettingsValidationError, load_backend_settings
from smart_rag_core.tools import (
    CORE_FORBIDDEN_TOOL_KEYS,
    default_registry,
    visible_tools,
)

from tests.unit.typed_openapi import as_openapi_client, json_object, json_object_list

_REPO = Path(__file__).resolve().parents[2]
_OWNER = "00000000-0000-4000-8000-000000000001"
_MEMBER = "00000000-0000-4000-8000-000000000002"
_VIEWER = "00000000-0000-4000-8000-000000000003"
_PACKET5_ROUTERS = (
    "auth_team.py",
    "conversations.py",
    "documents.py",
    "ingestion_status.py",
    "ops.py",
    "query_runs.py",
    "tables.py",
    "tools.py",
    "usage.py",
)


def _identity(user_id: str, role: str) -> dict[str, str]:
    """Return APP_ENV=test identity headers.

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


def _composite_context(
    *,
    run_id: UUID,
    conversation_id: UUID,
    reservation_id: UUID,
) -> AuthorizedRuntimeContext:
    """Build a Composite authorized context for HTTP tests.

    Args:
        run_id: Admitted run.
        conversation_id: Conversation.
        reservation_id: Reservation.

    Returns:
        Frozen authorized context.
    """

    now = datetime.now(tz=UTC)
    return AuthorizedRuntimeContext(
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
        payload_hash="a" * 64,
        status="pending",
    )


class _FakeConversationService:
    """In-memory conversation service for HTTP isolation tests."""

    def create(self, caller: CallerContext, *, title: str | None) -> ConversationRecord:
        """Escape the untrusted title exactly as production does.

        Args:
            caller: Authenticated caller.
            title: Optional raw title.

        Returns:
            Record with escaped title.
        """

        escaped = isolate_untrusted_text(title) if title else None
        return ConversationRecord(
            conversation_id=uuid4(),
            creator_user_id=UUID(caller.user_id),
            title=escaped,
            created_at=datetime.now(tz=UTC),
        )

    def list(
        self,
        caller: CallerContext,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[ConversationRecord, ...]:
        """Return no conversations.

        Args:
            caller: Authenticated caller.
            limit: Unused page size.
            cursor: Unused keyset cursor.

        Returns:
            Empty tuple.
        """

        del caller, limit, cursor
        return ()

    def get(
        self, caller: CallerContext, *, conversation_id: UUID
    ) -> ConversationRecord:
        """Return one escaped conversation.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation id.

        Returns:
            Record.
        """

        return ConversationRecord(
            conversation_id=conversation_id,
            creator_user_id=UUID(caller.user_id),
            title=isolate_untrusted_text("<em>owned</em>"),
            created_at=datetime.now(tz=UTC),
        )

    def delete(self, caller: CallerContext, *, conversation_id: UUID) -> None:
        """No-op owner delete for HTTP tests.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation id.
        """

        del caller, conversation_id

    async def generate_title(
        self,
        caller: CallerContext,
        *,
        conversation_id: UUID,
        gateway: object,
    ) -> ConversationRecord:
        """Return an escaped LLM-style title for HTTP tests.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation id.
            gateway: Unused gateway stand-in.

        Returns:
            Record with a compact escaped title.
        """

        del gateway
        return ConversationRecord(
            conversation_id=conversation_id,
            creator_user_id=UUID(caller.user_id),
            title=isolate_untrusted_text("Policy summary"),
            created_at=datetime.now(tz=UTC),
        )


class _FakeQueryRunService:
    """Admission stand-in that never opens Postgres."""

    def __init__(self, context: AuthorizedRuntimeContext, stream_path: str) -> None:
        """Store the canned admit result.

        Args:
            context: Authorized context.
            stream_path: Packet 6 stream path template.
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
        """Return the canned Composite admit.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation id.
            idempotency_key: Client key.
            message: User text.

        Returns:
            Context and stream path.
        """

        del caller, conversation_id, idempotency_key, message
        return self._context, self._stream_path

    def get(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
        """Reject foreign runs.

        Args:
            caller: Authenticated caller.
            run_id: Requested run.

        Returns:
            Never a foreign run.

        Raises:
            QueryAdmissionError: Always ``not_found``.
        """

        del caller, run_id
        raise QueryAdmissionError("not_found")


def _noop_rate_limit(*args: object, **kwargs: object) -> None:
    """Skip FastAPI-owned limiter in isolated HTTP tests.

    Args:
        *args: Ignored.
        **kwargs: Ignored.
    """

    del args, kwargs


def test_packet5_routers_do_not_import_repositories() -> None:
    """New packet 5 routers stay thin: no repository imports."""

    router_dir = _REPO / "apps" / "backend" / "src" / "smart_rag_api" / "routers"
    offenders: list[str] = []
    for name in _PACKET5_ROUTERS:
        tree = ast.parse((router_dir / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                if "repositories" in node.module:
                    offenders.append(f"{name}:{node.lineno}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "repositories" in alias.name:
                        offenders.append(f"{name}:{node.lineno}")
    assert offenders == []


def test_openapi_registers_packet5_paths() -> None:
    """Packet 5 routes appear in the public schema."""

    with TestClient(create_app()) as raw:
        client = as_openapi_client(raw)
        schema = json_object(client.get("/openapi.json").json())
    paths = json_object(schema.get("paths", {}))
    for path in (
        "/api/meta",
        "/me",
        "/conversations",
        "/conversations/{conversation_id}/messages",
        "/runs/{run_id}",
        "/runs/{run_id}/cancel",
        "/runs/{run_id}/citations",
        "/runs/{run_id}/events",
        "/tools",
        "/health/ready",
        "/ops/ready",
    ):
        assert path in paths, path


def test_api_meta_and_ready_never_claim_query_ready() -> None:
    """Handshake fields exist; mock/unconfigured processes are not query-ready."""

    with TestClient(create_app()) as raw:
        client = as_openapi_client(raw)
        meta = json_object(client.get("/api/meta").json())
        ready = json_object(client.get("/health/ready").json())
    assert "api_version" in meta
    assert "sse_schema_version" in meta
    assert "min_client_version" in meta
    assert ready["query_ready"] is False
    assert ready["status"] in {"unconfigured", "not_ready", "degraded"}
    assert "dependencies" not in ready
    serialized = str(ready).casefold()
    assert "paradedb" not in serialized
    assert "valkey" not in serialized
    assert "lightrag" not in serialized


def test_current_user_and_conversation_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``GET /me`` returns server role; conversation delete is 204."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.conversations.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_conversation_service] = lambda: (
        _FakeConversationService()
    )
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        me = client.get("/me", headers=_identity(_OWNER, "owner"))
        deleted = client.delete(
            f"/conversations/{uuid4()}",
            headers=_identity(_OWNER, "owner"),
        )
    assert me.status_code == 200
    body = json_object(me.json())
    assert body["role"] == "owner"
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert "text/html" not in deleted.headers.get("content-type", "")


def test_html_in_conversation_title_is_escaped_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Untrusted HTML is escaped in JSON and never returned as text/html."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.conversations.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_conversation_service] = lambda: (
        _FakeConversationService()
    )
    raw_title = '<script>alert("xss")</script>'
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            "/conversations",
            json={"title": raw_title},
            headers=_identity(_OWNER, "owner"),
        )
    assert response.status_code == 201
    assert "text/html" not in response.headers.get("content-type", "")
    assert response.headers.get("content-type", "").startswith("application/json")
    payload = json_object(response.json())
    title = str(payload["title"])
    assert "<script>" not in title
    assert "&lt;script&gt;" in title
    assert raw_title not in response.text


def test_generate_conversation_title_returns_escaped_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``POST /conversations/{id}/title`` returns the persisted title."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.conversations.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_conversation_service] = lambda: (
        _FakeConversationService()
    )
    application.dependency_overrides[get_model_gateway] = lambda: object()
    conversation_id = uuid4()
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            f"/conversations/{conversation_id}/title",
            headers=_identity(_OWNER, "owner"),
        )
    assert response.status_code == 200
    payload = json_object(response.json())
    assert payload["conversation_id"] == str(conversation_id)
    assert payload["title"] == "Policy summary"


def test_schema_extra_fields_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Injection of extra JSON fields is rejected."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.conversations.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            "/conversations",
            json={"title": "ok", "role": "owner"},
            headers=_identity(_OWNER, "owner"),
        )
    assert response.status_code == 422
    assert json_object(response.json())["detail"] == "validation_failed"


def test_oversized_body_is_rejected() -> None:
    """Content-Length above the configured cap returns 413 JSON."""

    with TestClient(create_app()) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            "/conversations",
            content=b"{}",
            headers={"content-type": "application/json", "content-length": "2000000"},
        )
    assert response.status_code == 413
    assert json_object(response.json())["detail"] == "payload_too_large"


def test_cors_reflects_exact_origin_not_wildcard() -> None:
    """Credentialed CORS reflects an allow-listed origin only."""

    with TestClient(create_app()) as raw:
        client = as_openapi_client(raw)
        allowed = client.get(
            "/health/live",
            headers={"Origin": "http://127.0.0.1:3000"},
        )
        denied = client.get(
            "/health/live",
            headers={"Origin": "https://evil.example"},
        )
    assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"
    assert allowed.headers.get("access-control-allow-credentials") == "true"
    allow_headers = allowed.headers.get("access-control-allow-headers", "")
    assert "X-Test-" not in allow_headers
    assert "Authorization" in allow_headers
    assert denied.headers.get("access-control-allow-origin") is None
    assert allowed.headers.get("x-content-type-options") == "nosniff"


def test_wildcard_cors_settings_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``CORS_ALLOW_ORIGINS=*`` cannot load."""

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    with pytest.raises(SettingsValidationError):
        load_backend_settings()


def test_viewer_tool_catalog_omits_admin_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live role recheck omits unauthorized tool names."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.tools.enforce_rate_limit",
        _noop_rate_limit,
    )
    with TestClient(create_app()) as raw:
        client = as_openapi_client(raw)
        viewer = client.get("/tools", headers=_identity(_VIEWER, "viewer"))
        owner = client.get("/tools", headers=_identity(_OWNER, "owner"))
    assert viewer.status_code == 200
    assert owner.status_code == 200
    viewer_keys = {str(item["tool_key"]) for item in json_object_list(viewer.json())}
    owner_keys = {str(item["tool_key"]) for item in json_object_list(owner.json())}
    assert "admin_user_invite" not in viewer_keys
    assert "admin_user_invite" in owner_keys
    assert CORE_FORBIDDEN_TOOL_KEYS.isdisjoint(viewer_keys)
    assert CORE_FORBIDDEN_TOOL_KEYS.isdisjoint(owner_keys)
    registry_viewer = {
        item.tool_key
        for item in visible_tools(default_registry(), role=UserRole.VIEWER)
    }
    assert viewer_keys == registry_viewer


def test_member_company_usage_is_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Members cannot read company usage."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.usage.enforce_rate_limit",
        _noop_rate_limit,
    )

    class _Usage:
        """Usage service stub that refuses member company reads."""

        def company_usage(self, caller: CallerContext) -> Any:
            """Reject members.

            Args:
                caller: Authenticated caller.

            Raises:
                QueryAdmissionError: ``forbidden``.
            """

            del caller
            raise QueryAdmissionError("forbidden")

    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_usage_service] = lambda: _Usage()
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        response = client.get("/usage/company", headers=_identity(_MEMBER, "member"))
    assert response.status_code == 403


def test_foreign_run_fetch_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IDOR run fetch returns 404, not 403."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.query_runs.enforce_rate_limit",
        _noop_rate_limit,
    )
    context = _composite_context(
        run_id=uuid4(),
        conversation_id=uuid4(),
        reservation_id=uuid4(),
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_run_fetch_service] = lambda: (
        _FakeQueryRunService(context, "/runs/x/events")
    )
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        response = client.get(f"/runs/{uuid4()}", headers=_identity(_MEMBER, "member"))
    assert response.status_code == 404
    assert json_object(response.json())["detail"] == "not_found"


def test_submit_message_returns_composite_stream_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto chat admits Composite and returns stream_path without SSE bodies."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.conversations.enforce_rate_limit",
        _noop_rate_limit,
    )
    run_id = uuid4()
    conversation_id = uuid4()
    reservation_id = uuid4()
    context = _composite_context(
        run_id=run_id,
        conversation_id=conversation_id,
        reservation_id=reservation_id,
    )
    stream_path = f"/runs/{run_id}/events"
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_query_run_service] = lambda: (
        _FakeQueryRunService(context, stream_path)
    )
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            f"/conversations/{conversation_id}/messages",
            json={"message": "What is the policy?"},
            headers={
                **_identity(_OWNER, "owner"),
                "Idempotency-Key": str(uuid4()),
                "X-Client-Version": "0.1.0",
            },
        )
    assert response.status_code == 202
    payload = json_object(response.json())
    assert payload["run_id"] == str(run_id)
    assert payload["stream_path"] == stream_path
    assert payload["route_family"] == "composite"
    assert "/events" in str(payload["stream_path"])


def test_operator_ready_returns_named_dependencies_for_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner ``GET /ops/ready`` includes named probes; members are forbidden."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    with TestClient(create_app()) as raw:
        client = as_openapi_client(raw)
        owner = client.get("/ops/ready", headers=_identity(_OWNER, "owner"))
        member = client.get("/ops/ready", headers=_identity(_MEMBER, "member"))
    assert owner.status_code == 200
    payload = json_object(owner.json())
    assert payload["query_ready"] is False
    dependencies = payload["dependencies"]
    names = {str(item["name"]) for item in json_object_list(dependencies)}
    assert "paradedb" in names
    assert "valkey_limits" in names
    assert "lightrag" in names
    assert member.status_code == 403


def test_lifespan_binds_offload_executor() -> None:
    """Serving processes keep a bounded thread pool on app state."""

    with TestClient(create_app()) as raw:
        executor = raw.app.state.offload_executor
        assert isinstance(executor, ThreadPoolExecutor)
        assert executor._max_workers == 8


def test_untrusted_text_helper_escapes_angle_brackets() -> None:
    """Prompt/data isolation helper HTML-escapes source text."""

    assert "<script>" not in isolate_untrusted_text("<script>x</script>")
    assert "&lt;script&gt;" in isolate_untrusted_text("<script>x</script>")


def _audit_row(
    *,
    seq: int,
    previous: str,
    payload: dict[str, str],
    event_id: UUID | None = None,
    mutate_hash: bool = False,
) -> AuditExportRow:
    """Build one locally hashed audit row.

    Args:
        seq: Chain sequence.
        previous: Previous hash or genesis.
        payload: Already-safe payload.
        event_id: Optional event id.
        mutate_hash: When True, store a wrong hash.

    Returns:
        Export row.
    """

    ident = event_id or uuid4()
    created = "2026-08-16T00:00:00+00:00"
    stored: dict[str, str] = {key: value for key, value in payload.items()}
    material = canonical_audit_material(
        event_type="test_event",
        actor_user_id=None,
        actor_role=None,
        target_type=None,
        target_id=None,
        authorization_version=1,
        visibility_generation=1,
        session_id=None,
        purpose="unit",
        resource_type=None,
        resource_id=None,
        payload=redact_audit_payload(payload),
        previous_hash=previous,
        created_at_iso=created,
    )
    digest = sha256_hex(material)
    if mutate_hash:
        digest = "b" * 64
    return AuditExportRow(
        chain_seq=seq,
        event_id=ident,
        event_hash=digest,
        previous_hash=previous,
        event_type="test_event",
        actor_user_id=None,
        actor_role=None,
        target_type=None,
        target_id=None,
        authorization_version=1,
        visibility_generation=1,
        session_id=None,
        purpose="unit",
        resource_type=None,
        resource_id=None,
        payload=stored,
        created_at_iso=created,
    )


def test_audit_export_detects_mutation_gap_fork_signing_and_passage() -> None:
    """Local HMAC exporter fails closed on chain faults. No passage text."""

    first = _audit_row(seq=1, previous=AUDIT_CHAIN_GENESIS_HASH, payload={"kind": "a"})
    second = _audit_row(seq=2, previous=first.event_hash, payload={"kind": "b"})
    ready = verify_audit_export_rows((first, second))
    assert ready.ready is True

    mutated = _audit_row(
        seq=1,
        previous=AUDIT_CHAIN_GENESIS_HASH,
        payload={"kind": "a"},
        mutate_hash=True,
    )
    assert verify_audit_export_rows((mutated,)).fault is AuditExportFault.MUTATED_ROW

    gapped = _audit_row(seq=3, previous=first.event_hash, payload={"kind": "c"})
    assert verify_audit_export_rows((first, gapped)).fault is AuditExportFault.GAP

    forked = _audit_row(
        seq=2,
        previous=AUDIT_CHAIN_GENESIS_HASH,
        payload={"kind": "fork"},
    )
    assert verify_audit_export_rows((first, forked)).fault is AuditExportFault.FORK

    passage = _audit_row(
        seq=1,
        previous=AUDIT_CHAIN_GENESIS_HASH,
        payload={"passage_text": "secret source"},
    )
    assert verify_audit_export_rows((passage,)).fault is AuditExportFault.PASSAGE_TEXT

    empty = verify_audit_export_rows(())
    assert empty.ready is False
    assert empty.fault is AuditExportFault.GAP

    unsigned = LocalHmacAuditExporter(b"").export((first, second))
    assert unsigned.ready is False
    assert unsigned.fault is AuditExportFault.SIGNING_FAILURE

    signed = LocalHmacAuditExporter(b"local-hmac-not-kms").export((first, second))
    assert signed.ready is True
    assert signed.signature_hex is not None


def test_cpu_slice_budget_and_offload_cancel() -> None:
    """Slices over 10 ms must offload; cancelled waits raise OffloadCancelledError."""

    assert CPU_SLICE_BUDGET_MS == 10.0
    assert cpu_slice_over_budget(0.011) is True
    assert cpu_slice_over_budget(0.001) is False

    async def _run() -> None:
        """Exercise thread offload, process offload, lag sample, and cancel."""

        executor = OffloadExecutor(cpu_workers=1, io_workers=1)
        try:
            slept = await executor.run_io(blocking_sleep_seconds, 0.0)
            assert slept == 0.0
            cpu = await executor.run_cpu(blocking_sleep_seconds, 0.0)
            assert cpu == 0.0
            lag = await sample_event_loop_lag(samples=5, interval_seconds=0.002)
            assert lag.p95_seconds >= 0.0
            task = asyncio.create_task(executor.run_io(blocking_sleep_seconds, 4.0))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(OffloadCancelledError):
                await task
        finally:
            executor.close()

    asyncio.run(_run())


class _FakeDocumentService:
    """In-memory document service for HTTP isolation tests."""

    def list(
        self,
        caller: CallerContext,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[DocumentRecord, ...]:
        """Return no documents.

        Args:
            caller: Authenticated caller.
            limit: Unused page size.
            cursor: Unused keyset cursor.

        Returns:
            Empty tuple.
        """

        del caller, limit, cursor
        return ()

    def get(self, caller: CallerContext, *, document_id: UUID) -> DocumentRecord:
        """Return one visible document.

        Args:
            caller: Authenticated caller.
            document_id: Document id.

        Returns:
            Record.
        """

        del caller
        return DocumentRecord(
            document_id=document_id,
            title="visible",
            visibility="company_visible",
            current_version_id=None,
            visibility_generation=1,
            created_at=datetime.now(tz=UTC),
        )

    def delete(self, caller: CallerContext, *, document_id: UUID) -> None:
        """Reject members; accept owner/admin.

        Args:
            caller: Authenticated caller.
            document_id: Document id.

        Raises:
            QueryAdmissionError: ``forbidden`` for members/viewers.
        """

        del document_id
        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")


class _FakeAuthTeamService:
    """Invitation create stand-in that never opens Postgres or mail."""

    def create_invitation(
        self,
        caller: CallerContext,
        *,
        email: str,
        role: str,
        upload_enabled: bool,
    ) -> CreatedInvitation:
        """Return a canned invitation including a mail-only token.

        Args:
            caller: Authenticated caller.
            email: Invitee email.
            role: Assigned role.
            upload_enabled: Upload flag.

        Returns:
            Created invitation.
        """

        del caller
        return CreatedInvitation(
            invitation_id=uuid4(),
            email=email,
            role=role,
            upload_enabled=upload_enabled,
            expires_at=datetime.now(tz=UTC),
            raw_token="mail-only-secret",  # noqa: S106 - fixture token, never a live secret
        )


def test_submit_message_rejects_missing_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paid POST without body or header idempotency key is 400."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.conversations.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_query_run_service] = lambda: (
        _FakeQueryRunService(
            _composite_context(
                run_id=uuid4(),
                conversation_id=uuid4(),
                reservation_id=uuid4(),
            ),
            "/runs/x/events",
        )
    )
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            f"/conversations/{uuid4()}/messages",
            json={"message": "What is the policy?"},
            headers={
                **_identity(_OWNER, "owner"),
                "X-Client-Version": "0.1.0",
            },
        )
    assert response.status_code == 400
    assert json_object(response.json())["detail"] == "idempotency_key_required"


def test_create_invitation_json_omits_raw_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invitation create JSON has identifiers only; token is a test header."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.auth_team.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_auth_team_service] = lambda: (
        _FakeAuthTeamService()
    )
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            "/admin/invitations",
            json={
                "email": "invitee@example.com",
                "role": "member",
                "upload_enabled": False,
            },
            headers=_identity(_OWNER, "owner"),
        )
    assert response.status_code == 201
    payload = json_object(response.json())
    assert "raw_token" not in payload
    assert payload["email"] == "invitee@example.com"
    assert response.headers.get("x-test-invitation-token") == "mail-only-secret"


def test_document_delete_is_owner_admin_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner DELETE is 204; members receive 403 for a visible document."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    monkeypatch.setattr(
        "smart_rag_api.routers.documents.enforce_rate_limit",
        _noop_rate_limit,
    )
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_document_service] = lambda: (
        _FakeDocumentService()
    )
    document_id = uuid4()
    with TestClient(application) as raw:
        client = as_openapi_client(raw)
        owner = client.delete(
            f"/documents/{document_id}",
            headers=_identity(_OWNER, "owner"),
        )
        member = client.delete(
            f"/documents/{document_id}",
            headers=_identity(_MEMBER, "member"),
        )
        schema = json_object(client.get("/openapi.json").json())
    assert owner.status_code == 204
    assert member.status_code == 403
    paths = json_object(schema.get("paths", {}))
    document_path = json_object(paths["/documents/{document_id}"])
    assert "delete" in document_path
    invite_schema = json_object(
        json_object(json_object(schema.get("components", {})).get("schemas", {})).get(
            "CreateInvitationResponse", {}
        )
    )
    invite_props = json_object(invite_schema.get("properties", {}))
    assert "raw_token" not in invite_props
