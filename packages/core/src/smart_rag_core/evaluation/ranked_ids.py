"""Holdout-blind ranked-ID, locator, ACL, table, and first-evidence eval.

Packet 9 Wave 2 scores Phase-4-owned open-split retrieve results. Gold
synthetic ids such as ``p4-chk-NNNN`` are joined through ``GoldIdSidecar``.
Occupancy helpers in ``coverage_eval`` are not Recall@K. This module never
loads sealed labels.

Recall@K uses ``HybridRunResult.ranked_ids`` after rerank/MMR when rerank
ran. Citation text must be canonical ``ChunkContext.raw_text``, never BM25
snippets. Frozen ``hybrid_default_v1`` is not retuned here.
"""

from __future__ import annotations

import json
import math
import platform
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from os import cpu_count
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.materialize import (
    GoldIdRecord,
    GoldIdSidecar,
    OpenSplitName,
    select_phase4_retrieve_cases,
)
from smart_rag_core.evaluation.schema import (
    EvaluationCase,
    ExpectedRoute,
    RefusalKind,
)
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
from smart_rag_core.tables.service import should_bind_structured_table

QT_EVAL_006_RECALL_AT_10 = 0.85
QT_EVAL_007_EXACT_CODE_RECALL_AT_5 = 0.98
QT_EVAL_008_ALIAS_RECALL_AT_10 = 0.95
QT_EVAL_002_LOCATOR_CORRECTNESS = 0.98
QT_LAT_001_FIRST_EVIDENCE_P95_MS = 2000.0

RECALL_AT_10_K = 10
EXACT_CODE_RECALL_K = 5
ALIAS_RECALL_K = 10

REFUSAL_QUERY_CLASSES = frozenset(
    {
        QueryClass.INSUFFICIENT_REFUSAL,
        QueryClass.MEDIA_LIMITATION,
        QueryClass.NEGATION,
        QueryClass.DOCUMENT_SUMMARY,
    }
)
FOLLOW_UP_REPAIR_NOTE = (
    "If a signed lexical/semantic gate misses, record the miss. Do not retune "
    "frozen hybrid_default_v1 in this wave. Follow-up: at most two development "
    "repairs then one qualification confirm."
)

EmbeddingsKind = Literal["mock", "openai", "unknown"]
TableExecutor = Callable[["EvaluationCase", GoldIdSidecar], bool]


class ScoringKind(StrEnum):
    """How one Phase-4-owned case is scored in this harness."""

    RECALL = "recall"
    REFUSAL = "refusal"
    ACL = "acl"
    TABLE = "table"


@dataclass(frozen=True, slots=True)
class CaseRetrieveOutcome:
    """Retrieve or table-executor product for one labeled case.

    Attributes:
        result: Hybrid retrieve result when the Hybrid path ran.
        contexts: Canonical chunk rows used to check locators and citation text.
        table_executed: True when Packet 7 ``execute_compiled_query`` / service ran.
        table_ok: Whether the table executor completed without refusal.
        table_operation: Executor operation label when known.
        embedding_cost_usd: Optional embedding cost for this case.
    """

    result: HybridRunResult | None = None
    contexts: tuple[ChunkContext, ...] = ()
    table_executed: bool = False
    table_ok: bool | None = None
    table_operation: str | None = None
    embedding_cost_usd: float | None = None


@dataclass(frozen=True, slots=True)
class RankedIdCaseScore:
    """Per-case ranked-ID and companion metrics.

    Attributes:
        case_id: Evaluation case identifier.
        query_class: Canonical query class.
        scoring_kind: Recall, refusal, ACL, or table path.
        gold_chunk_ids: Mapped real chunk UUIDs from the sidecar.
        recall_hit_at_10: Whether every gold UUID is in top-10 ranked ids.
        recall_hit_at_5: Same at rank 5.
        locator_units: Evidence units checked for locator/citation.
        locator_correct_units: Units whose locator and citation_text matched.
        locator_failures: Machine-readable locator/citation failure codes.
        acl_leak: True when a restricted gold UUID appeared for the actor.
        refusal_correct: Coverage/refusal agreement, or None when not scored.
        table_path_used: True when structured-table dispatch applied.
        first_evidence_ms: Retrieve ``first_evidence_ms`` when present.
    """

    case_id: str
    query_class: QueryClass
    scoring_kind: ScoringKind
    gold_chunk_ids: tuple[UUID, ...]
    recall_hit_at_10: bool | None
    recall_hit_at_5: bool | None
    locator_units: int
    locator_correct_units: int
    locator_failures: tuple[str, ...]
    acl_leak: bool
    refusal_correct: bool | None
    table_path_used: bool
    first_evidence_ms: float | None


