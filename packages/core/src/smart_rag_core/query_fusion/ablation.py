"""Hybrid-only vs naive-union vs resolved-path fusion ablation.

Holdout labels are never opened. Live Combined +10pp is recorded separately
as unverified until mapping/extraction on labeled relationship/multi-hop
cases is executed.
"""

from __future__ import annotations

from smart_rag_core.evaluation.holdout import HoldoutAccess, HoldoutSealedError
from smart_rag_core.query_fusion.assemble import fuse_evidence
from smart_rag_core.query_fusion.config_hash import fusion_config_hash
from smart_rag_core.query_fusion.exceptions import FusionError
from smart_rag_core.query_fusion.models import (
    AblationCaseScore,
    AblationReport,
    FusionAlgorithm,
    FusionInput,
)


def citation_completeness(
    selected_ids: tuple[str, ...],
    gold_ids: tuple[str, ...],
) -> float:
    """Return gold-ID recall over selected evidence.

    Args:
        selected_ids: Final evidence chunk IDs.
        gold_ids: Required canonical IDs.

    Returns:
        ``|intersection| / |gold|``, or 1.0 when gold is empty.
    """

    if not gold_ids:
        return 1.0
    selected = set(selected_ids)
    hits = sum(1 for item in gold_ids if item in selected)
    return hits / len(gold_ids)


def covers_gold(selected_ids: tuple[str, ...], gold_ids: tuple[str, ...]) -> bool:
    """Return whether every gold chunk ID is present.

    Args:
        selected_ids: Final evidence chunk IDs.
        gold_ids: Required canonical IDs.

    Returns:
        True when the gold set is a subset of selected IDs.
    """

    return set(gold_ids).issubset(set(selected_ids))


def score_case(
    fusion_input: FusionInput,
    *,
    case_id: str,
    gold_chunk_ids: tuple[str, ...],
) -> AblationCaseScore:
    """Score Hybrid-only, naive union, and resolved-path fusion on one fixture.

    Args:
        fusion_input: Shared retrieval snapshot.
        case_id: Stable fixture identifier.
        gold_chunk_ids: Canonical IDs required for path/answer success.

    Returns:
        Per-algorithm success and citation completeness.
    """

    hybrid_only = fuse_evidence(
        fusion_input.model_copy(
            update={
                "graph_paths": (),
                "graph_passages": (),
                "effective_route": "hybrid",
                "requested_route": "hybrid",
                "graph_survival_ratio": None,
                "graph_fallback_reason": None,
                "graph_timeout": False,
            }
        ),
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
    )
    union = fuse_evidence(fusion_input, algorithm=FusionAlgorithm.NAIVE_UNION)
    fusion = fuse_evidence(
        fusion_input,
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
    )
    hybrid_ids = tuple(item.chunk_id for item in hybrid_only.evidence)
    union_ids = tuple(item.chunk_id for item in union.evidence)
    fusion_ids = tuple(item.chunk_id for item in fusion.evidence)
    return AblationCaseScore(
        case_id=case_id,
        gold_chunk_ids=gold_chunk_ids,
        hybrid_success=covers_gold(hybrid_ids, gold_chunk_ids),
        union_success=covers_gold(union_ids, gold_chunk_ids),
        fusion_success=covers_gold(fusion_ids, gold_chunk_ids),
        hybrid_citation_completeness=citation_completeness(hybrid_ids, gold_chunk_ids),
        union_citation_completeness=citation_completeness(union_ids, gold_chunk_ids),
        fusion_citation_completeness=citation_completeness(fusion_ids, gold_chunk_ids),
    )


def decide_algorithm(
    *,
    fusion_success_rate: float,
    union_success_rate: float,
    fusion_completeness: float,
    union_completeness: float,
) -> tuple[FusionAlgorithm, bool]:
    """Keep fusion only when it beats naive union on success and completeness.

    Args:
        fusion_success_rate: Mean fusion path/answer success.
        union_success_rate: Mean union path/answer success.
        fusion_completeness: Mean fusion citation completeness.
        union_completeness: Mean union citation completeness.

    Returns:
        Selected algorithm and whether fusion beat union.
    """

    beats = (
        fusion_success_rate > union_success_rate + 1e-12
        and fusion_completeness + 1e-12 >= union_completeness
    ) or (
        abs(fusion_success_rate - union_success_rate) <= 1e-12
        and fusion_completeness > union_completeness + 1e-12
    )
    if beats:
        return FusionAlgorithm.RESOLVED_PATH_FUSION, True
    return FusionAlgorithm.NAIVE_UNION, False


def run_ablation(
    cases: tuple[tuple[str, FusionInput, tuple[str, ...]], ...],
    *,
    holdout_access: HoldoutAccess | None = None,
) -> AblationReport:
    """Evaluate development/qualification fixtures without opening holdout.

    Args:
        cases: ``(case_id, fusion_input, gold_chunk_ids)`` tuples.
        holdout_access: Must be denied. Authorized holdout opening is out of
            scope for this packet.

    Returns:
        Ablation report with selected algorithm and synthetic Combined-Hybrid
        gain in percentage points. Live QT-EVAL-009 stays ``unverified``.

    Raises:
        HoldoutSealedError: If holdout access is allowed.
        FusionError: If a case requests holdout tuning.
    """

    access = holdout_access if holdout_access is not None else HoldoutAccess.denied()
    if access.allowed:
        raise HoldoutSealedError("holdout is sealed; default access is denied")
    scores = [
        score_case(fusion_input, case_id=case_id, gold_chunk_ids=gold)
        for case_id, fusion_input, gold in cases
    ]
    count = max(1, len(scores))
    hybrid_rate = sum(item.hybrid_success for item in scores) / count
    union_rate = sum(item.union_success for item in scores) / count
    fusion_rate = sum(item.fusion_success for item in scores) / count
    union_complete = sum(item.union_citation_completeness for item in scores) / count
    fusion_complete = sum(item.fusion_citation_completeness for item in scores) / count
    selected, beats = decide_algorithm(
        fusion_success_rate=fusion_rate,
        union_success_rate=union_rate,
        fusion_completeness=fusion_complete,
        union_completeness=union_complete,
    )
    return AblationReport(
        cases=tuple(scores),
        hybrid_success_rate=hybrid_rate,
        union_success_rate=union_rate,
        fusion_success_rate=fusion_rate,
        union_completeness=union_complete,
        fusion_completeness=fusion_complete,
        selected_algorithm=selected,
        fusion_beats_union=beats,
        combined_minus_hybrid_pp=100.0 * (fusion_rate - hybrid_rate),
        live_combined_gain_status="unverified",
        config_hash=fusion_config_hash(selected),
        holdout_used=False,
    )


def refuse_holdout_tuning() -> None:
    """Fail closed when configuration would be tuned on holdout labels.

    Raises:
        FusionError: Always ``holdout_tuned_configuration``.
    """

    raise FusionError("holdout_tuned_configuration")
