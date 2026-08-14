"""Unit tests for Packet 6 coverage score, freeze, and prohibited methods."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from uuid import uuid4

import pytest
from smart_rag_core.evaluation.calibration import load_tuning_cases
from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.coverage_eval import gold_should_answer, score_case
from smart_rag_core.evaluation.loader import (
    load_development_cases,
    load_qualification_cases,
)
from smart_rag_core.evaluation.schema import (
    DatasetSplit,
    ExpectedRoute,
    FailureStage,
    QueryType,
)
from smart_rag_core.retrieval.coverage import (
    CoverageDecision,
    CoverageSignal,
    HybridCoverage,
)
from smart_rag_core.retrieval.coverage_score import (
    CoverageComponents,
    attach_numeric_coverage,
    coverage_score,
    first_failing_stage,
    profile_minimum_for,
    ranking_claim_allowed,
)
from smart_rag_core.retrieval.frozen_profile import (
    FROZEN_HYBRID_PROFILE_SHA256,
    FrozenProfileMutationError,
    UnknownRetrievalProfileError,
    canonical_profile_digest,
    coverage_threshold_for,
    load_frozen_profile,
)
from smart_rag_core.retrieval.hybrid import assemble_hybrid
from smart_rag_core.retrieval.profiles import (
    HYBRID_DEFAULT_PROFILE_ID,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.prohibited import (
    PROHIBITED_IMPORT_NAMES,
    scan_lockfile,
    scan_pyproject_files,
)
from smart_rag_core.retrieval.types import RetrievalCandidate

REPO_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_SCRIPT = REPO_ROOT / "scripts" / "eval_coverage_calibration.py"
QUALIFICATION_SCRIPT = REPO_ROOT / "scripts" / "eval_coverage_qualification.py"
CALIBRATION_MODULE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "evaluation"
    / "calibration.py"
)
COVERAGE_EVAL_MODULE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "evaluation"
    / "coverage_eval.py"
)


def _candidate() -> RetrievalCandidate:
    """Build one synthetic authorized candidate.

    Returns:
        Frozen candidate.
    """

    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )


def test_coverage_formula_and_class_minima() -> None:
    """The plan formula and type minima are deterministic."""

    assert profile_minimum_for(QueryType.FACTUAL, subquestion_count=3) == 1
    assert (
        profile_minimum_for(QueryType.RELATIONSHIP_MULTI_HOP, subquestion_count=1) == 2
    )
    assert profile_minimum_for(QueryType.BROAD_SUMMARY, subquestion_count=1) == 3
    assert profile_minimum_for(QueryType.MULTI_PART, subquestion_count=3) == 3
    score = coverage_score(
        CoverageComponents(
            required_term_entity_coverage=1.0,
            subquestion_coverage=1.0,
            evidence_ratio=1.0,
            support_confidence=0.60,
            distinct_evidence_count=1,
            profile_minimum=1,
        )
    )
    assert score == pytest.approx(0.60)


def test_numeric_refuse_does_not_overwrite_media_signal() -> None:
    """Media limitation stays the primary signal when numeric score is attached."""

    item = _candidate()
    result = assemble_hybrid(
        dense_variants=((item,),),
        bm25_variants=(),
        term_variants=(),
        media_dependence=True,
        principal_scope_hash="abc",
        query_normalized="chart",
        visibility_generation=1,
    )
    assert result.coverage.signal is CoverageSignal.MEDIA_LIMITATION
    assert result.coverage.decision is CoverageDecision.REFUSE
    assert result.coverage.coverage_score is not None


def test_weak_single_channel_factual_refuses_at_baseline() -> None:
    """A single-channel factual winner has support 0.60 and refuses at 0.65."""

    item = _candidate()
    result = assemble_hybrid(
        dense_variants=((item,),),
        bm25_variants=(),
        term_variants=(),
        principal_scope_hash="abc",
        query_normalized="what is retention",
        visibility_generation=1,
        query_type=QueryType.FACTUAL,
        query_class=QueryClass.SEMANTIC_FACTUAL,
    )
    assert result.coverage.coverage_score == pytest.approx(0.60)
    assert result.coverage.decision is CoverageDecision.REFUSE
    assert result.coverage.signal is CoverageSignal.WEAK_EVIDENCE
    assert result.coverage.first_failing_stage is FailureStage.COVERAGE


def test_two_channel_exact_supports_answer() -> None:
    """Exact two-channel winners reach support 1.0 and may answer."""

    item = _candidate()
    result = assemble_hybrid(
        dense_variants=((item,),),
        bm25_variants=(),
        term_variants=((item,),),
        principal_scope_hash="abc",
        query_normalized="INV-SR-1001",
        visibility_generation=1,
        query_type=QueryType.EXACT_IDENTIFIER,
        query_class=QueryClass.EXACT_CODE,
        exact_phrase_or_code=True,
    )
    assert result.coverage.support_confidence == pytest.approx(1.0)
    assert result.coverage.decision is CoverageDecision.ANSWER
    assert result.coverage.first_failing_stage is FailureStage.NONE


def test_bm25_degraded_keeps_signal_and_applies_threshold() -> None:
    """BM25 outage stays visible; the numeric threshold can still refuse."""

    item = _candidate()
    weak = assemble_hybrid(
        dense_variants=((item,),),
        bm25_variants=(),
        term_variants=(),
        bm25_fallback=RetrievalFallbackReason.BM25_UNAVAILABLE,
        principal_scope_hash="abc",
        query_normalized="what is retention",
        visibility_generation=1,
        query_type=QueryType.FACTUAL,
        query_class=QueryClass.SEMANTIC_FACTUAL,
    )
    assert weak.coverage.signal is CoverageSignal.BM25_DEGRADED
    assert weak.coverage.decision is CoverageDecision.REFUSE
    strong = assemble_hybrid(
        dense_variants=((item,),),
        bm25_variants=(),
        term_variants=((item,),),
        bm25_fallback=RetrievalFallbackReason.BM25_UNAVAILABLE,
        principal_scope_hash="abc",
        query_normalized="INV-SR-1001",
        visibility_generation=1,
        query_type=QueryType.EXACT_IDENTIFIER,
        query_class=QueryClass.EXACT_CODE,
        exact_phrase_or_code=True,
    )
    assert strong.coverage.signal is CoverageSignal.BM25_DEGRADED
    assert strong.coverage.decision is CoverageDecision.ANSWER


def test_profile_failure_is_attributed_before_ranking() -> None:
    """Ranking is not blamed when the profile stage failed."""

    coverage = attach_numeric_coverage(
        HybridCoverage(signal=CoverageSignal.NONE),
        fused=(_candidate(),),
        channel_hits=None,
        profile_ok=False,
        pre_recheck_count=10,
        authorized_count=10,
    )
    assert coverage.first_failing_stage is FailureStage.PROFILE


def test_first_failing_stage_candidate_before_coverage() -> None:
    """Empty candidate generation is attributed before coverage."""

    empty = HybridCoverage(
        signal=CoverageSignal.WEAK_EVIDENCE,
        decision=CoverageDecision.REFUSE,
    )
    stage = first_failing_stage(
        profile_ok=True,
        pre_recheck_count=0,
        authorized_count=0,
        fused_count=0,
        context_ok=True,
        coverage=empty,
    )
    assert stage is FailureStage.CANDIDATE


def test_unknown_runtime_profile_fails() -> None:
    """Unknown profile ids fail closed."""

    with pytest.raises(UnknownRetrievalProfileError):
        load_frozen_profile("hybrid_experimental_v2")
    with pytest.raises(UnknownRetrievalProfileError):
        load_frozen_profile("hybrid_packet5_v1")


def test_frozen_profile_hash_mismatch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutating the frozen artifact after pin is a runtime failure."""

    from smart_rag_core.retrieval import frozen_profile as module

    original = json.loads(module.FROZEN_PROFILE_PATH.read_text(encoding="utf-8"))
    original["rrf_k"] = 99
    mutated = tmp_path / "hybrid_default_v1.json"
    mutated.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(module, "FROZEN_PROFILE_PATH", mutated)
    with pytest.raises(FrozenProfileMutationError):
        load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)


