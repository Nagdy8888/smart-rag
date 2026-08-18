"""Contract tests for committed Phase 10 Packet 3 origin, egress, and timeout IaC."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.phase10_constants import (
    CADDY_MAX_CONNS_PER_HOST,
    CADDY_REQUEST_BODY_BYTES,
    DIRECT_ORIGIN_DENIAL_METRIC_NAME,
    EGRESS_DENIAL_LOG_GROUP,
    EGRESS_DENIAL_METRIC_NAME,
    GITHUB_WORKFLOWS_DIR,
    ORIGIN_KEEPALIVE_TIMEOUT_SECONDS,
    ORIGIN_READ_TIMEOUT_SECONDS,
    PACKET3_CRAWL_TEST_FILES,
    PACKET3_RELATIVE,
    PROVIDER_EGRESS_ALLOWLIST_FILE,
    PROVIDER_EGRESS_CADDY_FILE,
    STAGING_CADDY_FILE,
    STAGING_COMPOSE_FILE,
    TELEMETRY_NAMESPACE,
    WAF_RULE_METRIC_NAMES,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_egress import (
    allowlist_host_is_forbidden,
    assert_packet3_policy,
)
from smart_rag_core.release.phase10_packet1 import (
    packet1_checkbox_unchecked,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_packet2 import packet2_checkbox_unchecked
from smart_rag_core.release.phase10_packet3 import (
    packet3_checkbox_unchecked,
    packet3_status_pending,
)
from smart_rag_core.release.phase10_topology import (
    assert_caddy_policy,
    assert_cloudfront_timeouts,
    assert_committed_policy,
    load_terraform_bundle,
    strip_hcl_comments,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_origin_egress_timeout_telemetry_pass_policy() -> None:
    """Reviewed staging files satisfy Packet 3 policy without live CDN or scans."""

    report = assert_packet3_policy(REPO_ROOT)
    assert report.passed is True
    assert report.iac_sha256
    names = {item.check for item in report.findings}
    assert names == {
        "origin",
        "private_ports",
        "metadata",
        "egress",
        "timeouts",
        "telemetry",
    }
    assert all(item.passed for item in report.findings)


def test_staging_caddy_and_terraform_remain_90s() -> None:
    """Packet 3 asserts staging Caddy and CloudFront 90s without lowering to 60."""

    caddy = (REPO_ROOT / STAGING_CADDY_FILE).read_text(encoding="utf-8")
    assert_caddy_policy(caddy)
    assert "flush_interval -1" in caddy
    assert 'respond "direct origin denied" 403' in caddy
    assert f"max_conns_per_host {CADDY_MAX_CONNS_PER_HOST}" in caddy
    assert "max_size 16MB" in caddy
    assert CADDY_REQUEST_BODY_BYTES == 16 * 1024 * 1024
    hcl = strip_hcl_comments(load_terraform_bundle(REPO_ROOT / "infra" / "ec2"))
    assert_cloudfront_timeouts(hcl)
    assert f"origin_read_timeout      = {ORIGIN_READ_TIMEOUT_SECONDS}" in (
        REPO_ROOT / "infra" / "ec2" / "cloudfront_waf.tf"
    ).read_text(encoding="utf-8")
    assert f"origin_keepalive_timeout = {ORIGIN_KEEPALIVE_TIMEOUT_SECONDS}" in (
        REPO_ROOT / "infra" / "ec2" / "cloudfront_waf.tf"
    ).read_text(encoding="utf-8")
    assert "origin_read_timeout      = 60" not in (
        REPO_ROOT / "infra" / "ec2" / "cloudfront_waf.tf"
    ).read_text(encoding="utf-8")


def test_provider_egress_allowlist_and_parser_paradedb_boundaries() -> None:
    """Provider-egress default deny, public allowlist, parser none, ParadeDB private."""

    egress = (REPO_ROOT / PROVIDER_EGRESS_CADDY_FILE).read_text(encoding="utf-8")
    assert 'respond "provider egress denied" 403' in egress
    allowlist = (REPO_ROOT / PROVIDER_EGRESS_ALLOWLIST_FILE).read_text(encoding="utf-8")
    hosts = [
        line.split("#", 1)[0].strip()
        for line in allowlist.splitlines()
        if line.split("#", 1)[0].strip()
    ]
    assert hosts
    assert all(not allowlist_host_is_forbidden(host) for host in hosts)
    compose = (REPO_ROOT / STAGING_COMPOSE_FILE).read_text(encoding="utf-8")
    assert "network_mode: none" in compose
    assert "docker-compose.packet8.yml" not in compose
    assert "9621" not in compose
    assert "9624" not in compose
    telemetry = (REPO_ROOT / "infra" / "ec2" / "cloudwatch.tf").read_text(
        encoding="utf-8"
    )
    assert EGRESS_DENIAL_LOG_GROUP in telemetry
    assert EGRESS_DENIAL_METRIC_NAME in telemetry
    assert DIRECT_ORIGIN_DENIAL_METRIC_NAME in telemetry
    assert TELEMETRY_NAMESPACE in telemetry
    assert "actions_enabled     = false" in telemetry
    waf = (REPO_ROOT / "infra" / "ec2" / "cloudfront_waf.tf").read_text(
        encoding="utf-8"
    )
    for name in WAF_RULE_METRIC_NAMES:
        assert f'metric_name                = "{name}"' in waf


def test_wrapper_and_packet3_stay_pending() -> None:
    """Live Blocked Packet 3 must not complete the wrapper or require Packets 1-2."""

    wrapper = (REPO_ROOT / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (REPO_ROOT / PACKET3_RELATIVE).read_text(encoding="utf-8")
    assert wrapper_status_pending(wrapper) is True
    assert packet3_checkbox_unchecked(wrapper) is True
    assert packet1_checkbox_unchecked(wrapper) is True
    assert packet2_checkbox_unchecked(wrapper) is True
    assert packet3_status_pending(packet) is True
    packet1 = assert_committed_policy(REPO_ROOT)
    assert packet1.passed is True
    pr_fast = (REPO_ROOT / GITHUB_WORKFLOWS_DIR / "pr-fast.yml").read_text(
        encoding="utf-8"
    )
    assert "check_phase10_packet3.py" not in pr_fast
    for relative in PACKET3_CRAWL_TEST_FILES:
        assert (REPO_ROOT / relative).is_file()
