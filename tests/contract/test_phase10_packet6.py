"""Contract tests for committed Phase 10 Packet 6 restore and rebuild policy."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.phase10_constants import (
    BM25_REBUILD_RUNBOOK,
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    GITHUB_WORKFLOWS_DIR,
    INSTANCE_REBUILD_RUNBOOK,
    OLD_API_PRIOR_DIGEST,
    PACKET6_RELATIVE,
    PACKET6_RESTORE_INCOMPLETE_TEST_FILES,
    PHASE09_IMAGE_IDS,
    PHASE09_OLD_API_SMOKE,
    PHASE09_PACKET6_REBUILD,
    PHASE09_PACKET6_RESTORE,
    PROTECTED_MIGRATION_RUNBOOK,
    REQUIRED_STORAGE_BUCKETS,
    RPO_TARGET_HOURS,
    RTO_TARGET_HOURS,
    STAGING_CADDY_FILE,
    STAGING_COMPOSE_FILE,
    STORAGE_RECONCILE_RUNBOOK,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_packet1 import wrapper_status_pending
from smart_rag_core.release.phase10_packet2 import packet2_checkbox_unchecked
from smart_rag_core.release.phase10_packet3 import packet3_checkbox_unchecked
from smart_rag_core.release.phase10_packet4 import packet4_checkbox_unchecked
from smart_rag_core.release.phase10_packet5 import packet5_checkbox_unchecked
from smart_rag_core.release.phase10_packet6 import (
    assert_packet6_policy,
    evaluate_packet6,
    packet6_checkbox_unchecked,
    packet6_status_pending,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_restore_rebuild_runbooks_pass_policy() -> None:
    """Reviewed runbooks and Phase 9 supporting JSON satisfy Packet 6 policy."""

    report = assert_packet6_policy(REPO_ROOT)
    assert report.passed is True
    assert report.iac_sha256
    names = {item.check for item in report.findings}
    assert "reconcile_runbook" in names
    assert "bm25_runbook" in names
    assert "instance_runbook" in names
    assert "rebuild_after_reconcile" in names
    assert "old_api_smoke" in names
    assert "contraction" in names
    assert all(item.passed for item in report.findings)
    restore = (REPO_ROOT / PHASE09_PACKET6_RESTORE).read_text(encoding="utf-8")
    assert '"live_database_overwritten": false' in restore
    assert '"restore_returncode": 1' in restore
    for bucket in REQUIRED_STORAGE_BUCKETS:
        assert bucket in restore
    rebuild = (REPO_ROOT / PHASE09_PACKET6_REBUILD).read_text(encoding="utf-8")
    assert '"paradedb_used_as_canonical": false' in rebuild
    assert '"volume_destroyed": true' in rebuild
    smoke = (REPO_ROOT / PHASE09_OLD_API_SMOKE).read_text(encoding="utf-8")
    assert f'"freeze_api_id": "{PHASE09_IMAGE_IDS["api"]}"' in smoke
    assert f'"requested": "{OLD_API_PRIOR_DIGEST}"' in smoke
    assert '"restored_freeze": true' in smoke
    compose = (REPO_ROOT / STAGING_COMPOSE_FILE).read_text(encoding="utf-8")
    assert "api-blue:" in compose
    assert "api-green:" in compose
    caddy = (REPO_ROOT / STAGING_CADDY_FILE).read_text(encoding="utf-8")
    assert "ACTIVE_API_UPSTREAM" in caddy
    migration = (REPO_ROOT / PROTECTED_MIGRATION_RUNBOOK).read_text(encoding="utf-8")
    assert "forward fix" in migration.casefold()
    assert "not a down-migration" in migration.casefold()


def test_runbooks_require_reconcile_before_rebuild_and_target_rto() -> None:
    """Topology runbooks keep rebuild after reconcile and RTO/RPO as targets."""

    reconcile = (REPO_ROOT / STORAGE_RECONCILE_RUNBOOK).read_text(encoding="utf-8")
    rebuild = (REPO_ROOT / BM25_REBUILD_RUNBOOK).read_text(encoding="utf-8")
    instance = (REPO_ROOT / INSTANCE_REBUILD_RUNBOOK).read_text(encoding="utf-8")
    assert "```mermaid" in reconcile
    assert "```mermaid" in rebuild
    assert "```mermaid" in instance
    assert "rebuild only after reconciliation" in reconcile.casefold()
    assert "restore_incomplete" in reconcile
    assert "only from reconciled" in rebuild.casefold()
    assert "paradedb snapshot never canonical" in rebuild.casefold()
    assert "targets, not measurements" in instance.casefold()
    assert "host data is not canonical" in instance.casefold()
    assert "failed health check leaves the old slot active" in instance.casefold()
    assert str(RTO_TARGET_HOURS) in instance
    assert str(RPO_TARGET_HOURS) in instance


def test_wrapper_stays_pending_and_packets_1_5_unchecked_are_not_failures() -> None:
    """Live Blocked Packet 6 must not complete the wrapper."""

    wrapper = (REPO_ROOT / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (REPO_ROOT / PACKET6_RELATIVE).read_text(encoding="utf-8")
    assert wrapper_status_pending(wrapper) is True
    assert packet6_checkbox_unchecked(wrapper) is True
    assert packet2_checkbox_unchecked(wrapper) is True
    assert packet3_checkbox_unchecked(wrapper) is True
    assert packet4_checkbox_unchecked(wrapper) is True
    assert packet5_checkbox_unchecked(wrapper) is True
    assert packet6_status_pending(packet) is True
    policy, live, _restore, _rebuild, _smoke, contraction, rows = evaluate_packet6(
        REPO_ROOT,
        restore_incomplete_ok=True,
    )
    assert policy.passed is True
    assert contraction is True
    by_check = {row.check: row.classification for row in rows}
    assert by_check["P10-06-A"] == "Blocked"
    assert by_check["P10-06-B"] == "Blocked"
    assert by_check["P10-06-C"] == "Passed"
    assert by_check["P10-06-D"] == "Blocked"
    assert by_check["P10-06-E"] == "Blocked"
    assert live.apply_state in {"Blocked", "Not Run", "Failed"}
    pr_fast = (REPO_ROOT / GITHUB_WORKFLOWS_DIR / "pr-fast.yml").read_text(
        encoding="utf-8"
    )
    assert "check_phase10_packet6.py" not in pr_fast
    assert ENVELOPE_HYBRID_VERSIONS == 8
    assert ENVELOPE_CHUNKS == 16
    assert ENVELOPE_GRAPH_VERSIONS == 15
    for relative in PACKET6_RESTORE_INCOMPLETE_TEST_FILES:
        assert (REPO_ROOT / relative.split("::", 1)[0]).is_file()
