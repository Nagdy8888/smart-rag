"""Contract tests for committed Phase 10 Packet 4 rotation and degrade evidence."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.phase10_constants import (
    CDN_SSE_MIN_DURATION_SECONDS,
    GITHUB_WORKFLOWS_DIR,
    ORIGIN_KEEPALIVE_TIMEOUT_SECONDS,
    ORIGIN_READ_TIMEOUT_SECONDS,
    ORIGIN_ROTATION_OVERLAP_MAX_MINUTES,
    ORIGIN_ROTATION_RUNBOOK,
    PACKET4_JWKS_TEST_FILES,
    PACKET4_PARADEDB_TEST_FILES,
    PACKET4_RELATIVE,
    PACKET4_VALKEY_TEST_FILES,
    PHASE09_PACKET5_FAULT,
    PHASE09_PACKET6_REBUILD,
    STAGING_CADDY_FILE,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_packet1 import wrapper_status_pending
from smart_rag_core.release.phase10_packet2 import packet2_checkbox_unchecked
from smart_rag_core.release.phase10_packet3 import packet3_checkbox_unchecked
from smart_rag_core.release.phase10_packet4 import (
    assert_origin_rotation_policy,
    evaluate_packet4,
    packet4_checkbox_unchecked,
    packet4_status_pending,
)
from smart_rag_core.release.phase10_topology import (
    load_terraform_bundle,
    strip_hcl_comments,
)
from smart_rag_core.security.jwks import FORBIDDEN_ALGORITHMS

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_origin_rotation_policy_passes() -> None:
    """Caddy dual values, CloudFront header, overlap cap, and runbook pass."""

    report = assert_origin_rotation_policy(REPO_ROOT)
    assert report.passed is True
    assert report.iac_sha256
    names = {item.check for item in report.findings}
    assert names == {
        "caddy_dual",
        "cloudfront_header",
        "compose_previous",
        "overlap",
        "runbook",
        "hs256",
    }
    assert all(item.passed for item in report.findings)
    caddy = (REPO_ROOT / STAGING_CADDY_FILE).read_text(encoding="utf-8")
    assert "ORIGIN_HEADER_VALUE_CURRENT" in caddy
    assert "ORIGIN_HEADER_VALUE_PREVIOUS" in caddy
    hcl = strip_hcl_comments(load_terraform_bundle(REPO_ROOT / "infra" / "ec2"))
    assert "custom_header" in hcl
    assert "origin_header_value_previous" in hcl
    runbook = (REPO_ROOT / ORIGIN_ROTATION_RUNBOOK).read_text(encoding="utf-8")
    assert "Abort or rollback keeps at least one valid value" in runbook
    assert f"{ORIGIN_ROTATION_OVERLAP_MAX_MINUTES}-minute overlap" in runbook
    assert "HS256" in FORBIDDEN_ALGORITHMS


def test_phase09_rebuild_is_not_canonical_authority() -> None:
    """Packet 4 reuses Phase 9 rebuild only as derived projection evidence."""

    rebuild = (REPO_ROOT / PHASE09_PACKET6_REBUILD).read_text(encoding="utf-8")
    assert '"paradedb_used_as_canonical": false' in rebuild
    fault = (REPO_ROOT / PHASE09_PACKET5_FAULT).read_text(encoding="utf-8")
    assert '"fallback_reason": "bm25_unavailable"' in fault
    assert '"denied": true' in fault


def test_wrapper_stays_pending_and_packets_1_3_unchecked_are_not_failures() -> None:
    """Live Blocked Packet 4 must not complete the wrapper."""

    wrapper = (REPO_ROOT / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (REPO_ROOT / PACKET4_RELATIVE).read_text(encoding="utf-8")
    assert wrapper_status_pending(wrapper) is True
    assert packet4_checkbox_unchecked(wrapper) is True
    assert packet2_checkbox_unchecked(wrapper) is True
    assert packet3_checkbox_unchecked(wrapper) is True
    assert packet4_status_pending(packet) is True
    policy, _live, rows, degrade = evaluate_packet4(
        REPO_ROOT,
        jwks_subset_ok=True,
        paradedb_subset_ok=True,
        valkey_subset_ok=True,
    )
    assert policy.passed is True
    by_check = {row.check: row.classification for row in rows}
    assert by_check["P10-04-A"] == "Passed"
    assert by_check["P10-04-B"] == "Blocked"
    assert by_check["P10-04-C"] == "Blocked"
    assert by_check["P10-04-D"] == "Passed"
    assert by_check["P10-04-E"] == "Passed"
    assert degrade.paradedb_used_as_canonical is False
    pr_fast = (REPO_ROOT / GITHUB_WORKFLOWS_DIR / "pr-fast.yml").read_text(
        encoding="utf-8"
    )
    assert "check_phase10_packet4.py" not in pr_fast
    assert ORIGIN_READ_TIMEOUT_SECONDS == 90
    assert ORIGIN_KEEPALIVE_TIMEOUT_SECONDS == 90
    assert CDN_SSE_MIN_DURATION_SECONDS == 50
    for relative in (
        *PACKET4_JWKS_TEST_FILES,
        *(item.split("::", 1)[0] for item in PACKET4_PARADEDB_TEST_FILES),
        *(item.split("::", 1)[0] for item in PACKET4_VALKEY_TEST_FILES),
    ):
        assert (REPO_ROOT / relative).is_file()
