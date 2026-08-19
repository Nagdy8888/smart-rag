"""Unit tests for Phase 10 Packet 1 negatives and honest classification."""

from __future__ import annotations

from pathlib import Path

import pytest
from smart_rag_core.release.phase10_constants import (
    CACHING_DISABLED_POLICY_ID,
    CLOUDFRONT_PREFIX_LIST_NAME,
    PARADEDB_IMAGE,
    PHASE09_IMAGE_IDS,
    VALKEY_IMAGE,
)
from smart_rag_core.release.phase10_packet1 import (
    LiveProviderProbe,
    classify_p1001_a,
    classify_p1001_b,
    classify_p1001_c,
    classify_p1001_d,
    classify_p1001_e,
    live_network_scan_passed,
    live_runtime_assertions_passed,
    live_vercel_secret_found,
)
from smart_rag_core.release.phase10_topology import (
    Phase10TopologyError,
    assert_caddy_http443_policy,
    assert_caddy_policy,
    assert_cloudfront_timeouts,
    assert_compose_policy,
    assert_encrypted_ebs,
    assert_imdsv2,
    assert_inventory,
    assert_no_ssh,
    assert_no_vercel_secrets,
    assert_synthetic_corpus,
    assert_t3micro_overlay,
    strip_hcl_comments,
)

_API = PHASE09_IMAGE_IDS["api"].removeprefix("sha256:")
_WORKER = PHASE09_IMAGE_IDS["worker"].removeprefix("sha256:")
_CRAWL = PHASE09_IMAGE_IDS["crawl-proxy"].removeprefix("sha256:")
_PARSER = PHASE09_IMAGE_IDS["parser-sandbox"].removeprefix("sha256:")
_PARADE = PARADEDB_IMAGE.split("@", 1)[1]
_VALKEY = VALKEY_IMAGE.split("@", 1)[1]


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


def _private_compose(*, paradedb_image: str = PARADEDB_IMAGE) -> str:
    """Return a staging Compose snippet that satisfies private-port policy.

    Args:
        paradedb_image: ParadeDB image line.

    Returns:
        Compose YAML fragment.
    """

    return f"""
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
  caddy:
    image: caddy:2.8.4-alpine
    ports:
      - "443:443"
  paradedb:
    image: {paradedb_image}
    mem_limit: 2g
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


def test_ssh_ingress_is_rejected() -> None:
    """Port 22 ingress and key pairs fail closed."""

    with pytest.raises(Phase10TopologyError, match="aws_key_pair"):
        assert_no_ssh('resource "aws_key_pair" "operator" {}')
    with pytest.raises(Phase10TopologyError, match="SSH ingress"):
        assert_no_ssh(
            """
            ingress {
              from_port = 22
              to_port   = 22
              protocol  = "tcp"
            }
            """
        )


def test_imdsv1_optional_or_missing_tokens_are_rejected() -> None:
    """Missing or optional IMDS tokens are IMDSv1 and fail closed."""

    with pytest.raises(Phase10TopologyError, match="http_tokens is missing"):
        assert_imdsv2("http_put_response_hop_limit = 1")
    with pytest.raises(Phase10TopologyError, match="IMDSv1"):
        assert_imdsv2(
            """
            http_tokens = "optional"
            http_put_response_hop_limit = 1
            """
        )
    with pytest.raises(Phase10TopologyError, match="http_put_response_hop_limit"):
        assert_imdsv2(
            """
            http_tokens = "required"
            http_put_response_hop_limit = 2
            """
        )


def test_unencrypted_ebs_is_rejected() -> None:
    """Explicit unencrypted EBS is a Packet 1 blocker."""

    with pytest.raises(Phase10TopologyError, match="unencrypted"):
        assert_encrypted_ebs(
            """
            root_block_device {
              encrypted = false
            }
            """
        )


def test_origin_timeout_not_90_is_rejected() -> None:
    """CloudFront origin timeouts must be 90, not the provider-doc 60 bound."""

    hcl = strip_hcl_comments(
        """
        origin_read_timeout      = 60
        origin_keepalive_timeout = 90
        """
    )
    with pytest.raises(Phase10TopologyError, match="origin_read_timeout"):
        assert_cloudfront_timeouts(hcl)
    hcl_keep = strip_hcl_comments(
        """
        origin_read_timeout      = 90
        origin_keepalive_timeout = 5
        """
    )
    with pytest.raises(Phase10TopologyError, match="origin_keepalive_timeout"):
        assert_cloudfront_timeouts(hcl_keep)


def test_public_private_ports_are_rejected() -> None:
    """ParadeDB host ports fail closed."""

    compose = _private_compose().replace(
        "  paradedb:\n    image:",
        '  paradedb:\n    ports:\n      - "5432:5432"\n    image:',
    )
    with pytest.raises(Phase10TopologyError, match="publishes host ports"):
        assert_compose_policy(compose)


def test_mutable_paradedb_digest_is_rejected() -> None:
    """A floating ParadeDB tag is digest drift."""

    with pytest.raises(Phase10TopologyError, match="digest-pinned"):
        assert_compose_policy(_private_compose(paradedb_image="paradedb/paradedb:pg17"))


def test_lightrag_compose_service_is_rejected() -> None:
    """LightRAG must not appear as a Compose service."""

    compose = _private_compose() + "\n  lightrag:\n    image: fake\n"
    with pytest.raises(Phase10TopologyError, match="in-process"):
        assert_compose_policy(compose)


def test_t3micro_overlay_rejects_host_ports() -> None:
    """The t3.micro overlay must not publish ParadeDB or Valkey."""

    with pytest.raises(Phase10TopologyError, match="host ports"):
        assert_t3micro_overlay(
            """
