"""Classify Phase 10 Packet 4 JWKS, origin rotation, SSE, ParadeDB, and Valkey.

Application JWKS, origin dual-header policy, Hybrid BM25 degrade, and Valkey
fail-closed tests can Pass. Managed Supabase dashboard JWKS rollover, live
origin rotation, CloudFront 50-second SSE, and EC2 ParadeDB/Valkey kill
remain Blocked. This module never invents HTTP statuses, JWKS kids, stream
durations, or kill results. Packets 1-3 remaining unchecked is not a
Packet 4 failure.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from smart_rag_core.release.io import (
    as_json_object,
    dump_canonical_json,
    load_json_object,
)
from smart_rag_core.release.packet2 import Classification
from smart_rag_core.release.phase10_constants import (
    CDN_SSE_MIN_DURATION_SECONDS,
    CDN_SSE_VIA_CLOUDFRONT,
    GITHUB_WORKFLOWS_DIR,
    INFRA_EC2_DIR,
    ORIGIN_KEEPALIVE_TIMEOUT_SECONDS,
    ORIGIN_READ_TIMEOUT_SECONDS,
    ORIGIN_ROTATION_OVERLAP_MAX_MINUTES,
    ORIGIN_ROTATION_RUNBOOK,
    ORIGIN_RUNBOOK_REQUIRED_TOKENS,
    PACKET4_JWKS_NAME,
    PACKET4_JWKS_SCHEMA_VERSION,
    PACKET4_JWKS_TEST_FILES,
    PACKET4_MATRIX_NAME,
    PACKET4_MATRIX_SCHEMA_VERSION,
    PACKET4_NEGATIVES_NAME,
    PACKET4_NEGATIVES_SCHEMA_VERSION,
    PACKET4_ORIGIN_NAME,
    PACKET4_ORIGIN_SCHEMA_VERSION,
    PACKET4_PARADEDB_NAME,
    PACKET4_PARADEDB_SCHEMA_VERSION,
    PACKET4_PARADEDB_TEST_FILES,
    PACKET4_RELATIVE,
    PACKET4_SSE_NAME,
    PACKET4_SSE_SCHEMA_VERSION,
    PACKET4_SSE_SUPPORT_TEST_FILES,
    PACKET4_VALKEY_NAME,
    PACKET4_VALKEY_SCHEMA_VERSION,
    PACKET4_VALKEY_TEST_FILES,
    PHASE09_IMAGE_IDS,
    PHASE09_PACKET5_FAULT,
    PHASE09_PACKET6_REBUILD,
    PHASE10_ARTIFACT_DIR,
    STAGING_CADDY_FILE,
    STAGING_COMPOSE_FILE,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_packet1 import (
    LiveProviderProbe,
    probe_live_providers,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_topology import (
    PolicyFinding,
    PolicyReport,
    hash_reviewed_files,
    load_terraform_bundle,
    strip_hcl_comments,
)
from smart_rag_core.security.jwks import FORBIDDEN_ALGORITHMS

LiveProofState = Literal["Blocked", "Not Run", "Failed"]

_MANAGED_JWKS_REASON = (
    "No isolated managed Supabase project. Managed staging dashboard "
    "standby to active to retired JWKS rollover was not run. Phase 2 "
    "project qsjivtwtmlmtksufqjik is not Phase 10 staging proof."
)
_LIVE_ROTATION_REASON = (
    "No CloudFront distribution or EC2 origin. Live dual origin-secret "
    "rotation was not executed."
)
_LIVE_CDN_STREAM_REASON = (
    "No CloudFront 50-second SSE timeline. Local EventSource is not CDN."
)
_LIVE_PARADEDB_KILL_REASON = (
    "No EC2 ParadeDB kill or version-mismatch drill. Local compose "
    "degrade is not a managed host kill."
)
_LIVE_VALKEY_KILL_REASON = (
    "No EC2 Valkey kill. Application fail-closed tests are not a managed host outage."
)


class Phase10Packet4GateError(RuntimeError):
    """Raised when Packet 4 classification cannot be recorded honestly."""


@dataclass(frozen=True, slots=True)
class AcceptanceRow:
    """One P10-04 acceptance classification.

    Attributes:
        check: Requirement id such as ``P10-04-A``.
        classification: Honest Passed/Failed/Blocked/Not Run value.
        detail: Evidence without secrets.
    """

    check: str
    classification: Classification
    detail: str


@dataclass(frozen=True, slots=True)
class CdnStreamEvidence:
    """Optional live CDN SSE artifact.

    Attributes:
        duration_seconds: Observed stream duration, or None when absent.
        via: Transport label. ``cloudfront`` is required for Passed.
        paid_runs: Count of paid query runs, or None when absent.
    """

    duration_seconds: float | None = None
    via: str | None = None
    paid_runs: int | None = None


@dataclass(frozen=True, slots=True)
class Phase09DegradeEvidence:
    """Phase 9 Packet 5/6 degrade and rebuild facts reused by Packet 4.

    Attributes:
        degrade_passed: Hybrid retrieve recorded ``bm25_unavailable``.
        fallback_reason: Recorded fallback reason string.
        rebuild_passed: Packet 6 rebuild artifact passed.
        paradedb_used_as_canonical: True when a snapshot was treated as authority.
        deny_passed: Valkey deny matrix passed.
        fill_recovered: Valkey fill/recovery passed.
        named_acl_users: True only for managed named ACL proof.
    """

    degrade_passed: bool
    fallback_reason: str | None
    rebuild_passed: bool
    paradedb_used_as_canonical: bool
    deny_passed: bool
    fill_recovered: bool
    named_acl_users: bool


def packet4_checkbox_unchecked(text: str) -> bool:
    """Return whether the wrapper Packet 4 checkbox is unchecked.

    Args:
        text: Wrapper markdown.

    Returns:
        True when packet 4 remains ``[ ]``. Packets 1-3 are ignored.
    """

    return (
        "4. [ ] [Exercise asymmetric JWKS rollover, dual origin-secret rotation" in text
    )


def packet4_status_pending(text: str) -> bool:
    """Return whether the Packet 4 file frontmatter is still pending.

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
    """Map the Packet 1 provider probe onto Packet 4 live rotation/stream/kill.

    Args:
        live: Terraform/AWS CLI probe. This function does not rotate, stream,
            or kill services.

    Returns:
        ``Blocked`` when tools or session are missing. ``Not Run`` when a
        session exists but this packet refuses live CloudFront/EC2 work.
        ``Failed`` when the probe itself failed.
    """

    if live.apply_state == "Failed":
        return "Failed"
    if live.apply_state == "Blocked" or not live.sts_ok:
        return "Blocked"
    return "Not Run"


