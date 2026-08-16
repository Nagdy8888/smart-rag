"""Dependency-aware liveness/readiness probes. Never claim query-ready in mock."""

from __future__ import annotations

from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict, Field
from smart_rag_core.runtime.valkey import ValkeyClient, ValkeyTimeoutError
from smart_rag_core.settings import BackendSettings


class DependencyStatus(BaseModel):
    """One named dependency probe.

    Attributes:
        name: Dependency id.
        status: ``ok``, ``unconfigured``, ``down``, ``mock``, or ``attached``.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    status: str


class ReadinessResponse(BaseModel):
    """Honest readiness payload.

    Attributes:
        status: ``unconfigured``, ``not_ready``, ``degraded``, or ``ready``.
        query_ready: True only when DB, Valkey, real models, and LightRAG
            attach are all healthy. Mock mode never sets this true.
        detail: Short operator-facing reason.
        rate_limit_degraded: True when the emergency limiter was used.
        dependencies: Named probe results.
    """

    model_config = ConfigDict(frozen=True)

    status: str
    query_ready: bool = False
    detail: str = ""
    rate_limit_degraded: bool = False
    dependencies: tuple[DependencyStatus, ...] = Field(default_factory=tuple)


def _probe_postgres(url: str | None) -> str:
    """Probe Postgres without claiming query-ready.

    Args:
        url: Optional DSN.

    Returns:
        ``unconfigured``, ``ok``, or ``down``.
    """

    if url is None:
        return "unconfigured"
    try:
        with psycopg.connect(url, connect_timeout=1) as connection:
            connection.execute("SELECT 1")
    except psycopg.Error:
        return "down"
    return "ok"


def _probe_valkey(client: ValkeyClient | None) -> str:
    """Probe a Valkey client.

    Args:
        client: Optional limits or cache client.

    Returns:
        ``unconfigured``, ``ok``, or ``down``.
    """

    if client is None:
        return "unconfigured"
    try:
        return "ok" if client.ping() else "down"
    except ValkeyTimeoutError:
        return "down"


def build_readiness(
    settings: BackendSettings | None,
    *,
    valkey_limits: ValkeyClient | None,
    valkey_cache: ValkeyClient | None,
    lightrag_attached: bool,
    rate_limit_degraded: bool,
    postgres_probe: str | None = None,
) -> ReadinessResponse:
    """Compose an honest readiness document.

    Args:
        settings: Lifespan settings, or None before startup.
        valkey_limits: Limits instance client.
        valkey_cache: Cache instance client.
        lightrag_attached: True when the runtime adapter is bound.
        rate_limit_degraded: Emergency limiter flag.
        postgres_probe: Optional precomputed DB probe for tests.

    Returns:
        Readiness payload. ``query_ready`` is false in mock mode, when
        LightRAG is unconfigured, or when DB/Valkey are not ok.
    """

    if settings is None:
        return ReadinessResponse(
            status="unconfigured",
            query_ready=False,
            detail="Settings not bound; process has not started.",
            dependencies=(
                DependencyStatus(name="database", status="unconfigured"),
                DependencyStatus(name="valkey_limits", status="unconfigured"),
                DependencyStatus(name="valkey_cache", status="unconfigured"),
                DependencyStatus(name="model_gateway", status="unconfigured"),
                DependencyStatus(name="lightrag", status="unconfigured"),
            ),
        )

    db_url = (
        settings.supabase_db_url.get_secret_value()
        if settings.supabase_db_url is not None
        else None
    )
    database = postgres_probe if postgres_probe is not None else _probe_postgres(db_url)
    limits = _probe_valkey(valkey_limits)
    cache = _probe_valkey(valkey_cache)
    model = "mock" if settings.mock_model_mode else "ok"
    graph = "attached" if lightrag_attached else "unconfigured"
    dependencies = (
        DependencyStatus(name="database", status=database),
        DependencyStatus(name="valkey_limits", status=limits),
        DependencyStatus(name="valkey_cache", status=cache),
        DependencyStatus(name="model_gateway", status=model),
        DependencyStatus(name="lightrag", status=graph),
    )

    query_ready = (
        database == "ok"
        and limits == "ok"
        and cache == "ok"
        and model == "ok"
        and graph == "attached"
        and not rate_limit_degraded
    )
    if database == "unconfigured":
        status_value = "unconfigured"
        detail = "Database URL unset; query path is not wired."
    elif database == "down":
        status_value = "not_ready"
        detail = "Database probe failed."
    elif query_ready:
        status_value = "ready"
        detail = "Dependencies healthy."
    else:
        status_value = "degraded"
        detail = "Service is up but not query-ready (mock, graph, Valkey, or limiter)."

    return ReadinessResponse(
        status=status_value,
        query_ready=query_ready,
        detail=detail,
        rate_limit_degraded=rate_limit_degraded,
        dependencies=dependencies,
    )


def readiness_as_dict(payload: ReadinessResponse) -> dict[str, Any]:
    """Convert readiness to a JSON-safe mapping.

    Args:
        payload: Readiness model.

    Returns:
        Dictionary for the HTTP response.
    """

    return {
        "status": payload.status,
        "query_ready": payload.query_ready,
        "detail": payload.detail,
        "rate_limit_degraded": payload.rate_limit_degraded,
        "dependencies": [
            {"name": item.name, "status": item.status} for item in payload.dependencies
        ],
    }
