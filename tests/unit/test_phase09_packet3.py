"""Unit tests for Phase 9 Packet 3 fail-closed quality measurement mapping."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.phase6_registry import qt_eval_009_status
from smart_rag_core.release.constants import (
    CANDIDATE_COMPOSE_FILE,
    PACKET8_OVERLAY_FILE,
)
from smart_rag_core.release.packet2 import JUnitCounts
from smart_rag_core.release.packet3 import (
    EXPECTED_EXACT_CODE_DOCUMENT_ID,
    FIXTURE_COMBINED_GAIN_PP,
    HANDOFFS,
    PYTEST_SUITES,
    SEEDED_RETRIEVE_CASE_IDS,
    TARGET_SPECS,
    Phase09Packet3GateError,
    classify_suite_counts,
    classify_target,
    expected_image_ids,
    missing_pytest_files,
    mock_recall_must_not_be_live,
    percentile,
    pytest_spec_path,
    ranked_ids_eval_command,
    stale_phase4_sidecar_document_id,
    suite_failure_detail,
    suites_for_mode,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts" / "ci" / "check_phase09_packet3.py"
EVAL_RANKED = REPO_ROOT / "scripts" / "eval_phase4_ranked_ids.py"


def test_packet3_mapped_pytest_files_exist() -> None:
    """Every Packet 3 suite path must already exist; the matrix does not invent tests."""

    assert missing_pytest_files(REPO_ROOT) == ()
    for suite in PYTEST_SUITES:
        assert suite.pytest_args
        assert suite.fail_on_skip is True
    assert RUNNER.is_file()
    assert EVAL_RANKED.is_file()
    assert (REPO_ROOT / CANDIDATE_COMPOSE_FILE).is_file()
    assert (REPO_ROOT / PACKET8_OVERLAY_FILE).is_file()


def test_zero_collection_is_failed() -> None:
    """Empty suites are a Packet 3 failure, not a skip or pass."""

    counts = JUnitCounts(tests=0, failures=0, errors=0, skipped=0)
    assert classify_suite_counts(counts, returncode=5, fail_on_skip=True) == "Failed"
    assert suite_failure_detail(counts, returncode=5, fail_on_skip=True) == (
        "zero tests collected"
    )


def test_mandatory_skip_is_failed() -> None:
    """A skipped required local gate cannot be classified Passed."""

    counts = JUnitCounts(tests=4, failures=0, errors=0, skipped=1)
    assert classify_suite_counts(counts, returncode=0, fail_on_skip=True) == "Failed"


def test_mock_recall_cannot_be_labeled_live() -> None:
    """Mock embeddings must not set qt_eval_006_live."""

    assert mock_recall_must_not_be_live(
        {"embeddings": "mock", "qt_eval_006_live": True}
    )
    assert not mock_recall_must_not_be_live(
        {"embeddings": "mock", "qt_eval_006_live": False}
    )
    assert not mock_recall_must_not_be_live(
        {"embeddings": "openai", "qt_eval_006_live": True}
    )


def test_qt_eval_009_stays_unverified() -> None:
    """Live Combined +10pp remains unverified; fixture gain is not that gate."""

    assert qt_eval_009_status() == "unverified"
    assert HoldoutAccess.denied().allowed is False
    assert FIXTURE_COMBINED_GAIN_PP > 10.0
    handoff = next(
        item for item in HANDOFFS if item.item_id == "live_combined_plus_10pp"
    )
    assert handoff.classification == "Not Run"
    assert "keyword" in handoff.reason.lower()


def test_stale_phase4_sidecar_is_rejected() -> None:
    """Packet 1 gold_id_map document ids must not be treated as Packet 2 identity."""

    stale = stale_phase4_sidecar_document_id(
        {
            "records": [
                {
                    "case_id": "p4-exact_code-0003",
                    "document_id": "32fe04d0-661e-4ef4-8510-d86340576fce",
                }
            ]
        }
    )
    assert stale == "32fe04d0-661e-4ef4-8510-d86340576fce"
    assert stale != EXPECTED_EXACT_CODE_DOCUMENT_ID
    matching = stale_phase4_sidecar_document_id(
        {
            "records": [
                {
                    "case_id": "p4-exact_code-0003",
                    "document_id": EXPECTED_EXACT_CODE_DOCUMENT_ID,
                }
            ]
        }
    )
    assert matching is None


def test_live_qt_eval_006_is_not_run_under_mock() -> None:
    """Signed live Recall@10 cannot pass from mock embeddings."""

    spec = next(item for item in TARGET_SPECS if item.target_id == "QT-EVAL-006")
    row = classify_target(
        spec,
        measured=0.9,
        mock_model_mode=True,
        sample_size=7,
        detail="mock",
        passed=None,
    )
    assert row["classification"] == "Not Run"
    assert row["qt_eval_006_live"] is False


def test_acl_leak_is_failed_not_averaged() -> None:
    """QT-EVAL-001 cannot be averaged away."""

    spec = next(item for item in TARGET_SPECS if item.target_id == "QT-EVAL-001")
    row = classify_target(
        spec,
        measured=1,
        mock_model_mode=True,
        sample_size=7,
        detail="leak",
        passed=False,
    )
    assert row["classification"] == "Failed"


def test_overlay_suite_is_not_in_candidate_mode() -> None:
    """Host ParadeDB typed-query tests stay overlay-only."""

    candidate_ids = {suite.suite_id for suite in suites_for_mode("candidate")}
    overlay_ids = {suite.suite_id for suite in suites_for_mode("overlay")}
    assert "overlay_bm25_typed_rebuild" not in candidate_ids
    assert "overlay_bm25_typed_rebuild" in overlay_ids
    citations = next(
        suite
        for suite in PYTEST_SUITES
        if suite.suite_id == "quality_citations_coverage_table"
    )
    assert any(
        "test_symlink_escape_fails_closed" in item for item in citations.deselect
    )
    assert any(
        "test_in_process_payload_does_not_change_parent_rlimits" in item
        for item in citations.deselect
    )
    specs = [
        pytest_spec_path(spec)
        for suite in PYTEST_SUITES
        for spec in (*suite.pytest_args, *suite.deselect)
    ]
    assert "tests/contract/test_paradedb_bm25.py" in specs


def test_ranked_ids_command_uses_packet2_subset() -> None:
    """Live retrieve uses the existing CLI and Packet 2 case ids, not holdout."""

    command = ranked_ids_eval_command(sidecar=Path("docs/x.json"), live=True)
    assert command[0] == "scripts/eval_phase4_ranked_ids.py"
    assert "--live" in command
    assert "--split" in command
    assert "open" in command
    for case_id in SEEDED_RETRIEVE_CASE_IDS:
        assert case_id in command
        assert "holdout" not in case_id
    assert expected_image_ids()["api"].startswith("sha256:")


def test_percentile_p50_and_p95() -> None:
    """Latency percentiles are computed from raw samples."""

    assert percentile((), 0.95) is None
    assert percentile((10.0,), 0.50) == 10.0
    values = (10.0, 20.0, 30.0, 40.0, 50.0)
    assert percentile(values, 0.50) == 30.0


def test_graph_seven_day_handoff_is_blocked_local() -> None:
    """Unproven 2k rebuild is Blocked with a sizing-ladder reduction, not a fake pass."""

    item = next(row for row in HANDOFFS if row.item_id == "graph_seven_day_2k_rebuild")
    assert item.classification == "Blocked"
    assert item.managed_only is False
    assert "15" in item.sizing_ladder
    cap = next(row for row in HANDOFFS if row.item_id == "qt_cap_full_envelope")
    assert cap.classification == "Not Run"
    assert cap.managed_only is False


def test_packet3_gate_error_is_runtime() -> None:
    """Packet 3 failures stay typed runtime errors."""

    assert issubclass(Phase09Packet3GateError, RuntimeError)