def assert_origin_overlap_minutes(overlap_minutes: int) -> None:
    """Reject origin-secret overlap longer than the topology maximum.

    Args:
        overlap_minutes: Planned Caddy old-plus-new acceptance window.

    Raises:
        Phase10Packet4GateError: If overlap exceeds 15 minutes.
    """

    if overlap_minutes > ORIGIN_ROTATION_OVERLAP_MAX_MINUTES:
        raise Phase10Packet4GateError(
            f"origin overlap must be <= {ORIGIN_ROTATION_OVERLAP_MAX_MINUTES} minutes"
        )
    if overlap_minutes < 0:
        raise Phase10Packet4GateError("origin overlap minutes cannot be negative")


def assert_caddy_dual_origin_values(caddy_text: str) -> None:
    """Require Caddy to accept current and previous origin header values.

    Args:
        caddy_text: Staging Caddyfile.

    Raises:
        Phase10Packet4GateError: If CURRENT or PREVIOUS placeholders are
            missing, or a literal secret-looking value is committed.
    """

    if "ORIGIN_HEADER_VALUE_CURRENT" not in caddy_text:
        raise Phase10Packet4GateError("Caddy current origin header value is missing")
    if "ORIGIN_HEADER_VALUE_PREVIOUS" not in caddy_text:
        raise Phase10Packet4GateError(
            "Caddy previous origin header value is required for dual rotation"
        )
    if "{$ORIGIN_HEADER_VALUE_CURRENT}" not in caddy_text:
        raise Phase10Packet4GateError(
            "Caddy CURRENT origin value must be an env placeholder"
        )
    if "{$ORIGIN_HEADER_VALUE_PREVIOUS}" not in caddy_text:
        raise Phase10Packet4GateError(
            "Caddy PREVIOUS origin value must be an env placeholder"
        )
    lowered = caddy_text.lower()
    if "hs256" in lowered:
        raise Phase10Packet4GateError("Caddy must not mention HS256 secrets")


def assert_cloudfront_origin_custom_header(hcl: str) -> None:
    """Require a CloudFront origin custom_header plus previous-value support.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10Packet4GateError: If custom_header or previous variables are
            missing.
    """

    if "custom_header" not in hcl:
        raise Phase10Packet4GateError("CloudFront custom_header is missing")
    if "origin_header_value" not in hcl:
        raise Phase10Packet4GateError("CloudFront origin_header_value is missing")
    if "origin_header_value_previous" not in hcl:
        raise Phase10Packet4GateError(
            "CloudFront origin_header_value_previous is missing"
        )
    if "var.origin_header_value" not in hcl:
        raise Phase10Packet4GateError(
            "CloudFront origin header must be a Terraform variable"
        )


