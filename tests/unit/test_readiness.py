"""Readiness probes stay honest about ParadeDB without taking query_ready down."""

from __future__ import annotations

from smart_rag_api.services.readiness import (
    build_readiness,
    public_readiness_as_dict,
    readiness_as_dict,
)
from smart_rag_core.settings import BackendSettings


def test_unconfigured_readiness_lists_paradedb() -> None:
    """Import-time readiness includes ParadeDB as unconfigured."""

    payload = build_readiness(
        None,
        valkey_limits=None,
        valkey_cache=None,
        lightrag_attached=False,
        rate_limit_degraded=False,
    )
    names = {item.name: item.status for item in payload.dependencies}
    assert names["paradedb"] == "unconfigured"
    assert names["langgraph_checkpoint"] == "unconfigured"
    assert names["query_runtime"] == "unconfigured"
    assert names["run_event_store"] == "unconfigured"
    assert payload.query_ready is False


def test_paradedb_down_is_visible_and_does_not_clear_query_ready() -> None:
    """Killed ParadeDB is an approved Hybrid degrade, not a fake-ready BM25."""

    settings = BackendSettings()
    payload = build_readiness(
        settings,
        valkey_limits=None,
        valkey_cache=None,
        lightrag_attached=True,
        rate_limit_degraded=False,
        postgres_probe="ok",
        paradedb_probe="down",
        checkpoint_probe="ok",
    )
    names = {item.name: item.status for item in payload.dependencies}
    assert names["paradedb"] == "down"
    assert payload.query_ready is False
    mapping = readiness_as_dict(payload)
    assert mapping["query_ready"] is False
    assert any(item["name"] == "paradedb" for item in mapping["dependencies"])


def test_public_readiness_omits_named_dependencies() -> None:
    """Unauthenticated mapping never names ParadeDB, Valkey, or LightRAG."""

    settings = BackendSettings()
    payload = build_readiness(
        settings,
        valkey_limits=None,
        valkey_cache=None,
        lightrag_attached=False,
        rate_limit_degraded=False,
        postgres_probe="ok",
        paradedb_probe="down",
    )
    public = public_readiness_as_dict(payload)
    assert public["query_ready"] is False
    assert public["status"] in {"unconfigured", "not_ready", "degraded", "ready"}
    assert public["detail"] == "not_query_ready"
    serialized = str(public).casefold()
    assert "paradedb" not in serialized
    assert "valkey" not in serialized
    assert "lightrag" not in serialized
    assert "langgraph" not in serialized
    assert "checkpointer" not in serialized
    assert "query_runtime" not in serialized
    assert "run_event_store" not in serialized
    assert "dependencies" not in public


def test_public_http_ready_omits_named_dependencies() -> None:
    """``GET /health/ready`` is the public probe without topology names."""

    from fastapi.testclient import TestClient
    from smart_rag_api.main import create_app

    from tests.unit.typed_openapi import as_openapi_client, json_object

    with TestClient(create_app()) as raw:
        response = as_openapi_client(raw).get("/health/ready")
    body = json_object(response.json())
    assert response.status_code == 200
    assert body["query_ready"] is False
    assert "dependencies" not in body
    serialized = str(body).casefold()
    assert "paradedb" not in serialized
    assert "valkey" not in serialized
    assert "lightrag" not in serialized
    assert "langgraph" not in serialized
    assert "query_runtime" not in serialized
    assert "run_event_store" not in serialized


def test_live_and_meta_are_async_event_loop_handlers() -> None:
    """Liveness and handshake must not wait on the sync thread pool."""

    import inspect

    from smart_rag_api.routers.ops import api_meta, live

    assert inspect.iscoroutinefunction(live)
    assert inspect.iscoroutinefunction(api_meta)


def test_operator_ready_requires_authentication() -> None:
    """``GET /ops/ready`` is not a public topology leak."""

    from fastapi.testclient import TestClient
    from smart_rag_api.main import create_app

    from tests.unit.typed_openapi import as_openapi_client

    with TestClient(create_app()) as raw:
        response = as_openapi_client(raw).get("/ops/ready")
    assert response.status_code == 401


class _ReadyValkey:
    """Minimal Valkey stand-in that reports a successful ping."""

    def ping(self) -> bool:
        """Return a healthy ping.

        Returns:
            Always True.
        """

        return True


