"""Unit tests for Phase 10 Packet 3 origin, egress, timeout, and telemetry negatives."""

from __future__ import annotations

import pytest
from smart_rag_core.ingestion.crawl.exceptions import CrawlPolicyError
from smart_rag_core.ingestion.crawl.policy import normalize_url
from smart_rag_core.release.phase10_constants import (
    ALL_VIEWER_EXCEPT_HOST_POLICY_ID,
    CACHING_DISABLED_POLICY_ID,
    CLOUDFRONT_PREFIX_LIST_NAME,
    PARADEDB_IMAGE,
    PHASE09_IMAGE_IDS,
    VALKEY_IMAGE,
)
from smart_rag_core.release.phase10_egress import (
    Phase10EgressError,
    allowlist_host_is_forbidden,
    assert_caddy_direct_origin_deny,
    assert_caddy_waf_controls,
    assert_origin_security_group,
    assert_private_ports_policy,
    assert_provider_egress_policy,
    assert_timeout_policy,
    parse_caddy_size,
)
from smart_rag_core.release.phase10_packet1 import (
    LiveProviderProbe,
    packet1_checkbox_unchecked,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_packet2 import packet2_checkbox_unchecked
from smart_rag_core.release.phase10_packet3 import (
    classify_p1003_a,
    classify_p1003_b,
    classify_p1003_c,
    classify_p1003_d,
    classify_p1003_e,
    packet3_checkbox_unchecked,
    request_matrix_rows,
)

_GOOD_CADDY = """
{
	servers {
		max_header_size 16KB
		timeouts {
			read_timeout 90s
			read_header_timeout 15s
			write_timeout 90s
			idle_timeout 90s
		}
	}
}
:443 {
	request_body {
		max_size 16MB
	}
	flush_interval -1
	{$ORIGIN_HEADER_VALUE_CURRENT}
	{$ORIGIN_HEADER_VALUE_PREVIOUS}
	{$ACTIVE_API_UPSTREAM}
	max_conns_per_host 32
	respond "direct origin denied" 403
}
"""

_GOOD_TIMEOUT_HCL = f"""
origin_read_timeout = 90
origin_keepalive_timeout = 90
cache_policy_id = "{CACHING_DISABLED_POLICY_ID}"
origin_request_policy_id = "{ALL_VIEWER_EXCEPT_HOST_POLICY_ID}"
prefix_list_name = "{CLOUDFRONT_PREFIX_LIST_NAME}"
resource "aws_wafv2_web_acl" "staging" {{
  scope = "CLOUDFRONT"
  statement {{
    managed_rule_group_statement {{
      name = "AWSManagedRulesCommonRuleSet"
    }}
  }}
  statement {{
    managed_rule_group_statement {{
      name = "AWSManagedRulesKnownBadInputsRuleSet"
    }}
  }}
  statement {{
    managed_rule_group_statement {{
      name = "AWSManagedRulesAmazonIpReputationList"
    }}
  }}
  rate_based_statement {{
    limit = 2000
  }}
}}
"""


def _live_blocked() -> LiveProviderProbe:
    """Return a Blocked live-apply probe for classification tests.

    Returns:
        Frozen probe matching the current workstation constraint.
    """

    return LiveProviderProbe(
        terraform_installed=False,
        tofu_installed=False,
        aws_cli_installed=True,
        sts_ok=False,
        sts_detail="session expired",
        apply_state="Blocked",
        apply_reason="AWS session expired",
    )


def _private_compose() -> str:
    """Return a staging Compose snippet that satisfies private-port policy.

    Returns:
        Compose YAML fragment.
    """

    return f"""
networks:
  private:
    driver: bridge
    internal: true
services:
  api-blue:
    image: smart-rag-api@{PHASE09_IMAGE_IDS["api"]}
    mem_limit: 1g
  api-green:
    image: smart-rag-api@{PHASE09_IMAGE_IDS["api"]}
    mem_limit: 1g
  worker:
    image: smart-rag-worker@{PHASE09_IMAGE_IDS["worker"]}
    mem_limit: 1g
    networks:
      - private
  caddy:
    image: caddy:2.8.4-alpine
    ports:
      - "443:443"
  paradedb:
    image: {PARADEDB_IMAGE}
    mem_limit: 2g
    networks:
      - private
  valkey-limits:
    image: {VALKEY_IMAGE}
    command: ["valkey-server", "--requirepass", "${{VALKEY_LIMITS_PASSWORD}}", "--maxmemory-policy", "noeviction"]
    mem_limit: 128m
  valkey-cache:
    image: {VALKEY_IMAGE}
    command: ["valkey-server", "--requirepass", "${{VALKEY_CACHE_PASSWORD}}", "--maxmemory-policy", "allkeys-lru"]
    mem_limit: 320m
  crawl-proxy:
    image: smart-rag-crawl-proxy@{PHASE09_IMAGE_IDS["crawl-proxy"]}
    mem_limit: 128m
  provider-egress-proxy:
    image: caddy:2.8.4-alpine
    mem_limit: 128m
  clamav:
    image: clamav/clamav:stable
    mem_limit: 2g
  parser-sandbox:
    image: smart-rag-parser-sandbox@{PHASE09_IMAGE_IDS["parser-sandbox"]}
    network_mode: none
    mem_limit: 1g
"""


def test_origin_cidr_open_https_is_rejected() -> None:
    """Origin :443 ingress from 0.0.0.0/0 fails closed."""

    hcl = f"""
    {CLOUDFRONT_PREFIX_LIST_NAME}
    resource "aws_security_group" "origin" {{
      ingress {{
        from_port   = 443
        to_port     = 443
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
      }}
    }}
    """
    with pytest.raises(Phase10EgressError, match=r"0\.0\.0\.0/0"):
        assert_origin_security_group(hcl)


def test_direct_ip_or_header_secret_is_rejected() -> None:
    """Literal origin IPs and header secrets cannot be committed in Caddy."""

    poisoned = _GOOD_CADDY + "\nheader Host 203.0.113.10\n"
    with pytest.raises(Phase10EgressError, match="origin IP or header secrets"):
        assert_caddy_direct_origin_deny(poisoned)
    private = _GOOD_CADDY + "\nreverse_proxy 10.0.0.5\n"
    with pytest.raises(Phase10EgressError, match="private origin"):
        assert_caddy_direct_origin_deny(private)


def test_private_port_or_lightrag_publish_is_rejected() -> None:
    """Publishing ParadeDB or LightRAG ports fails Packet 3."""

    compose = _private_compose().replace(
        "  paradedb:\n    image:",
        '  paradedb:\n    ports:\n      - "5432:5432"\n    image:',
    )
    with pytest.raises(Phase10EgressError, match="publishes host ports"):
        assert_private_ports_policy(compose)
    lightrag = _private_compose() + "\n  lightrag:\n    ports:\n      - '9621:9621'\n"
    with pytest.raises(Phase10EgressError):
        assert_private_ports_policy(lightrag)


def test_allowlist_rfc1918_is_rejected() -> None:
    """Provider-egress allowlists cannot include RFC1918 or link-local targets."""

    assert allowlist_host_is_forbidden("10.0.0.1") is True
    assert allowlist_host_is_forbidden("192.168.1.8") is True
    assert allowlist_host_is_forbidden("169.254.169.254") is True
    assert allowlist_host_is_forbidden("api.openai.com") is False
    compose = _private_compose()
    with pytest.raises(Phase10EgressError, match="private/link-local"):
        assert_provider_egress_policy(
            compose,
            egress_caddy='handle {\n\trespond "provider egress denied" 403\n}\n',
            allowlist_text="10.40.0.10\n",
        )


def test_crawl_private_redirect_is_rejected() -> None:
    """Packet 3 reuses crawl policy instead of duplicating SSRF regexes."""

    with pytest.raises(CrawlPolicyError):
        normalize_url("http://127.0.0.1/private")
    with pytest.raises(CrawlPolicyError):
        normalize_url("http://169.254.169.254/")
    with pytest.raises(CrawlPolicyError):
        normalize_url("http://192.168.0.1/")


def test_origin_read_timeout_60_is_rejected() -> None:
    """CloudFront origin_read_timeout 60 cannot pass Packet 3."""

    hcl = _GOOD_TIMEOUT_HCL.replace(
        "origin_read_timeout = 90", "origin_read_timeout = 60"
    )
    with pytest.raises(Phase10EgressError, match="origin_read_timeout"):
        assert_timeout_policy(hcl, _GOOD_CADDY)


def test_sse_buffering_or_header_limit_excess_is_rejected() -> None:
    """Buffered SSE or oversized Caddy/WAF limits fail closed."""

    buffered = _GOOD_CADDY.replace("flush_interval -1", "flush_interval 1s")
    with pytest.raises(Phase10EgressError, match=r"buffering|flush_interval"):
        assert_timeout_policy(_GOOD_TIMEOUT_HCL, buffered)
    excess_header = _GOOD_CADDY.replace("max_header_size 16KB", "max_header_size 5MB")
    with pytest.raises(Phase10EgressError, match="max_header_size"):
        assert_caddy_waf_controls(excess_header, _GOOD_TIMEOUT_HCL)
    excess_rate = _GOOD_TIMEOUT_HCL.replace("limit = 2000", "limit = 2000000")
    with pytest.raises(Phase10EgressError, match="rate limit exceeds"):
        assert_caddy_waf_controls(_GOOD_CADDY, excess_rate)
    assert parse_caddy_size("16KB") == 16 * 1024
    assert parse_caddy_size("16MB") == 16 * 1024 * 1024


def test_fake_cdn_http_status_is_not_passed() -> None:
    """Invented 200/403 rows cannot classify P10-03-A as Passed."""

    assert (
        classify_p1003_a(
            origin_policy_passed=True,
            live_cdn_state="Blocked",
            live_cdn_passed=False,
        )
        == "Blocked"
    )
    rows = request_matrix_rows("Blocked")
    assert rows
    assert all(row["http_status"] is None for row in rows)
    assert all(row["classification"] == "Blocked" for row in rows)
    assert not any(row.get("http_status") in {200, 403} for row in rows)
    blocked = _live_blocked()
    assert blocked.apply_state == "Blocked"


def test_classifications_fail_closed_and_keep_live_blocked() -> None:
    """Policy misses fail; missing CDN/scan/alert stay Blocked, not Passed."""

    assert (
        classify_p1003_a(
            origin_policy_passed=False,
            live_cdn_state="Blocked",
            live_cdn_passed=False,
        )
        == "Failed"
    )
    assert (
        classify_p1003_b(
            ports_policy_passed=True,
            live_scan_state="Blocked",
            live_scan_passed=False,
            live_scan_present=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1003_b(
            ports_policy_passed=True,
            live_scan_state="Blocked",
            live_scan_passed=False,
            live_scan_present=True,
        )
        == "Failed"
    )
    assert classify_p1003_c(egress_policy_passed=True, crawl_subset_ok=True) == "Passed"
    assert (
        classify_p1003_c(egress_policy_passed=True, crawl_subset_ok=False) == "Failed"
    )
    assert classify_p1003_d(timeout_policy_passed=True) == "Passed"
    assert classify_p1003_d(timeout_policy_passed=False) == "Failed"
    assert (
        classify_p1003_e(
            telemetry_policy_passed=True,
            live_alert_state="Blocked",
            live_alert_passed=False,
        )
        == "Blocked"
    )
    wrapper = """---
status: pending
---
1. [ ] [Provision isolated managed Supabase
2. [ ] [Implement GitHub OIDC, protected immutable expand/contract
3. [ ] [Prove direct-origin rejection, provider/crawl/parser egress
"""
    assert wrapper_status_pending(wrapper) is True
    assert packet1_checkbox_unchecked(wrapper) is True
    assert packet2_checkbox_unchecked(wrapper) is True
    assert packet3_checkbox_unchecked(wrapper) is True
