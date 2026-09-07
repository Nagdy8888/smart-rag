"""Phase 8 packet 6: journey matrix names required limitation codes and GAP ids."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "docs" / "frontend" / "PHASE8_JOURNEY_MATRIX.md"

REQUIRED_LIMITATION_CODES = (
    "temporal_graph_limitation",
    "bm25_unavailable",
    "graph_outage",
    "media_limitation",
    "negation_unresolved",
    "coverage_gap",
    "insufficient_evidence",
    "graph_acl_blindness",
    "graph_pending",
    "graph_partial_readiness",
)

REQUIRED_GAP_IDS = (
    "GAP-07-01",
    "GAP-07-07",
    "GAP-07-08",
    "GAP-07-09",
    "GAP-07-12",
    "GAP-07-14",
)

REQUIRED_LAYERS = (
    "vitest-component",
    "vitest-unit",
    "playwright-unauth",
    "playwright-live",
    "python-contract-live",
)

REQUIRED_JOURNEY_MARKERS = (
    "handshake",
    "426",
    "Idempotency-Key",
    "Reconnect",
    "Cancel",
    "source_ranges",
    "ACME",
    "CSP",
    "session_revoked",
    "rate_limited",
    "budget_exhausted",
    "phase08-journeys.spec.ts",
    "unverified-live",
    "proven",
)


def test_journey_matrix_locks_limitation_codes_gaps_and_layers() -> None:
    """Matrix cites every required limitation code, GAP id, and test layer."""

    text = MATRIX_PATH.read_text(encoding="utf-8")
    for code in REQUIRED_LIMITATION_CODES:
        assert code in text, code
    for gap_id in REQUIRED_GAP_IDS:
        assert gap_id in text, gap_id
    for layer in REQUIRED_LAYERS:
        assert layer in text, layer
    for marker in REQUIRED_JOURNEY_MARKERS:
        assert marker in text, marker
    assert "template, not a layout" in text.lower()
    assert "does not send `X-Test-`" in text
