"""Readiness probes stay honest about ParadeDB without taking query_ready down."""

from __future__ import annotations

from smart_rag_api.services.readiness import build_readiness, readiness_as_dict
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
    )
    names = {item.name: item.status for item in payload.dependencies}
    assert names["paradedb"] == "down"
    assert payload.query_ready is False
    mapping = readiness_as_dict(payload)
    assert mapping["query_ready"] is False
    assert any(item["name"] == "paradedb" for item in mapping["dependencies"])
