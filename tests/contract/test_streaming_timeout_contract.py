"""Contract tests for local 90-second streaming timeout files."""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CADDY = _REPO / "infra" / "caddy" / "Caddyfile"
_DOCS = _REPO / "docs" / "deployment" / "STREAMING_TIMEOUTS.md"
_TIMEOUT_SECONDS = 90


def test_caddyfile_disables_buffering_and_uses_90s_timeouts() -> None:
    """Local Caddy contract file flushes immediately and times out at 90s."""

    raw = _CADDY.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", raw)
    assert "flush_interval -1" in normalized
    timeouts = re.findall(r"(?:read_timeout|write_timeout)\s+(\d+)s", raw)
    assert timeouts, raw
    assert all(int(value) == _TIMEOUT_SECONDS for value in timeouts), timeouts


def test_streaming_timeouts_doc_asserts_90s_inputs() -> None:
    """Docs name Caddy and CloudFront 90s values without claiming AWS proof."""

    raw = _DOCS.read_text(encoding="utf-8")
    assert "flush_interval -1" in raw
    assert "Phase 10" in raw
    assert "does **not** claim" in raw or "does not claim" in raw.lower()
    for name in (
        "Caddy upstream/read timeout",
        "OriginReadTimeout",
        "OriginKeepaliveTimeout",
    ):
        match = re.search(re.escape(name) + r".{0,80}?(\d+)s", raw, flags=re.DOTALL)
        assert match is not None, name
        assert int(match.group(1)) == _TIMEOUT_SECONDS, (name, match.group(1))