def test_core_healthy_without_lightrag_is_query_ready() -> None:
    """Missing LightRAG degrades graph but keeps Hybrid query-ready."""

    from pydantic import SecretStr

    settings = BackendSettings(
        mock_model_mode=False,
        openai_api_key=SecretStr("sk-unit-not-a-real-key"),
    )
    valkey = _ReadyValkey()
    payload = build_readiness(
        settings,
        valkey_limits=valkey,  # type: ignore[arg-type]
        valkey_cache=valkey,  # type: ignore[arg-type]
        lightrag_attached=False,
        rate_limit_degraded=False,
        postgres_probe="ok",
        paradedb_probe="ok",
        checkpoint_probe="ok",
        query_runtime_warmed=True,
        run_event_store_ready=True,
    )
    names = {item.name: item.status for item in payload.dependencies}
    assert names["lightrag"] == "unconfigured"
    assert names["langgraph_checkpoint"] == "ok"
    assert names["query_runtime"] == "ok"
    assert names["run_event_store"] == "ok"
    assert payload.query_ready is True
    assert payload.status == "degraded"
    assert "lightrag" in payload.detail.casefold()
    public = public_readiness_as_dict(payload)
    assert public["query_ready"] is True
    assert public["detail"] == "ok"
    assert "lightrag" not in str(public).casefold()


def test_checkpoint_down_blocks_query_ready() -> None:
    """A failed checkpointer probe is not query-ready."""

    from pydantic import SecretStr

    settings = BackendSettings(
        mock_model_mode=False,
        openai_api_key=SecretStr("sk-unit-not-a-real-key"),
    )
    valkey = _ReadyValkey()
    payload = build_readiness(
        settings,
        valkey_limits=valkey,  # type: ignore[arg-type]
        valkey_cache=valkey,  # type: ignore[arg-type]
        lightrag_attached=True,
        rate_limit_degraded=False,
        postgres_probe="ok",
        paradedb_probe="ok",
        checkpoint_probe="down",
        query_runtime_warmed=True,
        run_event_store_ready=True,
    )
    assert payload.query_ready is False
    assert payload.status == "not_ready"


def test_valkey_probes_ok_requires_both_instances() -> None:
    """Recovery helper is true only when both Valkey probes are ok."""

    from smart_rag_api.services.readiness import valkey_probes_ok

    settings = BackendSettings()
    payload = build_readiness(
        settings,
        valkey_limits=_ReadyValkey(),  # type: ignore[arg-type]
        valkey_cache=_ReadyValkey(),  # type: ignore[arg-type]
        lightrag_attached=False,
        rate_limit_degraded=True,
        postgres_probe="ok",
        paradedb_probe="ok",
        checkpoint_probe="ok",
    )
    assert valkey_probes_ok(payload) is True
    down = build_readiness(
        settings,
        valkey_limits=None,
        valkey_cache=_ReadyValkey(),  # type: ignore[arg-type]
        lightrag_attached=False,
        rate_limit_degraded=True,
        postgres_probe="ok",
        paradedb_probe="ok",
        checkpoint_probe="ok",
    )
    assert valkey_probes_ok(down) is False


def test_rate_limit_degraded_latch_clears_when_valkey_recovers() -> None:
    """GET /health/ready clears a stale emergency-limiter latch."""

    from fastapi.testclient import TestClient
    from smart_rag_api.main import create_app
    from smart_rag_core.runtime.valkey import MemoryValkeyClient

    from tests.unit.typed_openapi import as_openapi_client, client_app_state

    with TestClient(create_app()) as raw:
        state = client_app_state(raw)
        state.rate_limit_degraded = True
        state.valkey_limits_client = MemoryValkeyClient()
        state.valkey_cache_client = MemoryValkeyClient()
        response = as_openapi_client(raw).get("/health/ready")
        assert response.status_code == 200
        assert state.rate_limit_degraded is False


def test_rate_limit_degraded_latch_stays_when_valkey_is_down() -> None:
    """A live Valkey outage keeps the emergency-limiter latch."""

    from fastapi.testclient import TestClient
    from smart_rag_api.main import create_app
    from smart_rag_core.runtime.valkey import MemoryValkeyClient

    from tests.unit.typed_openapi import as_openapi_client, client_app_state

    with TestClient(create_app()) as raw:
        state = client_app_state(raw)
        state.rate_limit_degraded = True
        state.valkey_limits_client = MemoryValkeyClient(fail_closed=True)
        state.valkey_cache_client = MemoryValkeyClient(fail_closed=True)
        response = as_openapi_client(raw).get("/health/ready")
        assert response.status_code == 200
        assert state.rate_limit_degraded is True


