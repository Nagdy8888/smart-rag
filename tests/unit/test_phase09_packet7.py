"""Unit tests for Phase 9 Packet 7 blocker classification."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.constants import (
    CANDIDATE_COMPOSE_FILE,
    PACKET7_MATRIX_SCHEMA_VERSION,
)
from smart_rag_core.release.packet2 import PACKET1_EXPECTED_IMAGE_IDS
from smart_rag_core.release.packet7 import (
    CLAIMED_FULL_ENVELOPE,
    CLIENT_SIGNED_REDUCE,
    LOCAL_BLOCKERS,
    MANAGED_HANDOFFS,
    WRAPPER_RELATIVE,
    classify_p0907_a,
    classify_p0907_b,
    classify_p0907_c,
    classify_p0907_d,
    classify_p0907_e,
    expected_image_ids,
    missing_prior_artifacts,
    packet7_checkbox_unchecked,
    wrapper_status_pending,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts" / "ci" / "check_phase09_packet7.py"


def test_packet7_prior_artifacts_and_wrapper_exist() -> None:
    """Packet 7 reads Packet 1-6 artifacts; wrapper is complete after acceptance."""

    assert missing_prior_artifacts(REPO_ROOT) == ()
    assert RUNNER.is_file()
    assert (REPO_ROOT / WRAPPER_RELATIVE).is_file()
    assert (REPO_ROOT / CANDIDATE_COMPOSE_FILE).is_file()
    assert PACKET7_MATRIX_SCHEMA_VERSION.startswith("phase09-candidate-packet7")
    assert expected_image_ids() == PACKET1_EXPECTED_IMAGE_IDS
    text = (REPO_ROOT / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    assert wrapper_status_pending(text) is False
    assert packet7_checkbox_unchecked(text) is False


def test_trivy_criticals_passed_on_distroless() -> None:
    """Critical=0 tar scans clear the local Trivy no-go; High counts remain."""

    assert classify_p0907_a(has_failed_local=True, has_blocked_local=True) == "Failed"
    trivy = next(
        item for item in LOCAL_BLOCKERS if item.item_id == "trivy_critical_findings"
    )
    assert trivy.classification == "Passed"
    assert trivy.managed_only is False
    assert trivy.local_launch_blocking is False
    assert "Critical=0" in trivy.reason
    assert "a65f1aa4" in trivy.reason


def test_envelope_without_client_signoff_is_blocked() -> None:
    """10k/1M must not be claimed; unsigned reduce stays Blocked."""

    assert (
        classify_p0907_b(client_signed_reduce=False, claimed_full_envelope=False)
        == "Blocked"
    )
    assert (
        classify_p0907_b(client_signed_reduce=False, claimed_full_envelope=True)
        == "Failed"
    )


def test_signed_reduce_passes_p0907_b() -> None:
    """Client-signed 8-doc reduce passes; claiming 10k/1M still fails."""

    assert CLIENT_SIGNED_REDUCE is True
    assert CLAIMED_FULL_ENVELOPE is False
    assert (
        classify_p0907_b(
            client_signed_reduce=CLIENT_SIGNED_REDUCE,
            claimed_full_envelope=CLAIMED_FULL_ENVELOPE,
        )
        == "Passed"
    )
    assert (
        classify_p0907_b(client_signed_reduce=True, claimed_full_envelope=True)
        == "Failed"
    )
    item = next(
        row for row in LOCAL_BLOCKERS if row.item_id == "supported_envelope_reduce"
    )
    assert item.classification == "Passed"
    assert item.local_launch_blocking is False
    assert "QT-CAP-001-P9" in item.reason
    assert "QT-CAP-002-P9" in item.reason


def test_managed_items_stay_phase_10() -> None:
    """Relabeling a managed gate as local fails P09-07-C."""

    assert classify_p0907_c(managed_relabeled_local=False) == "Passed"
    assert classify_p0907_c(managed_relabeled_local=True) == "Failed"
    assert all(item.managed_only for item in MANAGED_HANDOFFS)


def test_jwt_issuer_split_is_passed_on_rebuilt_api() -> None:
    """Live /me and EventSource 200 on the rebuilt API clear the iss blocker."""

    item = next(
        row for row in LOCAL_BLOCKERS if row.item_id == "jwt_issuer_hostname_split"
    )
    assert item.classification == "Passed"
    assert item.local_launch_blocking is False
    assert "1d9f569b" in item.reason


def test_seventy_percent_pause_passed_without_live_trigger() -> None:
    """Held 8-doc Composite p95 passes P09-04-A without a 70% fire."""

    item = next(row for row in LOCAL_BLOCKERS if row.item_id == "seventy_percent_pause")
    assert item.classification == "Passed"
    assert item.local_launch_blocking is False
    assert item.managed_only is False
    assert "1828" in item.reason
    assert "1.49%" in item.reason
    assert "QT-CAP-001" in item.sizing_ladder
    assert "QT-CAP-001-P9" in item.next_action


def test_old_api_smoke_passed_on_prior_digest() -> None:
    """Distinct prior API digest smoked read/chat/upload then restored."""

    item = next(
        row for row in LOCAL_BLOCKERS if row.item_id == "old_api_new_schema_smoke"
    )
    assert item.classification == "Passed"
    assert item.local_launch_blocking is False
    assert "1d9f569b" in item.reason
    assert "a39d4456" in item.reason


def test_packet7_does_not_self_complete() -> None:
    """Checking Packet 7 or completing the wrapper fails P09-07-E."""

    assert classify_p0907_d(artifacts_complete=True) == "Passed"
    assert classify_p0907_e(wrapper_pending=True, packet7_unchecked=True) == "Passed"
    assert classify_p0907_e(wrapper_pending=False, packet7_unchecked=True) == "Failed"
    assert classify_p0907_e(wrapper_pending=True, packet7_unchecked=False) == "Failed"