def test_hardcoded_threshold_is_tethered_to_frozen_profile() -> None:
    """Runtime thresholds come from the hashed profile, not a bare literal."""

    assert coverage_threshold_for(QueryClass.EXACT_CODE) == pytest.approx(0.65)
    digest = canonical_profile_digest(
        json.loads(
            (
                REPO_ROOT
                / "packages"
                / "core"
                / "src"
                / "smart_rag_core"
                / "retrieval"
                / "frozen"
                / "hybrid_default_v1.json"
            ).read_text(encoding="utf-8")
        )
    )
    assert digest == FROZEN_HYBRID_PROFILE_SHA256


def test_tuning_is_development_only() -> None:
    """Calibration cannot see qualification or holdout labels."""

    tuning = load_tuning_cases()
    development = load_development_cases()
    qualification = load_qualification_cases()
    assert {case.case_id for case in tuning} == {case.case_id for case in development}
    assert {case.case_id for case in tuning}.isdisjoint(
        {case.case_id for case in qualification}
    )
    assert all(case.split is DatasetSplit.DEVELOPMENT for case in tuning)
    source = CALIBRATION_MODULE.read_text(encoding="utf-8")
    tree = ast.dump(ast.parse(source))
    assert "HOLDOUT" not in tree
    assert "load_holdout" not in tree
    assert "load_open_splits" not in tree
    assert "load_development_cases" in tree


