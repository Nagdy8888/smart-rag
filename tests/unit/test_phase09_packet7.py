"""Unit tests for Phase 9 Packet 7 blocker classification."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.constants import (
    CANDIDATE_COMPOSE_FILE,
    PACKET7_MATRIX_SCHEMA_VERSION,
)
from smart_rag_core.release.packet2 import PACKET1_EXPECTED_IMAGE_IDS
from smart_rag_core.release.packet7 import (
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
    """Packet 7 must read existing Packet 1-6 artifacts and the wrapper."""

    assert missing_prior_artifacts(REPO_ROOT) == ()
    assert RUNNER.is_file()
    assert (REPO_ROOT / WRAPPER_RELATIVE).is_file()
    assert (REPO_ROOT / CANDIDATE_COMPOSE_FILE).is_file()
    assert PACKET7_MATRIX_SCHEMA_VERSION.startswith("phase09-candidate-packet7")
    assert expected_image_ids() == PACKET1_EXPECTED_IMAGE_IDS
    text = (REPO_ROOT / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    assert wrapper_status_pending(text) is True
    assert packet7_checkbox_unchecked(text) is True


def test_trivy_failed_keeps_p0907_a_failed() -> None:
    """Unresolved Critical findings are a local no-go, not a managed skip."""

    assert classify_p0907_a(has_failed_local=True, has_blocked_local=True) == "Failed"
    trivy = next(
        item for item in LOCAL_BLOCKERS if item.item_id == "trivy_critical_findings"
    )
    assert trivy.classification == "Failed"
    assert trivy.managed_only is False
    assert trivy.local_launch_blocking is True


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


def test_managed_items_stay_phase_10() -> None:
    """Relabeling a managed gate as local fails P09-07-C."""

    assert classify_p0907_c(managed_relabeled_local=False) == "Passed"
    assert classify_p0907_c(managed_relabeled_local=True) == "Failed"
    assert all(item.managed_only for item in MANAGED_HANDOFFS)


def test_packet7_does_not_self_complete() -> None:
    """Checking Packet 7 or completing the wrapper fails P09-07-E."""

    assert classify_p0907_d(artifacts_complete=True) == "Passed"
    assert classify_p0907_e(wrapper_pending=True, packet7_unchecked=True) == "Passed"
    assert classify_p0907_e(wrapper_pending=False, packet7_unchecked=True) == "Failed"