def _query_ready_settings() -> BackendSettings:
    """Build real-model settings for query-ready unit cases.

    Returns:
        Backend settings with a dummy OpenAI key.
    """

    from pydantic import SecretStr

    return BackendSettings(
        mock_model_mode=False,
        openai_api_key=SecretStr("sk-unit-not-a-real-key"),
    )


def test_warmup_failure_clears_query_ready() -> None:
    """Query-runtime warmup is required for query_ready."""

    valkey = _ReadyValkey()
    payload = build_readiness(
        _query_ready_settings(),
        valkey_limits=valkey,  # type: ignore[arg-type]
        valkey_cache=valkey,  # type: ignore[arg-type]
        lightrag_attached=True,
        rate_limit_degraded=False,
        postgres_probe="ok",
        paradedb_probe="ok",
        checkpoint_probe="ok",
        query_runtime_warmed=False,
        run_event_store_ready=True,
    )
    names = {item.name: item.status for item in payload.dependencies}
    assert names["query_runtime"] == "down"
    assert payload.query_ready is False
    assert payload.status == "not_ready"
    assert "warmup" in payload.detail.casefold()


def test_event_store_failure_clears_query_ready() -> None:
    """Run-event store failure clears query_ready."""

    valkey = _ReadyValkey()
    payload = build_readiness(
        _query_ready_settings(),
        valkey_limits=valkey,  # type: ignore[arg-type]
        valkey_cache=valkey,  # type: ignore[arg-type]
        lightrag_attached=True,
        rate_limit_degraded=False,
        postgres_probe="ok",
        paradedb_probe="ok",
        checkpoint_probe="ok",
        query_runtime_warmed=True,
        run_event_store_ready=False,
    )
    names = {item.name: item.status for item in payload.dependencies}
    assert names["run_event_store"] == "down"
    assert payload.query_ready is False
    assert payload.status == "not_ready"


def test_warmup_and_store_recovery_restores_query_ready() -> None:
    """Recovery of warmup and event-store flags restores query_ready."""

    valkey = _ReadyValkey()
    failed = build_readiness(
        _query_ready_settings(),
        valkey_limits=valkey,  # type: ignore[arg-type]
        valkey_cache=valkey,  # type: ignore[arg-type]
        lightrag_attached=True,
        rate_limit_degraded=False,
        postgres_probe="ok",
        paradedb_probe="ok",
        checkpoint_probe="ok",
        query_runtime_warmed=False,
        run_event_store_ready=False,
    )
    recovered = build_readiness(
        _query_ready_settings(),
        valkey_limits=valkey,  # type: ignore[arg-type]
        valkey_cache=valkey,  # type: ignore[arg-type]
        lightrag_attached=True,
        rate_limit_degraded=False,
        postgres_probe="ok",
        paradedb_probe="ok",
        checkpoint_probe="ok",
        query_runtime_warmed=True,
        run_event_store_ready=True,
    )
    assert failed.query_ready is False
    assert recovered.query_ready is True
    assert recovered.status == "ready"


def test_public_ready_omits_event_store_exception_text() -> None:
    """``GET /health/ready`` never echoes DSN or exception text."""

    from fastapi.testclient import TestClient
    from smart_rag_api.main import create_app

    from tests.unit.typed_openapi import (
        as_openapi_client,
        client_app_state,
        json_object,
    )

    class _BoomStore:
        """Store whose probe leaks a secret in the exception."""

        def probe(self) -> None:
            """Raise a secret-bearing error.

            Raises:
                RuntimeError: Always, including a fake DSN.
            """

            raise RuntimeError(
                "password=super-secret postgresql://unit:secret@host/db boom"
            )

    with TestClient(create_app()) as raw:
        state = client_app_state(raw)
        state.query_runtime_warmed = True
        state.run_event_store = _BoomStore()
        response = as_openapi_client(raw).get("/health/ready")
    body = json_object(response.json())
    assert response.status_code == 200
    assert body["query_ready"] is False
    assert body["detail"] == "not_query_ready"
    serialized = str(body).casefold()
    assert "postgresql" not in serialized
    assert "password" not in serialized
    assert "super-secret" not in serialized
    assert "boom" not in serialized
    assert "exception" not in serialized