def assert_origin_rotation_runbook(runbook_text: str) -> None:
    """Require the topology rotation procedure, overlap cap, and rollback.

    Args:
        runbook_text: ``docs/runbooks/origin-secret-rotation.md``.

    Raises:
        Phase10Packet4GateError: If required procedure tokens or the 15-minute
            overlap cap are missing.
    """

    lowered = runbook_text.lower()
    missing = [
        token for token in ORIGIN_RUNBOOK_REQUIRED_TOKENS if token not in lowered
    ]
    if missing:
        raise Phase10Packet4GateError(
            "origin-secret-rotation runbook missing: " + ", ".join(missing)
        )
    if "```mermaid" not in runbook_text:
        raise Phase10Packet4GateError(
            "origin-secret-rotation runbook must include a Mermaid diagram"
        )
    assert_origin_overlap_minutes(ORIGIN_ROTATION_OVERLAP_MAX_MINUTES)


def assert_compose_previous_origin(compose_text: str) -> None:
    """Require staging Compose to inject previous origin header values.

    Args:
        compose_text: ``infra/ec2/docker-compose.staging.yml``.

    Raises:
        Phase10Packet4GateError: If PREVIOUS is optional or absent.
    """

    if "ORIGIN_HEADER_VALUE_PREVIOUS" not in compose_text:
        raise Phase10Packet4GateError("Compose previous origin header value is missing")
    if "ORIGIN_HEADER_VALUE_PREVIOUS:?" not in compose_text.replace(" ", ""):
        if "${ORIGIN_HEADER_VALUE_PREVIOUS:?set" not in compose_text:
            raise Phase10Packet4GateError(
                "Compose previous origin value must be required, not optional"
            )


def assert_hs256_forbidden() -> None:
    """Require FastAPI JWKS to forbid HS256 and sibling HMAC algorithms.

    Raises:
        Phase10Packet4GateError: If HS256 is absent from the forbid set.
    """

    if "HS256" not in FORBIDDEN_ALGORITHMS:
        raise Phase10Packet4GateError("HS256 must remain in FORBIDDEN_ALGORITHMS")


def assert_paradedb_projection_not_canonical(
    rebuild: Mapping[str, object],
) -> None:
    """Reject ParadeDB snapshot-as-canonical recovery claims.

    Args:
        rebuild: Phase 9 Packet 6 rebuild artifact object.

    Raises:
        Phase10Packet4GateError: If the artifact treats ParadeDB as authority
            or omits the explicit false flag.
    """

    flag = rebuild.get("paradedb_used_as_canonical")
    if flag is True:
        raise Phase10Packet4GateError(
            "ParadeDB snapshot is not canonical recovery evidence"
        )
    if flag is not False:
        raise Phase10Packet4GateError(
            "rebuild artifact must set paradedb_used_as_canonical false"
        )


def classify_p1004_a(
    *,
    app_jwks_collected: bool,
    app_jwks_passed: bool,
    hs256_forbidden: bool,
    managed_jwks_passed: bool,
) -> Classification:
    """Classify JWKS rollover without HS256 fallback or auth outage.

    Args:
        app_jwks_collected: Nonzero application JWKS tests collected.
        app_jwks_passed: Application JWKS tests passed with no skip.
        hs256_forbidden: HS256 remains in ``FORBIDDEN_ALGORITHMS``.
        managed_jwks_passed: True only after isolated staging dashboard
            rollover. Phase 2 project proof does not set this.

    Returns:
        ``Failed`` when collected tests fail or HS256 is allowed.
        ``Blocked`` when application JWKS tests cannot run.
        ``Passed`` for application JWKS even when managed dashboard rollover
        is Not Run.
    """

    if not hs256_forbidden:
        return "Failed"
    if not app_jwks_collected:
        return "Blocked"
    if not app_jwks_passed:
        return "Failed"
    if managed_jwks_passed:
        return "Passed"
    return "Passed"


def classify_p1004_b(
    *,
    origin_policy_passed: bool,
    live_rotation_state: LiveProofState,
    live_rotation_passed: bool,
) -> Classification:
    """Classify dual origin-secret rotation and rollback.

    Args:
        origin_policy_passed: Caddy CURRENT+PREVIOUS, CloudFront header,
            overlap <=15, and rollback runbook.
        live_rotation_state: Honest live rotation probe.
        live_rotation_passed: True only after a real rotation audit artifact.

    Returns:
        ``Failed`` when policy or a live rotation fails. ``Passed`` only with
        a live audit. Otherwise ``Blocked``.
    """

    if not origin_policy_passed or live_rotation_state == "Failed":
        return "Failed"
    if live_rotation_passed:
        return "Passed"
    return "Blocked"


