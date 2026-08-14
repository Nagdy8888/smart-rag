"""Unit tests for Phase 4 Packet 8 freeze and holdout isolation."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from smart_rag_core.evaluation.holdout import HoldoutSealedError
from smart_rag_core.evaluation.phase4_freeze import (
    LAUNCH_DECISION_NO_GO,
    REQUIRED_ABLATION_IDS,
    build_phase4_freeze_report,
    render_freeze_markdown,
)
from smart_rag_core.retrieval.frozen_profile import FROZEN_HYBRID_PROFILE_SHA256

REPO_ROOT = Path(__file__).resolve().parents[2]
FREEZE_MODULE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "evaluation"
    / "phase4_freeze.py"
)
FREEZE_SCRIPT = REPO_ROOT / "scripts" / "eval_phase4_freeze.py"
FREEZE_DOC = REPO_ROOT / "docs" / "evaluation" / "PHASE4_FREEZE.md"


def test_freeze_is_no_go_without_opening_holdout() -> None:
    """Packet 8 freeze records no-go and never claims holdout was opened."""

    report = build_phase4_freeze_report()
    assert report.launch_decision == LAUNCH_DECISION_NO_GO
    assert report.holdout_opened is False
    assert report.profile_sha256 == FROZEN_HYBRID_PROFILE_SHA256
    assert report.development_case_count == 216
    assert report.qualification_case_count == 77
    assert report.open_split_case_count == 293
    assert report.holdout_manifest_case_count == 112
    assert report.deferred_open_split_count > 0
    assert report.sme_approval_status == "synthetic_provisional"
    assert report.client_decision == "pending_user_acceptance"
    assert report.hashes["hybrid_default_v1"] == FROZEN_HYBRID_PROFILE_SHA256
    assert any(gate.status == "blocker" for gate in report.gates)
    assert {item.ablation_id for item in report.ablations} == set(REQUIRED_ABLATION_IDS)
    assert all(item.live_recall_claimed is False for item in report.ablations)


def test_freeze_module_cannot_materialize_sealed_labels() -> None:
    """Freeze sources do not load sealed-split labels or case loaders."""

    for path in (FREEZE_MODULE, FREEZE_SCRIPT):
        dumped = ast.dump(ast.parse(path.read_text(encoding="utf-8")))
        assert "load_holdout" not in dumped
        assert "DatasetSplit" not in dumped
        assert "load_cases" not in dumped
        source = path.read_text(encoding="utf-8")
        assert "SMART_RAG_HOLDOUT_ACCESS=true" not in source


def test_freeze_refuses_enabled_holdout_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A freeze job cannot run in the same process as authorized holdout access."""

    monkeypatch.setenv("SMART_RAG_HOLDOUT_ACCESS", "true")
    monkeypatch.setenv(
        "SMART_RAG_HOLDOUT_ACCESS_PURPOSE",
        "packet8_immutable_holdout",
    )
    monkeypatch.setenv("SMART_RAG_HOLDOUT_ACCESS_ACTOR", "unit-test")
    with pytest.raises(HoldoutSealedError, match="refuses to run"):
        build_phase4_freeze_report()


def test_rendered_freeze_markdown_matches_committed_doc() -> None:
    """Committed freeze markdown is generated from the report, not hand-edited."""

    report = build_phase4_freeze_report()
    rendered = render_freeze_markdown(report)
    committed = FREEZE_DOC.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == rendered
    assert LAUNCH_DECISION_NO_GO in committed
    assert FROZEN_HYBRID_PROFILE_SHA256 in committed
