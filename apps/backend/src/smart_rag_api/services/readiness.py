"""Dependency-aware liveness/readiness probes. Never claim query-ready in mock."""

from __future__ import annotations

from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict, Field
from smart_rag_core.runtime.valkey import ValkeyClient, ValkeyTimeoutError
from smart_rag_core.settings import BackendSettings
from smart_rag_core.settings.postgres_dsn import TransactionPoolerDsnError


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
        query_ready: True only when the core Hybrid query path, durable
            checkpointer/store, Valkey, and real models are healthy. Mock
            mode never sets this true. Missing LightRAG is a typed
            degraded dependency and does not clear ``query_ready``.
            ParadeDB down is reported but does not block ``query_ready``;
            Hybrid then degrades to dense+term.
        detail: Short operator-facing reason.
        rate_limit_degraded: True while the emergency limiter is still
            in use. Cleared after Valkey probes succeed again.
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


def _probe_paradedb(url: str | None) -> str:
    """Probe the private ParadeDB projection database.

    Unavailability is an approved Hybrid degradation, not a liveness failure.

    Args:
        url: Optional ParadeDB DSN from ``PARADEDB_URL``.

    Returns:
        ``unconfigured``, ``ok``, or ``down``.
    """

    return _probe_postgres(url)


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


def _probe_checkpoint(dsn: str | None) -> str:
    """Open the pinned LangGraph saver and store, then close.

    Args:
        dsn: Optional session/direct checkpoint DSN.

    Returns:
        ``unconfigured``, ``ok``, or ``down``. The result never includes
        the DSN.
    """

    if dsn is None:
        return "unconfigured"
    try:
        from smart_rag_agents.query.checkpointer import probe_query_checkpoint_runtime

        probe_query_checkpoint_runtime(dsn, timeout_seconds=1)
    except (TransactionPoolerDsnError, ValueError, psycopg.Error, OSError):
        return "down"
    except Exception:
        return "down"
    return "ok"


def build_readiness(
    settings: BackendSettings | None,
    *,
    valkey_limits: ValkeyClient | None,
    valkey_cache: ValkeyClient | None,
    lightrag_attached: bool,
    rate_limit_degraded: bool,
    postgres_probe: str | None = None,
    paradedb_probe: str | None = None,
    checkpoint_probe: str | None = None,
) -> ReadinessResponse:
    """Compose an honest readiness document.

    Args:
        settings: Lifespan settings, or None before startup.
        valkey_limits: Limits instance client.
        valkey_cache: Cache instance client.
        lightrag_attached: True when the runtime adapter is bound.
        rate_limit_degraded: Emergency limiter flag. Callers should pass
            False once Valkey probes are ``ok`` again.
        postgres_probe: Optional precomputed DB probe for tests.
        paradedb_probe: Optional precomputed ParadeDB probe for tests.
        checkpoint_probe: Optional precomputed checkpointer/store probe
            for tests.

    Returns:
        Readiness payload. ``query_ready`` is true when the core Hybrid
        path, durable checkpointer/store, Valkey, and real models are
        usable. Mock mode never sets it true. Missing LightRAG degrades
        graph but does not clear ``query_ready``. ParadeDB ``down`` is
        visible and does not by itself clear ``query_ready``.
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
                DependencyStatus(name="paradedb", status="unconfigured"),
                DependencyStatus(name="langgraph_checkpoint", status="unconfigured"),
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
    paradedb_url = (
        settings.paradedb_url.get_secret_value()
        if settings.paradedb_url is not None
        else None
    )
    paradedb = (
        paradedb_probe if paradedb_probe is not None else _probe_paradedb(paradedb_url)
    )
    try:
        checkpoint_dsn = settings.resolved_checkpoint_dsn()
    except (TransactionPoolerDsnError, ValueError):
        checkpoint_dsn = None
        checkpoint = "down"
    else:
        checkpoint = (
            checkpoint_probe
            if checkpoint_probe is not None
            else _probe_checkpoint(checkpoint_dsn)
        )
    limits = _probe_valkey(valkey_limits)
    cache = _probe_valkey(valkey_cache)
    model = "mock" if settings.mock_model_mode else "ok"
    graph = "attached" if lightrag_attached else "unconfigured"
    dependencies = (
        DependencyStatus(name="database", status=database),
        DependencyStatus(name="valkey_limits", status=limits),
        DependencyStatus(name="valkey_cache", status=cache),
        DependencyStatus(name="paradedb", status=paradedb),
        DependencyStatus(name="langgraph_checkpoint", status=checkpoint),
        DependencyStatus(name="model_gateway", status=model),
        DependencyStatus(name="lightrag", status=graph),
    )

    query_ready = (
        database == "ok"
        and checkpoint == "ok"
        and limits == "ok"
        and cache == "ok"
        and model == "ok"
        and not rate_limit_degraded
    )
    if database == "unconfigured":
        status_value = "unconfigured"
        detail = "Database URL unset; query path is not wired."
    elif database == "down":
        status_value = "not_ready"
        detail = "Database probe failed."
    elif checkpoint == "down":
        status_value = "not_ready"
        detail = "Checkpointer probe failed."
    elif checkpoint == "unconfigured":
        status_value = "degraded"
        detail = "Checkpointer DSN unset; query path cannot persist runs."
    elif query_ready and graph != "attached" and paradedb == "down":
        status_value = "degraded"
        detail = (
            "ParadeDB is down; Hybrid degrades to dense plus exact/trigram term. "
            "LightRAG is unconfigured."
        )
    elif query_ready and paradedb == "down":
        status_value = "degraded"
        detail = "ParadeDB is down; Hybrid degrades to dense plus exact/trigram term."
    elif query_ready and graph != "attached":
        status_value = "degraded"
        detail = "LightRAG is unconfigured; Hybrid query path remains available."
    elif query_ready:
        status_value = "ready"
        detail = "Dependencies healthy."
    else:
        status_value = "degraded"
        detail = "Service is up but not query-ready (mock, Valkey, or limiter)."

    return ReadinessResponse(
        status=status_value,
        query_ready=query_ready,
        detail=detail,
        rate_limit_degraded=rate_limit_degraded,
        dependencies=dependencies,
    )


def valkey_probes_ok(payload: ReadinessResponse) -> bool:
    """Return whether both Valkey instances reported ``ok``.

    Args:
        payload: Composed readiness document.

    Returns:
        True when ``valkey_limits`` and ``valkey_cache`` are ``ok``.
    """

    names = {item.name: item.status for item in payload.dependencies}
    return names.get("valkey_limits") == "ok" and names.get("valkey_cache") == "ok"


def readiness_as_dict(payload: ReadinessResponse) -> dict[str, Any]:
    """Convert readiness to a JSON-safe mapping.

    Args:
        payload: Readiness model.

    Returns:
        Dictionary for the authenticated operator HTTP response.
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


_PUBLIC_READY_DETAIL = {
    True: "ok",
    False: "not_query_ready",
}


def public_readiness_as_dict(payload: ReadinessResponse) -> dict[str, Any]:
    """Convert readiness to the unauthenticated probe mapping.

    The public body never names ParadeDB, Valkey, LightRAG, or other
    internals. Mock mode still reports ``query_ready=false``.

    Args:
        payload: Readiness model.

    Returns:
        ``status``, ``query_ready``, and a coarse ``detail`` only.
    """

    return {
        "status": payload.status,
        "query_ready": payload.query_ready,
        "detail": _PUBLIC_READY_DETAIL[payload.query_ready],
    }
