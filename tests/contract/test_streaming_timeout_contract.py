"""Contract tests for local 90-second streaming timeout files."""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CADDY = _REPO / "infra" / "caddy" / "Caddyfile"
_STAGING_CADDY = _REPO / "infra" / "ec2" / "Caddyfile"
_CLOUDFRONT = _REPO / "infra" / "ec2" / "cloudfront_waf.tf"
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


def test_staging_caddy_and_cloudfront_use_90s_timeouts() -> None:
    """Packet 3 asserts staging Caddy and Terraform 90s without live CDN proof."""

    caddy = _STAGING_CADDY.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", caddy)
    assert "flush_interval -1" in normalized
    timeouts = re.findall(r"(?:read_timeout|write_timeout)\s+(\d+)s", caddy)
    assert timeouts, caddy
    assert all(int(value) == _TIMEOUT_SECONDS for value in timeouts), timeouts
    terraform = _CLOUDFRONT.read_text(encoding="utf-8")
    assert re.search(r"origin_read_timeout\s*=\s*90\b", terraform)
    assert re.search(r"origin_keepalive_timeout\s*=\s*90\b", terraform)
    assert not re.search(r"origin_read_timeout\s*=\s*60\b", terraform)


def test_streaming_timeouts_doc_asserts_90s_inputs() -> None:
    """Docs name Caddy and CloudFront 90s values without claiming AWS proof."""

    raw = _DOCS.read_text(encoding="utf-8")
    assert "flush_interval -1" in raw
    assert "Phase 10" in raw
    assert "does **not** claim" in raw
    for name in (
        "Caddy upstream/read timeout",
        "OriginReadTimeout",
        "OriginKeepaliveTimeout",
    ):
        match = re.search(re.escape(name) + r".{0,80}?(\d+)s", raw, flags=re.DOTALL)
        assert match is not None, name
        assert int(match.group(1)) == _TIMEOUT_SECONDS, (name, match.group(1))
