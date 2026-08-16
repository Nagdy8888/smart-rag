"""Phase 7 packet 3: required visible states are specified, not mocked."""

from __future__ import annotations

from pathlib import Path

STATES_PATH = Path(__file__).resolve().parents[2] / "docs" / "frontend" / "STITCH_STATES.md"
BRIEF_PATH = Path(__file__).resolve().parents[2] / "docs" / "frontend" / "STITCH_BRIEF.md"


def test_state_matrix_covers_required_families() -> None:
    """Every packet-3 state family appears with a real signal or GAP."""

    text = STATES_PATH.read_text(encoding="utf-8")
    for token in (
        "First load",
        "Loading",
        "Empty",
        "partial",
        "MFA required",
        "quarantine",
        "Quota",
        "426",
        "402",
        "bm25_unavailable",
        "graph_outage",
        "graph_acl_blindness",
        "graph_pending",
        "temporal_graph_limitation",
        "media_limitation",
        "negation_unresolved",
        "coverage_gap",
        "Reconnect",
        "Cancelled",
        "budget_exhausted",
        "rate_limit_degraded",
        "GAP-07-07",
        "GAP-07-09",
        "GAP-07-11",
        "GAP-07-12",
        "GAP-07-13",
        "GAP-07-14",
    ):
        assert token in text, token


def test_states_forbid_graph_only_success_and_leaks() -> None:
    """Negative: no graph-only success, no unauthorized titles, no raw errors."""

    text = STATES_PATH.read_text(encoding="utf-8")
    assert "Graph-only is never a" in text
    assert "Never** show their titles" in text or "**Never** show their titles" in text
    assert "Raw exception / HTML" in text
    assert "Hidden retry spend" in text
    assert "FastAPI does **not** produce these banners for sign-in" in text


def test_brief_incorporates_state_matrix() -> None:
    """The brief links the state matrix as part of the specification."""

    brief = BRIEF_PATH.read_text(encoding="utf-8")
    assert "STITCH_STATES.md" in brief
