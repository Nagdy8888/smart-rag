"""Classify Phase 10 Packet 3 origin, egress, timeout, and telemetry gates.

IaC/Compose/Caddy/crawl-policy assertions can Pass. Live CDN request matrix,
live port/metadata scans, and live CloudWatch denial-alarm delivery are
Blocked when no CloudFront distribution, EC2 host, or WAF/log stream exists.
This module never curls origins, scans ports, or invents HTTP 200/403.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from smart_rag_core.release.io import dump_canonical_json
from smart_rag_core.release.packet2 import Classification
from smart_rag_core.release.phase10_constants import (
    CADDY_MAX_CONNS_PER_HOST,
    CADDY_MAX_HEADER_BYTES,
    CADDY_READ_HEADER_TIMEOUT_SECONDS,
    CADDY_REQUEST_BODY_BYTES,
    DIRECT_ORIGIN_DENIAL_METRIC_NAME,
    EGRESS_DENIAL_LOG_GROUP,
    EGRESS_DENIAL_METRIC_NAME,
    ORIGIN_KEEPALIVE_TIMEOUT_SECONDS,
    ORIGIN_READ_TIMEOUT_SECONDS,
    PACKET3_CRAWL_TEST_FILES,
    PACKET3_EGRESS_NAME,
    PACKET3_EGRESS_SCHEMA_VERSION,
    PACKET3_MATRIX_NAME,
    PACKET3_MATRIX_SCHEMA_VERSION,
    PACKET3_NEGATIVES_NAME,
    PACKET3_NEGATIVES_SCHEMA_VERSION,
    PACKET3_ORIGIN_NAME,
    PACKET3_ORIGIN_SCHEMA_VERSION,
    PACKET3_RELATIVE,
    PACKET3_SCANS_NAME,
    PACKET3_SCANS_SCHEMA_VERSION,
    PACKET3_TIMEOUTS_NAME,
    PACKET3_TIMEOUTS_SCHEMA_VERSION,
    PHASE09_IMAGE_IDS,
    PHASE10_ARTIFACT_DIR,
    TELEMETRY_NAMESPACE,
    WAF_RATE_LIMIT_COMMITTED,
    WAF_RULE_METRIC_NAMES,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_egress import (
    Phase10EgressError,
    assert_packet3_policy,
)
from smart_rag_core.release.phase10_packet1 import (
    LiveProviderProbe,
    probe_live_providers,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_topology import PolicyReport

LiveProofState = Literal["Blocked", "Not Run", "Failed"]

_LIVE_CDN_REASON = (
    "No CloudFront distribution, EC2 origin, or WAF logs. Live CDN and "
    "direct-origin requests were not sent."
)
_LIVE_SCAN_REASON = (
    "No EC2 host or scan artifact. Live private-port and metadata scans were not run."
)
_LIVE_ALERT_REASON = (
    "CloudWatch log group and metric filters exist in IaC. Live denial "
    "alarm delivery was not proven."
)


class Phase10Packet3GateError(RuntimeError):
    """Raised when Packet 3 classification cannot be recorded honestly."""


@dataclass(frozen=True, slots=True)
class AcceptanceRow:
    """One P10-03 acceptance classification.

    Attributes:
        check: Requirement id such as ``P10-03-A``.
        classification: Honest Passed/Failed/Blocked/Not Run value.
        detail: Evidence without secrets.
    """

    check: str
    classification: Classification
    detail: str


def packet3_checkbox_unchecked(text: str) -> bool:
    """Return whether the wrapper Packet 3 checkbox is unchecked.

    Args:
        text: Wrapper markdown.

    Returns:
        True when packet 3 remains ``[ ]``. Packet 1 and 2 states are ignored.
    """

    return "3. [ ] [Prove direct-origin rejection, provider/crawl/parser egress" in text


def packet3_status_pending(text: str) -> bool:
    """Return whether the Packet 3 file frontmatter is still pending.

    Args:
        text: Packet markdown.

    Returns:
        True when ``status: pending`` is present in frontmatter.
    """

    head = text.split("---", 2)
    if len(head) < 3:
        return False
    return "status: pending" in head[1]


def live_proof_state(live: LiveProviderProbe) -> LiveProofState:
    """Map the Packet 1 provider probe onto Packet 3 live CDN/scan/alert state.

    Args:
        live: Terraform/AWS CLI probe. This function does not send requests.

    Returns:
        ``Blocked`` when tools or session are missing. ``Not Run`` when a
        session exists but this packet refuses to curl or scan. ``Failed``
        when the probe itself failed.
    """

    if live.apply_state == "Failed":
        return "Failed"
    if live.apply_state == "Blocked" or not live.sts_ok:
        return "Blocked"
    return "Not Run"


def classify_p1003_a(
    *,
    origin_policy_passed: bool,
    live_cdn_state: LiveProofState,
    live_cdn_passed: bool,
) -> Classification:
    """Classify valid-CDN success plus direct-origin denial.

    Args:
        origin_policy_passed: Committed Caddy/SG/CloudFront origin policy.
        live_cdn_state: Honest live request probe.
        live_cdn_passed: True only after a real request-matrix artifact.

    Returns:
        ``Failed`` when origin policy or a live request fails. ``Passed``
        only with a real CDN success plus origin denials. Otherwise
        ``Blocked``.
    """

    if not origin_policy_passed or live_cdn_state == "Failed":
        return "Failed"
    if live_cdn_passed:
        return "Passed"
    return "Blocked"


def classify_p1003_b(
    *,
    ports_policy_passed: bool,
    live_scan_state: LiveProofState,
    live_scan_passed: bool,
    live_scan_present: bool,
) -> Classification:
    """Classify unpublished private/metadata/management ports.

    Args:
        ports_policy_passed: Compose/user-data/IMDS policy result.
        live_scan_state: Honest live scan probe.
        live_scan_passed: True only from a real scan artifact that passed.
        live_scan_present: True when a scan artifact exists.

    Returns:
        ``Passed`` only with a passing live scan. ``Failed`` when policy or
        a present scan fails. ``Blocked`` when the scan is absent.
    """

    if not ports_policy_passed or live_scan_state == "Failed":
        return "Failed"
    if live_scan_present and live_scan_passed:
        return "Passed"
    if live_scan_present and not live_scan_passed:
        return "Failed"
    return "Blocked"


def classify_p1003_c(
    *, egress_policy_passed: bool, crawl_subset_ok: bool
) -> Classification:
    """Classify provider/crawl/parser/ParadeDB egress from committed policy.

    Args:
        egress_policy_passed: Provider-egress/parser/ParadeDB policy result.
        crawl_subset_ok: Nonzero crawl-policy/ssrf tests collected with no skip.

    Returns:
        ``Passed`` when committed egress policy and crawl tests hold.
        ``Failed`` otherwise. Live destination reaches are not required.
    """

    if egress_policy_passed and crawl_subset_ok:
        return "Passed"
    return "Failed"


def classify_p1003_d(*, timeout_policy_passed: bool) -> Classification:
    """Classify WAF/Caddy controls and 90-second timeout assertions.

    Args:
        timeout_policy_passed: Committed CloudFront/Caddy/WAF timeout policy.

    Returns:
        ``Passed`` when IaC assertions hold. ``Failed`` on 60s timeouts,
        buffering, or missing WAF/Caddy caps. Runtime CDN drift is recorded
        separately and cannot green this check by itself.
    """

    if timeout_policy_passed:
        return "Passed"
    return "Failed"


def classify_p1003_e(
    *,
    telemetry_policy_passed: bool,
    live_alert_state: LiveProofState,
    live_alert_passed: bool,
) -> Classification:
    """Classify denial telemetry reaching monitoring.

    Args:
        telemetry_policy_passed: WAF metrics plus CloudWatch filter IaC.
        live_alert_state: Honest live alarm probe.
        live_alert_passed: True only after a delivered synthetic alert.

    Returns:
        ``Failed`` when IaC telemetry is missing or a live alert fails.
        ``Passed`` only after a real delivered alarm. Otherwise ``Blocked``.
    """

    if not telemetry_policy_passed or live_alert_state == "Failed":
        return "Failed"
    if live_alert_passed:
        return "Passed"
    return "Blocked"


def finding_passed(policy: PolicyReport | None, check: str) -> bool:
    """Return whether one named Packet 3 finding passed.

    Args:
        policy: Packet 3 policy report, or None when files are missing.
        check: Finding id.

    Returns:
        True when the report exists and that finding passed.
    """

    if policy is None:
        return False
    for item in policy.findings:
        if item.check == check:
            return item.passed
    return False


def request_matrix_rows(live_state: LiveProofState) -> tuple[dict[str, object], ...]:
    """Return the origin request matrix without invented HTTP statuses.

    Args:
        live_state: Honest live CDN state.

    Returns:
        Rows with ``http_status`` null and classification Blocked/Not Run.
    """

    cases = (
        "valid_cdn",
        "direct_origin_missing_header",
        "direct_origin_wrong_secret",
        "direct_ip",
        "direct_hostname",
    )
    return tuple(
        {
            "case": case,
            "classification": live_state,
            "http_status": None,
            "detail": _LIVE_CDN_REASON,
        }
        for case in cases
    )


def scan_rows(live_state: LiveProofState) -> tuple[dict[str, object], ...]:
    """Return private-port and metadata scan rows without invented results.

    Args:
        live_state: Honest live scan state.

    Returns:
        Scan rows. ``observed`` stays null because no scan ran.
    """

    targets = (
        ("tcp/443", "caddy origin beyond CloudFront prefix list"),
        ("tcp/22", "ssh"),
        ("tcp/5432", "paradedb"),
        ("tcp/6379", "valkey"),
        ("tcp/8080", "crawl-proxy/provider-egress host publish"),
        ("tcp/9621", "lightrag"),
        ("tcp/9624", "lightrag"),
        ("tcp/54329", "packet8 paradedb overlay"),
        ("udp/161", "management"),
        ("http://169.254.169.254/", "instance metadata"),
    )
    return tuple(
        {
            "target": target,
            "role": role,
            "classification": live_state,
            "observed": None,
            "detail": _LIVE_SCAN_REASON,
        }
        for target, role in targets
    )


def classify_packet3(
    *,
    policy: PolicyReport | None,
    live: LiveProviderProbe,
    crawl_subset_ok: bool,
    live_cdn_passed: bool = False,
    live_scan_passed: bool = False,
    live_scan_present: bool = False,
    live_alert_passed: bool = False,
) -> tuple[AcceptanceRow, ...]:
    """Classify P10-03-A through E from committed evidence and probes.

    Args:
        policy: Packet 3 policy report, or None when files are missing.
        live: Provider probe. Never a CDN request or port scan.
        crawl_subset_ok: Crawl-policy/ssrf subset collected without skip.
        live_cdn_passed: True only from a real request artifact.
        live_scan_passed: True only from a real passing scan artifact.
        live_scan_present: True when a scan artifact exists.
        live_alert_passed: True only from a delivered synthetic alarm.

    Returns:
        Five acceptance rows.
    """

    origin_ok = finding_passed(policy, "origin")
    ports_ok = finding_passed(policy, "private_ports") and finding_passed(
        policy, "metadata"
    )
    egress_ok = finding_passed(policy, "egress")
    timeout_ok = finding_passed(policy, "timeouts")
    telemetry_ok = finding_passed(policy, "telemetry")
    live_state = live_proof_state(live)
    return (
        AcceptanceRow(
            check="P10-03-A",
            classification=classify_p1003_a(
                origin_policy_passed=origin_ok,
                live_cdn_state=live_state,
                live_cdn_passed=live_cdn_passed,
            ),
            detail=(
                "Committed Caddy 403 / CloudFront custom header / prefix-list "
                "origin policy "
                + ("Passed" if origin_ok else "Failed")
                + f". Live CDN request matrix is {live_state}: "
                + _LIVE_CDN_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-03-B",
            classification=classify_p1003_b(
                ports_policy_passed=ports_ok,
                live_scan_state=live_state,
                live_scan_passed=live_scan_passed,
                live_scan_present=live_scan_present,
            ),
            detail=(
                "Committed unpublished private-port and metadata-deny policy "
                + ("Passed" if ports_ok else "Failed")
                + f". Live scan is {live_state}: "
                + _LIVE_SCAN_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-03-C",
            classification=classify_p1003_c(
                egress_policy_passed=egress_ok, crawl_subset_ok=crawl_subset_ok
            ),
            detail=(
                "Provider-egress default 403, public-only allowlist, parser "
                "network_mode none, and ParadeDB on internal private "
                + ("Passed" if egress_ok else "Failed")
                + ". Crawl-policy/ssrf subset "
                + ("Passed" if crawl_subset_ok else "Failed")
                + f" ({', '.join(PACKET3_CRAWL_TEST_FILES)})."
            ),
        ),
        AcceptanceRow(
            check="P10-03-D",
            classification=classify_p1003_d(timeout_policy_passed=timeout_ok),
            detail=(
                f"CloudFront origin_read/keepalive {ORIGIN_READ_TIMEOUT_SECONDS}s/"
                f"{ORIGIN_KEEPALIVE_TIMEOUT_SECONDS}s, Caddy 90s, flush_interval "
                "-1, CachingDisabled, WAF CLOUDFRONT, and Caddy header/body/"
                "connection caps "
                + ("Passed" if timeout_ok else "Failed")
                + ". origin_read_timeout 60 is rejected. Live CDN runtime drift "
                f"is {live_state}."
            ),
        ),
        AcceptanceRow(
            check="P10-03-E",
            classification=classify_p1003_e(
                telemetry_policy_passed=telemetry_ok,
                live_alert_state=live_state,
                live_alert_passed=live_alert_passed,
            ),
            detail=(
                "WAF visibility_config metric names and CloudWatch egress/"
                "origin denial filters "
                + ("Passed" if telemetry_ok else "Failed")
                + f". Live synthetic alarm is {live_state}: "
                + _LIVE_ALERT_REASON
            ),
        ),
    )


def negatives_catalog() -> tuple[dict[str, str], ...]:
    """Return the Packet 3 negative cases exercised by unit tests.

    Returns:
        Machine-readable negative catalog without secret values.
    """

    exercise = "tests/unit/test_phase10_packet3.py"
    expected = "Phase10EgressError"
    return (
        {
            "case": "origin_cidr_0_0_0_0_443",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "direct_ip_or_header_secret",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "private_port_or_lightrag_publish",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "allowlist_rfc1918",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "crawl_private_redirect",
            "expected": "CrawlPolicyError",
            "exercise": exercise,
        },
        {
            "case": "origin_read_timeout_60",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "sse_buffering_or_header_limit_excess",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "fake_cdn_http_status_is_not_passed",
            "expected": "Blocked",
            "exercise": exercise,
        },
    )


def write_packet3_artifacts(
    repo_root: Path,
    *,
    policy: PolicyReport,
    live: LiveProviderProbe,
    rows: Sequence[AcceptanceRow],
    crawl_subset: Mapping[str, object],
) -> dict[str, Path]:
    """Write Packet 3 JSON artifacts without secrets or fake HTTP statuses.

    Args:
        repo_root: Repository root.
        policy: Packet 3 policy report.
        live: Provider probe.
        rows: Acceptance classifications.
        crawl_subset: Collected crawl-policy/ssrf counts.

    Returns:
        Artifact name to path mapping.

    Side Effects:
        Overwrites files under ``docs/deployment/phase-10/``.
    """

    artifact_dir = repo_root / PHASE10_ARTIFACT_DIR
    live_state = live_proof_state(live)
    matrix: dict[str, object] = {
        "schema_version": PACKET3_MATRIX_SCHEMA_VERSION,
        "packet": "P10-03",
        "wrapper_status": "pending",
        "packet1_checkbox": "unchecked",
        "packet2_checkbox": "unchecked",
        "packet3_checkbox": "unchecked",
        "holdout_opened": False,
        "phase9_image_ids": dict(PHASE09_IMAGE_IDS),
        "iac_policy": "Passed" if policy.passed else "Failed",
        "iac_sha256": policy.iac_sha256,
        "live_cdn_requests": live_state,
        "live_port_scan": live_state,
        "live_denial_alert": live_state,
        "crawl_subset": dict(crawl_subset),
        "acceptance": [
            {
                "check": row.check,
                "classification": row.classification,
                "detail": row.detail,
            }
            for row in rows
        ],
    }
    origin_out: dict[str, object] = {
        "schema_version": PACKET3_ORIGIN_SCHEMA_VERSION,
        "policy": "Passed" if finding_passed(policy, "origin") else "Failed",
        "live_requests": live_state,
        "live_reason": _LIVE_CDN_REASON,
        "request_matrix": list(request_matrix_rows(live_state)),
    }
    egress_out: dict[str, object] = {
        "schema_version": PACKET3_EGRESS_SCHEMA_VERSION,
        "policy": "Passed" if finding_passed(policy, "egress") else "Failed",
        "parser_network_mode": "none",
        "paradedb_network": "private",
        "private_network_internal": True,
        "provider_egress_default": 403,
        "allowlist_rfc1918": False,
        "crawl_tests": list(PACKET3_CRAWL_TEST_FILES),
        "crawl_subset": dict(crawl_subset),
        "accepted_risk_adr": None,
    }
    timeouts_out: dict[str, object] = {
        "schema_version": PACKET3_TIMEOUTS_SCHEMA_VERSION,
        "policy": "Passed" if finding_passed(policy, "timeouts") else "Failed",
        "origin_read_timeout_seconds": ORIGIN_READ_TIMEOUT_SECONDS,
        "origin_keepalive_timeout_seconds": ORIGIN_KEEPALIVE_TIMEOUT_SECONDS,
        "caddy_flush_interval": -1,
        "caddy_max_header_bytes": CADDY_MAX_HEADER_BYTES,
        "caddy_request_body_bytes": CADDY_REQUEST_BODY_BYTES,
        "caddy_max_conns_per_host": CADDY_MAX_CONNS_PER_HOST,
        "caddy_read_header_timeout_seconds": CADDY_READ_HEADER_TIMEOUT_SECONDS,
        "waf_rate_limit": WAF_RATE_LIMIT_COMMITTED,
        "waf_rule_metrics": list(WAF_RULE_METRIC_NAMES),
        "origin_read_timeout_60_rejected": True,
        "live_runtime_drift": live_state,
    }
    scans_out: dict[str, object] = {
        "schema_version": PACKET3_SCANS_SCHEMA_VERSION,
        "policy": (
            "Passed"
            if finding_passed(policy, "private_ports")
            and finding_passed(policy, "metadata")
            else "Failed"
        ),
        "live_scan": live_state,
        "live_reason": _LIVE_SCAN_REASON,
        "live_alert": live_state,
        "live_alert_reason": _LIVE_ALERT_REASON,
        "log_group": EGRESS_DENIAL_LOG_GROUP,
        "metrics": {
            "namespace": TELEMETRY_NAMESPACE,
            "egress_denials": EGRESS_DENIAL_METRIC_NAME,
            "direct_origin_denials": DIRECT_ORIGIN_DENIAL_METRIC_NAME,
        },
        "targets": list(scan_rows(live_state)),
    }
    negatives_out: dict[str, object] = {
        "schema_version": PACKET3_NEGATIVES_SCHEMA_VERSION,
        "cases": list(negatives_catalog()),
    }
    paths = {
        PACKET3_MATRIX_NAME: artifact_dir / PACKET3_MATRIX_NAME,
        PACKET3_ORIGIN_NAME: artifact_dir / PACKET3_ORIGIN_NAME,
        PACKET3_EGRESS_NAME: artifact_dir / PACKET3_EGRESS_NAME,
        PACKET3_TIMEOUTS_NAME: artifact_dir / PACKET3_TIMEOUTS_NAME,
        PACKET3_SCANS_NAME: artifact_dir / PACKET3_SCANS_NAME,
        PACKET3_NEGATIVES_NAME: artifact_dir / PACKET3_NEGATIVES_NAME,
    }
    dump_canonical_json(matrix, paths[PACKET3_MATRIX_NAME])
    dump_canonical_json(origin_out, paths[PACKET3_ORIGIN_NAME])
    dump_canonical_json(egress_out, paths[PACKET3_EGRESS_NAME])
    dump_canonical_json(timeouts_out, paths[PACKET3_TIMEOUTS_NAME])
    dump_canonical_json(scans_out, paths[PACKET3_SCANS_NAME])
    dump_canonical_json(negatives_out, paths[PACKET3_NEGATIVES_NAME])
    return paths


def evaluate_packet3(
    repo_root: Path,
    *,
    crawl_subset_ok: bool,
) -> tuple[PolicyReport, LiveProviderProbe, tuple[AcceptanceRow, ...]]:
    """Run committed Packet 3 policy plus probes and classify P10-03.

    Packet 1 and Packet 2 remaining unchecked is not a failure. Wrapper and
    Packet 3 stay pending while live CDN/scan/alert is Blocked.

    Args:
        repo_root: Repository root.
        crawl_subset_ok: Nonzero crawl-policy/ssrf collection with no skip.

    Returns:
        Policy report, live probe, and acceptance rows.

    Raises:
        Phase10Packet3GateError: If policy fails, crawl subset is empty, or
            the wrapper was marked complete.
    """

    wrapper = (repo_root / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (repo_root / PACKET3_RELATIVE).read_text(encoding="utf-8")
    if not wrapper_status_pending(wrapper):
        raise Phase10Packet3GateError("Phase 10 wrapper must remain status: pending")
    if not packet3_checkbox_unchecked(wrapper):
        raise Phase10Packet3GateError(
            "Packet 3 checkbox must stay unchecked while live CDN/scan/alert is Blocked"
        )
    if not packet3_status_pending(packet):
        raise Phase10Packet3GateError("Packet 3 file must remain status: pending")
    if not crawl_subset_ok:
        raise Phase10Packet3GateError(
            "Packet 3 crawl-policy/ssrf subset collected zero tests or skipped"
        )
    try:
        policy = assert_packet3_policy(repo_root)
    except Phase10EgressError as exc:
        raise Phase10Packet3GateError(str(exc)) from exc
    live = probe_live_providers()
    rows = classify_packet3(policy=policy, live=live, crawl_subset_ok=crawl_subset_ok)
    return policy, live, rows