@dataclass(frozen=True, slots=True)
class RankedIdReport:
    """Aggregated open-split ranked-ID report. Holdout is never opened.

    Attributes:
        split: Open-split selector used to load cases.
        case_count: Number of Phase-4-owned cases scored or inspected.
        recall_at_10: Mean Recall@10, or None when fail-closed / empty.
        exact_code_recall_at_5: Mean exact-code Recall@5, or None.
        alias_recall_at_10: Mean alias Recall@10, or None.
        locator_correctness: Fraction of evidence units with matching locators.
        first_evidence_p95_ms: p95 of ``first_evidence_ms``.
        holdout_opened: Always false.
        sidecar_unmapped: True when gold chunk UUIDs are missing (dry sidecar).
        embeddings: Whether query embeddings were mock or OpenAI.
        qt_eval_006_live: True only for mapped OpenAI semantic Recall@10.
        cost_usd: Sum of known embedding costs, or None.
        acl_leak_count: Restricted gold UUIDs that appeared for unauthorized actors.
        table_case_count: Cases dispatched to the structured-table executor.
        table_executed_count: Cases where the Packet 7 executor ran.
        refusal_case_count: Coverage/refusal cases excluded from Recall@K.
        refusal_correct_rate: Fraction of refusal cases with matching coverage.
        recall_case_count: Cases included in Recall@K.
        recall_miss_case_ids: Recall cases whose gold UUID missed top-K.
        hardware: Host snapshot for QT-LAT-001 comparison.
        qt_lat_001_ms: Signed first-evidence p95 gate (never silently raised).
        follow_up: Repair note when a signed gate misses.
        scores: Per-case rows.
    """

    split: str
    case_count: int
    recall_at_10: float | None
    exact_code_recall_at_5: float | None
    alias_recall_at_10: float | None
    locator_correctness: float | None
    first_evidence_p95_ms: float | None
    holdout_opened: Literal[False]
    sidecar_unmapped: bool
    embeddings: EmbeddingsKind
    qt_eval_006_live: bool
    cost_usd: float | None
    acl_leak_count: int
    table_case_count: int
    table_executed_count: int
    refusal_case_count: int
    refusal_correct_rate: float | None
    recall_case_count: int
    recall_miss_case_ids: tuple[str, ...]
    hardware: dict[str, str | int | None]
    qt_lat_001_ms: float
    follow_up: str | None
    scores: tuple[RankedIdCaseScore, ...]


def load_gold_id_sidecar(path: Path) -> GoldIdSidecar:
    """Load a gold-id sidecar JSON file.

    Args:
        path: Path to ``gold_id_map.json``.

    Returns:
        Validated sidecar model.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the payload is not a gold-id sidecar.
    """

    payload = json.loads(path.read_text(encoding="utf-8"))
    return GoldIdSidecar.model_validate(payload)


def sidecar_has_unmapped_chunks(sidecar: GoldIdSidecar) -> bool:
    """Return whether any synthetic chunk gold lacks a real UUID.

    Dry materialization writes ``chunk_id=null``. Recall@K must fail closed
    rather than treat ``p4-chk-*`` as database identifiers.

    Args:
        sidecar: Gold-id sidecar.

    Returns:
        True when a synthetic chunk id is present and ``chunk_id`` is null.
    """

    for record in sidecar.records:
        if record.synthetic_chunk_id and record.chunk_id is None:
            return True
    return False


def hardware_snapshot() -> dict[str, str | int | None]:
    """Return a host snapshot for QT-LAT-001 reporting.

    Returns:
        OS, machine, processor, Python, and CPU count. The 2s p95 gate is
        never raised from this snapshot.
    """

    processor = platform.processor() or platform.machine()
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": processor,
        "python": platform.python_version(),
        "cpu_count": cpu_count(),
    }


def percentile_p95(values: Sequence[float]) -> float | None:
    """Return the linear-interpolation 95th percentile.

    Args:
        values: Sample of milliseconds.

    Returns:
        p95 in the same unit as ``values``, or None when empty.
    """

    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = 0.95 * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[low])
    weight = rank - low
    return float(ordered[low] * (1.0 - weight) + ordered[high] * weight)


