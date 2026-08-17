"""Unit tests for Phase 9 Packet 5 fault-gate mapping."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.constants import (
    CANDIDATE_COMPOSE_FILE,
    PACKET5_FAULT_SCHEMA_VERSION,
    PACKET5_MATRIX_SCHEMA_VERSION,
    PACKET8_OVERLAY_FILE,
)
from smart_rag_core.release.packet2 import PACKET1_EXPECTED_IMAGE_IDS, JUnitCounts
from smart_rag_core.release.packet5 import (
    HANDOFFS,
    PYTEST_SUITES,
    classify_counts,
    classify_p0905_a,
    classify_p0905_b,
    classify_p0905_c,
    classify_p0905_d,
    classify_p0905_e,
    expected_image_ids,
    failure_detail,
    missing_pytest_files,
    suites_for_mode,
)
from smart_rag_core.release.packet5_faults import canonical_drift

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts" / "ci" / "check_phase09_packet5.py"


def test_packet5_mapped_pytest_files_exist() -> None:
    """Every Packet 5 suite path must already exist; the matrix does not invent tests."""

    assert missing_pytest_files(REPO_ROOT) == ()
    for suite in PYTEST_SUITES:
        assert suite.pytest_args
        assert suite.fail_on_skip is True
        assert suite.overlay_required is False
    assert RUNNER.is_file()
    assert (REPO_ROOT / CANDIDATE_COMPOSE_FILE).is_file()
    assert (REPO_ROOT / PACKET8_OVERLAY_FILE).is_file()
    assert CANDIDATE_COMPOSE_FILE != PACKET8_OVERLAY_FILE
    assert PACKET5_MATRIX_SCHEMA_VERSION.startswith("phase09-candidate-packet5")
    assert PACKET5_FAULT_SCHEMA_VERSION.startswith("phase09-candidate-packet5")


def test_zero_collection_is_failed() -> None:
    """Empty suites are a Packet 5 failure, not a skip or pass."""

    counts = JUnitCounts(tests=0, failures=0, errors=0, skipped=0)
    assert classify_counts(counts, returncode=5, fail_on_skip=True) == "Failed"
    assert failure_detail(counts, returncode=5, fail_on_skip=True) == (
        "zero tests collected"
    )


def test_packet5_d_deselects_five_stream_lag_owned_by_packet4() -> None:
    """Packet 5 D is resume/deadline; five-stream lag remains Packet 4 evidence."""

    suite = next(
        item for item in PYTEST_SUITES if item.suite_id == "sse_resume_one_paid_run"
    )
    assert any(
        "test_five_held_streams_meet_lag_and_heartbeat_gates" in item
        for item in suite.deselect
    )


def test_overlay_is_not_candidate_identity() -> None:
    """Packet 5 candidate mode never selects overlay-required suites."""

    candidate = suites_for_mode("candidate")
    assert candidate == PYTEST_SUITES
    assert all(not suite.overlay_required for suite in candidate)


def test_packet1_image_ids_stay_frozen() -> None:
    """Packet 5 must consume the Packet 1 digest freeze."""

    assert expected_image_ids() == PACKET1_EXPECTED_IMAGE_IDS


def test_named_acl_users_are_phase10() -> None:
    """Local requirepass deny is not managed named-ACL proof."""

    item = next(row for row in HANDOFFS if row.item_id == "named_valkey_acl_users")
    assert item.classification == "Not Run"
    assert item.managed_only is True
    assert item.owner == "Phase 10"


def test_volume_destroy_is_packet6() -> None:
    """Packet 5 must not destroy ParadeDB volumes."""

    item = next(
        row for row in HANDOFFS if row.item_id == "paradedb_volume_destroy_rebuild"
    )
    assert item.classification == "Not Run"
    assert item.owner == "Phase 9 Packet 6"


def test_p0905_d_passes_when_asgi_passed_and_jwt_blocked() -> None:
    """Live docker EventSource 401 is Packet 7, not a Failed ASGI resume gate."""

    assert (
        classify_p0905_d(pytest_passed=True, live_passed=False, jwt_blocked=True)
        == "Passed"
    )
    assert (
        classify_p0905_d(pytest_passed=False, live_passed=False, jwt_blocked=True)
        == "Failed"
    )


def test_p0905_a_fails_on_duplicate_canonical() -> None:
    """Reclaim must not create extra versions or chunks."""

    assert (
        classify_p0905_a(
            pytest_passed=True,
            worker_restart_passed=True,
            duplicate_canonical=True,
        )
        == "Failed"
    )
    assert (
        classify_p0905_a(
            pytest_passed=True,
            worker_restart_passed=True,
            duplicate_canonical=False,
        )
        == "Passed"
    )


def test_p0905_b_requires_visible_down_and_degrade() -> None:
    """ParadeDB stop must be visible and Hybrid must name bm25_unavailable."""

    assert (
        classify_p0905_b(
            pytest_passed=True,
            parade_down_visible=False,
            degrade_passed=True,
            recovered=True,
        )
        == "Failed"
    )
    assert (
        classify_p0905_b(
            pytest_passed=True,
            parade_down_visible=True,
            degrade_passed=True,
            recovered=True,
        )
        == "Passed"
    )


def test_p0905_c_requires_independent_valkey_faults() -> None:
    """Limits and cache must fail independently; named ACL stays Phase 10."""

    assert (
        classify_p0905_c(
            pytest_passed=True,
            deny_passed=True,
            limits_down_visible=True,
            cache_down_visible=False,
            fill_recovered=True,
        )
        == "Failed"
    )
    assert (
        classify_p0905_c(
            pytest_passed=True,
            deny_passed=True,
            limits_down_visible=True,
            cache_down_visible=True,
            fill_recovered=True,
        )
        == "Passed"
    )


def test_p0905_e_fails_when_health_after_restore_fails() -> None:
    """Packet 5 must not leave the candidate stack down."""

    assert (
        classify_p0905_e(
            identity_held=True,
            canonical_reconciled=True,
            health_after_passed=False,
            authority_transferred=False,
        )
        == "Failed"
    )


def test_canonical_drift_ignores_job_reclaim_counts() -> None:
    """Job ledger growth during reclaim is not canonical duplication."""

    before = {"versions": 8, "chunks": 16, "ingestion_jobs": 2, "ledger_rows": 4}
    after = {"versions": 8, "chunks": 16, "ingestion_jobs": 0, "ledger_rows": 6}
    payload = canonical_drift(before, after)
    assert payload["canonical_matched"] is True
    assert payload["duplicate_canonical"] is False
    assert payload["authority_transferred"] is False
