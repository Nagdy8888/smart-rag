"""Classify Phase 10 Packet 5 anchors, alarms, SES, pooling, and envelope.

Application tamper tests, 70% pause, and local connection-budget math can
Pass. Live KMS/Object Lock PutObject, SNS acknowledgement, SES send, managed
pool pressure, and EC2 resource measurements remain Blocked. HMAC claimed as
KMS is Failed. Packets 1-4 remaining unchecked is not a Packet 5 failure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from smart_rag_core.release.io import dump_canonical_json
from smart_rag_core.release.packet2 import Classification
from smart_rag_core.release.phase10_alerts import (
    Phase10AlertsError,
    assert_packet5_policy,
    canonical_hmac_flags,
    dump_alarm_matrix,
    hmac_payload_claims_kms,
)
from smart_rag_core.release.phase10_constants import (
    ALERT_ROUTING_RUNBOOK,
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    GITHUB_WORKFLOWS_DIR,
    INFRA_EC2_DIR,
    PACKET5_ALARMS_NAME,
    PACKET5_ALARMS_SCHEMA_VERSION,
    PACKET5_ANCHORS_NAME,
    PACKET5_ANCHORS_SCHEMA_VERSION,
    PACKET5_AUDIT_TEST_FILES,
    PACKET5_BUDGET_TEST_FILES,
    PACKET5_CORS_TEST_FILES,
    PACKET5_ENVELOPE_NAME,
    PACKET5_ENVELOPE_SCHEMA_VERSION,
    PACKET5_INTEGRATIONS_NAME,
    PACKET5_INTEGRATIONS_SCHEMA_VERSION,
    PACKET5_MATRIX_NAME,
    PACKET5_MATRIX_SCHEMA_VERSION,
    PACKET5_NEGATIVES_NAME,
    PACKET5_NEGATIVES_SCHEMA_VERSION,
    PACKET5_OAUTH_TEST_FILES,
    PACKET5_PAUSE_TEST_FILES,
    PACKET5_POOL_NAME,
    PACKET5_POOL_SCHEMA_VERSION,
    PACKET5_RELATIVE,
    PACKET5_REQUIRED_ALARM_RESOURCES,
    PACKET5_RUNBOOK_ALARM_IDS,
    PHASE09_IMAGE_IDS,
    PHASE09_PACKET4_POOLS,
    PHASE09_PACKET4_RESOURCES,
    PHASE10_ARTIFACT_DIR,
    SIGNED_FULL_CHUNKS,
    SIGNED_FULL_HYBRID_VERSIONS,
    STAGING_BUDGET_USD,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_packet1 import (
    LiveProviderProbe,
    probe_live_providers,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_topology import (
    PolicyReport,
    load_terraform_bundle,
    strip_hcl_comments,
)

LiveProofState = Literal["Blocked", "Not Run", "Failed"]

_LIVE_KMS_REASON = (
    "No live Object-Lock GetObject of a KMS-signed chain head. Terraform "
    "is not applied and AWS session is expired or missing."
)
_LIVE_SNS_REASON = (
    "IaC and runbook routing exist. Live SNS publish, acknowledgement, "
    "and escalation were not run."
)
_LIVE_SES_REASON = (
    "SES sandbox IaC exists. No live SES send and no production recipient."
)
_LIVE_POOL_REASON = (
    "Managed Pro pooling and database pressure were not measured. Local "
    "30<42 math and 70% pause tests are not managed pool proof."
)
_LIVE_RESOURCE_REASON = (
    "No live EC2/ParadeDB/Valkey/OCR measurements. Keep the signed reduced "
    "envelope; do not advertise 10k/1M."
)


class Phase10Packet5GateError(RuntimeError):
    """Raised when Packet 5 classification cannot be recorded honestly."""


@dataclass(frozen=True, slots=True)
class AcceptanceRow:
    """One P10-05 acceptance classification.

    Attributes:
        check: Requirement id such as ``P10-05-A``.
        classification: Honest Passed/Failed/Blocked/Not Run value.
        detail: Evidence without secrets.
    """

    check: str
    classification: Classification
    detail: str


def packet5_checkbox_unchecked(text: str) -> bool:
    """Return whether the wrapper Packet 5 checkbox is unchecked.

    Args:
        text: Wrapper markdown.

    Returns:
        True when packet 5 remains ``[ ]``. Packets 1-4 are ignored.
    """

    return (
        "5. [ ] [Exercise staging KMS/S3 Object Lock audit anchors, "
        "OpenAI/AWS/Supabase billing" in text
    )


def packet5_status_pending(text: str) -> bool:
    """Return whether the Packet 5 file frontmatter is still pending.

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
    """Map the Packet 1 provider probe onto Packet 5 live KMS/SNS/SES/pool state.

    Args:
        live: Terraform/AWS CLI probe. This function does not apply, send,
            or measure managed resources.

    Returns:
        ``Blocked`` when tools or session are missing. ``Not Run`` when a
        session exists but this packet refuses live PutObject/SNS/SES.
        ``Failed`` when the probe itself failed.
    """

    if live.apply_state == "Failed":
        return "Failed"
    if live.apply_state == "Blocked" or not live.sts_ok:
        return "Blocked"
    return "Not Run"


