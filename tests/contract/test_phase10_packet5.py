"""Contract tests for committed Phase 10 Packet 5 KMS, alarms, and envelope IaC."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.phase10_alerts import assert_packet5_policy
from smart_rag_core.release.phase10_constants import (
    ALERT_ROUTING_RUNBOOK,
    ALERTS_TF,
    AUDIT_EXPORT_MODULE,
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    GITHUB_WORKFLOWS_DIR,
    KMS_S3_AUDIT_TF,
    PACKET5_AUDIT_TEST_FILES,
    PACKET5_BUDGET_TEST_FILES,
    PACKET5_PAUSE_TEST_FILES,
    PACKET5_RELATIVE,
    PACKET5_REQUIRED_ALARM_RESOURCES,
    STAGING_BUDGET_USD,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_packet1 import (
    packet1_checkbox_unchecked,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_packet2 import packet2_checkbox_unchecked
from smart_rag_core.release.phase10_packet3 import packet3_checkbox_unchecked
from smart_rag_core.release.phase10_packet4 import packet4_checkbox_unchecked
from smart_rag_core.release.phase10_packet5 import (
    evaluate_packet5,
    packet5_checkbox_unchecked,
    packet5_status_pending,
)
from smart_rag_core.release.phase10_topology import (
    load_terraform_bundle,
    strip_hcl_comments,
)
from smart_rag_core.security.audit_export import LocalHmacAuditExporter

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_kms_object_lock_alarm_envelope_pass_policy() -> None:
    """Reviewed staging files satisfy Packet 5 policy without live AWS."""

    report = assert_packet5_policy(REPO_ROOT)
    assert report.passed is True
    assert report.iac_sha256
    names = {item.check for item in report.findings}
    assert "kms" in names
    assert "object_lock" in names
    assert "alarm_routing" in names
    assert "runbook" in names
    assert all(item.passed for item in report.findings)
    hcl = strip_hcl_comments(load_terraform_bundle(REPO_ROOT / "infra" / "ec2"))
    kms = (REPO_ROOT / KMS_S3_AUDIT_TF).read_text(encoding="utf-8")
    alerts = (REPO_ROOT / ALERTS_TF).read_text(encoding="utf-8")
    telemetry = (REPO_ROOT / "infra" / "ec2" / "cloudwatch.tf").read_text(
        encoding="utf-8"
    )
    assert "object_lock_enabled = true" in kms
    assert 'resource "aws_s3_bucket_object_lock_configuration" "audit_anchors"' in kms
    assert (
        "object_lock_configuration {"
        not in kms.split('resource "aws_s3_bucket" "audit_anchors"', 1)[1].split(
            "resource ", 1
        )[0]
    )
    assert "enable_key_rotation     = true" in kms
    assert "DenyInstanceDecryptSign" in kms
    assert "kms:Decrypt" in hcl
    assert 'resource "aws_sns_topic" "staging_ops"' in alerts
    assert 'resource "aws_sns_topic_policy" "staging_ops"' in alerts
    assert "budgets.amazonaws.com" in alerts
    assert "cloudwatch.amazonaws.com" in alerts
    assert 'limit_amount = "50"' in alerts
    assert STAGING_BUDGET_USD == 50
    assert "subscriber_email_addresses" not in hcl
    assert "actions_enabled     = true" in telemetry
    assert "aws_sns_topic.staging_ops.arn" in telemetry
    for name in PACKET5_REQUIRED_ALARM_RESOURCES:
        assert f'resource "aws_cloudwatch_metric_alarm" "{name}"' in hcl
    exporter = (REPO_ROOT / AUDIT_EXPORT_MODULE).read_text(encoding="utf-8")
    assert '"kms": False' in exporter
    assert '"s3_object_lock": False' in exporter
    runbook = (REPO_ROOT / ALERT_ROUTING_RUNBOOK).read_text(encoding="utf-8")
    assert "no production email" in runbook.casefold()
    assert "```mermaid" in runbook


def test_local_hmac_export_keeps_kms_false() -> None:
    """Committed exporter source keeps kms and Object Lock flags false."""

    exporter = (REPO_ROOT / AUDIT_EXPORT_MODULE).read_text(encoding="utf-8")
    assert '"kms": False' in exporter
    assert '"s3_object_lock": False' in exporter
    assert '"phase_10_blocker": True' in exporter
    assert LocalHmacAuditExporter.__doc__ is not None
    assert "Not KMS" in LocalHmacAuditExporter.__doc__


def test_wrapper_stays_pending_and_packets_1_4_unchecked_are_not_failures() -> None:
    """Live Blocked Packet 5 must not complete the wrapper or require Packets 1-4."""

    wrapper = (REPO_ROOT / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (REPO_ROOT / PACKET5_RELATIVE).read_text(encoding="utf-8")
    assert wrapper_status_pending(wrapper) is True
    assert packet5_checkbox_unchecked(wrapper) is True
    assert packet1_checkbox_unchecked(wrapper) is True
    assert packet2_checkbox_unchecked(wrapper) is True
    assert packet3_checkbox_unchecked(wrapper) is True
    assert packet4_checkbox_unchecked(wrapper) is True
    assert packet5_status_pending(packet) is True
    policy, live, rows = evaluate_packet5(
        REPO_ROOT,
        tamper_subset_ok=True,
        pause_ok=True,
        budget_ok=True,
    )
    assert policy.passed is True
    by_check = {row.check: row.classification for row in rows}
    assert by_check["P10-05-A"] == "Blocked"
    assert by_check["P10-05-B"] == "Blocked"
    assert by_check["P10-05-C"] == "Blocked"
    assert by_check["P10-05-D"] == "Passed"
    assert by_check["P10-05-E"] == "Blocked"
    assert live.apply_state in {"Blocked", "Not Run", "Failed"}
    pr_fast = (REPO_ROOT / GITHUB_WORKFLOWS_DIR / "pr-fast.yml").read_text(
        encoding="utf-8"
    )
    assert "check_phase10_packet5.py" not in pr_fast
    assert ENVELOPE_HYBRID_VERSIONS == 8
    assert ENVELOPE_CHUNKS == 16
    assert ENVELOPE_GRAPH_VERSIONS == 15
    for relative in (
        *(item.split("::", 1)[0] for item in PACKET5_AUDIT_TEST_FILES),
        *PACKET5_PAUSE_TEST_FILES,
        *(item.split("::", 1)[0] for item in PACKET5_BUDGET_TEST_FILES),
    ):
        assert (REPO_ROOT / relative).is_file()
