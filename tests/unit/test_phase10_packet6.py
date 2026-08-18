"""Unit tests for Phase 10 Packet 6 restore, rebuild, and skew negatives."""

from __future__ import annotations

from pathlib import Path

import pytest
from smart_rag_core.release.phase10_constants import (
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    OLD_API_PRIOR_DIGEST,
    PHASE09_IMAGE_IDS,
    REQUIRED_STORAGE_BUCKETS,
    RPO_TARGET_HOURS,
    RTO_TARGET_HOURS,
)
from smart_rag_core.release.phase10_packet1 import (
    LiveProviderProbe,
    packet1_checkbox_unchecked,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_packet2 import packet2_checkbox_unchecked
from smart_rag_core.release.phase10_packet3 import packet3_checkbox_unchecked
from smart_rag_core.release.phase10_packet4 import packet4_checkbox_unchecked
from smart_rag_core.release.phase10_packet5 import packet5_checkbox_unchecked
from smart_rag_core.release.phase10_packet6 import (
    OldApiSmokeEvidence,
    Phase09RestoreEvidence,
    Phase10Packet6GateError,
    RestoreReconcileKind,
    assert_contraction_absent,
    assert_live_database_not_overwritten,
    assert_not_managed_pitr_claim,
    assert_old_api_smoke,
    assert_paradedb_not_canonical,
    assert_rebuild_after_reconcile,
    assert_required_buckets_present,
    assert_rto_rpo_targets_not_measurements,
    classify_p1006_a,
    classify_p1006_b,
    classify_p1006_c,
    classify_p1006_d,
    classify_p1006_e,
    decide_reconciliation,
    missing_required_buckets,
    packet6_checkbox_unchecked,
    rebuild_documented_before_reconcile,
    rto_rpo_invented,
)

from scripts.ci.check_migrations import find_migration_violations


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


def _restore(
    *,
    live_database_overwritten: bool = False,
    restore_returncode: int = 1,
    dump_passed: bool = True,
    disposable_passed: bool = True,
    paradedb_used_as_canonical: bool = False,
    present_buckets: tuple[str, ...] = REQUIRED_STORAGE_BUCKETS,
) -> Phase09RestoreEvidence:
    """Return supporting Phase 9 restore evidence with optional overrides.

    Args:
        live_database_overwritten: Live application database was overwritten.
        restore_returncode: ``pg_restore`` exit code.
        dump_passed: Local dump recorded passed.
        disposable_passed: Disposable-copy restore recorded passed.
        paradedb_used_as_canonical: ParadeDB treated as authority.
        present_buckets: Inventoried bucket names.

    Returns:
        Frozen restore evidence.
    """

    return Phase09RestoreEvidence(
        live_database_overwritten=live_database_overwritten,
        restore_returncode=restore_returncode,
        dump_passed=dump_passed,
        disposable_passed=disposable_passed,
        paradedb_used_as_canonical=paradedb_used_as_canonical,
        present_buckets=present_buckets,
        required_buckets=REQUIRED_STORAGE_BUCKETS,
    )


def test_restore_incomplete_excludes_hybrid_and_graph() -> None:
    """Missing objects mark restore_incomplete and exclude Hybrid/graph."""

    missing = decide_reconciliation(
        RestoreReconcileKind.MISSING_OBJECT,
        reconciliation_complete=False,
    )
    assert missing.mark_restore_incomplete is True
    assert missing.exclude_hybrid_graph is True
    assert missing.quarantine_orphan is False
    assert missing.alert is True
    assert missing.allow_rebuild is False
    hashed = decide_reconciliation(
        RestoreReconcileKind.HASH_MISMATCH,
        reconciliation_complete=False,
    )
    assert hashed.mark_restore_incomplete is True
    assert hashed.exclude_hybrid_graph is True
    assert hashed.allow_rebuild is False


def test_object_orphan_quarantines_and_alerts() -> None:
    """Object-only orphans quarantine with append-only audit and alert."""

    orphan = decide_reconciliation(
        RestoreReconcileKind.OBJECT_ORPHAN,
        reconciliation_complete=False,
    )
    assert orphan.quarantine_orphan is True
    assert orphan.append_only_audit is True
    assert orphan.alert is True
    assert orphan.mark_restore_incomplete is False
    assert orphan.allow_rebuild is False
    matched = decide_reconciliation(
        RestoreReconcileKind.MATCH,
        reconciliation_complete=True,
    )
    assert matched.allow_rebuild is True
    incomplete = decide_reconciliation(
        RestoreReconcileKind.MATCH,
        reconciliation_complete=False,
    )
    assert incomplete.allow_rebuild is False


def test_rebuild_before_reconcile_fails() -> None:
    """Documented rebuild-before-reconcile is Failed, not a live Pass."""

    assert rebuild_documented_before_reconcile("rebuild before reconciliation") is True
    with pytest.raises(Phase10Packet6GateError, match="before reconcile"):
        assert_rebuild_after_reconcile(
            reconcile_text="Rebuild before reconciliation of Storage.",
            rebuild_text="Only from reconciled authorized current Supabase.",
        )
    with pytest.raises(Phase10Packet6GateError, match="rebuild only after"):
        assert_rebuild_after_reconcile(
            reconcile_text="Quarantine orphans.",
            rebuild_text="Only from reconciled authorized current Supabase.",
        )
    assert_rebuild_after_reconcile(
        reconcile_text="Rebuild only after reconciliation of all buckets.",
        rebuild_text="Rebuild only from reconciled authorized current Supabase.",
    )
    assert (
        classify_p1006_c(
            local_rebuild_ok=True,
            snapshot_as_canonical=False,
            rebuild_before_reconcile=True,
            live_ec2_rebuild_passed=False,
        )
        == "Failed"
    )
    assert (
        classify_p1006_b(
            reconcile_policy_passed=True,
            rebuild_before_reconcile=True,
            invented_orphan_counts=False,
            live_reconcile_state="Blocked",
            live_reconcile_passed=False,
        )
        == "Failed"
    )


def test_paradedb_snapshot_canonical_fails() -> None:
    """A ParadeDB snapshot claimed as canonical recovery is Failed."""

    assert_paradedb_not_canonical(False)
    with pytest.raises(Phase10Packet6GateError, match="not canonical"):
        assert_paradedb_not_canonical(True)
    assert (
        classify_p1006_c(
            local_rebuild_ok=True,
            snapshot_as_canonical=True,
            rebuild_before_reconcile=False,
            live_ec2_rebuild_passed=False,
        )
        == "Failed"
    )


def test_missing_required_bucket_fails() -> None:
    """A missing durable Storage bucket fails Packet 6-A."""

    assert_required_buckets_present(REQUIRED_STORAGE_BUCKETS)
    missing = missing_required_buckets(("documents-originals",))
    assert "documents-quarantine" in missing
    assert "web-snapshots" in missing
    assert "table-artifacts" in missing
    with pytest.raises(Phase10Packet6GateError, match="missing required Storage"):
        assert_required_buckets_present(("documents-originals",))
    assert (
        classify_p1006_a(
            buckets_present=False,
            live_database_overwritten=False,
            claimed_managed_pitr=False,
            production_restore=False,
            live_pitr_state="Blocked",
            live_pitr_passed=False,
        )
        == "Failed"
    )


def test_live_database_overwritten_fails() -> None:
    """Restoring into the live application database is Failed."""

    assert_live_database_not_overwritten(False)
    with pytest.raises(Phase10Packet6GateError, match="live application database"):
        assert_live_database_not_overwritten(True)
    assert _restore().live_database_overwritten is False
    assert (
        classify_p1006_a(
            buckets_present=True,
            live_database_overwritten=True,
            claimed_managed_pitr=False,
            production_restore=False,
            live_pitr_state="Blocked",
            live_pitr_passed=False,
        )
        == "Failed"
    )


def test_claiming_local_dump_as_managed_pitr_fails() -> None:
    """Local dump/restore must not be labeled isolated managed PITR."""

    assert_not_managed_pitr_claim(claimed_managed_pitr=False, live_pitr_passed=False)
    with pytest.raises(Phase10Packet6GateError, match="managed PITR"):
        assert_not_managed_pitr_claim(claimed_managed_pitr=True, live_pitr_passed=False)
    assert (
        classify_p1006_a(
            buckets_present=True,
            live_database_overwritten=False,
            claimed_managed_pitr=True,
            production_restore=False,
            live_pitr_state="Blocked",
            live_pitr_passed=False,
        )
        == "Failed"
    )


def test_destructive_drop_table_contraction_fails() -> None:
    """DROP TABLE contraction fails expand/contract and Packet 6-E."""

    violations = find_migration_violations(
        "DROP TABLE app.documents;", Path("unsafe.sql")
    )
    assert any("DROP TABLE" in item for item in violations)
    with pytest.raises(Phase10Packet6GateError, match="destructive contract DDL"):
        assert_contraction_absent(False)
    assert_contraction_absent(True)
    assert (
        classify_p1006_e(
            old_api_ok=True,
            contraction_absent=False,
            freeze_held=True,
            live_drain_state="Blocked",
            live_drain_passed=False,
            live_deploy_orders_passed=False,
            live_failed_deploy_passed=False,
        )
        == "Failed"
    )


def test_invented_rto_rpo_measurements_fail() -> None:
    """RTO/RPO hours without a timed EC2 rebuild are invented measurements."""

    assert RTO_TARGET_HOURS == 4
    assert RPO_TARGET_HOURS == 24
    assert (
        rto_rpo_invented(
            measured_rto_hours=None,
            measured_rpo_hours=None,
            live_instance_passed=False,
        )
        is False
    )
    assert (
        rto_rpo_invented(
            measured_rto_hours=3.5,
            measured_rpo_hours=None,
            live_instance_passed=False,
        )
        is True
    )
    with pytest.raises(Phase10Packet6GateError, match="not invented measurements"):
        assert_rto_rpo_targets_not_measurements(
            measured_rto_hours=3.5,
            measured_rpo_hours=12.0,
            live_instance_passed=False,
        )
    assert (
        classify_p1006_d(
            instance_policy_passed=True,
            invented_measurements=True,
            live_instance_state="Blocked",
            live_instance_passed=False,
        )
        == "Failed"
    )


def test_old_api_smoke_requires_freeze_identity() -> None:
    """Old-API smoke must keep the freeze image and prior digest."""

    smoke = OldApiSmokeEvidence(
        classification="Passed",
        freeze_api_id=PHASE09_IMAGE_IDS["api"],
        requested=OLD_API_PRIOR_DIGEST,
        restored_freeze=True,
        holdout_opened=False,
    )
    assert_old_api_smoke(smoke)
    drifted = OldApiSmokeEvidence(
        classification="Passed",
        freeze_api_id="sha256:deadbeef",
        requested=OLD_API_PRIOR_DIGEST,
        restored_freeze=True,
        holdout_opened=False,
    )
    with pytest.raises(Phase10Packet6GateError, match="freeze_api_id"):
        assert_old_api_smoke(drifted)


def test_classifications_keep_live_blocked_and_ignore_packets_1_5() -> None:
    """Live PITR/EC2/drain stay Blocked; Packets 1-5 unchecked is not a failure."""

    assert ENVELOPE_HYBRID_VERSIONS == 8
    assert ENVELOPE_CHUNKS == 16
    assert ENVELOPE_GRAPH_VERSIONS == 15
    assert (
        classify_p1006_a(
            buckets_present=True,
            live_database_overwritten=False,
            claimed_managed_pitr=False,
            production_restore=False,
            live_pitr_state="Blocked",
            live_pitr_passed=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1006_b(
            reconcile_policy_passed=True,
            rebuild_before_reconcile=False,
            invented_orphan_counts=False,
            live_reconcile_state="Blocked",
            live_reconcile_passed=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1006_c(
            local_rebuild_ok=True,
            snapshot_as_canonical=False,
            rebuild_before_reconcile=False,
            live_ec2_rebuild_passed=False,
        )
        == "Passed"
    )
    assert (
        classify_p1006_d(
            instance_policy_passed=True,
            invented_measurements=False,
            live_instance_state="Blocked",
            live_instance_passed=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1006_e(
            old_api_ok=True,
            contraction_absent=True,
            freeze_held=True,
            live_drain_state="Blocked",
            live_drain_passed=False,
            live_deploy_orders_passed=False,
            live_failed_deploy_passed=False,
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
6. [ ] [Perform and record database-plus-Storage restore/reconciliation
"""
    assert wrapper_status_pending(wrapper) is True
    assert packet1_checkbox_unchecked(wrapper) is True
    assert packet2_checkbox_unchecked(wrapper) is True
    assert packet3_checkbox_unchecked(wrapper) is True
    assert packet4_checkbox_unchecked(wrapper) is True
    assert packet5_checkbox_unchecked(wrapper) is True
    assert packet6_checkbox_unchecked(wrapper) is True
    blocked = _live_blocked()
    assert blocked.apply_state == "Blocked"
    assert _restore().restore_returncode == 1
