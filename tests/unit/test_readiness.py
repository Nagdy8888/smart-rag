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
    )
    names = {item.name: item.status for item in payload.dependencies}
    assert names["lightrag"] == "unconfigured"
    assert names["langgraph_checkpoint"] == "ok"
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
    )
    assert payload.query_ready is False
    assert payload.status == "not_ready"
