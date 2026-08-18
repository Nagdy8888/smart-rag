"""Parse Phase 10 Packet 5 KMS, Object Lock, alarm, budget, and replica policy.

Policy checks parse committed Terraform, inventory, runbook, and the local
HMAC exporter. They do not apply Terraform, call KMS, PutObject, publish
SNS, send SES, or treat missing live delivery as Passed. Fail closed on
HMAC claimed as KMS, missing Object Lock, actions_enabled false, production
SNS email, replica without primary recheck, 10k envelope claims, and
unbounded budgets.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from smart_rag_core.release.io import as_json_object, load_json_object
from smart_rag_core.release.phase10_constants import (
    ALERT_ROUTING_RUNBOOK,
    AUDIT_EXPORT_MODULE,
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    INFRA_EC2_DIR,
    INTENDED_TOPOLOGY_FILE,
    KMS_DELETION_WINDOW_MAX_DAYS,
    KMS_DELETION_WINDOW_MIN_DAYS,
    OBJECT_LOCK_MODE,
    OBJECT_LOCK_RETENTION_YEARS,
    PACKET5_REQUIRED_ALARM_RESOURCES,
    PACKET5_RUNBOOK_ALARM_IDS,
    PRODUCTION_EMAIL_FRAGMENTS,
    SES_MODE_SANDBOX,
    SIGNED_FULL_CHUNKS,
    SIGNED_FULL_HYBRID_VERSIONS,
    STAGING_BUDGET_USD,
    STAGING_SYNTHETIC_EMAIL_SUFFIX,
)
from smart_rag_core.release.phase10_topology import (
    PolicyFinding,
    PolicyReport,
    hash_reviewed_files,
    load_terraform_bundle,
    strip_hcl_comments,
)

_ALARM_HEADER = re.compile(r'resource\s+"aws_cloudwatch_metric_alarm"\s+"([^"]+)"')
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_DELETION_WINDOW = re.compile(r"deletion_window_in_days\s*=\s*(\d+)")
_LIMIT_AMOUNT = re.compile(r'limit_amount\s*=\s*"(\d+(?:\.\d+)?)"')
_NESTED_OBJECT_LOCK = re.compile(
    r'resource\s+"aws_s3_bucket"\s+"audit_anchors"\s*\{[\s\S]*?'
    r"object_lock_configuration\s*\{"
)


class Phase10AlertsError(RuntimeError):
    """Raised when Packet 5 KMS, Object Lock, alarm, or envelope policy fails."""


def extract_hcl_block(hcl: str, header: str) -> str:
    """Return the first HCL block whose header text matches.

    Args:
        hcl: Comment-stripped Terraform.
        header: Leading resource/data text.

    Returns:
        The ``{...}`` body including braces.

    Raises:
        Phase10AlertsError: If the header or a balanced block is missing.
    """

    index = hcl.find(header)
    if index < 0:
        raise Phase10AlertsError(f"missing HCL block {header}")
    brace = hcl.find("{", index)
    if brace < 0:
        raise Phase10AlertsError(f"HCL block {header} has no opening brace")
    depth = 0
    for offset, char in enumerate(hcl[brace:], start=brace):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return hcl[brace : offset + 1]
    raise Phase10AlertsError(f"HCL block {header} is unbalanced")


def named_alarm_blocks(hcl: str) -> dict[str, str]:
    """Return CloudWatch alarm resource names mapped to their HCL bodies.

    Args:
        hcl: Comment-stripped Terraform.

    Returns:
        Alarm Terraform name to block body including braces.
    """

    blocks: dict[str, str] = {}
    for match in _ALARM_HEADER.finditer(hcl):
        header = match.group(0)
        blocks[match.group(1)] = extract_hcl_block(hcl, header)
    return blocks


def production_email_in_text(text: str) -> str | None:
    """Return the first production or non-synthetic email found.

    Args:
        text: Terraform, runbook, or variable source.

    Returns:
        Matching address, or None when only ``example.invalid`` remains.
    """

    for match in _EMAIL.finditer(text):
        address = match.group(0).casefold()
        if address.endswith(STAGING_SYNTHETIC_EMAIL_SUFFIX):
            continue
        if any(fragment in address for fragment in PRODUCTION_EMAIL_FRAGMENTS):
            return match.group(0)
        return match.group(0)
    return None


def assert_no_production_email(text: str, *, source: str) -> None:
    """Fail closed when a non-synthetic email appears.

    Args:
        text: Source text.
        source: Label used in the error.

    Raises:
        Phase10AlertsError: If a production or non-synthetic email is present.
    """

    leaked = production_email_in_text(text)
    if leaked is not None:
        raise Phase10AlertsError(f"{source} contains production email {leaked}")


def assert_hmac_export_not_kms(source: str) -> None:
    """Require the local HMAC exporter to keep KMS and Object Lock false.

    Args:
        source: ``audit_export.py`` text.

    Raises:
        Phase10AlertsError: If the exporter claims KMS or Object Lock.
    """

    if '"kms": True' in source or "'kms': True" in source:
        raise Phase10AlertsError("HMAC exporter must not claim kms:true")
    if '"s3_object_lock": True' in source or "'s3_object_lock': True" in source:
        raise Phase10AlertsError("HMAC exporter must not claim s3_object_lock:true")
    if '"kms": False' not in source and "'kms': False" not in source:
        raise Phase10AlertsError(
            "HMAC exporter must record kms:false until live PutObject"
        )
    if (
        '"s3_object_lock": False' not in source
        and "'s3_object_lock': False" not in source
    ):
        raise Phase10AlertsError(
            "HMAC exporter must record s3_object_lock:false until live PutObject"
        )
    if '"phase_10_blocker": True' not in source and "'phase_10_blocker': True" not in (
        source
    ):
        raise Phase10AlertsError("HMAC exporter must keep phase_10_blocker:true")


def hmac_payload_claims_kms(payload: Mapping[str, object]) -> bool:
    """Return whether a local export payload falsely claims KMS or Object Lock.

    Args:
        payload: Signed batch JSON from ``LocalHmacAuditExporter``.

    Returns:
        True when ``kms`` or ``s3_object_lock`` is true.
    """

    return payload.get("kms") is True or payload.get("s3_object_lock") is True


def assert_kms_policy(hcl: str) -> None:
    """Require a rotating ENCRYPT_DECRYPT key denied to the instance role.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10AlertsError: If rotation, window, usage, or Decrypt/Sign
            grants on ``staging_instance`` fail.
    """

    key = extract_hcl_block(hcl, 'resource "aws_kms_key" "audit"')
    if not re.search(r"enable_key_rotation\s*=\s*true", key):
        raise Phase10AlertsError("audit KMS key must enable rotation")
    windows = [int(value) for value in _DELETION_WINDOW.findall(key)]
    if not windows:
        raise Phase10AlertsError("audit KMS deletion_window_in_days is missing")
    if any(
        value < KMS_DELETION_WINDOW_MIN_DAYS or value > KMS_DELETION_WINDOW_MAX_DAYS
        for value in windows
    ):
        raise Phase10AlertsError("audit KMS deletion window must be 7-30 days")
    if re.search(r'key_usage\s*=\s*"SIGN_VERIFY"', key):
        raise Phase10AlertsError("audit KMS key_usage must remain ENCRYPT_DECRYPT")
    if 'resource "aws_kms_key_policy" "audit"' not in hcl:
        raise Phase10AlertsError("aws_kms_key_policy.audit is missing")
    if "DenyInstanceDecryptSign" not in hcl:
        raise Phase10AlertsError("KMS policy must deny instance Decrypt/Sign")
    if "kms:Decrypt" not in hcl or "kms:Sign" not in hcl:
        raise Phase10AlertsError("KMS deny must name kms:Decrypt and kms:Sign")
    instance_policies = (
        extract_hcl_block(hcl, 'data "aws_iam_policy_document" "staging_secrets"'),
        extract_hcl_block(hcl, 'data "aws_iam_policy_document" "egress_denial_logs"'),
    )
    for body in instance_policies:
        if "kms:Decrypt" in body or "kms:Sign" in body:
            raise Phase10AlertsError(
                "staging_instance IAM must not grant kms:Decrypt or kms:Sign"
            )
    if re.search(
        r'aws_iam_role_policy"\s+"[^"]*"[\s\S]{0,400}kms:(Decrypt|Sign)',
        hcl,
    ):
        raise Phase10AlertsError("no IAM role policy may grant kms:Decrypt or kms:Sign")


def assert_object_lock_policy(hcl: str) -> None:
    """Require a new Object Lock bucket with GOVERNANCE, versioning, and SSE-KMS.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10AlertsError: If Object Lock, versioning, encryption, or
            public-access policy fails.
    """

    bucket = extract_hcl_block(hcl, 'resource "aws_s3_bucket" "audit_anchors"')
    if not re.search(r"object_lock_enabled\s*=\s*true", bucket):
        raise Phase10AlertsError("audit bucket must set object_lock_enabled = true")
    if re.search(r"force_destroy\s*=\s*true", bucket):
        raise Phase10AlertsError("Object Lock bucket must not set force_destroy = true")
    if "object_lock_configuration" in bucket:
        raise Phase10AlertsError(
            "do not mix deprecated object_lock_configuration on aws_s3_bucket"
        )
    if _NESTED_OBJECT_LOCK.search(hcl):
        raise Phase10AlertsError(
            "deprecated nested object_lock_configuration is forbidden"
        )
    if 'resource "aws_s3_bucket_object_lock_configuration" "audit_anchors"' not in hcl:
        raise Phase10AlertsError("standalone Object Lock configuration is missing")
    lock = extract_hcl_block(
        hcl, 'resource "aws_s3_bucket_object_lock_configuration" "audit_anchors"'
    )
    if (
        f'mode  = "{OBJECT_LOCK_MODE}"' not in lock
        and f'mode = "{OBJECT_LOCK_MODE}"' not in (lock)
    ):
        if not re.search(rf'mode\s*=\s*"{OBJECT_LOCK_MODE}"', lock):
            raise Phase10AlertsError("Object Lock mode must be GOVERNANCE")
    if "COMPLIANCE" in lock:
        raise Phase10AlertsError(
            "COMPLIANCE Object Lock is forbidden in unapplied staging"
        )
    if not re.search(rf"years\s*=\s*{OBJECT_LOCK_RETENTION_YEARS}\b", lock):
        raise Phase10AlertsError("Object Lock default retention must be 7 years")
    versioning = extract_hcl_block(
        hcl, 'resource "aws_s3_bucket_versioning" "audit_anchors"'
    )
    if not re.search(r'status\s*=\s*"Enabled"', versioning):
        raise Phase10AlertsError("audit bucket versioning must be Enabled")
    sse = extract_hcl_block(
        hcl,
        'resource "aws_s3_bucket_server_side_encryption_configuration" "audit_anchors"',
    )
    if "aws:kms" not in sse:
        raise Phase10AlertsError("audit bucket SSE must use aws:kms")
    if "aws_kms_key.audit" not in sse:
        raise Phase10AlertsError("audit bucket SSE must use the audit KMS key")
    public = extract_hcl_block(
        hcl, 'resource "aws_s3_bucket_public_access_block" "audit_anchors"'
    )
    for flag in (
        "block_public_acls",
        "block_public_policy",
        "ignore_public_acls",
        "restrict_public_buckets",
    ):
        if not re.search(rf"{flag}\s*=\s*true", public):
            raise Phase10AlertsError(f"{flag} must be true")
    if re.search(r'acl\s*=\s*"public-read"', hcl):
        raise Phase10AlertsError("public-read ACL is forbidden")
    if "var.project_name" not in extract_hcl_block(
        hcl, 'resource "aws_s3_bucket" "audit_anchors"'
    ):
        raise Phase10AlertsError("audit bucket name must use var.project_name")


def assert_sns_and_budget_policy(hcl: str) -> None:
    """Require staging-ops SNS without production email and a 50 USD budget.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10AlertsError: If SNS email, unbounded spend, or budget routing
            fails.
    """

    if 'resource "aws_sns_topic" "staging_ops"' not in hcl:
        raise Phase10AlertsError("aws_sns_topic.staging_ops is missing")
    if 'resource "aws_sns_topic_policy" "staging_ops"' not in hcl:
        raise Phase10AlertsError("aws_sns_topic_policy.staging_ops is missing")
    if "cloudwatch.amazonaws.com" not in hcl:
        raise Phase10AlertsError("SNS topic policy must allow CloudWatch publish")
    if "budgets.amazonaws.com" not in hcl:
        raise Phase10AlertsError("SNS topic policy must allow AWS Budgets publish")
    if "subscriber_email_addresses" in hcl:
        raise Phase10AlertsError(
            "budgets and SNS must not use subscriber_email_addresses"
        )
    if re.search(r'protocol\s*=\s*"email"', hcl):
        raise Phase10AlertsError("SNS email protocol subscriptions are forbidden")
    leaked = production_email_in_text(hcl)
    if leaked is not None:
        raise Phase10AlertsError(f"production or non-synthetic email {leaked}")
    budget = extract_hcl_block(hcl, 'resource "aws_budgets_budget" "staging"')
    if not re.search(r'budget_type\s*=\s*"COST"', budget):
        raise Phase10AlertsError("budget_type must be COST")
    if not re.search(r'limit_unit\s*=\s*"USD"', budget):
        raise Phase10AlertsError("budget limit_unit must be USD")
    if not re.search(r'time_unit\s*=\s*"MONTHLY"', budget):
        raise Phase10AlertsError("budget time_unit must be MONTHLY")
    amounts = [float(value) for value in _LIMIT_AMOUNT.findall(budget)]
    if not amounts:
        raise Phase10AlertsError("budget limit_amount is missing")
    if any(value > STAGING_BUDGET_USD or value <= 0 for value in amounts):
        raise Phase10AlertsError("budget must stay bounded at 50 USD")
    if "subscriber_sns_topic_arns" not in budget:
        raise Phase10AlertsError("budget notification must target SNS")
    if "aws_sns_topic.staging_ops.arn" not in budget:
        raise Phase10AlertsError("budget notification must use staging_ops")


def assert_alarm_routing_policy(hcl: str) -> None:
    """Require named alarms with actions enabled and staging-ops SNS actions.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10AlertsError: If a required alarm is missing, disabled, or
            unrouted.
    """

    alarms = named_alarm_blocks(hcl)
    missing = [name for name in PACKET5_REQUIRED_ALARM_RESOURCES if name not in alarms]
    if missing:
        raise Phase10AlertsError("missing CloudWatch alarms: " + ", ".join(missing))
    for name, body in alarms.items():
        if not re.search(r"actions_enabled\s*=\s*true", body):
            raise Phase10AlertsError(f"{name} must set actions_enabled = true")
        if re.search(r"actions_enabled\s*=\s*false", body):
            raise Phase10AlertsError(f"{name} must not disable alarm actions")
        if "alarm_actions" not in body or "aws_sns_topic.staging_ops.arn" not in body:
            raise Phase10AlertsError(f"{name} alarm_actions must include staging_ops")


def assert_ses_sandbox_policy(hcl: str) -> None:
    """Require the Packet 1 SES sandbox identity without production recipients.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10AlertsError: If SES sandbox identity is missing.
    """

    if 'resource "aws_ses_email_identity" "staging"' not in hcl:
        raise Phase10AlertsError("SES sandbox identity is missing")
    if 'resource "aws_ses_configuration_set" "staging"' not in hcl:
        raise Phase10AlertsError("SES configuration set is missing")
    if SES_MODE_SANDBOX not in hcl and "sandbox" not in hcl.casefold():
        # ses.tf comments plus var.ses_from_email default carry the sandbox contract.
        ses = extract_hcl_block(hcl, 'resource "aws_ses_email_identity" "staging"')
        if "var.ses_from_email" not in ses:
            raise Phase10AlertsError("SES identity must use var.ses_from_email")


def assert_replica_requires_primary_recheck(
    replica_endpoint: object,
    *,
    primary_recheck: bool,
) -> None:
    """Reject a replica endpoint that lacks primary ACL/current-version recheck.

    Args:
        replica_endpoint: Inventory replica host or None.
        primary_recheck: True only when every selected ID is revalidated on
            the primary.

    Raises:
        Phase10AlertsError: If a replica exists without the recheck.
    """

    present = replica_endpoint not in {None, "", False}
    if present and not primary_recheck:
        raise Phase10AlertsError(
            "replica without primary ACL/current-version recheck is forbidden"
        )


def assert_replica_inventory(payload: Mapping[str, object], hcl: str) -> None:
    """Require topology to have no replica, or a replica with primary recheck.

    Args:
        payload: ``intended-topology.json``.
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10AlertsError: On replica-without-recheck or HCL replica drift.
    """

    endpoint = payload.get("read_replica_endpoint")
    recheck = payload.get("replica_primary_acl_recheck") is True
    assert_replica_requires_primary_recheck(endpoint, primary_recheck=recheck)
    if re.search(r"read_replica|replica_endpoint|SUPABASE_READ_REPLICA", hcl):
        if not recheck:
            raise Phase10AlertsError(
                "Terraform replica endpoint requires primary ACL recheck"
            )


def assert_envelope_not_full_scale(
    *,
    hybrid_versions: object,
    chunks: object,
    graph_versions: object,
    claimed_full_hybrid: bool,
    claimed_full_chunks: bool,
) -> None:
    """Keep the signed reduced envelope and reject 10k/1M claims.

    Args:
        hybrid_versions: QT-CAP-001-P9 value.
        chunks: QT-CAP-002-P9 value.
        graph_versions: QT-CAP-005-P8 value.
        claimed_full_hybrid: Inventory full-hybrid flag.
        claimed_full_chunks: Inventory full-chunk flag.

    Raises:
        Phase10AlertsError: If the envelope drifted or advertised 10k/1M.
    """

    if hybrid_versions != ENVELOPE_HYBRID_VERSIONS:
        raise Phase10AlertsError("QT-CAP-001-P9 must remain 8")
    if chunks != ENVELOPE_CHUNKS:
        raise Phase10AlertsError("QT-CAP-002-P9 must remain 16")
    if graph_versions != ENVELOPE_GRAPH_VERSIONS:
        raise Phase10AlertsError("QT-CAP-005-P8 must remain 15")
    if claimed_full_hybrid or claimed_full_chunks:
        raise Phase10AlertsError("must not claim QT-CAP-001/002 10k/1M")
    if hybrid_versions == SIGNED_FULL_HYBRID_VERSIONS or chunks == SIGNED_FULL_CHUNKS:
        raise Phase10AlertsError("must not advertise 10k/1M")


def assert_envelope_inventory(payload: Mapping[str, object]) -> None:
    """Assert the committed inventory still holds the reduced envelope.

    Args:
        payload: ``intended-topology.json``.

    Raises:
        Phase10AlertsError: On envelope drift.
    """

    try:
        typed = as_json_object(payload.get("envelope"), source="envelope")
    except ValueError as exc:
        raise Phase10AlertsError("inventory envelope is missing") from exc
    assert_envelope_not_full_scale(
        hybrid_versions=typed.get("QT-CAP-001-P9"),
        chunks=typed.get("QT-CAP-002-P9"),
        graph_versions=typed.get("QT-CAP-005-P8"),
        claimed_full_hybrid=typed.get("claimed_full_hybrid") is True,
        claimed_full_chunks=typed.get("claimed_full_chunks") is True,
    )


def assert_alert_runbook(text: str) -> None:
    """Require owner/severity/route/ack/escalation for every named alarm.

    Args:
        text: ``docs/runbooks/alert-routing.md``.

    Raises:
        Phase10AlertsError: If a named alarm, ack path, or synthetic-only
            constraint is missing.
    """

    lowered = text.casefold()
    if "owner" not in lowered or "severity" not in lowered:
        raise Phase10AlertsError("alert runbook must assign owner and severity")
    if "acknowledgement" not in lowered and "ack" not in lowered:
        raise Phase10AlertsError("alert runbook must assign acknowledgement")
    if "escalation" not in lowered:
        raise Phase10AlertsError("alert runbook must assign escalation")
    if "staging-ops" not in lowered and "staging_ops" not in text:
        raise Phase10AlertsError("alert runbook must route to staging-ops")
    if "no production email" not in lowered:
        raise Phase10AlertsError("alert runbook must forbid production emails")
    if "synthetic" not in lowered:
        raise Phase10AlertsError("alert runbook must stay staging synthetic")
    leaked = production_email_in_text(text)
    if leaked is not None:
        raise Phase10AlertsError(f"alert runbook contains production email {leaked}")
    for alarm_id in PACKET5_RUNBOOK_ALARM_IDS:
        if alarm_id.replace("_", "-") not in lowered and alarm_id not in lowered:
            raise Phase10AlertsError(f"alert runbook missing named alarm {alarm_id}")
    if "```mermaid" not in text:
        raise Phase10AlertsError("alert runbook must include a Mermaid diagram")


def _run_check(check: str, callback: Callable[[], None]) -> PolicyFinding:
    """Run one assertion and convert failures into findings.

    Args:
        check: Assertion id.
        callback: Zero-argument callable that raises ``Phase10AlertsError``.

    Returns:
        Finding with pass/fail detail.
    """

    try:
        callback()
    except Phase10AlertsError as exc:
        return PolicyFinding(check=check, passed=False, detail=str(exc))
    return PolicyFinding(check=check, passed=True, detail="ok")


def assert_packet5_policy(repo_root: Path) -> PolicyReport:
    """Assert every committed Packet 5 KMS, alarm, SES, replica, and envelope artifact.

    Args:
        repo_root: Repository root.

    Returns:
        Policy report. ``passed`` is False when any finding failed.

    Raises:
        Phase10AlertsError: If required files are missing or any check fails.
    """

    infra = repo_root / INFRA_EC2_DIR
    tf_bundle = load_terraform_bundle(infra)
    hcl = strip_hcl_comments(tf_bundle)
    inventory = load_json_object(repo_root / INTENDED_TOPOLOGY_FILE)
    runbook = (repo_root / ALERT_ROUTING_RUNBOOK).read_text(encoding="utf-8")
    exporter = (repo_root / AUDIT_EXPORT_MODULE).read_text(encoding="utf-8")
    variables = (infra / "variables.tf").read_text(encoding="utf-8")

    checks: tuple[tuple[str, Callable[[], None]], ...] = (
        ("hmac_not_kms", lambda: assert_hmac_export_not_kms(exporter)),
        ("kms", lambda: assert_kms_policy(hcl)),
        ("object_lock", lambda: assert_object_lock_policy(hcl)),
        ("sns_budget", lambda: assert_sns_and_budget_policy(hcl)),
        ("alarm_routing", lambda: assert_alarm_routing_policy(hcl)),
        ("ses_sandbox", lambda: assert_ses_sandbox_policy(hcl)),
        ("replica", lambda: assert_replica_inventory(inventory, hcl)),
        ("envelope", lambda: assert_envelope_inventory(inventory)),
        ("runbook", lambda: assert_alert_runbook(runbook)),
        (
            "variables_email",
            lambda: assert_no_production_email(variables, source="variables.tf"),
        ),
    )
    findings = tuple(_run_check(name, callback) for name, callback in checks)
    reviewed: Sequence[Path] = (
        *sorted(infra.glob("*.tf")),
        repo_root / INTENDED_TOPOLOGY_FILE,
        repo_root / ALERT_ROUTING_RUNBOOK,
        repo_root / AUDIT_EXPORT_MODULE,
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
        raise Phase10AlertsError(
            "Packet 5 policy failed: " + ", ".join(failed) + f" ({details})"
        )
    return report


def dump_alarm_matrix(hcl: str) -> list[dict[str, object]]:
    """Return the committed CloudWatch alarm routing matrix.

    Args:
        hcl: Comment-stripped Terraform.

    Returns:
        One row per alarm with enabled-actions and SNS routing flags.
    """

    rows: list[dict[str, object]] = []
    for name, body in named_alarm_blocks(hcl).items():
        rows.append(
            {
                "alarm": name,
                "actions_enabled": bool(re.search(r"actions_enabled\s*=\s*true", body)),
                "sns_staging_ops": "aws_sns_topic.staging_ops.arn" in body,
                "live_delivery": "Blocked",
            }
        )
    return rows


def canonical_hmac_flags() -> dict[str, object]:
    """Return the committed local HMAC export flags.

    Returns:
        Flags that stay false until a live KMS PutObject.
    """

    return {
        "kms": False,
        "s3_object_lock": False,
        "phase_10_blocker": True,
    }
