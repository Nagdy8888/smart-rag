"""HTTP helpers for packet 6 SSE contract tests."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from smart_rag_api.dependencies.services import get_postgres_url
from smart_rag_api.main import create_app
from smart_rag_api.routers.conversations import get_query_run_service
from smart_rag_api.routers.query_runs import (
    get_query_run_service as get_run_fetch_service,
)
from smart_rag_api.services.sse_stream import FixtureQueryRunExecutor, QueryRunRegistry
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.settings import BackendSettings, load_backend_settings
from smart_rag_core.sse.store import MemoryRunEventStore

from tests.unit.typed_openapi import OpenAPIClient, as_openapi_client


def require_str(value: object) -> str:
    """Narrow a JSON field to str.

    Args:
        value: Decoded JSON value.

    Returns:
        The string.

    Raises:
        TypeError: If the value is not a string.
    """

    if not isinstance(value, str):
        raise TypeError("expected string")
    return value


OWNER_ID = "00000000-0000-4000-8000-000000000001"
MEMBER_ID = "00000000-0000-4000-8000-000000000002"


def client_headers(user_id: str = OWNER_ID, *, role: str = "owner") -> dict[str, str]:
    """Return test identity plus a supported client version.

    Args:
        user_id: Subject UUID.
        role: Role label.

    Returns:
        Header mapping including ``X-Client-Version``.
    """

    return {
        "X-Test-User-Id": user_id,
        "X-Test-Role": role,
        "X-Test-Authorization-Version": "1",
        "X-Client-Version": "0.1.0",
        "Accept": "application/json",
    }


def sse_headers(user_id: str = OWNER_ID, *, role: str = "owner") -> dict[str, str]:
    """Return identity headers that request an EventSource body.

    Args:
        user_id: Subject UUID.
        role: Role label.

    Returns:
        Header mapping with ``Accept: text/event-stream``.
    """

    return {
        **client_headers(user_id, role=role),
        "Accept": "text/event-stream",
    }


def noop_rate_limit(*args: object, **kwargs: object) -> None:
    """Skip FastAPI-owned limiter in isolated HTTP tests.

    Args:
        *args: Ignored.
        **kwargs: Ignored.
    """

    del args, kwargs


def patch_sse_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable router and pre-auth limiters for SSE HTTP tests.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """

    monkeypatch.setattr(
        "smart_rag_api.dependencies.services.enforce_rate_limit",
        noop_rate_limit,
    )
    monkeypatch.setattr(
        "smart_rag_api.routers.conversations.enforce_rate_limit",
        noop_rate_limit,
    )
    monkeypatch.setattr(
        "smart_rag_api.routers.query_runs.enforce_rate_limit",
        noop_rate_limit,
    )


def composite_context(
    *,
    run_id: UUID | None = None,
    conversation_id: UUID | None = None,
    reservation_id: UUID | None = None,
    user_id: str = OWNER_ID,
    reconnect: bool = False,
    status: str = "pending",
) -> AuthorizedRuntimeContext:
    """Build a Composite authorized context.

    Args:
        run_id: Admitted run.
        conversation_id: Conversation.
        reservation_id: Reservation.
        user_id: Owner UUID string.
        reconnect: Duplicate-key flag.
        status: Durable status.

    Returns:
        Frozen authorized context.
    """

    now = datetime.now(tz=UTC)
    return AuthorizedRuntimeContext(
        user_id=UUID(user_id),
        role=UserRole.OWNER if user_id == OWNER_ID else UserRole.MEMBER,
        authorization_version=1,
        conversation_id=conversation_id or uuid4(),
        run_id=run_id or uuid4(),
        reservation_id=reservation_id or uuid4(),
        reconnect=reconnect,
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
        status=status,
    )


