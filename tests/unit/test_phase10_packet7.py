"""Unit tests for Phase 10 Packet 7 suite, assessment, and promotion negatives."""

from __future__ import annotations

from pathlib import Path

import pytest
from smart_rag_core.release.phase10_constants import (
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    PHASE09_IMAGE_IDS,
    PHASE11_NO_GO_RECOMMENDATION,
    USER_ACCEPTANCE_REQUEST,
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
from smart_rag_core.release.phase10_packet6 import packet6_checkbox_unchecked
from smart_rag_core.release.phase10_packet7 import (
    AcceptanceRow,
    PacketMatrixRecord,
    Phase10Packet7GateError,
    all_phase10_checkboxes_unchecked,
    assert_holdout_sealed,
    assert_no_fake_assessment,
    assert_no_full_scale_claim,
    assert_wrapper_pending_unchecked,
    claims_fake_assessment_pass,
    claims_full_scale_envelope,
    classify_p1007_a,
    classify_p1007_b,
    classify_p1007_c,
    classify_p1007_d,
    classify_p1007_e,
    fake_origin_http_claimed,
    freeze_image_ids_match,
    later_phase10_checkboxes_unchecked,
    packet7_checkbox_unchecked,
    recommendation_is_go,
)

_UNCHECKED_WRAPPER = """---
status: pending
---
1. [ ] [Provision isolated managed Supabase
2. [ ] [Implement GitHub OIDC, protected immutable expand/contract
3. [ ] [Prove direct-origin rejection, provider/crawl/parser egress
4. [ ] [Exercise asymmetric JWKS rollover, dual origin-secret rotation
5. [ ] [Exercise staging KMS/S3 Object Lock audit anchors, OpenAI/AWS/Supabase billing
6. [ ] [Perform and record database-plus-Storage restore/reconciliation
7. [ ] [Run the complete release suite and an independent external security assessment
"""

_PACKET_PENDING = """---
status: pending
---
"""


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


def test_fake_pentest_passed_fails() -> None:
    """Invented pentest Passed or Critical=0 is Failed, not a real assessment."""

    assert claims_fake_assessment_pass("scope only, status not run") is False
    assert claims_fake_assessment_pass("independent assessment passed") is True
    assert claims_fake_assessment_pass('"critical_open": 0') is True
    assert claims_fake_assessment_pass("Trivy as pentest") is True
    with pytest.raises(Phase10Packet7GateError, match="completed pentest"):
        assert_no_fake_assessment(
            "Independent assessment Passed with Critical=0",
            source="fake-report",
        )
    assert (
        classify_p1007_c(
            scope_ok=True,
            assessment_run=False,
            invented_pass=True,
        )
        == "Failed"
    )


def test_checkbox_checked_fails() -> None:
    """Checking Packet 7 fails Packet 7-E and evaluate."""

    checked = _UNCHECKED_WRAPPER.replace(
        "7. [ ] [Run the complete release suite",
        "7. [x] [Run the complete release suite",
    )
    assert packet7_checkbox_unchecked(_UNCHECKED_WRAPPER) is True
    assert packet7_checkbox_unchecked(checked) is False
    assert all_phase10_checkboxes_unchecked(_UNCHECKED_WRAPPER) is True
    assert all_phase10_checkboxes_unchecked(checked) is False
    with pytest.raises(Phase10Packet7GateError, match="packets 2-7"):
        assert_wrapper_pending_unchecked(checked, _PACKET_PENDING)
    assert (
        classify_p1007_e(
            manifest_ok=True,
            wrapper_pending=True,
            all_unchecked=False,
            nogo=True,
            envelope_ok=True,
            holdout_closed=True,
            acceptance_request=True,
        )
        == "Failed"
    )


def test_packet1_checked_still_allows_packet7_pending_gate() -> None:
    """Packet 1 may be checked while packets 2-7 stay unchecked."""

    checked_packet1 = _UNCHECKED_WRAPPER.replace(
        "1. [ ] [Provision isolated managed Supabase",
        "1. [x] [Provision isolated managed Supabase",
    )
    assert packet1_checkbox_unchecked(checked_packet1) is False
    assert later_phase10_checkboxes_unchecked(checked_packet1) is True
    assert all_phase10_checkboxes_unchecked(checked_packet1) is False
    assert_wrapper_pending_unchecked(checked_packet1, _PACKET_PENDING)


def test_wrapper_complete_fails() -> None:
    """Setting the Phase 10 wrapper complete is Failed."""

    complete = _UNCHECKED_WRAPPER.replace("status: pending", "status: complete", 1)
    assert wrapper_status_pending(_UNCHECKED_WRAPPER) is True
    assert wrapper_status_pending(complete) is False
    with pytest.raises(Phase10Packet7GateError, match="pending"):
        assert_wrapper_pending_unchecked(complete, _PACKET_PENDING)
    assert (
        classify_p1007_e(
            manifest_ok=True,
            wrapper_pending=False,
            all_unchecked=True,
            nogo=True,
            envelope_ok=True,
            holdout_closed=True,
            acceptance_request=True,
        )
        == "Failed"
    )


def test_digest_drift_fails() -> None:
    """Phase 9 freeze digest drift fails Packet 7-D."""

    assert freeze_image_ids_match(PHASE09_IMAGE_IDS) is True
    drifted = dict(PHASE09_IMAGE_IDS)
    drifted["api"] = "sha256:deadbeef"
    assert freeze_image_ids_match(drifted) is False
    assert (
        classify_p1007_d(
            freeze_match=False,
            suite_blocked=True,
            assessment_blocked=True,
            live_blocked=True,
        )
        == "Failed"
    )


def test_ten_k_claim_fails() -> None:
    """Advertising 10k/1M or a Phase 11 go fails Packet 7-E."""

    assert claims_full_scale_envelope('"QT-CAP-001-P9": 8') is False
    assert claims_full_scale_envelope('"QT-CAP-001-P9": 10000') is True
    with pytest.raises(Phase10Packet7GateError, match="10k/1M"):
        assert_no_full_scale_claim(
            '{"QT-CAP-001-P9": 10000, "QT-CAP-002-P9": 1000000}',
            source="promotion",
        )
    assert recommendation_is_go(PHASE11_NO_GO_RECOMMENDATION) is False
    assert recommendation_is_go("go for Phase 11") is True
    assert (
        classify_p1007_e(
            manifest_ok=True,
            wrapper_pending=True,
            all_unchecked=True,
            nogo=False,
            envelope_ok=False,
            holdout_closed=True,
            acceptance_request=True,
        )
        == "Failed"
    )
    assert ENVELOPE_HYBRID_VERSIONS == 8
    assert ENVELOPE_CHUNKS == 16
    assert ENVELOPE_GRAPH_VERSIONS == 15


def test_zero_packet_matrices_fail() -> None:
    """Missing or empty Packets 1-6 matrices fail the suite gate."""

    assert (
        classify_p1007_a(
            matrices_ok=False,
            blocked_launch_rows=False,
            zero_tests=False,
            claimed_suite_passed=False,
        )
        == "Failed"
    )
    assert (
        classify_p1007_a(
            matrices_ok=True,
            blocked_launch_rows=False,
            zero_tests=True,
            claimed_suite_passed=False,
        )
        == "Failed"
    )
    assert (
        classify_p1007_a(
            matrices_ok=True,
            blocked_launch_rows=True,
            zero_tests=False,
            claimed_suite_passed=True,
        )
        == "Failed"
    )
    empty = PacketMatrixRecord(
        packet="P10-01",
        schema_version="phase10-packet1-matrix-v1",
        path="missing.json",
        acceptance=(),
        image_ids=dict(PHASE09_IMAGE_IDS),
        holdout_opened=False,
        wrapper_status="pending",
        live_fields={},
    )
    assert empty.acceptance == ()


def test_holdout_opened_fails() -> None:
    """Opening holdout fails Packet 7-E."""

    assert (
        classify_p1007_e(
            manifest_ok=True,
            wrapper_pending=True,
            all_unchecked=True,
            nogo=True,
            envelope_ok=True,
            holdout_closed=False,
            acceptance_request=True,
        )
        == "Failed"
    )
    opened = PacketMatrixRecord(
        packet="P10-01",
        schema_version="phase10-packet1-matrix-v1",
        path="docs/deployment/phase-10/packet1-gate-matrix.json",
        acceptance=(
            AcceptanceRow(
                check="P10-01-A",
                classification="Passed",
                detail="n/a",
            ),
        ),
        image_ids=dict(PHASE09_IMAGE_IDS),
        holdout_opened=True,
        wrapper_status="pending",
        live_fields={},
    )
    assert opened.holdout_opened is True


def test_holdout_env_true_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """SMART_RAG_HOLDOUT_ACCESS=true is Failed for Packet 7."""

    monkeypatch.setenv("SMART_RAG_HOLDOUT_ACCESS", "true")
    monkeypatch.setenv("SMART_RAG_HOLDOUT_ACCESS_PURPOSE", "packet8_immutable_holdout")
    monkeypatch.setenv("SMART_RAG_HOLDOUT_ACCESS_ACTOR", "unit-test")
    with pytest.raises(Phase10Packet7GateError, match="HOLDOUT"):
        assert_holdout_sealed(Path(__file__).resolve().parents[2])


def test_honest_classifications_keep_suite_blocked_and_custody_passed() -> None:
    """A/C/D stay Blocked; B/E can Pass; fake 200/403 is Failed."""

    assert (
        classify_p1007_a(
            matrices_ok=True,
            blocked_launch_rows=True,
            zero_tests=False,
            claimed_suite_passed=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1007_b(
            custody_passed=True,
            fake_http=False,
            live_oidc_state="Blocked",
        )
        == "Passed"
    )
    assert (
        classify_p1007_b(
            custody_passed=True,
            fake_http=True,
            live_oidc_state="Blocked",
        )
        == "Failed"
    )
    assert (
        classify_p1007_c(
            scope_ok=True,
            assessment_run=False,
            invented_pass=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1007_d(
            freeze_match=True,
            suite_blocked=True,
            assessment_blocked=True,
            live_blocked=True,
        )
        == "Blocked"
    )
    assert (
        classify_p1007_e(
            manifest_ok=True,
            wrapper_pending=True,
            all_unchecked=True,
            nogo=True,
            envelope_ok=True,
            holdout_closed=True,
            acceptance_request=True,
        )
        == "Passed"
    )
    assert fake_origin_http_claimed(
        {
            "live_requests": "Blocked",
            "request_matrix": [
                {"case": "valid_cdn", "classification": "Passed", "http_status": 200}
            ],
        }
    )
    assert not fake_origin_http_claimed(
        {
            "live_requests": "Blocked",
            "request_matrix": [
                {
                    "case": "valid_cdn",
                    "classification": "Blocked",
                    "http_status": None,
                }
            ],
        }
    )
    blocked = _live_blocked()
    assert blocked.apply_state == "Blocked"
    assert packet1_checkbox_unchecked(_UNCHECKED_WRAPPER) is True
    assert packet2_checkbox_unchecked(_UNCHECKED_WRAPPER) is True
    assert packet3_checkbox_unchecked(_UNCHECKED_WRAPPER) is True
    assert packet4_checkbox_unchecked(_UNCHECKED_WRAPPER) is True
    assert packet5_checkbox_unchecked(_UNCHECKED_WRAPPER) is True
    assert packet6_checkbox_unchecked(_UNCHECKED_WRAPPER) is True
    assert USER_ACCEPTANCE_REQUEST.startswith("Request for user acceptance:")
    assert Path("docs/security/phase-10-external-assessment-scope.md").name.endswith(
        ".md"
    )
