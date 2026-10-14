"""FastAPI application entrypoint for the Smart RAG backend.

Importing this module must not construct provider clients, database pools, or
other networked dependencies. ``create_app`` loads typed settings so docs URLs
and ``version`` match the environment; sockets stay in lifespan.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from pydantic import SecretStr
from smart_rag_core.observability import (
    configure_error_telemetry,
    configure_json_logging,
    configure_langsmith,
    correlation_context,
    flush_error_telemetry,
    telemetry_span,
)
from smart_rag_core.settings import BackendSettings, Environment, load_backend_settings

from smart_rag_api.dependencies.identity import reject_forbidden_test_identity_headers
from smart_rag_api.middleware import (
    add_cors,
    add_security_headers,
    install_error_handlers,
    limit_preauth_ip,
    limit_request_body,
    normalized_request_id,
)
from smart_rag_api.services.readiness import build_readiness, public_readiness_as_dict

if TYPE_CHECKING:
    from smart_rag_core.runtime.valkey import SocketValkeyClient

LOGGER = logging.getLogger(__name__)
_OFFLOAD_MAX_WORKERS = 8


def _bind_valkey_client(
    url: SecretStr | None, *, timeout_seconds: float
) -> SocketValkeyClient | None:
    """Construct a per-command Valkey client without opening a socket.

    Args:
        url: Optional Redis-protocol URL secret.
        timeout_seconds: Connect/command timeout.

    Returns:
        Client or None when the URL is unset.
    """
    from smart_rag_core.runtime.valkey import SocketValkeyClient

    if url is None:
        return None
    secret = url.get_secret_value()
    if not secret:
        return None
    return SocketValkeyClient(secret, timeout_seconds=timeout_seconds)


def _warm_app_api_pools(postgres_url: str) -> None:
    """Open one admission session and one run session, then return them idle.

    A failure is logged by type only. The first Ask still connects on demand.

    Args:
        postgres_url: Transaction-pooler URL. Never logged.

    Side Effects:
        Leaves at most one idle connection in each app_api pool.
    """
    from smart_rag_api.services.api_postgres_pool import admission_session
    from smart_rag_api.services.query_graph_runtime import (
        open_run_app_api_connection,
        release_run_app_api_connection,
    )

    try:
        with admission_session(postgres_url) as connection:
            connection.execute("SELECT 1")
            connection.rollback()
    except Exception as exc:
        LOGGER.warning(
            "admission pool warmup failed",
            extra={
                "event": "backend.query_runtime.admission_pool_warmup_failed",
                "error_type": type(exc).__name__,
            },
        )
    try:
        run_connection = open_run_app_api_connection(postgres_url)
    except Exception as exc:
        LOGGER.warning(
            "run pool warmup failed",
            extra={
                "event": "backend.query_runtime.run_pool_warmup_failed",
                "error_type": type(exc).__name__,
            },
        )
        return
    release_run_app_api_connection(run_connection)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    """Validate startup settings and own lifecycle-scoped foundation resources.

    Args:
        application: FastAPI application entering its process lifespan.

    Yields:
        Control while validated settings, structured logs, the deterministic
        model gateway, and mock-mode network guard are active.

    Raises:
        SettingsValidationError: If environment configuration is invalid.
        ModelGatewayUnavailableError: If real-model mode is requested before
            the provider adapter is implemented.

    Side Effects:
        Configures process logging, LangSmith hide/tracing flags via the model
        gateway factory, optional GlitchTip and Grafana export, and, in mock
        mode, denies OpenAI DNS access. Shutdown flushes both LangSmith and
        error telemetry for at most two seconds.
        When ``LIGHTRAG_DB_URL`` is set, attaches the runtime LightRAG adapter
        without calling schema-admin ``initialize_storages``. Constructs Valkey
        clients without connecting.         Starts a bounded ``ThreadPoolExecutor`` on
        ``application.state.offload_executor`` and shuts it down on exit.
        When ``PDF_EVAL_WORKSPACE_ENABLED`` is true in local/test and an
        ``app_api`` DSN is set, starts one exam supervisor task. Durable
        exam authority remains SQL claim/heartbeat, not the task.
        Closes a lazily created run-event database store and finalizes the
        adapter on shutdown, then gives the process-cached LangSmith client at
        most two seconds to drain. Outside ``test``, binds one query executor
        and warms Hybrid/checkpointer/graph compile so the first Ask run does
        not open hosted pools under the Composite deadline. Gateway and
        retrieval adapters are imported here so constructing ``create_app``
        cannot form a retrieval import cycle.
    """
    from smart_rag_core.gateways import block_openai_network, create_model_gateway
    from smart_rag_core.observability.langsmith_tracing import flush_langsmith_traces
    from smart_rag_core.retrieval.lightrag_adapter import bind_process_runtime_adapter
    from smart_rag_core.security.jwks import JwksVerifier

    from smart_rag_api.services.sse_stream import (
        LangGraphQueryRunExecutor,
        QueryRunRegistry,
    )

    settings = load_backend_settings()
    configure_json_logging(
        service=settings.service_name,
        environment=settings.app_env.value,
        level=settings.log_level.value,
    )
    configure_langsmith(settings)
    configure_error_telemetry(settings)
    LOGGER.info(
        "LangSmith tracing configured project=%s enabled=%s",
        settings.langsmith_project,
        settings.langsmith_tracing,
        extra={"event": "backend.langsmith.configured"},
    )
    application.state.settings = settings
    application.state.rate_limit_degraded = False
    application.state.query_runtime_warmed = False
    offload_executor = ThreadPoolExecutor(
        max_workers=_OFFLOAD_MAX_WORKERS,
        thread_name_prefix="api-offload",
    )
    application.state.offload_executor = offload_executor
    application.state.valkey_limits_client = _bind_valkey_client(
        settings.valkey_limits_url,
        timeout_seconds=settings.valkey_timeout_seconds,
    )
    application.state.valkey_cache_client = _bind_valkey_client(
        settings.valkey_cache_url,
        timeout_seconds=settings.valkey_timeout_seconds,
    )
    application.state.jwks_verifier = JwksVerifier(
        supabase_url=str(settings.supabase_url),
        audience=settings.supabase_jwt_audience,
        cache_seconds=settings.jwks_cache_seconds,
    )
    application.state.query_run_registry = QueryRunRegistry()
    query_executor: LangGraphQueryRunExecutor | None = None
    warmup_task: asyncio.Task[None] | None = None
    exam_task: asyncio.Task[None] | None = None
    adapter = await bind_process_runtime_adapter(
        dsn=settings.lightrag_db_url,
        settings=settings,
    )
    application.state.lightrag_adapter = adapter
    try:
        async with block_openai_network(settings.mock_model_mode):
            application.state.model_gateway = create_model_gateway(settings)
            if settings.app_env is not Environment.TEST:
                query_executor = LangGraphQueryRunExecutor()
                application.state.query_run_executor = query_executor
                warmed_executor = query_executor

                async def _warmup_query_runtime() -> None:
                    """Open process query pools without blocking ``/health/live``.

                    Side Effects:
                        Caches Hybrid, memory store, checkpointer, and the
                        compiled graph on ``warmed_executor``. Opens one idle
                        admission connection and one idle run connection so
                        the first Ask skips those pooler handshakes. Failures
                        are logged by type only so DSN text cannot leak.
                    """
                    try:
                        await warmed_executor.warmup(settings)
                        dsn = settings.supabase_db_url
                        if dsn is not None:
                            await asyncio.to_thread(
                                _warm_app_api_pools,
                                dsn.get_secret_value(),
                            )
                        application.state.query_runtime_warmed = True
                        LOGGER.info(
                            "query runtime warmed",
                            extra={"event": "backend.query_runtime.warmed"},
                        )
                    except Exception as exc:
                        application.state.query_runtime_warmed = False
                        LOGGER.warning(
                            "query runtime warmup failed; first Ask run opens lazily",
                            extra={
                                "event": "backend.query_runtime.warmup_failed",
                                "error_type": type(exc).__name__,
                            },
                        )

                warmup_task = asyncio.create_task(_warmup_query_runtime())
            from smart_rag_api.services.eval_exam_supervisor import (
                bind_eval_exam_supervisor,
            )

            exam_task = bind_eval_exam_supervisor(application, settings)
            LOGGER.info(
                "Backend foundation startup",
                extra={"event": "backend.startup"},
            )
            yield
            LOGGER.info(
                "Backend foundation shutdown",
                extra={"event": "backend.shutdown"},
            )
    finally:
        if exam_task is not None:
            exam_task.cancel()
            try:
                await exam_task
            except asyncio.CancelledError:
                pass
            application.state.eval_exam_supervisor = None
        if warmup_task is not None:
            warmup_task.cancel()
            try:
                await warmup_task
            except asyncio.CancelledError:
                pass
        if query_executor is not None:
            await query_executor.aclose()
            application.state.query_run_executor = None
        run_event_store = getattr(application.state, "run_event_store", None)
        close_run_event_store = getattr(run_event_store, "close", None)
        if callable(close_run_event_store):
            close_run_event_store()
            application.state.run_event_store = None
        from smart_rag_api.services.api_postgres_pool import close_api_postgres_pools

        close_api_postgres_pools()
        offload_executor.shutdown(wait=True, cancel_futures=True)
        application.state.offload_executor = None
        if adapter is not None:
            await adapter.finalize()
            application.state.lightrag_adapter = None
        flush_langsmith_traces(timeout_seconds=2.0)
        flush_error_telemetry(timeout_seconds=2.0)


async def add_correlation_context(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Bind a safe request identifier and return it to the caller.

    Args:
        request: Incoming HTTP request.
        call_next: FastAPI middleware continuation.

    Returns:
        Downstream response with ``X-Request-ID`` set.

    Side Effects:
        Binds request-local logging context and, when OTLP export is on, a
        span named ``http.request``. It logs no URL, query, body,
        authorization header, or source content.
    """
    request_id = normalized_request_id(request.headers.get("X-Request-ID"))
    with correlation_context(request_id=request_id), telemetry_span("http.request"):
        LOGGER.info(
            "HTTP request started",
            extra={"event": "http.request.started"},
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        LOGGER.info(
            "HTTP request completed",
            extra={"event": "http.request.completed"},
        )
        return response


def _openapi_docs_enabled(settings: BackendSettings) -> bool:
    """Return whether unauthenticated OpenAPI/docs routes may be mounted.

    Staging and production disable ``/docs``, ``/redoc``, and
    ``/openapi.json``. Local and test keep them for developers.

    Args:
        settings: Validated backend settings.

    Returns:
        True only for ``local`` and ``test``.
    """
    return settings.app_env in {Environment.LOCAL, Environment.TEST}


def create_app() -> FastAPI:
    """Create the FastAPI transport application.

    Settings load is the approved configuration boundary. Docs URLs and the
    public ``version`` follow that snapshot. Lifecycle sockets still start
    in ``lifespan``.

    Returns:
        FastAPI application with thin routers, security middleware, and
        dependency-aware readiness.

    Raises:
        SettingsValidationError: If environment configuration is invalid.

    Side Effects:
        Reads process environment through ``load_backend_settings``.
    """
    settings = load_backend_settings()
    docs_enabled = _openapi_docs_enabled(settings)
    application = FastAPI(
        title="Smart RAG API",
        version=settings.api_version,
        description=(
            "Authenticated RAG API with Bearer fetch SSE. "
            "Readiness is dependency-aware and never query-ready in mock mode."
        ),
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    application.middleware("http")(add_correlation_context)
    application.middleware("http")(limit_preauth_ip)
    application.middleware("http")(limit_request_body)
    application.middleware("http")(add_security_headers)
    application.middleware("http")(add_cors)
    application.middleware("http")(reject_forbidden_test_identity_headers)
    install_error_handlers(application)

    from smart_rag_api.routers.auth_team import router as auth_team_router
    from smart_rag_api.routers.conversations import router as conversations_router
    from smart_rag_api.routers.documents import router as documents_router
    from smart_rag_api.routers.figures import router as figures_router
    from smart_rag_api.routers.entity_rules import router as entity_rules_router
    from smart_rag_api.routers.glossary import router as glossary_router
    from smart_rag_api.routers.governance_reviews import (
        router as governance_reviews_router,
    )
    from smart_rag_api.routers.graph_inspect import router as graph_inspect_router
    from smart_rag_api.routers.ingestion_crawl import router as ingestion_crawl_router
    from smart_rag_api.routers.ingestion_status import router as ingestion_status_router
    from smart_rag_api.routers.ops import router as ops_router
    from smart_rag_api.routers.pdf_eval import (
        pdf_eval_routes_enabled,
    )
    from smart_rag_api.routers.pdf_eval import (
        router as pdf_eval_router,
    )
    from smart_rag_api.routers.query_runs import router as query_runs_router
    from smart_rag_api.routers.tables import router as tables_router
    from smart_rag_api.routers.tools import admin_router as tools_admin_router
    from smart_rag_api.routers.tools import catalog_router as tools_catalog_router
    from smart_rag_api.routers.usage import router as usage_router

    application.include_router(ops_router)
    application.include_router(auth_team_router)
    application.include_router(documents_router)
    application.include_router(figures_router)
    application.include_router(conversations_router)
    application.include_router(query_runs_router)
    application.include_router(ingestion_status_router)
    application.include_router(ingestion_crawl_router)
    application.include_router(glossary_router)
    application.include_router(governance_reviews_router)
    application.include_router(graph_inspect_router)
    application.include_router(entity_rules_router)
    application.include_router(tables_router)
    application.include_router(tools_catalog_router)
    application.include_router(tools_admin_router)
    application.include_router(usage_router)
    if pdf_eval_routes_enabled(settings):
        application.include_router(pdf_eval_router)
    return application


def live() -> dict[str, str]:
    """Call the registered liveness behavior for direct smoke tests.

    Returns:
        A mapping with ``status=live``.
    """
    return {"status": "live"}


def ready() -> dict[str, object]:
    """Import-time readiness: settings are not bound, so status is unconfigured.

    HTTP ``GET /health/ready`` uses request-scoped probes. This helper stays
    honest for package-import tests that never start lifespan.

    Returns:
        Readiness mapping with ``status=unconfigured`` and ``query_ready=false``
        in the public shape (no named dependencies).
    """
    payload = build_readiness(
        None,
        valkey_limits=None,
        valkey_cache=None,
        lightrag_attached=False,
        rate_limit_degraded=False,
    )
    return public_readiness_as_dict(payload)


app = create_app()


def run() -> None:
    """Validate process settings and run uvicorn as a console script.

    Side Effects:
        Reads centralized settings and starts an HTTP server. Provider/database
        clients are not initialized at import time.

    Raises:
        SettingsValidationError: If backend settings are invalid.
        ModuleNotFoundError: If uvicorn is not installed in the environment.
    """
    import uvicorn

    settings: BackendSettings = load_backend_settings()
    uvicorn.run(
        "smart_rag_api.main:app",
        host=settings.bind_host,
        port=settings.bind_port,
        factory=False,
    )


__all__ = [
    "add_correlation_context",
    "app",
    "create_app",
    "lifespan",
    "live",
    "ready",
    "run",
]