def profile_string_list(value: object) -> tuple[str, ...]:
    """Extract non-empty strings from a profile field value.

    Args:
        value: List or scalar profile JSON value.

    Returns:
        String tuple.
    """

    if isinstance(value, list):
        texts: list[str] = []
        for raw_item in cast(list[object], value):
            if raw_item:
                texts.append(str(raw_item))
        return tuple(texts)
    if isinstance(value, str) and value:
        return (value,)
    return ()


def table_dispatch_required(case: EvaluationCase) -> bool:
    """Return whether Packet 7 structured-table execution owns the case.

    Ordinary cell/text lookup stays Hybrid retrieve. Numeric aggregation with
    table intent and calculation hints binds the table executor.

    Args:
        case: Phase-4-owned evaluation case.

    Returns:
        True when ``should_bind_structured_table`` is true or the class is
        ``tabular_aggregation``.
    """

    hints = profile_string_list(case.expected_profile.table_operation_hints.value)
    intent = case.expected_profile.table_intent.value is True
    if case.query_class is QueryClass.TABULAR_AGGREGATION:
        return should_bind_structured_table(
            table_intent=True,
            operation_hints=hints or ("sum",),
        )
    return should_bind_structured_table(table_intent=intent, operation_hints=hints)


def scoring_kind(case: EvaluationCase) -> ScoringKind:
    """Return the Packet 9 scoring lane for one case.

    Args:
        case: Phase-4-owned open-split case.

    Returns:
        ``acl`` for ACL-negative labels, ``table`` for structured aggregation,
        ``refusal`` for insufficient/media/negation/document_summary, else
        ``recall``.
    """

    if case.query_class is QueryClass.ACL_NEGATIVE:
        return ScoringKind.ACL
    if table_dispatch_required(case):
        return ScoringKind.TABLE
    if case.query_class in REFUSAL_QUERY_CLASSES:
        return ScoringKind.REFUSAL
    return ScoringKind.RECALL


def gold_records_for_case(
    sidecar: GoldIdSidecar, case_id: str
) -> tuple[GoldIdRecord, ...]:
    """Return sidecar rows for one case id.

    Args:
        sidecar: Gold-id sidecar.
        case_id: Evaluation case identifier.

    Returns:
        Matching records in sidecar order.
    """

    return tuple(record for record in sidecar.records if record.case_id == case_id)


def mapped_gold_chunk_ids(sidecar: GoldIdSidecar, case_id: str) -> tuple[UUID, ...]:
    """Return real chunk UUIDs mapped from synthetic gold ids.

    Args:
        sidecar: Gold-id sidecar.
        case_id: Evaluation case identifier.

    Returns:
        Unique mapped chunk UUIDs. Empty when unmapped.
    """

    seen: set[UUID] = set()
    ordered: list[UUID] = []
    for record in gold_records_for_case(sidecar, case_id):
        chunk_id = record.chunk_id
        if chunk_id is None or chunk_id in seen:
            continue
        seen.add(chunk_id)
        ordered.append(chunk_id)
    return tuple(ordered)


def restricted_gold_chunk_ids(sidecar: GoldIdSidecar, case_id: str) -> tuple[UUID, ...]:
    """Return mapped gold UUIDs that must not appear for the labeled actor.

    Args:
        sidecar: Gold-id sidecar.
        case_id: Evaluation case identifier.

    Returns:
        Chunk UUIDs marked restricted, not visible, or ACL-negative.
    """

    ids: list[UUID] = []
    for record in gold_records_for_case(sidecar, case_id):
        if record.chunk_id is None:
            continue
        if (
            record.restricted_actor
            or not record.visible_to_actor
            or record.visibility == "restricted"
        ):
            ids.append(record.chunk_id)
    return tuple(ids)


def recall_hit_at_k(
    ranked_ids: Sequence[UUID],
    gold_ids: Sequence[UUID],
    k: int,
) -> bool:
    """Return whether every gold UUID appears in the top-K ranked ids.

    Args:
        ranked_ids: Final Hybrid order after rerank/MMR when rerank ran.
        gold_ids: Mapped real chunk UUIDs.
        k: Cutoff rank (10 for Recall@10, 5 for exact-code).

    Returns:
        True when gold_ids is non-empty and each id is in ``ranked_ids[:k]``.
        False when gold is missing from the cutoff.
    """

    if not gold_ids:
        return False
    cutoff = tuple(ranked_ids[:k])
    ranked_set = set(cutoff)
    return all(gold_id in ranked_set for gold_id in gold_ids)


