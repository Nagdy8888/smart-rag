"""Contract tests for committed Phase 10 Packet 7 suite and promotion policy."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.io import load_json_object
from smart_rag_core.release.phase10_constants import (
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    EXTERNAL_ASSESSMENT_SCOPE,
    GITHUB_WORKFLOWS_DIR,
    PACKET7_RELATIVE,
    PARADEDB_IMAGE,
    PHASE09_IMAGE_IDS,
    PHASE10_EVIDENCE,
    PHASE10_PHASE11_PROMOTION_MANIFEST,
    PHASE11_NO_GO_RECOMMENDATION,
    USER_ACCEPTANCE_REQUEST,
    VALKEY_IMAGE,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_packet1 import (
    packet1_checkbox_unchecked,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_packet2 import packet2_checkbox_unchecked
from smart_rag_core.release.phase10_packet3 import packet3_checkbox_unchecked
from smart_rag_core.release.phase10_packet4 import packet4_checkbox_unchecked
from smart_rag_core.release.phase10_packet5 import packet5_checkbox_unchecked
from smart_rag_core.release.phase10_packet6 import packet6_checkbox_unchecked
from smart_rag_core.release.phase10_packet7 import (
    all_phase10_checkboxes_unchecked,
    assert_scope_doc,
    evaluate_packet7,
    load_packet_matrices,
    packet7_checkbox_unchecked,
    packet7_status_pending,
    validate_promotion_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_packet_matrices_load_and_keep_freeze() -> None:
    """Packets 1-6 gate matrices exist, are nonempty, and keep freeze ids."""

    matrices = load_packet_matrices(REPO_ROOT)
    assert len(matrices) == 6
    for matrix in matrices:
        assert matrix.acceptance
        assert matrix.image_ids == dict(PHASE09_IMAGE_IDS)
        assert matrix.holdout_opened is False
        assert matrix.wrapper_status == "pending"
    blocked = [
        row.check
        for matrix in matrices
        for row in matrix.acceptance
        if row.classification == "Blocked"
    ]
    assert "P10-01-B" in blocked
    assert "P10-04-C" in blocked
    assert "P10-06-A" in blocked


def test_scope_doc_is_not_run_and_not_a_report() -> None:
    """Assessment scope documents required areas and stays not run."""

    text = (REPO_ROOT / EXTERNAL_ASSESSMENT_SCOPE).read_text(encoding="utf-8")
    assert_scope_doc(text)
    assert "status: not-run" in text
    assert "Trivy is image scan, not Packet 7-C" in text
    assert "does not claim Critical=0" in text
    assert "```mermaid" in text


def test_wrapper_stays_pending_and_all_seven_checkboxes_unchecked() -> None:
    """Packet 7 must not complete the wrapper or check any packet box."""

    wrapper = (REPO_ROOT / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (REPO_ROOT / PACKET7_RELATIVE).read_text(encoding="utf-8")
    assert wrapper_status_pending(wrapper) is True
    assert all_phase10_checkboxes_unchecked(wrapper) is True
    assert packet1_checkbox_unchecked(wrapper) is True
    assert packet2_checkbox_unchecked(wrapper) is True
    assert packet3_checkbox_unchecked(wrapper) is True
    assert packet4_checkbox_unchecked(wrapper) is True
    assert packet5_checkbox_unchecked(wrapper) is True
    assert packet6_checkbox_unchecked(wrapper) is True
    assert packet7_checkbox_unchecked(wrapper) is True
    assert packet7_status_pending(packet) is True
    pr_fast = (REPO_ROOT / GITHUB_WORKFLOWS_DIR / "pr-fast.yml").read_text(
        encoding="utf-8"
    )
    assert "check_phase10_packet7.py" not in pr_fast
    streaming = (REPO_ROOT / "docs/deployment/STREAMING_TIMEOUTS.md").read_text(
        encoding="utf-8"
    )
    assert "does **not** claim" in streaming


def test_evaluate_classifies_honest_no_go() -> None:
    """Committed evidence classifies A/C/D Blocked and B/E Passed."""

    evidence = (REPO_ROOT / PHASE10_EVIDENCE).read_text(encoding="utf-8")
    assert USER_ACCEPTANCE_REQUEST in evidence
    policy, live, matrices, rows = evaluate_packet7(
        REPO_ROOT,
        packet7_tests_ok=True,
    )
    assert policy.passed is True
    assert len(matrices) == 6
    by_check = {row.check: row.classification for row in rows}
    assert by_check["P10-07-A"] == "Blocked"
    assert by_check["P10-07-B"] == "Passed"
    assert by_check["P10-07-C"] == "Blocked"
    assert by_check["P10-07-D"] == "Blocked"
    assert by_check["P10-07-E"] == "Passed"
    assert live.apply_state in {"Blocked", "Not Run", "Failed"}
    promotion = load_json_object(REPO_ROOT / PHASE10_PHASE11_PROMOTION_MANIFEST)
    validate_promotion_manifest(promotion)
    assert promotion.get("recommendation") == PHASE11_NO_GO_RECOMMENDATION
    envelope = promotion.get("envelope")
    assert envelope == {
        "QT-CAP-001-P9": ENVELOPE_HYBRID_VERSIONS,
        "QT-CAP-002-P9": ENVELOPE_CHUNKS,
        "QT-CAP-005-P8": ENVELOPE_GRAPH_VERSIONS,
    }
    assert promotion.get("phase9_image_ids") == dict(PHASE09_IMAGE_IDS)
    assert promotion.get("paradedb_image") == PARADEDB_IMAGE
    assert promotion.get("valkey_image") == VALKEY_IMAGE
    assert ENVELOPE_HYBRID_VERSIONS == 8
    assert ENVELOPE_CHUNKS == 16
    assert ENVELOPE_GRAPH_VERSIONS == 15