def test_calibration_scripts_cannot_read_holdout() -> None:
    """Packet 6 eval scripts are holdout-blind."""

    for path in (CALIBRATION_SCRIPT, QUALIFICATION_SCRIPT, COVERAGE_EVAL_MODULE):
        dumped = ast.dump(ast.parse(path.read_text(encoding="utf-8")))
        assert "HOLDOUT" not in dumped
        assert "load_holdout" not in dumped


def test_development_gold_has_no_false_supported_at_frozen_threshold() -> None:
    """Frozen thresholds do not emit false-supported answers on development."""

    outcomes = [score_case(case) for case in load_development_cases()]
    assert outcomes
    assert not any(item.false_supported for item in outcomes)
    assert any(gold_should_answer(case) for case in load_development_cases())
    deferred = [
        case
        for case in load_development_cases()
        if case.expected_route
        in {
            ExpectedRoute.COMBINED,
            ExpectedRoute.STRUCTURED_TABLE,
            ExpectedRoute.GRAPH_INSPECTION,
        }
    ]
    assert deferred
    assert all(not gold_should_answer(case) for case in deferred)


def test_qualification_fail_is_not_relabeled_pass() -> None:
    """The qualification script records FAIL when false-supported is non-zero."""

    source = QUALIFICATION_SCRIPT.read_text(encoding="utf-8")
    assert 'status = "PASS" if passed else "FAIL"' in source
    assert "return 0 if passed else 1" in source
    assert "do not retune" in source.lower()
    dumped = ast.dump(ast.parse(source))
    assert "sweep_thresholds" not in dumped
    assert "load_development_cases" not in dumped


def test_acl_negative_is_authorization_not_ranking() -> None:
    """ACL-filtered gold occupancy is attributed before ranking."""

    cases = [
        case
        for case in load_development_cases()
        if case.query_class is QueryClass.ACL_NEGATIVE
    ]
    assert cases
    outcome = score_case(cases[0])
    assert outcome.first_failing_stage is FailureStage.AUTHORIZATION
    assert not ranking_claim_allowed(outcome.first_failing_stage)
    assert outcome.predicted is CoverageDecision.REFUSE
    assert not outcome.false_supported


def test_frozen_profile_covers_every_query_class() -> None:
    """Every labeled class has a frozen threshold; unequal weights are off."""

    profile = load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)
    assert profile.unequal_channel_weights_selected is False
    assert profile.rrf_k == 60
    for query_class in QueryClass:
        assert query_class.value in profile.coverage_thresholds
        assert profile.coverage_thresholds[query_class.value] == pytest.approx(0.65)


def test_prohibited_methods_absent_from_lock_and_pyproject() -> None:
    """HyDE/RAPTOR/SPLADE/ColBERT/local rerankers are not installed."""

    lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert scan_lockfile(lock) == ()
    assert scan_pyproject_files(REPO_ROOT) == ()
    for path in (REPO_ROOT / "packages").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = tuple(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = (node.module.split(".", 1)[0],)
            else:
                continue
            for name in names:
                assert name not in PROHIBITED_IMPORT_NAMES
