"""Phase 7 packet 1: mapping inventory matches OpenAPI and SSE catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from smart_rag_core.sse.catalog import ALLOWED_SSE_EVENT_TYPES, TERMINAL_SSE_EVENT_TYPES

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "docs" / "frontend" / "api-ui-inventory.json"
MAPPING_PATH = ROOT / "docs" / "frontend" / "API_UI_MAPPING.md"
OPENAPI_PATH = ROOT / "docs" / "api" / "openapi.foundation.json"


def _load_json(path: Path) -> dict[str, Any]:
    """Load one object JSON document.

    Args:
        path: Repository file.

    Returns:
        Parsed object.

    Raises:
        AssertionError: If the file is missing or not an object.
    """

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def test_inventory_fastapi_paths_match_openapi_snapshot() -> None:
    """Every OpenAPI path is inventoried; invented FastAPI paths are absent."""

    inventory = _load_json(INVENTORY_PATH)
    openapi = _load_json(OPENAPI_PATH)
    snapshot_paths = set(cast(dict[str, Any], openapi["paths"]).keys())
    listed = set(cast(list[str], inventory["fastapi_paths"]))
    assert listed == snapshot_paths
    invented = set(cast(list[str], inventory["invented_paths_rejected"]))
    assert invented.isdisjoint(snapshot_paths)


def test_inventory_sse_types_match_allow_list() -> None:
    """SSE inventory matches the extra=forbid catalog, including terminals."""

    inventory = _load_json(INVENTORY_PATH)
    listed = set(cast(list[str], inventory["sse_event_types"]))
    terminals = set(cast(list[str], inventory["terminal_sse_event_types"]))
    assert listed == set(ALLOWED_SSE_EVENT_TYPES)
    assert terminals == set(TERMINAL_SSE_EVENT_TYPES)


def test_mapping_markdown_covers_paths_events_and_gaps() -> None:
    """Human mapping cites every path, SSE type, gap id, and Auth split."""

    inventory = _load_json(INVENTORY_PATH)
    mapping = MAPPING_PATH.read_text(encoding="utf-8")
    for path in cast(list[str], inventory["fastapi_paths"]):
        assert path in mapping, path
    for event in cast(list[str], inventory["sse_event_types"]):
        assert f"`{event}`" in mapping, event
    for gap_id in cast(list[str], inventory["gap_ids"]):
        assert gap_id in mapping, gap_id
    assert inventory["auth_direct_not_throttled_by_fastapi"] is True
    assert "FastAPI throttle? |" in mapping
    assert "**No**" in mapping
    assert "signInWithPassword" in mapping
    for invented in cast(list[str], inventory["invented_paths_rejected"]):
        assert invented in mapping


def test_mapping_rejects_client_authority_and_bm25_evidence() -> None:
    """Negative contract: mapping forbids client auth and BM25-as-evidence."""

    mapping = MAPPING_PATH.read_text(encoding="utf-8")
    assert "Client-only authorization" in mapping
    assert "BM25 snippets or LightRAG prose as citations" in mapping
    assert "FastAPI throttles browser-direct Auth" in mapping
    assert "Graph-only answering" in mapping
    assert "`dangerouslySetInnerHTML`" in mapping
