"""Unit tests for Phase 9 Packet 2 fail-closed gate mapping."""

from __future__ import annotations

from pathlib import Path

import pytest
from smart_rag_core.release.constants import (
    CANDIDATE_COMPOSE_FILE,
    PACKET8_OVERLAY_FILE,
)
from smart_rag_core.release.packet2 import (
    HANDOFFS,
    PACKET1_EXPECTED_IMAGE_IDS,
    PYTEST_SUITES,
    JUnitCounts,
    Phase09Packet2GateError,
    assert_holdout_sealed,
    classify_suite_counts,
    junit_counts,
    load_packet1_image_ids,
    local_handoffs_block,
    merge_suite_rows,
    missing_pytest_files,
    pytest_spec_path,
    suite_failure_detail,
    suites_for_mode,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts" / "ci" / "check_phase09_packet2.py"


def test_packet2_mapped_pytest_files_exist() -> None:
    """Every Packet 2 suite path must already exist; the matrix does not invent tests."""

    assert missing_pytest_files(REPO_ROOT) == ()
    for suite in PYTEST_SUITES:
        assert suite.pytest_args
        assert suite.fail_on_skip is True


def test_zero_collection_is_failed() -> None:
    """Empty suites are a Packet 2 failure, not a skip or pass."""

    counts = JUnitCounts(tests=0, failures=0, errors=0, skipped=0)
    assert classify_suite_counts(counts, returncode=5, fail_on_skip=True) == "Failed"
    assert suite_failure_detail(counts, returncode=5, fail_on_skip=True) == (
        "zero tests collected"
    )


def test_mandatory_skip_is_failed() -> None:
    """A skipped required local gate cannot be classified Passed."""

    counts = JUnitCounts(tests=4, failures=0, errors=0, skipped=1)
    assert classify_suite_counts(counts, returncode=0, fail_on_skip=True) == "Failed"
    assert classify_suite_counts(counts, returncode=0, fail_on_skip=False) == "Passed"


def test_failures_and_errors_are_failed() -> None:
    """Non-zero pytest status fails even when JUnit skipped is zero."""

    failed = JUnitCounts(tests=2, failures=1, errors=0, skipped=0)
    errored = JUnitCounts(tests=2, failures=0, errors=1, skipped=0)
    assert classify_suite_counts(failed, returncode=1, fail_on_skip=True) == "Failed"
    assert classify_suite_counts(errored, returncode=1, fail_on_skip=True) == "Failed"


def test_clean_nonzero_collection_is_passed() -> None:
    """Collected tests with no fail/error/skip pass the fail-closed rule."""

    counts = JUnitCounts(tests=3, failures=0, errors=0, skipped=0)
    assert classify_suite_counts(counts, returncode=0, fail_on_skip=True) == "Passed"
    assert suite_failure_detail(counts, returncode=0, fail_on_skip=True) == ""


def test_managed_jwks_is_not_a_packet2_pytest_suite() -> None:
    """Managed JWKS rollover stays a Phase 10 handoff, not a fake local pass."""

    specs = [
        pytest_spec_path(spec)
        for suite in PYTEST_SUITES
        for spec in (*suite.pytest_args, *suite.deselect)
    ]
    assert "tests/contract/test_jwks_rollover.py" not in specs
    handoff = next(item for item in HANDOFFS if item.item_id == "managed_jwks_rollover")
    assert handoff.classification == "Not Run"
    assert handoff.managed_only is True
    assert handoff.acceptance == "P09-02-B"


def test_old_api_new_schema_is_blocked_local_gap() -> None:
    """Missing old-slot smoke is Blocked locally, not relabeled as managed."""

    item = local_handoffs_block("P09-02-D")
    assert item is not None
    assert item.item_id == "old_api_new_schema_smoke"
    assert item.classification == "Blocked"
    assert item.managed_only is False
    assert "Do not fake" in item.next_action


def test_trivy_is_packet6_blocked_and_not_retried() -> None:
    """Packet 2 must not retry docker.sock Trivy."""

    item = next(row for row in HANDOFFS if row.item_id == "trivy_sbom")
    assert item.classification == "Blocked"
    assert "Packet 6" in item.owner
    assert "must not retry" in item.reason
    source = RUNNER.read_text(encoding="utf-8")
    assert "trivy" not in source.lower()
    assert "|| true" not in source


def test_overlay_suite_is_not_candidate_identity() -> None:
    """Host-port malware/proxy/BM25 tests are overlay-only."""

    overlay = suites_for_mode("overlay")
    candidate = suites_for_mode("candidate")
    assert {suite.suite_id for suite in overlay} == {"overlay_malware_proxy_bm25"}
    assert all(not suite.overlay_required for suite in candidate)
    assert CANDIDATE_COMPOSE_FILE == "docker-compose.yml"
    assert PACKET8_OVERLAY_FILE == "docker-compose.packet8.yml"
    assert CANDIDATE_COMPOSE_FILE != PACKET8_OVERLAY_FILE


def test_packet1_image_freeze_is_consumed() -> None:
    """Packet 2 refuses drifted image Ids instead of rebuilding."""

    found = load_packet1_image_ids(REPO_ROOT)
    assert found["api"] == PACKET1_EXPECTED_IMAGE_IDS["api"]
    assert found["worker"] == PACKET1_EXPECTED_IMAGE_IDS["worker"]
    assert found["frontend"] == PACKET1_EXPECTED_IMAGE_IDS["frontend"]
    assert found["crawl-proxy"] == PACKET1_EXPECTED_IMAGE_IDS["crawl-proxy"]
    assert found["parser-sandbox"] == PACKET1_EXPECTED_IMAGE_IDS["parser-sandbox"]


def test_holdout_stays_sealed() -> None:
    """Packet 2 consumes the Packet 1 corpus freeze with holdout closed."""

    assert_holdout_sealed(REPO_ROOT)


def test_schema_determinism_handoff_requires_reseed() -> None:
    """After the double reset, Packet 3 must consume rewritten corpus ids."""

    item = next(
        row for row in HANDOFFS if row.item_id == "schema_determinism_reset_reapply"
    )
    assert item.classification == "Passed"
    assert item.managed_only is False
    assert "wiped" in item.reason
    assert "candidate-corpus-manifest.json" in item.next_action
    assert "Image Ids stay" in item.next_action


def test_junit_counts_read_nested_suites(tmp_path: Path) -> None:
    """JUnit testsuites roots are summed the same way as Packet 1."""

    report = tmp_path / "junit.xml"
    report.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="a" tests="2" failures="0" errors="0" skipped="1"/>
  <testsuite name="b" tests="3" failures="1" errors="0" skipped="0"/>
</testsuites>
""",
        encoding="utf-8",
    )
    counts = junit_counts(report)
    assert counts == JUnitCounts(tests=5, failures=1, errors=0, skipped=1)


def test_missing_junit_report_fails_closed(tmp_path: Path) -> None:
    """A missing pytest report is not treated as an empty pass."""

    with pytest.raises(Phase09Packet2GateError, match="unavailable"):
        junit_counts(tmp_path / "missing.xml")


def test_merge_suite_rows_preserves_matrix_order() -> None:
    """Overlay merges replace by suite_id without inventing rows."""

    existing = [
        {"suite_id": "identity_acl_graph_cache", "classification": "Passed"},
        {"suite_id": "overlay_malware_proxy_bm25", "classification": "Not Run"},
    ]
    incoming = [
        {"suite_id": "overlay_malware_proxy_bm25", "classification": "Passed"},
    ]
    merged = merge_suite_rows(existing, incoming)
    assert [row["suite_id"] for row in merged] == [
        "identity_acl_graph_cache",
        "overlay_malware_proxy_bm25",
    ]
    assert merged[1]["classification"] == "Passed"
