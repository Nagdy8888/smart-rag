"""Unit tests for Phase 10 Packet 5 KMS, alarm, replica, and envelope negatives."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from smart_rag_core.release.phase10_alerts import (
    Phase10AlertsError,
    assert_alarm_routing_policy,
    assert_envelope_not_full_scale,
    assert_hmac_export_not_kms,
    assert_kms_policy,
    assert_no_production_email,
    assert_object_lock_policy,
    assert_replica_requires_primary_recheck,
    assert_sns_and_budget_policy,
    hmac_payload_claims_kms,
)
from smart_rag_core.release.phase10_constants import (
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    PACKET5_REQUIRED_ALARM_RESOURCES,
    SIGNED_FULL_CHUNKS,
    SIGNED_FULL_HYBRID_VERSIONS,
)
from smart_rag_core.release.phase10_packet1 import (
    LiveProviderProbe,
    packet1_checkbox_unchecked,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_packet2 import packet2_checkbox_unchecked
from smart_rag_core.release.phase10_packet3 import packet3_checkbox_unchecked
from smart_rag_core.release.phase10_packet4 import packet4_checkbox_unchecked
from smart_rag_core.release.phase10_packet5 import (
    classify_p1005_a,
    classify_p1005_b,
    classify_p1005_c,
    classify_p1005_d,
    classify_p1005_e,
    packet5_checkbox_unchecked,
)
from smart_rag_core.security.audit_chain import (
    AUDIT_CHAIN_GENESIS_HASH,
    canonical_audit_material,
    redact_audit_payload,
    sha256_hex,
)
from smart_rag_core.security.audit_export import AuditExportRow, LocalHmacAuditExporter

_KMS_HCL = """
resource "aws_kms_key" "audit" {
  enable_key_rotation     = true
  deletion_window_in_days = 30
  key_usage               = "ENCRYPT_DECRYPT"
}
resource "aws_kms_key_policy" "audit" {
  key_id = aws_kms_key.audit.id
}
DenyInstanceDecryptSign
kms:Decrypt
kms:Sign
data "aws_iam_policy_document" "staging_secrets" {
  actions = ["secretsmanager:GetSecretValue"]
}
data "aws_iam_policy_document" "egress_denial_logs" {
  actions = ["logs:PutLogEvents"]
}
"""

_OBJECT_LOCK_HCL = """
resource "aws_s3_bucket" "audit_anchors" {
  bucket              = "${var.project_name}-audit-anchors"
  object_lock_enabled = true
}
resource "aws_s3_bucket_versioning" "audit_anchors" {
  versioning_configuration {
    status = "Enabled"
  }
}
resource "aws_s3_bucket_object_lock_configuration" "audit_anchors" {
  rule {
    default_retention {
      mode  = "GOVERNANCE"
      years = 7
    }
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "audit_anchors" {
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.audit.arn
      sse_algorithm     = "aws:kms"
    }
  }
}
resource "aws_s3_bucket_public_access_block" "audit_anchors" {
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
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


def _alarm_hcl(*, enabled: bool = True, sns: bool = True) -> str:
    """Return CloudWatch alarm HCL covering the Packet 5 required set.

    Args:
        enabled: ``actions_enabled`` value.
        sns: Whether ``alarm_actions`` include staging-ops.

    Returns:
        Terraform fragment.
    """

    flag = "true" if enabled else "false"
    actions = "[aws_sns_topic.staging_ops.arn]" if sns else "[]"
    parts = [
        'resource "aws_sns_topic" "staging_ops" { name = "${var.project_name}-ops" }'
    ]
    for name in PACKET5_REQUIRED_ALARM_RESOURCES:
        parts.append(
            f"""
resource "aws_cloudwatch_metric_alarm" "{name}" {{
  actions_enabled = {flag}
  alarm_actions   = {actions}
}}
"""
        )
    return "\n".join(parts)


def _budget_hcl(*, amount: str = "50", email: str | None = None) -> str:
    """Return a COST MONTHLY budget fragment.

    Args:
        amount: ``limit_amount`` string.
        email: Optional production subscriber email.

    Returns:
        Terraform fragment.
    """

    notification = """
  notification {
    subscriber_sns_topic_arns = [aws_sns_topic.staging_ops.arn]
  }
"""
    if email is not None:
        notification = f"""
  notification {{
    subscriber_email_addresses = ["{email}"]
  }}
"""
    return f"""
resource "aws_sns_topic" "staging_ops" {{
  name = "${{var.project_name}}-ops"
}}
resource "aws_sns_topic_policy" "staging_ops" {{
  arn = aws_sns_topic.staging_ops.arn
}}
data "aws_iam_policy_document" "staging_ops_sns" {{
  principals {{
    identifiers = ["cloudwatch.amazonaws.com", "budgets.amazonaws.com"]
  }}
  actions = ["sns:Publish"]
}}
resource "aws_budgets_budget" "staging" {{
  budget_type  = "COST"
  limit_amount = "{amount}"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  {notification}
}}
"""


def _hmac_row(seq: int, previous: str, payload: dict[str, str]) -> AuditExportRow:
    """Build one locally hashed audit row for HMAC export tests.

    Args:
        seq: Chain sequence.
        previous: Previous hash or genesis.
        payload: Already-safe payload.

    Returns:
        Export row.
    """

    created = "2026-08-18T00:00:00+00:00"
    material = canonical_audit_material(
        event_type="test_event",
        actor_user_id=None,
        actor_role=None,
        target_type=None,
        target_id=None,
        authorization_version=1,
        visibility_generation=1,
        session_id=None,
        purpose="unit",
        resource_type=None,
        resource_id=None,
        payload=redact_audit_payload(payload),
        previous_hash=previous,
        created_at_iso=created,
    )
    return AuditExportRow(
        chain_seq=seq,
        event_id=uuid4(),
        event_hash=sha256_hex(material),
        previous_hash=previous,
        event_type="test_event",
        actor_user_id=None,
        actor_role=None,
        target_type=None,
        target_id=None,
        authorization_version=1,
        visibility_generation=1,
        session_id=None,
        purpose="unit",
        resource_type=None,
        resource_id=None,
        payload=payload,
        created_at_iso=created,
    )


def test_hmac_claimed_as_kms_is_failed(tmp_path: Path) -> None:
    """Local HMAC export claiming kms:true cannot classify P10-05-A Passed."""

    destination = tmp_path / "hmac.json"
    first = _hmac_row(1, AUDIT_CHAIN_GENESIS_HASH, {"kind": "a"})
    second = _hmac_row(2, first.event_hash, {"kind": "b"})
    signed = LocalHmacAuditExporter(
        b"local-hmac-not-kms", destination=destination
    ).export((first, second))
    assert signed.ready is True
    text = destination.read_text(encoding="utf-8")
    assert '"kms": false' in text
    assert '"s3_object_lock": false' in text
    source = '"kms": False\n"s3_object_lock": False\n"phase_10_blocker": True\n'
    assert_hmac_export_not_kms(source)
    with pytest.raises(Phase10AlertsError, match="kms:true"):
        assert_hmac_export_not_kms('"kms": True\n"s3_object_lock": False\n')
    assert hmac_payload_claims_kms({"kms": True, "s3_object_lock": False}) is True
    assert hmac_payload_claims_kms({"kms": False, "s3_object_lock": False}) is False
    assert (
        classify_p1005_a(
            object_lock_policy_passed=True,
            tamper_subset_ok=True,
            hmac_claimed_kms=True,
            live_kms_state="Blocked",
            live_kms_passed=False,
        )
        == "Failed"
    )


def test_missing_object_lock_is_rejected() -> None:
    """A mutable bucket without Object Lock fails Packet 5 policy."""

    assert_object_lock_policy(_OBJECT_LOCK_HCL)
    mutable = _OBJECT_LOCK_HCL.replace(
        "object_lock_enabled = true", "object_lock_enabled = false"
    )
    with pytest.raises(Phase10AlertsError, match="object_lock_enabled"):
        assert_object_lock_policy(mutable)
    nested = _OBJECT_LOCK_HCL.replace(
        "object_lock_enabled = true",
        'object_lock_enabled = true\n  object_lock_configuration {\n    object_lock_enabled = "Enabled"\n  }',
    )
    with pytest.raises(Phase10AlertsError, match="deprecated"):
        assert_object_lock_policy(nested)


def test_actions_enabled_false_is_rejected() -> None:
    """Packet 5 requires actions_enabled true and SNS alarm_actions."""

    assert_alarm_routing_policy(_alarm_hcl())
    with pytest.raises(Phase10AlertsError, match="actions_enabled"):
        assert_alarm_routing_policy(_alarm_hcl(enabled=False))
    with pytest.raises(Phase10AlertsError, match="alarm_actions"):
        assert_alarm_routing_policy(_alarm_hcl(sns=False))


def test_production_sns_email_is_rejected() -> None:
    """Production subscriber emails fail closed."""

    assert_sns_and_budget_policy(_budget_hcl())
    with pytest.raises(Phase10AlertsError, match="subscriber_email_addresses"):
        assert_sns_and_budget_policy(_budget_hcl(email="ops@company.com"))
    missing_policy = _budget_hcl().replace(
        'resource "aws_sns_topic_policy" "staging_ops"',
        'resource "aws_sns_topic_policy" "other"',
    )
    with pytest.raises(Phase10AlertsError, match="sns_topic_policy"):
        assert_sns_and_budget_policy(missing_policy)
    with pytest.raises(Phase10AlertsError, match="production email"):
        assert_no_production_email(
            'subscriber_email_addresses = ["alerts@gmail.com"]',
            source="sns",
        )


def test_replica_without_primary_recheck_is_rejected() -> None:
    """A replica endpoint without primary ACL recheck is Failed."""

    assert_replica_requires_primary_recheck(None, primary_recheck=False)
    with pytest.raises(Phase10AlertsError, match="replica without primary"):
        assert_replica_requires_primary_recheck(
            "db-replica.example.invalid",
            primary_recheck=False,
        )
    assert (
        classify_p1005_d(
            pause_ok=True,
            budget_ok=True,
            replica_without_recheck=True,
            live_pool_passed=False,
        )
        == "Failed"
    )


def test_envelope_10k_claim_is_rejected() -> None:
    """Advertising QT-CAP-001/002 10k/1M fails Packet 5."""

    assert_envelope_not_full_scale(
        hybrid_versions=ENVELOPE_HYBRID_VERSIONS,
        chunks=ENVELOPE_CHUNKS,
        graph_versions=ENVELOPE_GRAPH_VERSIONS,
        claimed_full_hybrid=False,
        claimed_full_chunks=False,
    )
    with pytest.raises(
        Phase10AlertsError, match="must not claim QT-CAP-001/002 10k/1M"
    ):
        assert_envelope_not_full_scale(
            hybrid_versions=ENVELOPE_HYBRID_VERSIONS,
            chunks=ENVELOPE_CHUNKS,
            graph_versions=ENVELOPE_GRAPH_VERSIONS,
            claimed_full_hybrid=True,
            claimed_full_chunks=True,
        )
    with pytest.raises(Phase10AlertsError, match="QT-CAP-001-P9 must remain 8"):
        assert_envelope_not_full_scale(
            hybrid_versions=SIGNED_FULL_HYBRID_VERSIONS,
            chunks=SIGNED_FULL_CHUNKS,
            graph_versions=ENVELOPE_GRAPH_VERSIONS,
            claimed_full_hybrid=False,
            claimed_full_chunks=False,
        )
    assert (
        classify_p1005_e(
            envelope_policy_passed=True,
            claimed_full_scale=True,
            live_resource_state="Blocked",
            live_resource_passed=False,
        )
        == "Failed"
    )


def test_unbounded_budget_is_rejected() -> None:
    """Missing or huge COST limits fail Packet 5."""

    with pytest.raises(Phase10AlertsError, match="bounded"):
        assert_sns_and_budget_policy(_budget_hcl(amount="999999"))
    missing = _budget_hcl().replace('limit_amount = "50"', "")
    with pytest.raises(Phase10AlertsError, match="limit_amount"):
        assert_sns_and_budget_policy(missing)


def test_kms_instance_decrypt_grant_is_rejected() -> None:
    """Instance IAM must not receive kms:Decrypt or kms:Sign."""

    assert_kms_policy(_KMS_HCL)
    granted = _KMS_HCL.replace(
        'actions = ["secretsmanager:GetSecretValue"]',
        'actions = ["kms:Decrypt"]',
    )
    with pytest.raises(Phase10AlertsError, match="kms:Decrypt"):
        assert_kms_policy(granted)


def test_classifications_keep_live_blocked_and_ignore_packets_1_4() -> None:
    """Live KMS/SNS/SES stay Blocked; Packets 1-4 unchecked is not a failure."""

    assert (
        classify_p1005_a(
            object_lock_policy_passed=True,
            tamper_subset_ok=True,
            hmac_claimed_kms=False,
            live_kms_state="Blocked",
            live_kms_passed=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1005_b(
            routing_policy_passed=True,
            live_sns_state="Blocked",
            live_sns_passed=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1005_c(
            ses_policy_passed=True,
            production_recipient=False,
            live_ses_state="Blocked",
            live_ses_passed=False,
            managed_storage_cors_passed=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1005_d(
            pause_ok=True,
            budget_ok=True,
            replica_without_recheck=False,
            live_pool_passed=False,
        )
        == "Passed"
    )
    assert (
        classify_p1005_e(
            envelope_policy_passed=True,
            claimed_full_scale=False,
            live_resource_state="Blocked",
            live_resource_passed=False,
        )
        == "Blocked"
    )
    wrapper = """---
status: pending
---
1. [ ] [Provision isolated managed Supabase
2. [ ] [Implement GitHub OIDC, protected immutable expand/contract
3. [ ] [Prove direct-origin rejection, provider/crawl/parser egress
4. [ ] [Exercise asymmetric JWKS rollover, dual origin-secret rotation
5. [ ] [Exercise staging KMS/S3 Object Lock audit anchors, OpenAI/AWS/Supabase billing
"""
    assert wrapper_status_pending(wrapper) is True
    assert packet1_checkbox_unchecked(wrapper) is True
    assert packet2_checkbox_unchecked(wrapper) is True
    assert packet3_checkbox_unchecked(wrapper) is True
    assert packet4_checkbox_unchecked(wrapper) is True
    assert packet5_checkbox_unchecked(wrapper) is True
    blocked = _live_blocked()
    assert blocked.apply_state == "Blocked"