services:
  paradedb:
    ports:
      - "5432:5432"
    mem_limit: 280m
"""
        )


def test_committed_t3micro_overlay_fits_one_gib() -> None:
    """Accepted t3.micro overlay keeps ParadeDB/Valkey private and small."""

    overlay = (
        Path(__file__).resolve().parents[2]
        / "infra"
        / "ec2"
        / "docker-compose.t3micro.yml"
    )
    assert_t3micro_overlay(overlay.read_text(encoding="utf-8"))


def test_vercel_service_role_is_rejected() -> None:
    """Vercel inventories cannot carry service_role or DB URLs."""

    with pytest.raises(Phase10TopologyError, match="SERVICE_ROLE"):
        assert_no_vercel_secrets("NEXT_PUBLIC_SERVICE_ROLE_KEY=not-a-real-secret")
    with pytest.raises(Phase10TopologyError, match="DATABASE_URL"):
        assert_no_vercel_secrets("DATABASE_URL=postgres://example")


def test_production_seed_is_rejected() -> None:
    """Holdout-open or production-labeled rows fail the synthetic manifest."""

    with pytest.raises(Phase10TopologyError, match="holdout_opened"):
        assert_synthetic_corpus(
            {"holdout_opened": True, "rows": [{"split": "development"}]}
        )
    with pytest.raises(Phase10TopologyError, match="not synthetic"):
        assert_synthetic_corpus(
            {
                "holdout_opened": False,
                "rows": [
                    {
                        "case_id": "production-leak-0001",
                        "split": "development",
                    }
                ],
            }
        )


def test_caddy_without_dual_origin_values_is_rejected() -> None:
    """Packet 1 must not make origin-secret rotation impossible."""

    with pytest.raises(Phase10TopologyError, match="previous origin header"):
        assert_caddy_policy(
            """
            read_timeout 90s
            write_timeout 90s
            flush_interval -1
            {$ORIGIN_HEADER_VALUE_CURRENT}
            {$ACTIVE_API_UPSTREAM}
            respond 403
            """
        )


def test_inventory_production_flag_fails() -> None:
    """Production data flags fail P10-01-E inventory policy."""

    with pytest.raises(Phase10TopologyError, match="production data"):
        assert_inventory(
            {
                "schema_version": "phase10-intended-topology-v1",
                "aws_region": "us-east-1",
                "supabase_region": "us-east-1",
                "supabase_plan": "Pro",
                "pg_search_on_managed_supabase": False,
                "ses_mode": "sandbox",
                "lightrag_deployment": "in-process",
                "production_data": True,
                "holdout_opened": False,
            }
        )


def test_classifications_fail_closed_and_do_not_pass_missing_runtime() -> None:
    """Negatives fail; missing runtime/network scans stay Blocked, not Passed."""

    assert classify_p1001_a(inventory_matches=False) == "Failed"
    assert classify_p1001_a(inventory_matches=True) == "Passed"
    assert (
        classify_p1001_b(
            iac_policy_passed=False,
            runtime_assertions_passed=False,
            live_apply_state="Blocked",
        )
        == "Failed"
    )
    assert (
        classify_p1001_b(
            iac_policy_passed=True,
            runtime_assertions_passed=False,
            live_apply_state="Blocked",
        )
        == "Blocked"
    )
    assert (
        classify_p1001_b(
            iac_policy_passed=True,
            runtime_assertions_passed=True,
            live_apply_state="Blocked",
        )
        == "Passed"
    )
    assert (
        classify_p1001_c(
            iac_policy_passed=True,
            network_scan_passed=False,
            network_scan_present=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1001_c(
            iac_policy_passed=True,
            network_scan_passed=False,
            network_scan_present=True,
        )
        == "Failed"
    )
    assert classify_p1001_d(committed_env_clean=False, live_secret_found=False) == (
        "Failed"
    )
    assert classify_p1001_d(committed_env_clean=True, live_secret_found=True) == (
        "Failed"
    )
    assert classify_p1001_d(committed_env_clean=True, live_secret_found=False) == (
        "Passed"
    )
    assert (
        classify_p1001_e(
            manifest_synthetic=True,
            production_data=True,
            holdout_opened=False,
        )
        == "Failed"
    )
    blocked = _live_blocked()
    assert blocked.apply_state == "Blocked"
    assert CACHING_DISABLED_POLICY_ID.startswith("4135ea2d")
    assert CLOUDFRONT_PREFIX_LIST_NAME.endswith("origin-facing")
    assert _API and _WORKER and _CRAWL and _PARSER and _PARADE and _VALKEY


def test_live_runtime_and_scan_helpers_fail_closed() -> None:
    """Missing IMDS/SSH/encryption or an open private port cannot Pass."""

    assert live_runtime_assertions_passed({"imds_http_tokens": "required"}) is False
    assert (
        live_runtime_assertions_passed(
            {
                "imds_http_tokens": "required",
                "imds_hop_limit": 1,
                "ssh_ingress": False,
                "sshd_disabled": True,
                "instance_state": "running",
                "volumes": [{"encrypted": True}],
            }
        )
        is True
    )
    assert live_network_scan_passed({"qualifies_for_p10_01_c": True}) is False
    assert (
        live_network_scan_passed(
            {
                "qualifies_for_p10_01_c": True,
                "results": [
                    {"port": 22, "open": False},
                    {"port": 5432, "open": False},
                    {"port": 6379, "open": False},
                    {"port": 8000, "open": False},
                    {"port": 8080, "open": False},
                ],
            }
        )
        is True
    )
    assert (
        live_network_scan_passed(
            {
                "qualifies_for_p10_01_c": True,
                "results": [
                    {"port": 22, "open": True},
                    {"port": 5432, "open": False},
                    {"port": 6379, "open": False},
                    {"port": 8000, "open": False},
                    {"port": 8080, "open": False},
                ],
            }
        )
        is False
    )
    assert live_vercel_secret_found({"service_role_present": True}) is True
    assert live_vercel_secret_found({"service_role_present": False}) is False


def test_committed_http443_caddy_keeps_origin_rules() -> None:
    """The t3.micro HTTP-on-443 Caddyfile still denies unmatched origins."""

    path = Path(__file__).resolve().parents[2] / "infra" / "ec2" / "Caddyfile.http443"
    text = path.read_text(encoding="utf-8")
    assert_caddy_http443_policy(text)
    missing_http_port = "\n".join(
        line for line in text.splitlines() if line.strip() != "http_port 443"
    )
    with pytest.raises(Phase10TopologyError, match="http_port 443"):
        assert_caddy_http443_policy(missing_http_port)