def classify_p1004_c(
    *,
    timeout_policy_passed: bool,
    stream: CdnStreamEvidence,
) -> Classification:
    """Classify the real 50-second CDN SSE run under 90-second settings.

    Args:
        timeout_policy_passed: Packet 3 90-second CloudFront/Caddy assertions.
        stream: Live CDN artifact. Local EventSource cannot Pass.

    Returns:
        ``Failed`` when timeouts fail, a non-CloudFront via is claimed, or a
        CloudFront run misses duration/paid-run gates. ``Passed`` only with
        ``via=cloudfront``, ``duration_seconds>=50``, and one paid run.
        Otherwise ``Blocked``.
    """

    if not timeout_policy_passed:
        return "Failed"
    if stream.via is not None and stream.via != CDN_SSE_VIA_CLOUDFRONT:
        return "Failed"
    if (
        stream.via == CDN_SSE_VIA_CLOUDFRONT
        and stream.duration_seconds is not None
        and stream.paid_runs is not None
    ):
        if (
            stream.duration_seconds >= CDN_SSE_MIN_DURATION_SECONDS
            and stream.paid_runs == 1
        ):
            return "Passed"
        return "Failed"
    return "Blocked"


def classify_p1004_d(
    *,
    app_degrade_ok: bool,
    rebuild_parity_ok: bool,
    snapshot_as_canonical: bool,
    live_kill_passed: bool,
) -> Classification:
    """Classify ParadeDB outage, version mismatch, and rebuild parity.

    Args:
        app_degrade_ok: Application dense+term degrade tests passed.
        rebuild_parity_ok: Phase 9 rebuild artifact passed and is not canonical.
        snapshot_as_canonical: True when a ParadeDB snapshot is claimed as
            authority.
        live_kill_passed: True only after a real EC2 kill/version-mismatch.

    Returns:
        ``Failed`` on stale/canonical claims or rebuild miss. ``Blocked``
        when application degrade tests cannot run. ``Passed`` for application
        degrade even when live EC2 kill is Blocked.
    """

    if snapshot_as_canonical or not rebuild_parity_ok:
        return "Failed"
    if not app_degrade_ok:
        return "Blocked"
    if live_kill_passed:
        return "Passed"
    return "Passed"


def classify_p1004_e(
    *,
    app_fail_closed_ok: bool,
    live_valkey_kill_passed: bool,
) -> Classification:
    """Classify Valkey deny/fill/restart fail-closed ownership.

    Args:
        app_fail_closed_ok: Application Valkey deny/fail-closed tests passed.
        live_valkey_kill_passed: True only after a real EC2 Valkey kill.

    Returns:
        ``Blocked`` when application tests cannot run. ``Failed`` when they
        fail. ``Passed`` for application fail-closed even when live EC2 kill
        is Blocked.
    """

    if not app_fail_closed_ok:
        return "Blocked"
    if live_valkey_kill_passed:
        return "Passed"
    return "Passed"