def gold_locator_for_chunk(
    case: EvaluationCase,
    sidecar: GoldIdSidecar,
    chunk_id: UUID,
) -> dict[str, str]:
    """Join a real chunk UUID back to the labeled gold locator.

    Args:
        case: Labeled case whose evidence links carry synthetic ids.
        sidecar: Gold-id sidecar.
        chunk_id: Real canonical chunk UUID.

    Returns:
        Locator dict from the matching evidence link, or empty.
    """

    for record in gold_records_for_case(sidecar, case.case_id):
        if record.chunk_id != chunk_id:
            continue
        for link in case.evidence_links:
            if link.chunk_id and link.chunk_id == record.synthetic_chunk_id:
                return dict(link.locator)
    return {}


def locator_matches_gold(
    locator: EvidenceLocator, gold: Mapping[str, str]
) -> tuple[bool, tuple[str, ...]]:
    """Compare an evidence locator to labeled page/section/sheet/range/URL.

    Args:
        locator: Canonical evidence locator.
        gold: Evidence-link locator dict.

    Returns:
        ``(ok, failure_codes)``. Missing gold keys are not failures.
    """

    failures: list[str] = []
    page_raw = gold.get("page")
    if page_raw is not None:
        try:
            expected_page = int(page_raw)
        except ValueError:
            expected_page = None
            failures.append("gold_page_unparseable")
        if expected_page is not None and locator.page_number != expected_page:
            failures.append("page_mismatch")
    section = gold.get("section")
    if section:
        path_lcase = tuple(item.casefold() for item in locator.section_path)
        joined = "/".join(locator.section_path)
        if (
            section.casefold() not in path_lcase
            and section.casefold() not in joined.casefold()
        ):
            failures.append("section_mismatch")
    sheet = gold.get("sheet")
    if sheet and (locator.sheet_name or "").casefold() != sheet.casefold():
        failures.append("sheet_mismatch")
    range_ref = gold.get("range")
    if range_ref and (locator.range_ref or "").casefold() != range_ref.casefold():
        failures.append("range_mismatch")
    url = gold.get("url") or gold.get("source_url")
    if url and (locator.source_url or "") != url:
        failures.append("url_mismatch")
    return (not failures, tuple(failures))


def locator_matches_context(
    unit: EvidenceUnit, context: ChunkContext
) -> tuple[bool, tuple[str, ...]]:
    """Require evidence locators and citation text to match canonical context.

    Args:
        unit: Returned Hybrid evidence unit.
        context: Authorized ``ChunkContext`` for the same chunk id.

    Returns:
        ``(ok, failure_codes)``. ``citation_bm25_text`` is recorded when
        ``citation_text`` is not ``raw_text``.
    """

    failures: list[str] = []
    if unit.citation_text != context.raw_text:
        failures.append("citation_not_raw_text")
    if unit.locator.page_number != context.page_number:
        failures.append("page_mismatch")
    if tuple(unit.locator.section_path) != tuple(context.section_path):
        failures.append("section_mismatch")
    if unit.locator.sheet_name != context.sheet_name:
        failures.append("sheet_mismatch")
    if unit.locator.range_ref != context.range_ref:
        failures.append("range_mismatch")
    if unit.locator.source_url != context.source_url:
        failures.append("url_mismatch")
    return (not failures, tuple(failures))