class RecordingAdmitService:
    """Idempotent admit stand-in that never opens Postgres."""

    def __init__(self) -> None:
        """Create an empty key map."""

        self.calls = 0
        self._by_key: dict[UUID, AuthorizedRuntimeContext] = {}

    def submit_auto_message(
        self,
        caller: CallerContext,
        *,
        conversation_id: UUID,
        idempotency_key: UUID,
        message: str,
        requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO,
    ) -> tuple[AuthorizedRuntimeContext, str]:
        """Admit or reconnect one Composite run.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation.
            idempotency_key: Client key.
            message: User text.
            requested_search_scope: Client source preference stored on the run.

        Returns:
            Context and stream path.
        """

        del message
        self.calls += 1
        existing = self._by_key.get(idempotency_key)
        if existing is not None:
            reused = existing.model_copy(update={"reconnect": True})
            return reused, f"/runs/{reused.run_id}/events"
        context = composite_context(
            conversation_id=conversation_id,
            user_id=caller.user_id,
        ).model_copy(update={"requested_search_scope": requested_search_scope})
        self._by_key[idempotency_key] = context
        return context, f"/runs/{context.run_id}/events"

    def get(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
        """Fetch an owned canned run.

        Args:
            caller: Caller.
            run_id: Run id.

        Returns:
            Run record.

        Raises:
            QueryAdmissionError: Foreign or missing.
        """

        for context in self._by_key.values():
            if context.run_id == run_id:
                if str(context.user_id) != caller.user_id:
                    raise QueryAdmissionError("not_found")
                return QueryRunRecord(
                    run_id=context.run_id,
                    conversation_id=context.conversation_id,
                    creator_user_id=context.user_id,
                    status=context.status,
                    reservation_id=context.reservation_id,
                    requested_search_scope=context.requested_search_scope,
                    created_at=None,
                )
        raise QueryAdmissionError("not_found")

    def cancel(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
        """Mark a canned run cancelled.

        Args:
            caller: Caller.
            run_id: Run id.

        Returns:
            Updated record.

        Raises:
            QueryAdmissionError: Foreign or missing.
        """

        record = self.get(caller, run_id=run_id)
        return QueryRunRecord(
            run_id=record.run_id,
            conversation_id=record.conversation_id,
            creator_user_id=record.creator_user_id,
            status="cancelled",
            reservation_id=record.reservation_id,
            created_at=record.created_at,
        )


def build_sse_app(
    *,
    store: MemoryRunEventStore,
    executor: FixtureQueryRunExecutor,
    admit: RecordingAdmitService,
) -> FastAPI:
    """Create a FastAPI app with in-memory SSE dependencies.

    Args:
        store: Event store bound after startup.
        executor: Fixture executor bound after startup.
        admit: Admit stand-in.

    Returns:
        Application with dependency overrides. Caller must bind ``app.state``
        store/executor (and settings when lifespan is not started).
    """

    del store, executor
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_query_run_service] = lambda: admit
    application.dependency_overrides[get_run_fetch_service] = lambda: admit
    return application


def bind_sse_state(
    application: object,
    *,
    store: MemoryRunEventStore,
    executor: FixtureQueryRunExecutor,
    registry: QueryRunRegistry | None = None,
    settings: BackendSettings | None = None,
) -> None:
    """Attach in-memory SSE collaborators on ``app.state``.

    Args:
        application: FastAPI app or TestClient ``.app``.
        store: Event store.
        executor: Fixture executor.
        registry: Optional process registry. ``None`` keeps lifespan registry.
        settings: Optional settings when lifespan is not running.
    """

    state = getattr(application, "state", None)
    if state is None:
        raise TypeError("application_state_missing")
    if settings is not None:
        state.settings = settings
    state.run_event_store = store
    state.query_run_executor = executor
    state.rate_limit_degraded = False
    if registry is not None:
        state.query_run_registry = registry


@contextmanager
def sse_test_client(
    *,
    store: MemoryRunEventStore,
    executor: FixtureQueryRunExecutor,
    admit: RecordingAdmitService,
) -> Generator[TestClient, None, None]:
    """Enter TestClient lifespan and bind the in-memory SSE store.

    Args:
        store: Event store.
        executor: Fixture executor.
        admit: Admit stand-in.

    Yields:
        Started TestClient.
    """

    application = build_sse_app(store=store, executor=executor, admit=admit)
    with TestClient(application) as client:
        bind_sse_state(application, store=store, executor=executor)
        yield client


@contextmanager
def sse_openapi_client(
    *,
    store: MemoryRunEventStore,
    executor: FixtureQueryRunExecutor,
    admit: RecordingAdmitService,
) -> Generator[OpenAPIClient, None, None]:
    """Enter a typed TestClient for JSON and completed SSE bodies.

    Args:
        store: Event store.
        executor: Fixture executor.
        admit: Admit stand-in.

    Yields:
        OpenAPI-typed client.
    """

    with sse_test_client(store=store, executor=executor, admit=admit) as raw:
        yield as_openapi_client(raw)


def lifespanless_sse_app(
    *,
    store: MemoryRunEventStore,
    executor: FixtureQueryRunExecutor,
    admit: RecordingAdmitService,
    registry: QueryRunRegistry | None = None,
) -> FastAPI:
    """Build an app with settings bound and no lifespan sockets.

    Args:
        store: Event store.
        executor: Fixture executor.
        admit: Admit stand-in.
        registry: Optional registry. A new empty registry is used when omitted.

    Returns:
        App ready for ``httpx.ASGITransport``.
    """

    application = build_sse_app(store=store, executor=executor, admit=admit)
    bind_sse_state(
        application,
        store=store,
        executor=executor,
        registry=registry or QueryRunRegistry(),
        settings=load_backend_settings(),
    )
    return application