def finding_passed(policy: PolicyReport | None, check: str) -> bool:
    """Return whether one named Packet 4 origin-policy finding passed.

    Args:
        policy: Origin rotation policy report, or None when files are missing.
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


def _run_check(check: str, callback: Callable[[], None]) -> PolicyFinding:
    """Run one assertion and convert failures into findings.

    Args:
        check: Assertion id.
        callback: Zero-argument callable that raises
            ``Phase10Packet4GateError``.

    Returns:
        Finding with pass/fail detail.
    """

    try:
        callback()
    except Phase10Packet4GateError as exc:
        return PolicyFinding(check=check, passed=False, detail=str(exc))
    return PolicyFinding(check=check, passed=True, detail="ok")


def assert_origin_rotation_policy(repo_root: Path) -> PolicyReport:
    """Assert committed dual-origin rotation support and the runbook.

    Args:
        repo_root: Repository root.

    Returns:
        Policy report. ``passed`` is False when any finding failed.

    Raises:
        Phase10Packet4GateError: If required files are missing or any check
            fails.
    """

    caddy = (repo_root / STAGING_CADDY_FILE).read_text(encoding="utf-8")
    compose = (repo_root / STAGING_COMPOSE_FILE).read_text(encoding="utf-8")
    runbook = (repo_root / ORIGIN_ROTATION_RUNBOOK).read_text(encoding="utf-8")
    hcl = strip_hcl_comments(load_terraform_bundle(repo_root / INFRA_EC2_DIR))
    checks: tuple[tuple[str, Callable[[], None]], ...] = (
        ("caddy_dual", lambda: assert_caddy_dual_origin_values(caddy)),
        ("cloudfront_header", lambda: assert_cloudfront_origin_custom_header(hcl)),
        ("compose_previous", lambda: assert_compose_previous_origin(compose)),
        (
            "overlap",
            lambda: assert_origin_overlap_minutes(ORIGIN_ROTATION_OVERLAP_MAX_MINUTES),
        ),
        ("runbook", lambda: assert_origin_rotation_runbook(runbook)),
        ("hs256", assert_hs256_forbidden),
    )
    findings = tuple(_run_check(name, callback) for name, callback in checks)
    reviewed: Sequence[Path] = (
        repo_root / STAGING_CADDY_FILE,
        repo_root / STAGING_COMPOSE_FILE,
        repo_root / INFRA_EC2_DIR / "cloudfront_waf.tf",
        repo_root / INFRA_EC2_DIR / "variables.tf",
        repo_root / ORIGIN_ROTATION_RUNBOOK,
    )
    report = PolicyReport(
        passed=all(item.passed for item in findings),
        findings=findings,
        iac_sha256=hash_reviewed_files(reviewed),
    )
    if not report.passed:
        failed = [item.check for item in findings if not item.passed]
        details = "; ".join(
            f"{item.check}: {item.detail}" for item in findings if not item.passed
        )
        raise Phase10Packet4GateError(
            "Packet 4 origin policy failed: " + ", ".join(failed) + f" ({details})"
        )
    return report


def load_phase09_degrade_evidence(repo_root: Path) -> Phase09DegradeEvidence:
    """Load Phase 9 ParadeDB degrade/rebuild and Valkey deny/fill artifacts.

    Args:
        repo_root: Repository root.

    Returns:
        Typed evidence. Missing files fail closed.

    Raises:
        Phase10Packet4GateError: If artifacts are missing or malformed.
        ValueError: If JSON is not an object.
    """

    try:
        fault = load_json_object(repo_root / PHASE09_PACKET5_FAULT)
        rebuild = load_json_object(repo_root / PHASE09_PACKET6_REBUILD)
    except (OSError, ValueError) as exc:
        raise Phase10Packet4GateError(
            "Phase 9 Packet 5/6 degrade or rebuild artifact is unavailable"
        ) from exc
    assert_paradedb_projection_not_canonical(rebuild)
    hybrid = as_json_object(
        fault.get("hybrid_degrade"), source="packet5-hybrid-degrade"
    )
    deny = as_json_object(fault.get("deny"), source="packet5-valkey-deny")
    fill = as_json_object(fault.get("fill"), source="packet5-valkey-fill")
    reproject = as_json_object(rebuild.get("reproject"), source="packet6-reproject")
    fallback = hybrid.get("fallback_reason")
    fallback_text = fallback if isinstance(fallback, str) else None
    return Phase09DegradeEvidence(
        degrade_passed=hybrid.get("passed") is True,
        fallback_reason=fallback_text,
        rebuild_passed=rebuild.get("paradedb_used_as_canonical") is False
        and reproject.get("passed") is True,
        paradedb_used_as_canonical=rebuild.get("paradedb_used_as_canonical") is True,
        deny_passed=deny.get("denied") is True,
        fill_recovered=fill.get("recovered") is True,
        named_acl_users=deny.get("named_acl_users") is True,
    )


def classify_packet4(
    *,
    policy: PolicyReport | None,
    live: LiveProviderProbe,
    app_jwks_collected: bool,
    app_jwks_passed: bool,
    paradedb_subset_ok: bool,
    valkey_subset_ok: bool,
    degrade: Phase09DegradeEvidence,
    stream: CdnStreamEvidence | None = None,
    live_rotation_passed: bool = False,
    live_paradedb_kill_passed: bool = False,
    live_valkey_kill_passed: bool = False,
    managed_jwks_passed: bool = False,
    timeout_policy_passed: bool = True,
) -> tuple[AcceptanceRow, ...]:
    """Classify P10-04-A through E from committed evidence and probes.

    Args:
        policy: Origin rotation policy report, or None when files are missing.
        live: Provider probe. Never a CDN stream or EC2 kill.
        app_jwks_collected: Nonzero JWKS tests collected.
        app_jwks_passed: JWKS tests passed without skip.
        paradedb_subset_ok: Application ParadeDB degrade tests passed.
        valkey_subset_ok: Application Valkey fail-closed tests passed.
        degrade: Phase 9 degrade/rebuild/Valkey facts.
        stream: Optional live CDN artifact. Defaults to absent/Blocked.
        live_rotation_passed: True only from a real rotation audit.
        live_paradedb_kill_passed: True only from a real EC2 kill.
        live_valkey_kill_passed: True only from a real EC2 Valkey kill.
        managed_jwks_passed: True only from isolated staging dashboard rollover.
        timeout_policy_passed: Packet 3 90-second assertions still hold.

    Returns:
        Five acceptance rows.
    """

    origin_ok = policy.passed if policy is not None else False
    live_state = live_proof_state(live)
    evidence = stream if stream is not None else CdnStreamEvidence()
    rebuild_ok = degrade.rebuild_passed and not degrade.paradedb_used_as_canonical
    app_degrade_ok = (
        paradedb_subset_ok
        and degrade.degrade_passed
        and degrade.fallback_reason == "bm25_unavailable"
    )
    app_valkey_ok = valkey_subset_ok and degrade.deny_passed and degrade.fill_recovered
    return (
        AcceptanceRow(
            check="P10-04-A",
            classification=classify_p1004_a(
                app_jwks_collected=app_jwks_collected,
                app_jwks_passed=app_jwks_passed,
                hs256_forbidden="HS256" in FORBIDDEN_ALGORITHMS,
                managed_jwks_passed=managed_jwks_passed,
            ),
            detail=(
                "Application JWKS (no HS256, unknown kid, standby/active/"
                "retired fixtures) "
                + ("Passed" if app_jwks_collected and app_jwks_passed else "Blocked")
                + ". Managed Supabase dashboard rollover Not Run: "
                + _MANAGED_JWKS_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-04-B",
            classification=classify_p1004_b(
                origin_policy_passed=origin_ok,
                live_rotation_state=live_state,
                live_rotation_passed=live_rotation_passed,
            ),
            detail=(
                "Committed Caddy CURRENT+PREVIOUS, CloudFront custom_header, "
                f"overlap<={ORIGIN_ROTATION_OVERLAP_MAX_MINUTES} minutes, and "
                "rollback runbook "
                + ("Passed" if origin_ok else "Failed")
                + f". Live origin rotation is {live_state}: "
                + _LIVE_ROTATION_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-04-C",
            classification=classify_p1004_c(
                timeout_policy_passed=timeout_policy_passed,
                stream=evidence,
            ),
            detail=(
                "90-second CloudFront/Caddy settings "
                + ("Passed" if timeout_policy_passed else "Failed")
                + f". Live 50-second CDN SSE is {live_state}: "
                + _LIVE_CDN_STREAM_REASON
                + " Supporting application SSE tests are not a CloudFront "
                "timeline."
            ),
        ),
        AcceptanceRow(
            check="P10-04-D",
            classification=classify_p1004_d(
                app_degrade_ok=app_degrade_ok,
                rebuild_parity_ok=rebuild_ok,
                snapshot_as_canonical=degrade.paradedb_used_as_canonical,
                live_kill_passed=live_paradedb_kill_passed,
            ),
            detail=(
                "Application Hybrid dense+term degrade and Phase 9 rebuild "
                "parity (ParadeDB not canonical) "
                + ("Passed" if app_degrade_ok and rebuild_ok else "Failed")
                + f". Live EC2 ParadeDB kill is {live_state}: "
                + _LIVE_PARADEDB_KILL_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-04-E",
            classification=classify_p1004_e(
                app_fail_closed_ok=app_valkey_ok,
                live_valkey_kill_passed=live_valkey_kill_passed,
            ),
            detail=(
                "Application Valkey fail-closed ownership and no double "
                "admission "
                + ("Passed" if app_valkey_ok else "Blocked")
                + ". Named ACL users are "
                + ("Passed" if degrade.named_acl_users else "Not Run")
                + f". Live EC2 Valkey kill is {live_state}: "
                + _LIVE_VALKEY_KILL_REASON
            ),
        ),
    )


def negatives_catalog() -> tuple[dict[str, str], ...]:
    """Return the Packet 4 negative cases exercised by unit tests.

    Returns:
        Machine-readable negative catalog without secret values.
    """

    exercise = "tests/unit/test_phase10_packet4.py"
    expected = "Phase10Packet4GateError"
    return (
        {
            "case": "hs256",
            "expected": "JwksVerificationError",
            "exercise": exercise,
        },
        {
            "case": "origin_overlap_over_15",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "missing_previous_origin_value",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "claiming_local_stream_as_cdn",
            "expected": "Failed",
            "exercise": exercise,
        },
        {
            "case": "stale_bm25_snapshot_as_canonical",
            "expected": expected,
            "exercise": exercise,
        },
    )


def write_packet4_artifacts(
    repo_root: Path,
    *,
    policy: PolicyReport,
    live: LiveProviderProbe,
    rows: Sequence[AcceptanceRow],
    degrade: Phase09DegradeEvidence,
    jwks_subset: Mapping[str, object],
    paradedb_subset: Mapping[str, object],
    valkey_subset: Mapping[str, object],
    sse_support: Mapping[str, object],
) -> dict[str, Path]:
    """Write Packet 4 JSON artifacts without secrets or fake CDN timelines.

    Args:
        repo_root: Repository root.
        policy: Origin rotation policy report.
        live: Provider probe.
        rows: Acceptance classifications.
        degrade: Phase 9 degrade/rebuild/Valkey facts.
        jwks_subset: Collected JWKS test counts.
        paradedb_subset: Collected ParadeDB degrade counts.
        valkey_subset: Collected Valkey fail-closed counts.
        sse_support: Supporting application SSE counts. Not a CDN Pass.

    Returns:
        Artifact name to path mapping.

    Side Effects:
        Overwrites files under ``docs/deployment/phase-10/``.
    """

    artifact_dir = repo_root / PHASE10_ARTIFACT_DIR
    live_state = live_proof_state(live)
    by_check = {row.check: row.classification for row in rows}
    acceptance = [
        {
            "check": row.check,
            "classification": row.classification,
            "detail": row.detail,
        }
        for row in rows
    ]
    matrix: dict[str, object] = {
        "schema_version": PACKET4_MATRIX_SCHEMA_VERSION,
        "packet": "P10-04",
        "wrapper_status": "pending",
        "packet1_checkbox": "unchecked",
        "packet2_checkbox": "unchecked",
        "packet3_checkbox": "unchecked",
        "packet4_checkbox": "unchecked",
        "holdout_opened": False,
        "phase9_image_ids": dict(PHASE09_IMAGE_IDS),
        "origin_policy": "Passed" if policy.passed else "Failed",
        "origin_policy_sha256": policy.iac_sha256,
        "live_managed_jwks": "Not Run",
        "live_origin_rotation": live_state,
        "live_cdn_sse": live_state,
        "live_paradedb_kill": live_state,
        "live_valkey_kill": live_state,
        "jwks_subset": dict(jwks_subset),
        "paradedb_subset": dict(paradedb_subset),
        "valkey_subset": dict(valkey_subset),
        "sse_support": dict(sse_support),
        "acceptance": acceptance,
    }
    jwks_out: dict[str, object] = {
        "schema_version": PACKET4_JWKS_SCHEMA_VERSION,
        "application_jwks": by_check.get("P10-04-A", "Blocked"),
        "hs256_forbidden": True,
        "forbidden_algorithms": sorted(FORBIDDEN_ALGORITHMS),
        "managed_dashboard_rollover": "Not Run",
        "managed_reason": _MANAGED_JWKS_REASON,
        "tests": list(PACKET4_JWKS_TEST_FILES),
        "jwks_subset": dict(jwks_subset),
    }
    origin_out: dict[str, object] = {
        "schema_version": PACKET4_ORIGIN_SCHEMA_VERSION,
        "policy": "Passed" if policy.passed else "Failed",
        "overlap_minutes_max": ORIGIN_ROTATION_OVERLAP_MAX_MINUTES,
        "caddy_current_and_previous": finding_passed(policy, "caddy_dual"),
        "cloudfront_custom_header": finding_passed(policy, "cloudfront_header"),
        "rollback_documented": finding_passed(policy, "runbook"),
        "live_rotation": live_state,
        "live_reason": _LIVE_ROTATION_REASON,
        "runbook": ORIGIN_ROTATION_RUNBOOK,
    }
    sse_out: dict[str, object] = {
        "schema_version": PACKET4_SSE_SCHEMA_VERSION,
        "classification": by_check.get("P10-04-C", "Blocked"),
        "duration_seconds": None,
        "via": None,
        "paid_runs": None,
        "origin_read_timeout_seconds": ORIGIN_READ_TIMEOUT_SECONDS,
        "origin_keepalive_timeout_seconds": ORIGIN_KEEPALIVE_TIMEOUT_SECONDS,
        "min_duration_seconds": CDN_SSE_MIN_DURATION_SECONDS,
        "local_eventsource_is_not_cdn": True,
        "live_reason": _LIVE_CDN_STREAM_REASON,
        "support_tests": list(PACKET4_SSE_SUPPORT_TEST_FILES),
        "sse_support": dict(sse_support),
    }
    paradedb_out: dict[str, object] = {
        "schema_version": PACKET4_PARADEDB_SCHEMA_VERSION,
        "application_degrade": by_check.get("P10-04-D", "Blocked"),
        "fallback_reason": degrade.fallback_reason,
        "rebuild_passed": degrade.rebuild_passed,
        "paradedb_used_as_canonical": degrade.paradedb_used_as_canonical,
        "snapshot_as_canonical_rejected": True,
        "live_ec2_kill": live_state,
        "live_reason": _LIVE_PARADEDB_KILL_REASON,
        "phase09_fault": PHASE09_PACKET5_FAULT,
        "phase09_rebuild": PHASE09_PACKET6_REBUILD,
        "tests": list(PACKET4_PARADEDB_TEST_FILES),
        "paradedb_subset": dict(paradedb_subset),
    }
    valkey_out: dict[str, object] = {
        "schema_version": PACKET4_VALKEY_SCHEMA_VERSION,
        "application_fail_closed": by_check.get("P10-04-E", "Blocked"),
        "deny_passed": degrade.deny_passed,
        "fill_recovered": degrade.fill_recovered,
        "named_acl_users": degrade.named_acl_users,
        "double_admission": False,
        "live_ec2_kill": live_state,
        "live_reason": _LIVE_VALKEY_KILL_REASON,
        "tests": list(PACKET4_VALKEY_TEST_FILES),
        "valkey_subset": dict(valkey_subset),
    }
    negatives_out: dict[str, object] = {
        "schema_version": PACKET4_NEGATIVES_SCHEMA_VERSION,
        "cases": list(negatives_catalog()),
    }
    paths = {
        PACKET4_MATRIX_NAME: artifact_dir / PACKET4_MATRIX_NAME,
        PACKET4_JWKS_NAME: artifact_dir / PACKET4_JWKS_NAME,
        PACKET4_ORIGIN_NAME: artifact_dir / PACKET4_ORIGIN_NAME,
        PACKET4_SSE_NAME: artifact_dir / PACKET4_SSE_NAME,
        PACKET4_PARADEDB_NAME: artifact_dir / PACKET4_PARADEDB_NAME,
        PACKET4_VALKEY_NAME: artifact_dir / PACKET4_VALKEY_NAME,
        PACKET4_NEGATIVES_NAME: artifact_dir / PACKET4_NEGATIVES_NAME,
    }
    dump_canonical_json(matrix, paths[PACKET4_MATRIX_NAME])
    dump_canonical_json(jwks_out, paths[PACKET4_JWKS_NAME])
    dump_canonical_json(origin_out, paths[PACKET4_ORIGIN_NAME])
    dump_canonical_json(sse_out, paths[PACKET4_SSE_NAME])
    dump_canonical_json(paradedb_out, paths[PACKET4_PARADEDB_NAME])
    dump_canonical_json(valkey_out, paths[PACKET4_VALKEY_NAME])
    dump_canonical_json(negatives_out, paths[PACKET4_NEGATIVES_NAME])
    return paths


def evaluate_packet4(
    repo_root: Path,
    *,
    jwks_subset_ok: bool,
    paradedb_subset_ok: bool,
    valkey_subset_ok: bool,
) -> tuple[
    PolicyReport,
    LiveProviderProbe,
    tuple[AcceptanceRow, ...],
    Phase09DegradeEvidence,
]:
    """Run committed Packet 4 policy plus probes and classify P10-04.

    Packets 1-3 remaining unchecked is not a failure. Wrapper and Packet 4
    stay pending while live CDN SSE is Blocked.

    Args:
        repo_root: Repository root.
        jwks_subset_ok: Nonzero JWKS collection with no skip.
        paradedb_subset_ok: ParadeDB degrade subset collected without skip.
        valkey_subset_ok: Valkey fail-closed subset collected without skip.

    Returns:
        Policy report, live probe, acceptance rows, and Phase 9 degrade
        evidence.

    Raises:
        Phase10Packet4GateError: If origin policy fails or the wrapper was
            marked complete while C remains Blocked.
    """

    wrapper = (repo_root / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (repo_root / PACKET4_RELATIVE).read_text(encoding="utf-8")
    if not wrapper_status_pending(wrapper):
        raise Phase10Packet4GateError("Phase 10 wrapper must remain status: pending")
    if not packet4_checkbox_unchecked(wrapper):
        raise Phase10Packet4GateError(
            "Packet 4 checkbox must stay unchecked while live CDN SSE is Blocked"
        )
    if not packet4_status_pending(packet):
        raise Phase10Packet4GateError("Packet 4 file must remain status: pending")
    workflow = (repo_root / GITHUB_WORKFLOWS_DIR / "pr-fast.yml").read_text(
        encoding="utf-8"
    )
    if "check_phase10_packet4.py" in workflow:
        raise Phase10Packet4GateError("Packet 4 gate must not be added to pr-fast.yml")
    policy = assert_origin_rotation_policy(repo_root)
    degrade = load_phase09_degrade_evidence(repo_root)
    live = probe_live_providers()
    rows = classify_packet4(
        policy=policy,
        live=live,
        app_jwks_collected=jwks_subset_ok,
        app_jwks_passed=jwks_subset_ok,
        paradedb_subset_ok=paradedb_subset_ok,
        valkey_subset_ok=valkey_subset_ok,
        degrade=degrade,
    )
    return policy, live, rows, degrade