def score_evidence_unit(
    unit: EvidenceUnit,
    *,
    case: EvaluationCase,
    sidecar: GoldIdSidecar,
    context: ChunkContext | None,
    forbidden_citation_text: str | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Score one evidence unit for locator correctness and citation provenance.

    Args:
        unit: Returned evidence unit.
        case: Labeled case.
        sidecar: Gold-id sidecar.
        context: Canonical row when loaded.
        forbidden_citation_text: Optional BM25 snippet that must never be cited.

    Returns:
        ``(ok, failure_codes)``.
    """

    failures: list[str] = []
    if forbidden_citation_text and unit.citation_text == forbidden_citation_text:
        failures.append("citation_bm25_text")
    if context is not None:
        _ok, context_failures = locator_matches_context(unit, context)
        failures.extend(context_failures)
    gold = gold_locator_for_chunk(case, sidecar, unit.chunk_id)
    if gold:
        _ok, gold_failures = locator_matches_gold(unit.locator, gold)
        failures.extend(gold_failures)
    unique = tuple(dict.fromkeys(failures))
    return (not unique, unique)


def gold_expects_refusal(case: EvaluationCase) -> bool:
    """Return whether the label expects coverage/refusal rather than an answer.

    Args:
        case: Labeled case.

    Returns:
        True when the route is refusal or ``refusal_kind`` is not ``none``.
    """

    return (
        case.expected_route is ExpectedRoute.REFUSAL
        or case.refusal_kind is not RefusalKind.NONE
    )


def refusal_decision_correct(
    case: EvaluationCase, coverage: HybridCoverage
) -> bool | None:
    """Compare Hybrid coverage decision to labeled refusal truth.

    Args:
        case: Labeled case in the refusal scoring lane.
        coverage: Retrieve coverage diagnostics.

    Returns:
        True/False when a decision exists; None when coverage was not decided.
    """

    decision = coverage.decision
    if decision is None:
        return None
    expects_refuse = gold_expects_refusal(case)
    if expects_refuse:
        return decision is CoverageDecision.REFUSE
    return decision is CoverageDecision.ANSWER


def empty_hybrid_result(*, first_evidence_ms: float = 0.0) -> HybridRunResult:
    """Build an empty retrieve result for tests and missing live runs.

    Args:
        first_evidence_ms: Timing to record.

    Returns:
        Empty ranked/evidence Hybrid result.
    """

    return HybridRunResult(
        ranked_ids=(),
        evidence=(),
        coverage=HybridCoverage(signal=CoverageSignal.NONE),
        fallback_reason=RetrievalFallbackReason.RETRIEVAL_EMPTY,
        deadline_exhausted=False,
        first_evidence_ms=first_evidence_ms,
        embedding_call_count=0,
        rerank_call_count=0,
    )


def score_case(
    case: EvaluationCase,
    sidecar: GoldIdSidecar,
    outcome: CaseRetrieveOutcome,
    *,
    forbidden_citation_text: str | None = None,
) -> RankedIdCaseScore:
    """Score one Phase-4-owned case. Does not invent Recall@K from occupancy.

    Args:
        case: Open-split evaluation case.
        sidecar: Mapped or dry gold-id sidecar.
        outcome: Retrieve and/or table executor product.
        forbidden_citation_text: Optional BM25 snippet that must never be cited.

    Returns:
        Per-case metric row. Recall fields are None for non-recall lanes.
    """

    kind = scoring_kind(case)
    gold_ids = mapped_gold_chunk_ids(sidecar, case.case_id)
    result = outcome.result
    ranked = result.ranked_ids if result is not None else ()
    evidence = result.evidence if result is not None else ()
    context_by_id = {item.chunk_id: item for item in outcome.contexts}
    locator_ok = 0
    locator_failures: list[str] = []
    for unit in evidence:
        ok, codes = score_evidence_unit(
            unit,
            case=case,
            sidecar=sidecar,
            context=context_by_id.get(unit.chunk_id),
            forbidden_citation_text=forbidden_citation_text,
        )
        if ok:
            locator_ok += 1
        else:
            locator_failures.extend(codes)
    restricted_ids = restricted_gold_chunk_ids(sidecar, case.case_id)
    ranked_set = set(ranked)
    acl_leak = any(gold_id in ranked_set for gold_id in restricted_ids)
    if kind is ScoringKind.ACL:
        acl_leak = acl_leak or any(gold_id in ranked_set for gold_id in gold_ids)
    recall_at_10: bool | None = None
    recall_at_5: bool | None = None
    if kind is ScoringKind.RECALL:
        recall_at_10 = recall_hit_at_k(ranked, gold_ids, RECALL_AT_10_K)
        recall_at_5 = recall_hit_at_k(ranked, gold_ids, EXACT_CODE_RECALL_K)
    refusal_ok: bool | None = None
    if kind is ScoringKind.REFUSAL and result is not None:
        refusal_ok = refusal_decision_correct(case, result.coverage)
    first_ms = result.first_evidence_ms if result is not None else None
    return RankedIdCaseScore(
        case_id=case.case_id,
        query_class=case.query_class,
        scoring_kind=kind,
        gold_chunk_ids=gold_ids,
        recall_hit_at_10=recall_at_10,
        recall_hit_at_5=recall_at_5,
        locator_units=len(evidence),
        locator_correct_units=locator_ok,
        locator_failures=tuple(dict.fromkeys(locator_failures)),
        acl_leak=acl_leak,
        refusal_correct=refusal_ok,
        table_path_used=kind is ScoringKind.TABLE,
        first_evidence_ms=first_ms,
    )


def _mean_bool(flags: Sequence[bool]) -> float | None:
    """Return the mean of boolean flags.

    Args:
        flags: Hit/miss flags.

    Returns:
        Mean in ``[0, 1]``, or None when empty.
    """

    if not flags:
        return None
    return sum(1.0 if item else 0.0 for item in flags) / float(len(flags))


def evaluate_ranked_ids(
    cases: Sequence[EvaluationCase],
    sidecar: GoldIdSidecar,
    outcomes: Mapping[str, CaseRetrieveOutcome],
    *,
    split: OpenSplitName = "development",
    embeddings: EmbeddingsKind = "unknown",
    forbidden_citation_text: str | None = None,
    table_executor: TableExecutor | None = None,
) -> RankedIdReport:
    """Aggregate ranked-ID metrics for Phase-4-owned open-split cases.

    Args:
        cases: Cases from ``select_phase4_retrieve_cases`` only.
        sidecar: Gold-id sidecar. Null chunk ids fail closed.
        outcomes: Per-case retrieve/table products keyed by case id.
        split: Open-split name recorded on the report.
        embeddings: ``mock`` or ``openai``. Mock semantic Recall@10 is not
            live QT-EVAL-006.
        forbidden_citation_text: Optional BM25 snippet that must never be cited.
        table_executor: Optional Packet 7 executor. Ordinary lookup does not
            call it.

    Returns:
        Report with ``holdout_opened=False``. Recall fields are None when the
        sidecar is unmapped.

    Side Effects:
        May invoke ``table_executor`` for tabular aggregation cases.
    """

    unmapped = sidecar_has_unmapped_chunks(sidecar)
    scores: list[RankedIdCaseScore] = []
    table_executed = 0
    cost_total = 0.0
    cost_known = False
    for case in cases:
        outcome = outcomes.get(case.case_id, CaseRetrieveOutcome())
        if scoring_kind(case) is ScoringKind.TABLE:
            executed = outcome.table_executed
            if table_executor is not None and not executed:
                executed = table_executor(case, sidecar)
            if executed:
                table_executed += 1
            outcome = CaseRetrieveOutcome(
                result=outcome.result,
                contexts=outcome.contexts,
                table_executed=executed,
                table_ok=True if executed else outcome.table_ok,
                table_operation=outcome.table_operation,
                embedding_cost_usd=outcome.embedding_cost_usd,
            )
        scores.append(
            score_case(
                case,
                sidecar,
                outcome,
                forbidden_citation_text=forbidden_citation_text,
            )
        )
        if outcome.embedding_cost_usd is not None:
            cost_total += outcome.embedding_cost_usd
            cost_known = True
    recall_rows = [row for row in scores if row.scoring_kind is ScoringKind.RECALL]
    exact_rows = [
        row for row in recall_rows if row.query_class is QueryClass.EXACT_CODE
    ]
    alias_rows = [row for row in recall_rows if row.query_class is QueryClass.ALIAS]
    refusal_rows = [row for row in scores if row.scoring_kind is ScoringKind.REFUSAL]
    locator_units = sum(row.locator_units for row in scores)
    locator_ok = sum(row.locator_correct_units for row in scores)
    latencies = [
        row.first_evidence_ms for row in scores if row.first_evidence_ms is not None
    ]
    p95 = percentile_p95(latencies)
    acl_leaks = sum(1 for row in scores if row.acl_leak)
    recall_at_10 = None
    exact_at_5 = None
    alias_at_10 = None
    locator_rate = None
    if not unmapped:
        recall_at_10 = _mean_bool(
            tuple(bool(row.recall_hit_at_10) for row in recall_rows)
        )
        exact_at_5 = _mean_bool(tuple(bool(row.recall_hit_at_5) for row in exact_rows))
        alias_at_10 = _mean_bool(
            tuple(bool(row.recall_hit_at_10) for row in alias_rows)
        )
        if locator_units:
            locator_rate = locator_ok / float(locator_units)
    refusal_flags = [
        row.refusal_correct for row in refusal_rows if row.refusal_correct is not None
    ]
    miss_ids = tuple(
        row.case_id for row in recall_rows if row.recall_hit_at_10 is False
    )
    qt_live = not unmapped and embeddings == "openai" and recall_at_10 is not None
    gate_miss = False
    if not unmapped and embeddings == "openai":
        if recall_at_10 is not None and recall_at_10 < QT_EVAL_006_RECALL_AT_10:
            gate_miss = True
        if exact_at_5 is not None and exact_at_5 < QT_EVAL_007_EXACT_CODE_RECALL_AT_5:
            gate_miss = True
        if alias_at_10 is not None and alias_at_10 < QT_EVAL_008_ALIAS_RECALL_AT_10:
            gate_miss = True
    if (
        locator_rate is not None
        and locator_rate < QT_EVAL_002_LOCATOR_CORRECTNESS
        and not unmapped
    ):
        gate_miss = True
    if p95 is not None and p95 > QT_LAT_001_FIRST_EVIDENCE_P95_MS:
        gate_miss = True
    if acl_leaks:
        gate_miss = True
    return RankedIdReport(
        split=split,
        case_count=len(cases),
        recall_at_10=recall_at_10,
        exact_code_recall_at_5=exact_at_5,
        alias_recall_at_10=alias_at_10,
        locator_correctness=locator_rate,
        first_evidence_p95_ms=p95,
        holdout_opened=False,
        sidecar_unmapped=unmapped,
        embeddings=embeddings,
        qt_eval_006_live=qt_live,
        cost_usd=cost_total if cost_known else None,
        acl_leak_count=acl_leaks,
        table_case_count=sum(1 for row in scores if row.table_path_used),
        table_executed_count=table_executed,
        refusal_case_count=len(refusal_rows),
        refusal_correct_rate=_mean_bool(tuple(bool(item) for item in refusal_flags)),
        recall_case_count=len(recall_rows),
        recall_miss_case_ids=miss_ids,
        hardware=hardware_snapshot(),
        qt_lat_001_ms=QT_LAT_001_FIRST_EVIDENCE_P95_MS,
        follow_up=FOLLOW_UP_REPAIR_NOTE if gate_miss else None,
        scores=tuple(scores),
    )


def report_to_json(report: RankedIdReport) -> dict[str, object]:
    """Serialize a ranked-ID report to the CLI JSON contract.

    Args:
        report: Aggregated metrics.

    Returns:
        JSON-ready mapping including ``holdout_opened=false``.
    """

    return {
        "split": report.split,
        "case_count": report.case_count,
        "recall_at_10": report.recall_at_10,
        "exact_code_recall_at_5": report.exact_code_recall_at_5,
        "alias_recall_at_10": report.alias_recall_at_10,
        "locator_correctness": report.locator_correctness,
        "first_evidence_p95_ms": report.first_evidence_p95_ms,
        "holdout_opened": False,
        "sidecar_unmapped": report.sidecar_unmapped,
        "embeddings": report.embeddings,
        "qt_eval_006_live": report.qt_eval_006_live,
        "cost": report.cost_usd,
        "acl_leak_count": report.acl_leak_count,
        "table_case_count": report.table_case_count,
        "table_executed_count": report.table_executed_count,
        "refusal_case_count": report.refusal_case_count,
        "refusal_correct_rate": report.refusal_correct_rate,
        "recall_case_count": report.recall_case_count,
        "recall_miss_case_ids": list(report.recall_miss_case_ids),
        "hardware": report.hardware,
        "qt_lat_001_ms": report.qt_lat_001_ms,
        "follow_up": report.follow_up,
        "qt_eval_006_threshold": QT_EVAL_006_RECALL_AT_10,
        "qt_eval_007_threshold": QT_EVAL_007_EXACT_CODE_RECALL_AT_5,
        "qt_eval_008_threshold": QT_EVAL_008_ALIAS_RECALL_AT_10,
        "qt_eval_002_threshold": QT_EVAL_002_LOCATOR_CORRECTNESS,
    }


def load_eval_cases(
    split: OpenSplitName = "development",
    *,
    limit: int | None = None,
) -> list[EvaluationCase]:
    """Load Phase-4-owned open-split cases for ranked-ID eval.

    Args:
        split: ``development``, ``qualification``, or ``open``.
        limit: Optional positive cap after filtering.

    Returns:
        Cases from ``select_phase4_retrieve_cases`` only.
    """

    return select_phase4_retrieve_cases(split=split, limit=limit)
