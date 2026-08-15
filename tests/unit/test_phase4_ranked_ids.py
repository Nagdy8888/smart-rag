"""Unit tests for Phase 4 Packet 9 Wave 2 ranked-ID eval (no Docker)."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.materialize import (
    DocumentVisibility,
    GoldIdRecord,
    GoldIdSidecar,
)
from smart_rag_core.evaluation.ranked_ids import (
    QT_LAT_001_FIRST_EVIDENCE_P95_MS,
    CaseRetrieveOutcome,
    ScoringKind,
    evaluate_ranked_ids,
    load_eval_cases,
    recall_hit_at_k,
    report_to_json,
    score_case,
    score_evidence_unit,
    scoring_kind,
    sidecar_has_unmapped_chunks,
    table_dispatch_required,
)
from smart_rag_core.evaluation.schema import EvaluationCase, ExpectedRoute, RefusalKind
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.coverage import (
    CoverageDecision,
    CoverageSignal,
    HybridCoverage,
)
from smart_rag_core.retrieval.hybrid_run import (
    EvidenceLocator,
    EvidenceUnit,
    HybridRunResult,
)
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason

REPO_ROOT = Path(__file__).resolve().parents[2]
RANKED_MODULE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "evaluation"
    / "ranked_ids.py"
)
EVAL_SCRIPT = REPO_ROOT / "scripts" / "eval_phase4_ranked_ids.py"
BM25_SNIPPET = "bm25 snippet must never be cited"
CANONICAL_TEXT = "canonical raw_text for citation"


def _case(query_class: QueryClass) -> EvaluationCase:
    """Return one development case for the requested class.

    Args:
        query_class: Canonical query class.

    Returns:
        First matching Phase-4-owned development case.
    """

    return next(
        item
        for item in load_eval_cases("development")
        if item.query_class is query_class
    )


def _record(
    case: EvaluationCase,
    *,
    chunk_id: UUID | None,
    table_id: UUID | None = None,
    visibility: str = "company_visible",
    visible_to_actor: bool | None = None,
) -> GoldIdRecord:
    """Build one sidecar record for a labeled case.

    Args:
        case: Evaluation case.
        chunk_id: Mapped real chunk UUID, or None for dry-run rows.
        table_id: Optional mapped table UUID.
        visibility: Canonical visibility.
        visible_to_actor: Optional visibility override.

    Returns:
        Frozen gold-id record.
    """

    link = case.evidence_links[0] if case.evidence_links else None
    restricted = (
        case.query_class is QueryClass.ACL_NEGATIVE or case.acl_actor.restricted
    )
    vis: DocumentVisibility = "restricted" if restricted else "company_visible"
    if visibility == "restricted":
        vis = "restricted"
    return GoldIdRecord(
        case_id=case.case_id,
        split=case.split.value,
        query_class=case.query_class.value,
        synthetic_chunk_id=link.chunk_id if link is not None else None,
        synthetic_table_id=link.table_id if link is not None else None,
        synthetic_source_id=link.source_id if link is not None else None,
        synthetic_version_id=link.version_id if link is not None else None,
        chunk_id=chunk_id,
        table_id=table_id,
        document_id=uuid4() if chunk_id or table_id else None,
        version_id=uuid4() if chunk_id or table_id else None,
        visibility=vis,
        labeled_actor_id=case.acl_actor.actor_id,
        restricted_actor=restricted,
        visible_to_actor=(
            False
            if restricted
            else (link.visible_to_actor if link is not None else True)
            if visible_to_actor is None
            else visible_to_actor
        ),
    )


def _sidecar(records: tuple[GoldIdRecord, ...]) -> GoldIdSidecar:
    """Wrap records in a holdout-closed sidecar.

    Args:
        records: Gold-id rows.

    Returns:
        Sidecar model with ``holdout_opened=False``.
    """

    splits = tuple(dict.fromkeys(item.split for item in records))
    return GoldIdSidecar(
        splits=splits or ("development",),
        case_count=len({item.case_id for item in records}),
        records=records,
        holdout_opened=False,
    )


def _result(
    ranked_ids: tuple[UUID, ...],
    *,
    evidence: tuple[EvidenceUnit, ...] = (),
    first_evidence_ms: float = 12.0,
    decision: CoverageDecision | None = CoverageDecision.ANSWER,
) -> HybridRunResult:
    """Build a fake Hybrid retrieve result.

    Args:
        ranked_ids: Final ranked chunk ids.
        evidence: Evidence units.
        first_evidence_ms: Timing sample.
        decision: Coverage decision.

    Returns:
        Frozen Hybrid run result.
    """

    return HybridRunResult(
        ranked_ids=ranked_ids,
        evidence=evidence,
        coverage=HybridCoverage(
            signal=CoverageSignal.NONE,
            decision=decision,
        ),
        fallback_reason=RetrievalFallbackReason.NONE,
        deadline_exhausted=False,
        first_evidence_ms=first_evidence_ms,
        embedding_call_count=1,
        rerank_call_count=1,
    )


def _unit(
    chunk_id: UUID,
    *,
    citation_text: str = CANONICAL_TEXT,
    page: int | None = 1,
    section: tuple[str, ...] = ("Overview",),
    sheet_name: str | None = None,
    range_ref: str | None = None,
) -> EvidenceUnit:
    """Build one fake evidence unit.

    Args:
        chunk_id: Chunk UUID.
        citation_text: Citation payload.
        page: Page locator.
        section: Section path.
        sheet_name: Optional sheet.
        range_ref: Optional range.

    Returns:
        Frozen evidence unit.
    """

    return EvidenceUnit(
        chunk_id=chunk_id,
        document_id=uuid4(),
        version_id=uuid4(),
        citation_text=citation_text,
        locator=EvidenceLocator(
            page_number=page,
            section_path=section,
            sheet_name=sheet_name,
            range_ref=range_ref,
        ),
    )


def _context(unit: EvidenceUnit, *, raw_text: str = CANONICAL_TEXT) -> ChunkContext:
    """Build canonical context matching an evidence unit.

    Args:
        unit: Evidence unit identity and locators.
        raw_text: Canonical raw_text.

    Returns:
        Frozen chunk context.
    """

    return ChunkContext(
        chunk_id=unit.chunk_id,
        document_id=unit.document_id,
        version_id=unit.version_id,
        parent_chunk_id=None,
        chunk_index=0,
        page_number=unit.locator.page_number,
        section_path=unit.locator.section_path,
        token_count=8,
        raw_text=raw_text,
        is_search_representative=True,
        sheet_name=unit.locator.sheet_name,
        range_ref=unit.locator.range_ref,
        source_url=unit.locator.source_url,
    )


def test_recall_at_k_math_on_fake_ranked_ids() -> None:
    """Gold UUID in top-10 is a hit; rank 11 is a miss; exact-code uses @5."""

    gold = uuid4()
    filler = tuple(uuid4() for _ in range(12))
    assert recall_hit_at_k((gold, *filler), (gold,), 10) is True
    assert recall_hit_at_k((*filler[:10], gold), (gold,), 10) is False
    assert recall_hit_at_k((*filler[:4], gold), (gold,), 5) is True
    assert recall_hit_at_k((*filler[:5], gold), (gold,), 5) is False
    exact = _case(QueryClass.EXACT_CODE)
    alias = _case(QueryClass.ALIAS)
    gold_exact = uuid4()
    gold_alias = uuid4()
    sidecar = _sidecar(
        (
            _record(exact, chunk_id=gold_exact),
            _record(alias, chunk_id=gold_alias),
        )
    )
    outcomes = {
        exact.case_id: CaseRetrieveOutcome(
            result=_result((gold_exact, *filler)),
        ),
        alias.case_id: CaseRetrieveOutcome(
            result=_result((*filler[:3], gold_alias)),
        ),
    }
    report = evaluate_ranked_ids(
        [exact, alias],
        sidecar,
        outcomes,
        split="development",
        embeddings="openai",
    )
    assert report.holdout_opened is False
    assert report.sidecar_unmapped is False
    assert report.recall_at_10 == 1.0
    assert report.exact_code_recall_at_5 == 1.0
    assert report.alias_recall_at_10 == 1.0
    miss_exact = evaluate_ranked_ids(
        [exact],
        sidecar,
        {
            exact.case_id: CaseRetrieveOutcome(
                result=_result((*filler[:5], gold_exact)),
            )
        },
        split="development",
        embeddings="openai",
    )
    assert miss_exact.exact_code_recall_at_5 == 0.0
    assert miss_exact.recall_at_10 == 1.0
    assert miss_exact.follow_up is not None


def test_acl_negative_gold_uuid_is_a_leak() -> None:
    """Restricted gold UUID in ranked_ids fails ACL and is not Recall@K."""

    case = _case(QueryClass.ACL_NEGATIVE)
    gold = uuid4()
    sidecar = _sidecar((_record(case, chunk_id=gold),))
    leak = evaluate_ranked_ids(
        [case],
        sidecar,
        {case.case_id: CaseRetrieveOutcome(result=_result((gold, uuid4())))},
        split="development",
        embeddings="openai",
    )
    assert leak.acl_leak_count == 1
    assert leak.recall_case_count == 0
    assert leak.scores[0].scoring_kind is ScoringKind.ACL
    assert leak.scores[0].recall_hit_at_10 is None
    clean = evaluate_ranked_ids(
        [case],
        sidecar,
        {case.case_id: CaseRetrieveOutcome(result=_result((uuid4(),)))},
        split="development",
        embeddings="openai",
    )
    assert clean.acl_leak_count == 0


def test_locator_mismatch_fails() -> None:
    """Page/section that does not match gold locator fails correctness."""

    case = _case(QueryClass.EXACT_CODE)
    gold = uuid4()
    sidecar = _sidecar((_record(case, chunk_id=gold),))
    unit = _unit(gold, page=9, section=("Wrong",))
    scored = score_case(
        case,
        sidecar,
        CaseRetrieveOutcome(result=_result((gold,), evidence=(unit,))),
    )
    assert scored.locator_units == 1
    assert scored.locator_correct_units == 0
    assert "page_mismatch" in scored.locator_failures
    assert "section_mismatch" in scored.locator_failures


def test_bm25_text_citation_fails() -> None:
    """citation_text equal to a BM25 snippet is never locator-correct."""

    case = _case(QueryClass.SEMANTIC_FACTUAL)
    gold = uuid4()
    sidecar = _sidecar((_record(case, chunk_id=gold),))
    unit = _unit(gold, citation_text=BM25_SNIPPET)
    context = _context(unit, raw_text=CANONICAL_TEXT)
    ok, codes = score_evidence_unit(
        unit,
        case=case,
        sidecar=sidecar,
        context=context,
        forbidden_citation_text=BM25_SNIPPET,
    )
    assert ok is False
    assert "citation_bm25_text" in codes
    assert "citation_not_raw_text" in codes
    good = _unit(gold, citation_text=CANONICAL_TEXT)
    good_context = _context(good, raw_text=CANONICAL_TEXT)
    ok_good, _codes = score_evidence_unit(
        good,
        case=case,
        sidecar=sidecar,
        context=good_context,
        forbidden_citation_text=BM25_SNIPPET,
    )
    assert ok_good is True


def test_holdout_ast_guard_on_ranked_ids_and_eval_script() -> None:
    """Ranked-ID sources must not reference sealed-label loaders."""

    for path in (RANKED_MODULE, EVAL_SCRIPT):
        source = path.read_text(encoding="utf-8")
        dumped = ast.dump(ast.parse(source, filename=str(path)))
        assert "load_holdout" not in dumped
        assert "HoldoutAccess" not in dumped
        assert "HOLDOUT" not in dumped
        assert "evaluation.holdout" not in source
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "holdout":
                raise AssertionError(f"{path.name} contains a holdout loader string")


def test_refusal_classes_are_not_recall_at_k() -> None:
    """insufficient/media/negation/document_summary are coverage, not Recall@K."""

    classes = (
        QueryClass.INSUFFICIENT_REFUSAL,
        QueryClass.MEDIA_LIMITATION,
        QueryClass.NEGATION,
        QueryClass.DOCUMENT_SUMMARY,
    )
    records: list[GoldIdRecord] = []
    outcomes: dict[str, CaseRetrieveOutcome] = {}
    cases: list[EvaluationCase] = []
    for query_class in classes:
        case = _case(query_class)
        cases.append(case)
        assert scoring_kind(case) is ScoringKind.REFUSAL
        gold = uuid4() if case.evidence_links else None
        records.append(_record(case, chunk_id=gold))
        decision = CoverageDecision.REFUSE
        ranked = (gold,) if gold is not None else (uuid4(),)
        outcomes[case.case_id] = CaseRetrieveOutcome(
            result=_result(ranked, decision=decision),
        )
    sidecar = _sidecar(tuple(records))
    report = evaluate_ranked_ids(
        cases,
        sidecar,
        outcomes,
        split="development",
        embeddings="openai",
    )
    assert report.recall_case_count == 0
    assert report.recall_at_10 is None
    assert report.refusal_case_count == 4
    assert all(row.recall_hit_at_10 is None for row in report.scores)
    assert all(row.scoring_kind is ScoringKind.REFUSAL for row in report.scores)


def test_null_sidecar_fail_closed_does_not_report_recall() -> None:
    """Dry-run null chunk_id sidecars fail closed with holdout_opened false."""

    case = _case(QueryClass.EXACT_CODE)
    sidecar = _sidecar((_record(case, chunk_id=None),))
    assert sidecar_has_unmapped_chunks(sidecar) is True
    gold = uuid4()
    report = evaluate_ranked_ids(
        [case],
        sidecar,
        {case.case_id: CaseRetrieveOutcome(result=_result((gold,)))},
        split="development",
        embeddings="openai",
    )
    payload = report_to_json(report)
    assert payload["holdout_opened"] is False
    assert payload["sidecar_unmapped"] is True
    assert payload["recall_at_10"] is None
    assert payload["exact_code_recall_at_5"] is None
    assert payload["alias_recall_at_10"] is None
    assert payload["qt_eval_006_live"] is False


def test_occupancy_helpers_are_not_the_ranked_id_metric() -> None:
    """coverage_eval occupancy helpers must not be imported as Recall@K."""

    source = RANKED_MODULE.read_text(encoding="utf-8")
    dumped = ast.dump(ast.parse(source, filename=str(RANKED_MODULE)))
    imported: set[str] = set()
    tree = ast.parse(source, filename=str(RANKED_MODULE))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert "smart_rag_core.evaluation.coverage_eval" not in imported
    assert "simulate_fused" not in imported
    assert "simulate_fused" not in dumped
    from smart_rag_core.evaluation import coverage_eval, ranked_ids

    assert ranked_ids.evaluate_ranked_ids is not coverage_eval.score_case
    assert ranked_ids.recall_hit_at_k is not coverage_eval.simulate_fused


def test_tabular_aggregation_uses_table_executor_not_recall() -> None:
    """tabular_aggregation binds Packet 7 and is excluded from Recall@K."""

    case = _case(QueryClass.TABULAR_AGGREGATION)
    assert table_dispatch_required(case) is True
    assert scoring_kind(case) is ScoringKind.TABLE
    exact = _case(QueryClass.EXACT_CODE)
    assert table_dispatch_required(exact) is False
    gold = uuid4()
    table_id = uuid4()
    sidecar = _sidecar(
        (
            _record(case, chunk_id=None, table_id=table_id),
            _record(exact, chunk_id=gold),
        )
    )
    called: list[str] = []

    def _executor(item: EvaluationCase, _sidecar: GoldIdSidecar) -> bool:
        """Record Packet 7 dispatch.

        Args:
            item: Evaluation case.
            _sidecar: Gold-id sidecar.

        Returns:
            True to mark the executor as completed.
        """

        called.append(item.case_id)
        return True

    report = evaluate_ranked_ids(
        [case, exact],
        sidecar,
        {
            exact.case_id: CaseRetrieveOutcome(result=_result((gold,))),
            case.case_id: CaseRetrieveOutcome(),
        },
        split="development",
        embeddings="openai",
        table_executor=_executor,
    )
    assert called == [case.case_id]
    assert report.table_case_count == 1
    assert report.table_executed_count == 1
    assert report.recall_case_count == 1
    assert report.recall_at_10 == 1.0
    table_row = next(row for row in report.scores if row.case_id == case.case_id)
    assert table_row.table_path_used is True
    assert table_row.recall_hit_at_10 is None


def test_mock_embeddings_are_not_live_qt_eval_006() -> None:
    """MOCK_MODEL_MODE Recall@10 must not be labeled live QT-EVAL-006."""

    case = _case(QueryClass.EXACT_CODE)
    gold = uuid4()
    sidecar = _sidecar((_record(case, chunk_id=gold),))
    report = evaluate_ranked_ids(
        [case],
        sidecar,
        {case.case_id: CaseRetrieveOutcome(result=_result((gold,)))},
        split="development",
        embeddings="mock",
    )
    payload = report_to_json(report)
    assert payload["embeddings"] == "mock"
    assert payload["qt_eval_006_live"] is False
    assert payload["recall_at_10"] == 1.0
    live = evaluate_ranked_ids(
        [case],
        sidecar,
        {case.case_id: CaseRetrieveOutcome(result=_result((gold,)))},
        split="development",
        embeddings="openai",
    )
    assert live.qt_eval_006_live is True


def test_first_evidence_p95_does_not_raise_qt_lat_001() -> None:
    """p95 is reported against the signed 2s gate; the gate is not raised."""

    case = _case(QueryClass.TYPO)
    gold = uuid4()
    sidecar = _sidecar((_record(case, chunk_id=gold),))
    outcomes = {
        case.case_id: CaseRetrieveOutcome(
            result=_result((gold,), first_evidence_ms=3500.0),
        )
    }
    report = evaluate_ranked_ids(
        [case],
        sidecar,
        outcomes,
        split="development",
        embeddings="openai",
    )
    assert report.first_evidence_p95_ms == 3500.0
    assert report.qt_lat_001_ms == QT_LAT_001_FIRST_EVIDENCE_P95_MS
    assert report.qt_lat_001_ms == 2000.0
    assert report.follow_up is not None
    assert "hardware" in report_to_json(report)


def test_cli_fail_closed_json_on_unmapped_sidecar(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI prints fail-closed JSON and exits 2 when chunk_id is null."""

    import importlib.util

    case = _case(QueryClass.EXACT_CODE)
    sidecar = _sidecar((_record(case, chunk_id=None),))
    path = tmp_path / "gold_id_map.json"
    path.write_text(
        json.dumps(sidecar.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("eval_phase4_ranked_ids", EVAL_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    code = module.main(
        ["--sidecar", str(path), "--split", "development", "--limit", "3"]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 2
    assert payload["holdout_opened"] is False
    assert payload["sidecar_unmapped"] is True
    assert payload["recall_at_10"] is None
    assert payload["qt_eval_006_live"] is False
    assert "first_evidence_p95_ms" in payload
    assert "cost" in payload
    assert payload["embeddings"] in {"mock", "openai"}


def test_load_eval_cases_is_phase4_open_split_only() -> None:
    """Eval case loader uses select_phase4_retrieve_cases, not sealed labels."""

    cases = load_eval_cases("development", limit=5)
    assert len(cases) == 5
    assert all(item.split.value == "development" for item in cases)
    assert all(
        item.query_class
        not in {
            QueryClass.RELATIONSHIP,
            QueryClass.MULTI_HOP,
            QueryClass.GRAPH_MAPPING,
            QueryClass.PROMPT_INJECTION,
        }
        for item in cases
    )
    refusal = _case(QueryClass.INSUFFICIENT_REFUSAL)
    assert refusal.expected_route is ExpectedRoute.REFUSAL or (
        refusal.refusal_kind is not RefusalKind.NONE
    )
