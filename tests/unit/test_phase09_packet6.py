"""Unit tests for Phase 9 Packet 6 egress/scan/restore mapping."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.constants import (
    CANDIDATE_COMPOSE_FILE,
    PACKET6_MATRIX_SCHEMA_VERSION,
    PACKET8_OVERLAY_FILE,
)
from smart_rag_core.release.packet2 import PACKET1_EXPECTED_IMAGE_IDS, JUnitCounts
from smart_rag_core.release.packet6 import (
    DISPOSABLE_RESTORE_DATABASE,
    HANDOFFS,
    PARADEDB_BOOTSTRAP_SQL,
    PYTEST_SUITES,
    REQUIRED_STORAGE_BUCKETS,
    classify_counts,
    classify_p0906_a,
    classify_p0906_b,
    classify_p0906_c,
    classify_p0906_d,
    classify_p0906_e,
    expected_image_ids,
    failure_detail,
    missing_bootstrap_sql_files,
    missing_pytest_files,
    process_exit_ok,
    restore_exit_acceptable,
    suites_for_mode,
)
from smart_rag_core.release.scans import trivy_critical_ids

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts" / "ci" / "check_phase09_packet6.py"


def test_packet6_mapped_pytest_files_exist() -> None:
    """Every Packet 6 suite path must already exist."""

    assert missing_pytest_files(REPO_ROOT) == ()
    assert missing_bootstrap_sql_files(REPO_ROOT) == ()
    assert PARADEDB_BOOTSTRAP_SQL[0].endswith("arabic_norm_v1.sql")
    for suite in PYTEST_SUITES:
        assert suite.fail_on_skip is True
        assert suite.overlay_required is False
    assert RUNNER.is_file()
    assert (REPO_ROOT / CANDIDATE_COMPOSE_FILE).is_file()
    assert CANDIDATE_COMPOSE_FILE != PACKET8_OVERLAY_FILE
    assert PACKET6_MATRIX_SCHEMA_VERSION.startswith("phase09-candidate-packet6")
    assert "documents-quarantine" in REQUIRED_STORAGE_BUCKETS
    assert DISPOSABLE_RESTORE_DATABASE != "postgres"


def test_zero_collection_is_failed() -> None:
    """Empty suites are a Packet 6 failure."""

    counts = JUnitCounts(tests=0, failures=0, errors=0, skipped=0)
    assert classify_counts(counts, returncode=5, fail_on_skip=True) == "Failed"
    assert failure_detail(counts, returncode=5, fail_on_skip=True) == (
        "zero tests collected"
    )


def test_overlay_is_not_candidate_identity() -> None:
    """Packet 6 candidate mode never selects overlay-required suites."""

    candidate = suites_for_mode("candidate")
    assert all(not suite.overlay_required for suite in candidate)


def test_packet1_image_ids_stay_frozen() -> None:
    """Packet 6 must consume the Packet 1 digest freeze."""

    assert expected_image_ids() == PACKET1_EXPECTED_IMAGE_IDS


def test_trivy_blocked_is_not_failed_when_host_scans_pass() -> None:
    """Tar Trivy timeout is Blocked, not a fake pass or host-scan failure."""

    assert (
        classify_p0906_b(
            pip_passed=True,
            pnpm_passed=True,
            gitleaks_passed=True,
            trivy_failed=False,
            trivy_blocked=True,
            trivy_passed=False,
        )
        == "Blocked"
    )


def test_p0906_c_fails_if_live_database_overwritten() -> None:
    """Disposable restore must not target live postgres."""

    assert (
        classify_p0906_c(
            dump_passed=True,
            disposable_restore_passed=True,
            buckets_present=True,
            restored_into_live=True,
        )
        == "Failed"
    )


def test_p0906_d_fails_if_paradedb_treated_as_authority() -> None:
    """ParadeDB snapshots are not canonical backups."""

    assert (
        classify_p0906_d(
            reconciled_before_rebuild=True,
            volume_destroyed=True,
            rebuild_passed=True,
            parade_as_authority=True,
        )
        == "Failed"
    )


def test_p0906_e_fails_on_full_envelope_claim() -> None:
    """Local restore duration is not QT-CAP-001 proof."""

    assert (
        classify_p0906_e(
            identity_held=True,
            health_after_passed=True,
            claimed_full_envelope=True,
            claimed_managed_ec2=False,
        )
        == "Failed"
    )
    assert classify_p0906_a(pytest_passed=True) == "Passed"
    assert restore_exit_acceptable(0) is True
    assert restore_exit_acceptable(1) is True
    assert restore_exit_acceptable(2) is False
    assert process_exit_ok(0) is True
    assert process_exit_ok(1) is False
    assert process_exit_ok(None) is False
    sock = next(item for item in HANDOFFS if item.item_id == "trivy_docker_sock")
    assert sock.classification == "Not Run"
    assert sock.managed_only is False
    assert trivy_critical_ids(
        {
            "Results": [
                {
                    "Vulnerabilities": [
                        {"Severity": "CRITICAL", "VulnerabilityID": "CVE-TEST-1"},
                        {"Severity": "HIGH", "VulnerabilityID": "CVE-TEST-2"},
                    ]
                }
            ]
        }
    ) == ("CVE-TEST-1",)
