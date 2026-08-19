"""FastAPI application entrypoint for the Smart RAG backend.

Importing this module must not construct provider clients, database pools, or
other networked dependencies. ``create_app`` loads typed settings so docs URLs
and ``version`` match the environment; sockets stay in lifespan.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from pydantic import SecretStr
from smart_rag_core.observability import configure_json_logging, correlation_context
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
        gateway factory, and, in mock mode, denies OpenAI DNS access.
        When ``LIGHTRAG_DB_URL`` is set, attaches the runtime LightRAG adapter
        without calling schema-admin ``initialize_storages``. Constructs Valkey
        clients without connecting. Starts a bounded ``ThreadPoolExecutor`` on
        ``application.state.offload_executor`` and shuts it down on exit.
        Finalizes the adapter on shutdown. Gateway and retrieval adapters are
        imported here so constructing ``create_app`` cannot form a retrieval
        import cycle.
    """

    from smart_rag_core.gateways import block_openai_network, create_model_gateway
    from smart_rag_core.retrieval.lightrag_adapter import bind_process_runtime_adapter
    from smart_rag_core.security.jwks import JwksVerifier

    from smart_rag_api.services.sse_stream import QueryRunRegistry

    settings = load_backend_settings()
    configure_json_logging(
        service=settings.service_name,
        environment=settings.app_env.value,
        level=settings.log_level.value,
    )
    application.state.settings = settings
    application.state.rate_limit_degraded = False
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
        app_env=settings.app_env.value,
    )
    application.state.query_run_registry = QueryRunRegistry()
    adapter = await bind_process_runtime_adapter(
        dsn=settings.lightrag_db_url,
        settings=settings,
    )
    application.state.lightrag_adapter = adapter
    try:
        async with block_openai_network(settings.mock_model_mode):
            application.state.model_gateway = create_model_gateway(settings)
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
        offload_executor.shutdown(wait=True, cancel_futures=True)
        application.state.offload_executor = None
        if adapter is not None:
            await adapter.finalize()
            application.state.lightrag_adapter = None


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
        Binds request-local logging context. It logs no URL, query, body,
        authorization header, or source content.
    """

    request_id = normalized_request_id(request.headers.get("X-Request-ID"))
    with correlation_context(request_id=request_id):
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
    from smart_rag_api.routers.entity_rules import router as entity_rules_router
    from smart_rag_api.routers.glossary import router as glossary_router
    from smart_rag_api.routers.graph_inspect import router as graph_inspect_router
    from smart_rag_api.routers.ingestion_crawl import router as ingestion_crawl_router
    from smart_rag_api.routers.ingestion_status import router as ingestion_status_router
    from smart_rag_api.routers.ops import router as ops_router
    from smart_rag_api.routers.query_runs import router as query_runs_router
    from smart_rag_api.routers.tables import router as tables_router
    from smart_rag_api.routers.tools import admin_router as tools_admin_router
    from smart_rag_api.routers.tools import catalog_router as tools_catalog_router
    from smart_rag_api.routers.usage import router as usage_router

    application.include_router(ops_router)
    application.include_router(auth_team_router)
    application.include_router(documents_router)
    application.include_router(conversations_router)
    application.include_router(query_runs_router)
    application.include_router(ingestion_status_router)
    application.include_router(ingestion_crawl_router)
    application.include_router(glossary_router)
    application.include_router(graph_inspect_router)
    application.include_router(entity_rules_router)
    application.include_router(tables_router)
    application.include_router(tools_catalog_router)
    application.include_router(tools_admin_router)
    application.include_router(usage_router)
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