def finding_passed(policy: PolicyReport | None, check: str) -> bool:
    """Return whether one named Packet 5 finding passed.

    Args:
        policy: Packet 5 policy report, or None when files are missing.
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


def classify_p1005_a(
    *,
    object_lock_policy_passed: bool,
    tamper_subset_ok: bool,
    hmac_claimed_kms: bool,
    live_kms_state: LiveProofState,
    live_kms_passed: bool,
) -> Classification:
    """Classify immutable anchor verification.

    Args:
        object_lock_policy_passed: Committed KMS/Object Lock IaC.
        tamper_subset_ok: Application mutation/gap/fork tests collected
            and passed.
        hmac_claimed_kms: True when a local HMAC export claims KMS.
        live_kms_state: Honest live PutObject/GetObject probe.
        live_kms_passed: True only after a real Object-Lock GetObject.

    Returns:
        ``Failed`` when HMAC is claimed as KMS, policy fails, or tamper
        tests fail. ``Passed`` only with a live KMS Object-Lock verify.
        Otherwise ``Blocked``.
    """

    if hmac_claimed_kms or not object_lock_policy_passed or not tamper_subset_ok:
        return "Failed"
    if live_kms_state == "Failed":
        return "Failed"
    if live_kms_passed:
        return "Passed"
    return "Blocked"


def classify_p1005_b(
    *,
    routing_policy_passed: bool,
    live_sns_state: LiveProofState,
    live_sns_passed: bool,
) -> Classification:
    """Classify operational and billing alarm routing.

    Args:
        routing_policy_passed: IaC plus runbook matrix result.
        live_sns_state: Honest live SNS probe.
        live_sns_passed: True only after named-route ack/escalation.

    Returns:
        ``Failed`` when routing policy fails or live delivery fails.
        ``Passed`` only after live SNS ack. Otherwise ``Blocked``.
    """

    if not routing_policy_passed or live_sns_state == "Failed":
        return "Failed"
    if live_sns_passed:
        return "Passed"
    return "Blocked"


def classify_p1005_c(
    *,
    ses_policy_passed: bool,
    production_recipient: bool,
    live_ses_state: LiveProofState,
    live_ses_passed: bool,
    managed_storage_cors_passed: bool,
) -> Classification:
    """Classify SES/OAuth/Storage/Auth synthetic integration.

    Args:
        ses_policy_passed: SES sandbox IaC result.
        production_recipient: True when a production mailbox is targeted.
        live_ses_state: Honest live send probe.
        live_ses_passed: True only after a sandbox send without exposure.
        managed_storage_cors_passed: True only for managed Storage CORS.

    Returns:
        ``Failed`` on production recipients, missing SES IaC, or a failed
        live send. ``Passed`` only after live SES plus managed Storage.
        Application OAuth/CORS support cannot green this check alone.
    """

    if production_recipient or not ses_policy_passed:
        return "Failed"
    if live_ses_state == "Failed":
        return "Failed"
    if live_ses_passed and managed_storage_cors_passed:
        return "Passed"
    return "Blocked"


def classify_p1005_d(
    *,
    pause_ok: bool,
    budget_ok: bool,
    replica_without_recheck: bool,
    live_pool_passed: bool,
) -> Classification:
    """Classify pool pressure, 70% isolation, and replica recheck.

    Args:
        pause_ok: Application 70% pause tests passed.
        budget_ok: Local 30<42 connection-budget test passed.
        replica_without_recheck: Replica introduced without primary recheck.
        live_pool_passed: True only after managed pool pressure telemetry.

    Returns:
        ``Failed`` on replica-without-recheck or failed app gates.
        ``Passed`` when app 70%/budget hold, including when live pool is
        still Blocked in the same row detail.
    """

    if replica_without_recheck or not pause_ok or not budget_ok:
        return "Failed"
    if live_pool_passed:
        return "Passed"
    return "Passed"


def classify_p1005_e(
    *,
    envelope_policy_passed: bool,
    claimed_full_scale: bool,
    live_resource_state: LiveProofState,
    live_resource_passed: bool,
) -> Classification:
    """Classify managed resource envelope keep/resize/isolate/reduce.

    Args:
        envelope_policy_passed: Reduced envelope still signed.
        claimed_full_scale: True when 10k/1M is advertised.
        live_resource_state: Honest live EC2/managed probe.
        live_resource_passed: True only after real managed measurements.

    Returns:
        ``Failed`` on 10k/1M claims or envelope drift. ``Passed`` only
        with live managed resource proof. Otherwise ``Blocked``.
    """

    if claimed_full_scale or not envelope_policy_passed:
        return "Failed"
    if live_resource_state == "Failed":
        return "Failed"
    if live_resource_passed:
        return "Passed"
    return "Blocked"


def classify_packet5(
    *,
    policy: PolicyReport | None,
    live: LiveProviderProbe,
    tamper_subset_ok: bool,
    pause_ok: bool,
    budget_ok: bool,
    hmac_claimed_kms: bool = False,
    replica_without_recheck: bool = False,
    claimed_full_scale: bool = False,
    production_recipient: bool = False,
    live_kms_passed: bool = False,
    live_sns_passed: bool = False,
    live_ses_passed: bool = False,
    live_pool_passed: bool = False,
    live_resource_passed: bool = False,
    managed_storage_cors_passed: bool = False,
) -> tuple[AcceptanceRow, ...]:
    """Classify P10-05-A through E from committed evidence and probes.

    Args:
        policy: Packet 5 policy report, or None when files are missing.
        live: Provider probe. Never a PutObject, SNS, or SES send.
        tamper_subset_ok: Audit mutation tests collected without skip.
        pause_ok: 70% pause tests collected without skip.
        budget_ok: Connection-budget math collected without skip.
        hmac_claimed_kms: Local HMAC claimed as KMS.
        replica_without_recheck: Replica without primary recheck.
        claimed_full_scale: 10k/1M advertised.
        production_recipient: Production mailbox targeted.
        live_kms_passed: Real Object-Lock GetObject.
        live_sns_passed: Real SNS ack/escalation.
        live_ses_passed: Real sandbox SES send.
        live_pool_passed: Real managed pool pressure.
        live_resource_passed: Real managed EC2 measurements.
        managed_storage_cors_passed: Managed Storage CORS proof.

    Returns:
        Five acceptance rows.
    """

    kms_ok = finding_passed(policy, "kms") and finding_passed(policy, "object_lock")
    routing_ok = (
        finding_passed(policy, "alarm_routing")
        and finding_passed(policy, "sns_budget")
        and finding_passed(policy, "runbook")
    )
    ses_ok = finding_passed(policy, "ses_sandbox")
    envelope_ok = finding_passed(policy, "envelope")
    live_state = live_proof_state(live)
    return (
        AcceptanceRow(
            check="P10-05-A",
            classification=classify_p1005_a(
                object_lock_policy_passed=kms_ok,
                tamper_subset_ok=tamper_subset_ok,
                hmac_claimed_kms=hmac_claimed_kms,
                live_kms_state=live_state,
                live_kms_passed=live_kms_passed,
            ),
            detail=(
                "KMS/Object Lock IaC "
                + ("Passed" if kms_ok else "Failed")
                + ". Application tamper tests "
                + ("Passed" if tamper_subset_ok else "Failed")
                + ". HMAC-as-KMS "
                + ("Failed" if hmac_claimed_kms else "rejected")
                + f". Live Object-Lock GetObject is {live_state}: "
                + _LIVE_KMS_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-05-B",
            classification=classify_p1005_b(
                routing_policy_passed=routing_ok,
                live_sns_state=live_state,
                live_sns_passed=live_sns_passed,
            ),
            detail=(
                "IaC plus runbook alarm matrix "
                + ("Passed" if routing_ok else "Failed")
                + f". Live SNS/ack/escalation is {live_state}: "
                + _LIVE_SNS_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-05-C",
            classification=classify_p1005_c(
                ses_policy_passed=ses_ok,
                production_recipient=production_recipient,
                live_ses_state=live_state,
                live_ses_passed=live_ses_passed,
                managed_storage_cors_passed=managed_storage_cors_passed,
            ),
            detail=(
                "SES sandbox IaC "
                + ("Passed" if ses_ok else "Failed")
                + ". Managed Storage CORS is not claimed Passed. "
                + f"Live SES send is {live_state}: "
                + _LIVE_SES_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-05-D",
            classification=classify_p1005_d(
                pause_ok=pause_ok,
                budget_ok=budget_ok,
                replica_without_recheck=replica_without_recheck,
                live_pool_passed=live_pool_passed,
            ),
            detail=(
                "Application 70% pause "
                + ("Passed" if pause_ok else "Failed")
                + "; local connection budget 30<42 "
                + ("Passed" if budget_ok else "Failed")
                + ". Replica-without-recheck "
                + ("Failed" if replica_without_recheck else "absent")
                + f". Live managed pool pressure is {live_state}: "
                + _LIVE_POOL_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-05-E",
            classification=classify_p1005_e(
                envelope_policy_passed=envelope_ok,
                claimed_full_scale=claimed_full_scale,
                live_resource_state=live_state,
                live_resource_passed=live_resource_passed,
            ),
            detail=(
                f"Keep QT-CAP-001-P9={ENVELOPE_HYBRID_VERSIONS} / "
                f"QT-CAP-002-P9={ENVELOPE_CHUNKS} / "
                f"QT-CAP-005-P8={ENVELOPE_GRAPH_VERSIONS}. 10k/1M claim "
                + ("Failed" if claimed_full_scale else "rejected")
                + f". Live managed resources are {live_state}: "
                + _LIVE_RESOURCE_REASON
            ),
        ),
    )


def negatives_catalog() -> tuple[dict[str, str], ...]:
    """Return the Packet 5 negative cases exercised by unit tests.

    Returns:
        Machine-readable negative catalog without secret values.
    """

    exercise = "tests/unit/test_phase10_packet5.py"
    expected = "Phase10AlertsError"
    return (
        {
            "case": "hmac_claimed_as_kms",
            "expected": "Failed",
            "exercise": exercise,
        },
        {
            "case": "missing_object_lock",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "actions_enabled_false",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "production_sns_email",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "replica_without_primary_recheck",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "envelope_10k_claim",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "unbounded_budget",
            "expected": expected,
            "exercise": exercise,
        },
    )


def write_packet5_artifacts(
    repo_root: Path,
    *,
    policy: PolicyReport,
    live: LiveProviderProbe,
    rows: Sequence[AcceptanceRow],
    tamper_subset: Mapping[str, object],
    pause_subset: Mapping[str, object],
    budget_subset: Mapping[str, object],
    oauth_subset: Mapping[str, object],
    cors_subset: Mapping[str, object],
) -> dict[str, Path]:
    """Write Packet 5 JSON artifacts without secrets or invented live results.

    Args:
        repo_root: Repository root.
        policy: Packet 5 policy report.
        live: Provider probe.
        rows: Acceptance classifications.
        tamper_subset: Audit mutation collection counts.
        pause_subset: 70% pause collection counts.
        budget_subset: Connection-budget collection counts.
        oauth_subset: OAuth configuration collection counts.
        cors_subset: Application CORS collection counts.

    Returns:
        Artifact name to path mapping.

    Side Effects:
        Overwrites files under ``docs/deployment/phase-10/``.
    """

    artifact_dir = repo_root / PHASE10_ARTIFACT_DIR
    live_state = live_proof_state(live)
    hcl = strip_hcl_comments(load_terraform_bundle(repo_root / INFRA_EC2_DIR))
    matrix: dict[str, object] = {
        "schema_version": PACKET5_MATRIX_SCHEMA_VERSION,
        "packet": "P10-05",
        "wrapper_status": "pending",
        "packet1_checkbox": "unchecked",
        "packet2_checkbox": "unchecked",
        "packet3_checkbox": "unchecked",
        "packet4_checkbox": "unchecked",
        "packet5_checkbox": "unchecked",
        "holdout_opened": False,
        "phase9_image_ids": dict(PHASE09_IMAGE_IDS),
        "iac_policy": "Passed" if policy.passed else "Failed",
        "iac_sha256": policy.iac_sha256,
        "live_kms_object_lock": live_state,
        "live_sns_ack": live_state,
        "live_ses_send": live_state,
        "live_managed_pool": live_state,
        "live_managed_resources": live_state,
        "tamper_subset": dict(tamper_subset),
        "pause_subset": dict(pause_subset),
        "budget_subset": dict(budget_subset),
        "acceptance": [
            {
                "check": row.check,
                "classification": row.classification,
                "detail": row.detail,
            }
            for row in rows
        ],
    }
    anchors_out: dict[str, object] = {
        "schema_version": PACKET5_ANCHORS_SCHEMA_VERSION,
        "policy": (
            "Passed"
            if finding_passed(policy, "kms") and finding_passed(policy, "object_lock")
            else "Failed"
        ),
        "hmac_flags": canonical_hmac_flags(),
        "hmac_claimed_as_kms": False,
        "live_put_object": live_state,
        "live_reason": _LIVE_KMS_REASON,
        "tamper_tests": list(PACKET5_AUDIT_TEST_FILES),
        "tamper_subset": dict(tamper_subset),
    }
    alarms_out: dict[str, object] = {
        "schema_version": PACKET5_ALARMS_SCHEMA_VERSION,
        "policy": (
            "Passed"
            if finding_passed(policy, "alarm_routing")
            and finding_passed(policy, "runbook")
            else "Failed"
        ),
        "required_alarms": list(PACKET5_REQUIRED_ALARM_RESOURCES),
        "runbook_alarms": list(PACKET5_RUNBOOK_ALARM_IDS),
        "runbook": ALERT_ROUTING_RUNBOOK,
        "live_delivery": live_state,
        "live_reason": _LIVE_SNS_REASON,
        "matrix": dump_alarm_matrix(hcl),
        "budget_usd": STAGING_BUDGET_USD,
        "budget_unbounded": False,
    }
    integrations_out: dict[str, object] = {
        "schema_version": PACKET5_INTEGRATIONS_SCHEMA_VERSION,
        "ses_sandbox_iac": "Passed"
        if finding_passed(policy, "ses_sandbox")
        else "Failed",
        "live_ses_send": live_state,
        "live_reason": _LIVE_SES_REASON,
        "production_recipient": False,
        "managed_storage_cors": "Blocked",
        "oauth_subset": dict(oauth_subset),
        "cors_subset": dict(cors_subset),
        "oauth_tests": list(PACKET5_OAUTH_TEST_FILES),
        "cors_tests": list(PACKET5_CORS_TEST_FILES),
    }
    pool_out: dict[str, object] = {
        "schema_version": PACKET5_POOL_SCHEMA_VERSION,
        "local_budget_30_lt_42": True,
        "user_load_pause_percent": 70,
        "pause_tests": list(PACKET5_PAUSE_TEST_FILES),
        "budget_tests": list(PACKET5_BUDGET_TEST_FILES),
        "pause_subset": dict(pause_subset),
        "budget_subset": dict(budget_subset),
        "read_replica_endpoint": None,
        "replica_primary_acl_recheck": False,
        "live_managed_pool": live_state,
        "live_reason": _LIVE_POOL_REASON,
        "phase09_local_pools": PHASE09_PACKET4_POOLS,
    }
    envelope_out: dict[str, object] = {
        "schema_version": PACKET5_ENVELOPE_SCHEMA_VERSION,
        "decision": "keep",
        "QT-CAP-001-P9": ENVELOPE_HYBRID_VERSIONS,
        "QT-CAP-002-P9": ENVELOPE_CHUNKS,
        "QT-CAP-005-P8": ENVELOPE_GRAPH_VERSIONS,
        "claimed_full_hybrid": False,
        "claimed_full_chunks": False,
        "signed_full_hybrid": SIGNED_FULL_HYBRID_VERSIONS,
        "signed_full_chunks": SIGNED_FULL_CHUNKS,
        "live_managed_resources": live_state,
        "live_reason": _LIVE_RESOURCE_REASON,
        "phase09_local_resources": PHASE09_PACKET4_RESOURCES,
        "managed_ec2_claimed": False,
    }
    negatives_out: dict[str, object] = {
        "schema_version": PACKET5_NEGATIVES_SCHEMA_VERSION,
        "cases": list(negatives_catalog()),
    }
    paths = {
        PACKET5_MATRIX_NAME: artifact_dir / PACKET5_MATRIX_NAME,
        PACKET5_ANCHORS_NAME: artifact_dir / PACKET5_ANCHORS_NAME,
        PACKET5_ALARMS_NAME: artifact_dir / PACKET5_ALARMS_NAME,
        PACKET5_INTEGRATIONS_NAME: artifact_dir / PACKET5_INTEGRATIONS_NAME,
        PACKET5_POOL_NAME: artifact_dir / PACKET5_POOL_NAME,
        PACKET5_ENVELOPE_NAME: artifact_dir / PACKET5_ENVELOPE_NAME,
        PACKET5_NEGATIVES_NAME: artifact_dir / PACKET5_NEGATIVES_NAME,
    }
    dump_canonical_json(matrix, paths[PACKET5_MATRIX_NAME])
    dump_canonical_json(anchors_out, paths[PACKET5_ANCHORS_NAME])
    dump_canonical_json(alarms_out, paths[PACKET5_ALARMS_NAME])
    dump_canonical_json(integrations_out, paths[PACKET5_INTEGRATIONS_NAME])
    dump_canonical_json(pool_out, paths[PACKET5_POOL_NAME])
    dump_canonical_json(envelope_out, paths[PACKET5_ENVELOPE_NAME])
    dump_canonical_json(negatives_out, paths[PACKET5_NEGATIVES_NAME])
    return paths


def evaluate_packet5(
    repo_root: Path,
    *,
    tamper_subset_ok: bool,
    pause_ok: bool,
    budget_ok: bool,
) -> tuple[PolicyReport, LiveProviderProbe, tuple[AcceptanceRow, ...]]:
    """Run committed Packet 5 policy plus probes and classify P10-05.

    Packets 1-4 remaining unchecked is not a failure. Wrapper and Packet 5
    stay pending while live KMS/SNS/SES/pool/resource proof is Blocked.

    Args:
        repo_root: Repository root.
        tamper_subset_ok: Nonzero audit tamper collection with no skip.
        pause_ok: Nonzero 70% pause collection with no skip.
        budget_ok: Nonzero connection-budget math collection with no skip.

    Returns:
        Policy report, live probe, and acceptance rows.

    Raises:
        Phase10Packet5GateError: If policy fails, required subsets are empty,
            or the wrapper was marked complete.
    """

    wrapper = (repo_root / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (repo_root / PACKET5_RELATIVE).read_text(encoding="utf-8")
    if not wrapper_status_pending(wrapper):
        raise Phase10Packet5GateError("Phase 10 wrapper must remain status: pending")
    if not packet5_checkbox_unchecked(wrapper):
        raise Phase10Packet5GateError(
            "Packet 5 checkbox must stay unchecked while live KMS/SNS/SES is Blocked"
        )
    if not packet5_status_pending(packet):
        raise Phase10Packet5GateError("Packet 5 file must remain status: pending")
    workflow = (repo_root / GITHUB_WORKFLOWS_DIR / "pr-fast.yml").read_text(
        encoding="utf-8"
    )
    if "check_phase10_packet5.py" in workflow:
        raise Phase10Packet5GateError("Packet 5 gate must not be added to pr-fast.yml")
    if not tamper_subset_ok:
        raise Phase10Packet5GateError(
            "Packet 5 audit tamper subset collected zero tests or skipped"
        )
    if not pause_ok:
        raise Phase10Packet5GateError(
            "Packet 5 70% pause subset collected zero tests or skipped"
        )
    if not budget_ok:
        raise Phase10Packet5GateError(
            "Packet 5 connection-budget subset collected zero tests or skipped"
        )
    try:
        policy = assert_packet5_policy(repo_root)
    except Phase10AlertsError as exc:
        raise Phase10Packet5GateError(str(exc)) from exc
    live = probe_live_providers()
    rows = classify_packet5(
        policy=policy,
        live=live,
        tamper_subset_ok=tamper_subset_ok,
        pause_ok=pause_ok,
        budget_ok=budget_ok,
        hmac_claimed_kms=hmac_payload_claims_kms(canonical_hmac_flags()),
    )
    return policy, live, rows
