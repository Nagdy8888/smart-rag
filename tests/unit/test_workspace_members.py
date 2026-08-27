"""Workspace member listing RPC contract."""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _REPO
    / "supabase"
    / "migrations"
    / "20260827160000_workspace_member_directory_v1.sql"
)


def test_workspace_member_rpc_is_bounded_and_token_free() -> None:
    """Listing RPCs are owner/admin, bounded, and omit invitation secrets."""

    source = _MIGRATION.read_text(encoding="utf-8")
    assert "app.list_workspace_members" in source
    assert "app.list_pending_team_invitations" in source
    assert "GRANT EXECUTE ON FUNCTION app.list_workspace_members" in source
    assert "GRANT EXECUTE ON FUNCTION app.list_pending_team_invitations" in source
    assert "TO app_api" in source
    query_blocks = re.findall(r"RETURN QUERY\s+(.*?)\s+LIMIT 200;", source, re.DOTALL)
    assert len(query_blocks) == 2
    for block in query_blocks:
        assert "token_hash" not in block
    assert "LIMIT 200" in source
    assert "caller_role NOT IN ('owner', 'admin')" in source
    assert "LEFT JOIN auth.users" in source
    assert "REVOKE ALL ON FUNCTION app.list_workspace_members" in source
