"""Tool catalog HTTP overlay and permission-seed contracts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from smart_rag_api.services.tools_http import ToolHttpService
from smart_rag_core.security.identity import CallerContext, UserRole

_REPO = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _REPO
    / "supabase"
    / "migrations"
    / "20260827140000_tool_admin_catalog_overlay_v1.sql"
)
_OWNER = CallerContext(
    user_id="00000000-0000-4000-8000-000000000001",
    role=UserRole.OWNER,
    authorization_version=1,
)
_MEMBER = CallerContext(
    user_id="00000000-0000-4000-8000-000000000002",
    role=UserRole.MEMBER,
    authorization_version=1,
)


def _fixed_seeds(
    seeds: dict[str, bool],
) -> Callable[[ToolHttpService, CallerContext], dict[str, bool]]:
    """Return a ``_catalog_seeds`` stand-in with a known overlay map.

    Args:
        seeds: Active flags keyed by tool_key.

    Returns:
        Replacement method.
    """

    def _load(self: ToolHttpService, caller: CallerContext) -> dict[str, bool]:
        """Return the fixed overlay map.

        Args:
            self: Unused service instance.
            caller: Unused caller.

        Returns:
            Seeded overlay flags keyed by tool_key.
        """

        del self, caller
        return seeds

    return _load


def test_search_overlays_disabled_seed_for_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner/admin still see a seed-disabled tool with ``active=false``."""

    monkeypatch.setattr(
        ToolHttpService, "_catalog_seeds", _fixed_seeds({"export_csv": False})
    )
    service = ToolHttpService("postgresql://unused")
    cards = service.search(_OWNER)
    csv_card = next(item for item in cards if item.tool_key == "export_csv")
    assert csv_card.active is False


def test_search_hides_disabled_seed_from_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Members do not learn the name of a seed-disabled tool."""

    monkeypatch.setattr(
        ToolHttpService, "_catalog_seeds", _fixed_seeds({"export_csv": False})
    )
    service = ToolHttpService("postgresql://unused")
    keys = {item.tool_key for item in service.search(_MEMBER)}
    assert "export_csv" not in keys


def test_search_query_still_filters_overlaid_cards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Substring ``q`` applies after seed overlay."""

    monkeypatch.setattr(ToolHttpService, "_catalog_seeds", _fixed_seeds({}))
    service = ToolHttpService("")
    keys = {item.tool_key for item in service.search(_OWNER, query="csv")}
    assert "export_csv" in keys
    assert "admin_user_invite" not in keys


def test_caller_usage_scope_is_me() -> None:
    """Caller totals use ``me`` so the UI can distinguish company totals."""

    source = (
        _REPO
        / "apps"
        / "backend"
        / "src"
        / "smart_rag_api"
        / "services"
        / "feedback_usage.py"
    ).read_text(encoding="utf-8")
    assert 'scope="company" if company else "me"' in source


def test_permission_rpc_upserts_and_lists_seeds() -> None:
    """Migration upserts role permissions and lists catalog seed flags."""

    source = _MIGRATION.read_text(encoding="utf-8")
    assert (
        "ON CONFLICT (tool_id, role) WHERE user_id IS NULL AND role IS NOT NULL"
        in source
    )
    assert "app.list_tool_catalog_seeds" in source
    assert "GRANT EXECUTE ON FUNCTION app.list_tool_catalog_seeds" in source
