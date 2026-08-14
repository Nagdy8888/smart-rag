"""FastAPI application entrypoint for the Smart RAG backend.

Importing this module must not construct provider clients, database pools, or
other networked dependencies. The app object exists so process startup and
import smoke tests can load the transport boundary.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from smart_rag_core.gateways import block_openai_network, create_model_gateway
from smart_rag_core.observability import configure_json_logging, correlation_context
from smart_rag_core.security.jwks import JwksVerifier
from smart_rag_core.settings import BackendSettings, load_backend_settings

from smart_rag_api.middleware import normalized_request_id

LOGGER = logging.getLogger(__name__)


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
        No provider or database client is constructed.
    """

    settings = load_backend_settings()
    configure_json_logging(
        service=settings.service_name,
        environment=settings.app_env.value,
        level=settings.log_level.value,
    )
    application.state.settings = settings
    application.state.jwks_verifier = JwksVerifier(
        supabase_url=str(settings.supabase_url),
        audience=settings.supabase_jwt_audience,
        cache_seconds=settings.jwks_cache_seconds,
    )
    async with block_openai_network(settings.mock_model_mode):
        application.state.model_gateway = create_model_gateway(settings)
        LOGGER.info(
            "Backend foundation startup is unconfigured",
            extra={"event": "backend.startup.unconfigured"},
        )
        yield
        LOGGER.info(
            "Backend foundation shutdown",
            extra={"event": "backend.shutdown"},
        )


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


def create_app() -> FastAPI:
    """Create the import-safe FastAPI transport application.

    Returns:
        FastAPI application with liveness, honest unconfigured readiness, and
        correlation middleware.

    Side Effects:
        Creates in-memory FastAPI routing objects only. Settings validation and
        all lifecycle resources are deferred until application startup.
    """

    application = FastAPI(
        title="Smart RAG API",
        version="0.1.0",
        description=(
            "Phase 1 foundation transport scaffold. Business routes are not "
            "implemented; readiness is unconfigured until later phases."
        ),
        lifespan=lifespan,
    )
    application.middleware("http")(add_correlation_context)
    application.get("/health/live", tags=["health"])(live)
    application.get("/health/ready", tags=["health"])(ready)
    from smart_rag_api.routers.glossary import router as glossary_router
    from smart_rag_api.routers.ingestion_crawl import router as ingestion_crawl_router
    from smart_rag_api.routers.ingestion_status import router as ingestion_status_router

    application.include_router(ingestion_status_router)
    application.include_router(ingestion_crawl_router)
    application.include_router(glossary_router)
    return application


def live() -> dict[str, str]:
    """Call the registered liveness behavior for direct smoke tests.

    Returns:
        A mapping with ``status=live``.
    """

    return {"status": "live"}


def ready() -> dict[str, str]:
    """Call the honest unconfigured readiness behavior for direct smoke tests.

    Returns:
        A mapping with ``status=unconfigured``.
    """

    return {
        "status": "unconfigured",
        "detail": "Phase 1 foundation scaffold; dependencies not wired.",
    }


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
