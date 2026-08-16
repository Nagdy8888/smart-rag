"""Golden Combined fusion formulas, negatives, ablation, and representative contracts."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from smart_rag_core.evaluation.holdout import HoldoutAccess, HoldoutSealedError
from smart_rag_core.query_fusion import (
    AGREEMENT_CAP,
    EDGE_SUPPORT_MULTIPLIER_CAP,
    FUSION_RRF_K,
    GRAPH_DISCOVERED_ONLY_CAP,
    GRAPH_WEIGHT,
    HOP_PENALTY,
    SELECTED_FUSION_ALGORITHM,
    apply_agreement_multiplier,
    combined_rrf_score,
    edge_support_multiplier,
    fuse_evidence,
    fusion_config_hash,
    fusion_input_from_branches,
    graph_passage_strength_for_path,
    path_support,
    refuse_holdout_tuning,
    run_ablation,
)
from smart_rag_core.query_fusion.constants import (
    FALLBACK_GRAPH_ONLY_ANSWER,
    FALLBACK_GRAPH_SURVIVAL_BELOW_THRESHOLD,
    FALLBACK_HIDDEN_KEYWORD,
    FALLBACK_HIDDEN_LIGHTRAG_ANSWER,
    FALLBACK_HOLDOUT_TUNING,
    FALLBACK_MISSING_EDGE_SUPPORT,
    FALLBACK_NATIVE_PROSE,
    FALLBACK_UNMAPPED_PATH,
    FUSION_DOCUMENT_QUOTA,
    FUSION_FINAL_EVIDENCE_MAX,
    FUSION_SECTION_QUOTA,
    FUSION_SURVIVAL_THRESHOLD,
)
from smart_rag_core.query_fusion.exceptions import FusionError
from smart_rag_core.query_fusion.models import (
    FusionAlgorithm,
    FusionInput,
    GraphPassage,
    GraphPathInput,
    HybridPassage,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.models import BranchKind, BranchResult
from smart_rag_core.retrieval.graph import GRAPH_SURVIVAL_FALLBACK_THRESHOLD
from smart_rag_core.retrieval.profiles import (
    DOCUMENT_QUOTA,
    FINAL_EVIDENCE_MAX,
    RRF_K,
    SECTION_QUOTA,
)


def _uid(n: int) -> str:
    """Return a 36-character synthetic UUID from a small integer.

    Args:
        n: Discriminator in ``0..2**32-1``.

    Returns:
        Canonical UUID string.
    """

    return f"{n:08x}-0000-4000-8000-000000000000"


def _hybrid(
    n: int,
    *,
    rank: int,
    doc: int,
    text: str = "hybrid passage",
) -> HybridPassage:
    """Build one authorized Hybrid passage.

    Args:
        n: Chunk discriminator.
        rank: 1-based Hybrid rank.
        doc: Document discriminator.
        text: Canonical citation text.

    Returns:
        Frozen Hybrid passage.
    """

    return HybridPassage(
        chunk_id=_uid(n),
        document_id=_uid(10_000 + doc),
        version_id=_uid(20_000 + doc),
        citation_text=text,
        hybrid_rank=rank,
    )


def _path(
    *chunk_ns: int,
    supports: tuple[float, ...] | None = None,
    fully_mapped: bool = True,
    unmapped: bool = False,
    stale: bool = False,
    deleted: bool = False,
    unauthorized: bool = False,
    missing_edge_support: bool = False,
    native_prose: bool = False,
    steering_only: bool = False,
) -> GraphPathInput:
    """Build one application path over the given chunk discriminators.

    Args:
        chunk_ns: Chunk discriminators, one per hop.
        supports: Per-hop mapping supports. Defaults to ``1.0`` each.
        fully_mapped: Mapping completeness flag.
        unmapped: Missing-mapping flag.
        stale: Stale-version flag.
        deleted: Deleted-source flag.
        unauthorized: ACL denial flag.
        missing_edge_support: Missing support flag.
        native_prose: Forbidden vendor-prose flag.
        steering_only: GlobalSteering flag. Never scored.

    Returns:
        Frozen path input.
    """

    hops = len(chunk_ns)
    ids = tuple(_uid(item) for item in chunk_ns)
    edge_supports = supports if supports is not None else tuple(1.0 for _ in chunk_ns)
    return GraphPathInput(
        statement_ids=tuple(f"stmt-{item}" for item in chunk_ns),
        hops=hops,
        canonical_chunk_ids=ids,
        edge_chunk_ids=tuple((item,) for item in ids),
        edge_supports=edge_supports,
        fully_mapped=fully_mapped,
        unmapped=unmapped,
        stale=stale,
        deleted=deleted,
        unauthorized=unauthorized,
        missing_edge_support=missing_edge_support,
        native_prose=native_prose,
        steering_only=steering_only,
    )


def _graph_passage(
    n: int, *, doc: int, text: str = "canonical graph passage"
) -> GraphPassage:
    """Build one canonical locator for a graph-resolved chunk.

    Args:
        n: Chunk discriminator.
        doc: Document discriminator.
        text: Canonical citation text. Never vendor prose.

    Returns:
        Frozen graph passage.
    """

    return GraphPassage(
        chunk_id=_uid(n),
        document_id=_uid(10_000 + doc),
        version_id=_uid(20_000 + doc),
        citation_text=text,
    )


def _distractors(count: int = 12) -> tuple[HybridPassage, ...]:
    """Return Hybrid distractors that fill the frozen evidence cap.

    Args:
        count: Number of distractors. Twelve fills ``FINAL_EVIDENCE_MAX``.

    Returns:
        Ranked Hybrid passages with two per document.
    """

    return tuple(
        _hybrid(index, rank=index, doc=(index - 1) // 2, text=f"distractor {index}")
        for index in range(1, count + 1)
    )


def test_frozen_constants_match_plan() -> None:
    """Hop penalty, caps, RRF k, graph weight, and quotas are exact."""

    assert HOP_PENALTY == 0.25
    assert EDGE_SUPPORT_MULTIPLIER_CAP == 1.20
    assert FUSION_RRF_K == 60
    assert RRF_K == 60
    assert GRAPH_WEIGHT == 0.50
    assert AGREEMENT_CAP == 1.10
    assert GRAPH_DISCOVERED_ONLY_CAP == 0.40
    assert FUSION_SURVIVAL_THRESHOLD == 0.50
    assert GRAPH_SURVIVAL_FALLBACK_THRESHOLD == 0.50
    assert FUSION_FINAL_EVIDENCE_MAX == FINAL_EVIDENCE_MAX == 12
    assert FUSION_DOCUMENT_QUOTA == DOCUMENT_QUOTA == 2
    assert FUSION_SECTION_QUOTA == SECTION_QUOTA == 2


def test_path_support_and_edge_multiplier_golden() -> None:
    """Byte-identical hop penalty and 1.20 edge-support cap."""

    assert path_support(min_edge_support=1.0, hop_count=1) == pytest.approx(1.0)
    assert path_support(min_edge_support=1.0, hop_count=2) == pytest.approx(0.8)
    assert path_support(min_edge_support=1.0, hop_count=3) == pytest.approx(2.0 / 3.0)
    assert path_support(min_edge_support=0.5, hop_count=2) == pytest.approx(0.4)
    with pytest.raises(FusionError, match="hop_count_out_of_bounds"):
        path_support(min_edge_support=1.0, hop_count=4)
    assert edge_support_multiplier(1) == pytest.approx(1.0)
    assert edge_support_multiplier(2) == pytest.approx(1.10)
    assert edge_support_multiplier(3) == pytest.approx(1.20)
    assert edge_support_multiplier(4) == pytest.approx(1.20)
    with pytest.raises(FusionError, match="no_supported_edges_in_passage"):
        edge_support_multiplier(0)
    assert graph_passage_strength_for_path(
        min_edge_support=1.0,
        hop_count=2,
        distinct_supported_edges_in_passage=2,
    ) == pytest.approx(0.8 * 1.10)


def test_combined_rrf_and_agreement_cap() -> None:
    """RRF k=60, graph weight 0.50, agreement at most 1.10, absent branch is 0."""

    assert combined_rrf_score(hybrid_rank=1, graph_rank=None) == pytest.approx(
        1.0 / 61.0
    )
    assert combined_rrf_score(hybrid_rank=None, graph_rank=1) == pytest.approx(
        0.50 / 61.0
    )
    both = combined_rrf_score(hybrid_rank=1, graph_rank=1)
    assert both == pytest.approx(1.50 / 61.0)
    agreed = apply_agreement_multiplier(both, ranks_in_both=True)
    assert agreed == pytest.approx((1.50 / 61.0) * 1.10)
    assert apply_agreement_multiplier(1.0, ranks_in_both=False) == 1.0
    with pytest.raises(FusionError, match="agreement_multiplier_above_cap"):
        apply_agreement_multiplier(1.0, ranks_in_both=True, multiplier=1.11)
    with pytest.raises(FusionError, match="model_fusion_weight"):
        combined_rrf_score(hybrid_rank=1, graph_rank=1, graph_weight=0.51)


def test_model_fusion_weight_rejected_on_input() -> None:
    """LLM-generated graph weights fail closed at parse time."""

    with pytest.raises((FusionError, ValidationError), match="model_fusion_weight"):
        FusionInput(
            requested_route="combined",
            effective_route="combined",
            graph_weight=0.70,
        )


def test_refund_period_uses_hybrid_evidence_only() -> None:
    """Refund-period fact is Hybrid-only; graph paths do not score."""

    gold = _hybrid(1, rank=1, doc=1, text="The refund period is 30 days.")
    fusion = fuse_evidence(
        FusionInput(
            requested_route="hybrid",
            effective_route="hybrid",
            hybrid_passages=(gold,),
            graph_paths=(_path(99),),
            graph_passages=(_graph_passage(99, doc=99),),
        ),
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
    )
    assert fusion.effective_route == "hybrid"
    assert [item.chunk_id for item in fusion.evidence] == [_uid(1)]
    assert fusion.evidence[0].graph_rank is None
    assert fusion.evidence[0].citation_text == "The refund period is 30 days."
    assert fusion.keyword_extract_count == 0


def test_project_atlas_combined_resolved_support() -> None:
    """Project Atlas product relationships promote resolved canonical support."""

    gold = _hybrid(
        90,
        rank=20,
        doc=90,
        text="Project Atlas ships the Atlas Controller with Supplier A.",
    )
    fusion = fuse_evidence(
        FusionInput(
            requested_route="combined",
            effective_route="combined",
            hybrid_passages=(*_distractors(), gold),
            graph_paths=(_path(90),),
            graph_passages=(_graph_passage(90, doc=90, text=gold.citation_text),),
            graph_survival_ratio=1.0,
        ),
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
    )
    ids = [item.chunk_id for item in fusion.evidence]
    assert _uid(90) in ids
    scored = next(item for item in fusion.evidence if item.chunk_id == _uid(90))
    assert scored.graph_rank == 1
    assert scored.hybrid_rank == 20
    assert scored.origin.value == "both"
    assert fusion.requested_route == "combined"
    assert fusion.effective_route == "combined"
    assert fusion.graph_discovered_only_ratio <= GRAPH_DISCOVERED_ONLY_CAP + 1e-12


def test_atlas_to_supplier_multihop_path() -> None:
    """Atlas-to-Supplier two-hop path contributes both canonical chunks."""

    atlas = _hybrid(
        91, rank=15, doc=91, text="Atlas Controller is a Project Atlas product."
    )
    supplier = _hybrid(
        92, rank=16, doc=92, text="Supplier A manufactures the Atlas Controller."
    )
    fusion = fuse_evidence(
        FusionInput(
            requested_route="combined",
            effective_route="combined",
            hybrid_passages=(*_distractors(), atlas, supplier),
            graph_paths=(_path(91, 92, supports=(1.0, 0.9)),),
            graph_passages=(
                _graph_passage(91, doc=91, text=atlas.citation_text),
                _graph_passage(92, doc=92, text=supplier.citation_text),
            ),
            graph_survival_ratio=1.0,
        ),
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
    )
    ids = {item.chunk_id for item in fusion.evidence}
    assert {_uid(91), _uid(92)}.issubset(ids)
    for chunk_id in (_uid(91), _uid(92)):
        scored = next(item for item in fusion.evidence if item.chunk_id == chunk_id)
        assert scored.statement_ids == ("stmt-91", "stmt-92")
        assert scored.path_support == pytest.approx(0.9 / 1.25)


def test_lightrag_timeout_is_hybrid_fallback_not_combined() -> None:
    """LightRAG timeout keeps requested Combined and effective Hybrid."""

    gold = _hybrid(1, rank=1, doc=1, text="Canonical Hybrid fact.")
    fusion = fuse_evidence(
        FusionInput(
            requested_route="combined",
            effective_route="combined",
            hybrid_passages=(gold,),
            graph_paths=(_path(90),),
            graph_timeout=True,
            graph_survival_ratio=1.0,
        ),
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
    )
    assert fusion.requested_route == "combined"
    assert fusion.effective_route == "hybrid"
    assert fusion.fallback_reason == "graph_timeout"
    assert fusion.evidence[0].graph_rank is None


def test_survival_below_threshold_degrades_to_hybrid() -> None:
    """Combined with survival < 0.50 becomes effective Hybrid."""

    fusion = fuse_evidence(
        FusionInput(
            requested_route="combined",
            effective_route="combined",
            hybrid_passages=(_hybrid(1, rank=1, doc=1),),
            graph_paths=(_path(90),),
            graph_survival_ratio=0.49,
        ),
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
    )
    assert fusion.effective_route == "hybrid"
    assert fusion.fallback_reason == FALLBACK_GRAPH_SURVIVAL_BELOW_THRESHOLD
    assert fusion.evidence[0].graph_rank is None


def test_unmapped_stale_deleted_unauthorized_and_missing_edge_are_discarded() -> None:
    """Unusable paths never contribute graph ranks."""

    gold = _hybrid(1, rank=1, doc=1)
    fusion = fuse_evidence(
        FusionInput(
            requested_route="combined",
            effective_route="combined",
            hybrid_passages=(gold,),
            graph_paths=(
                _path(2, fully_mapped=False, unmapped=True),
                _path(3, stale=True),
                _path(4, deleted=True),
                _path(5, unauthorized=True),
                _path(6, missing_edge_support=True),
            ),
            graph_survival_ratio=1.0,
        ),
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
    )
    assert all(item.graph_rank is None for item in fusion.evidence)
    assert FALLBACK_UNMAPPED_PATH in fusion.discarded_paths
    assert FALLBACK_MISSING_EDGE_SUPPORT in fusion.discarded_paths


def test_native_prose_and_bm25_snippet_fail_closed() -> None:
    """Vendor description/reference and BM25 snippets cannot be evidence."""

    with pytest.raises(FusionError, match=FALLBACK_NATIVE_PROSE):
        fuse_evidence(
            FusionInput(
                requested_route="combined",
                effective_route="combined",
                graph_paths=(_path(1, native_prose=True),),
                graph_survival_ratio=1.0,
            ),
            algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        )
    with pytest.raises(FusionError, match=FALLBACK_NATIVE_PROSE):
        fuse_evidence(
            FusionInput(
                requested_route="combined",
                effective_route="combined",
                hybrid_passages=(_hybrid(1, rank=1, doc=1),),
                graph_passages=(
                    GraphPassage(
                        chunk_id=_uid(1),
                        document_id=_uid(10_001),
                        version_id=_uid(20_001),
                        citation_text="vendor description",
                        native_prose=True,
                    ),
                ),
                graph_survival_ratio=1.0,
            ),
            algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        )
    snippet = HybridPassage.model_construct(
        chunk_id=_uid(1),
        document_id=_uid(10_001),
        version_id=_uid(20_001),
        citation_text="bm25 hit",
        hybrid_rank=1,
        bm25_snippet=True,
    )
    with pytest.raises(FusionError, match="bm25_snippet_evidence"):
        fuse_evidence(
            FusionInput(
                requested_route="hybrid",
                effective_route="hybrid",
                hybrid_passages=(snippet,),
            ),
            algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        )


def test_graph_only_answer_fallback_fails() -> None:
    """Combined cannot answer from graph-discovered-only passages alone."""

    with pytest.raises(FusionError, match=FALLBACK_GRAPH_ONLY_ANSWER):
        fuse_evidence(
            FusionInput(
                requested_route="combined",
                effective_route="combined",
                graph_paths=(_path(51), _path(52)),
                graph_passages=(
                    _graph_passage(51, doc=51),
                    _graph_passage(52, doc=52),
                ),
                graph_survival_ratio=1.0,
            ),
            algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        )


def test_graph_discovered_only_cap_is_forty_percent() -> None:
    """Final evidence may include at most 40% graph-discovered-only units."""

    hybrid = tuple(_hybrid(index, rank=index, doc=index) for index in range(1, 7))
    paths = tuple(_path(50 + index) for index in range(1, 7))
    passages = tuple(
        _graph_passage(50 + index, doc=50 + index) for index in range(1, 7)
    )
    fusion = fuse_evidence(
        FusionInput(
            requested_route="combined",
            effective_route="combined",
            hybrid_passages=hybrid,
            graph_paths=paths,
            graph_passages=passages,
            graph_survival_ratio=1.0,
        ),
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
    )
    assert fusion.graph_discovered_only_ratio <= GRAPH_DISCOVERED_ONLY_CAP + 1e-12
    graph_only = [item for item in fusion.evidence if item.graph_discovered_only]
    assert len(graph_only) / len(fusion.evidence) <= 0.40 + 1e-12
    assert len(fusion.dropped_graph_only) >= 1


def test_global_steering_never_receives_graph_score() -> None:
    """GlobalSteering expansions return through Hybrid and are not graph-ranked."""

    steered = _hybrid(7, rank=1, doc=7, text="theme expansion")
    fusion = fuse_evidence(
        FusionInput(
            requested_route="combined",
            effective_route="combined",
            hybrid_passages=(steered,),
            graph_paths=(_path(7, steering_only=True),),
            global_steering_chunk_ids=(_uid(7),),
            graph_survival_ratio=1.0,
        ),
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
    )
    assert fusion.evidence[0].graph_rank is None
    assert fusion.evidence[0].graph_discovered_only is False


def test_hidden_keyword_and_lightrag_answer_fail_closed() -> None:
    """Hidden LightRAG keyword extract and answer_generate stay forbidden."""

    hidden_keyword = FusionInput.model_construct(
        requested_route="combined",
        effective_route="combined",
        hybrid_passages=(),
        graph_paths=(),
        graph_passages=(),
        keyword_extract_count=1,
        lightrag_answer_generate_count=0,
        graph_weight=GRAPH_WEIGHT,
        tune_on_holdout=False,
    )
    with pytest.raises(FusionError, match=FALLBACK_HIDDEN_KEYWORD):
        fuse_evidence(hidden_keyword, algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION)
    hidden_answer = FusionInput.model_construct(
        requested_route="combined",
        effective_route="combined",
        hybrid_passages=(),
        graph_paths=(),
        graph_passages=(),
        keyword_extract_count=0,
        lightrag_answer_generate_count=1,
        graph_weight=GRAPH_WEIGHT,
        tune_on_holdout=False,
    )
    with pytest.raises(FusionError, match=FALLBACK_HIDDEN_LIGHTRAG_ANSWER):
        fuse_evidence(hidden_answer, algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION)


def test_holdout_tuned_configuration_fails() -> None:
    """Holdout labels cannot tune fusion configuration."""

    with pytest.raises(FusionError, match=FALLBACK_HOLDOUT_TUNING):
        refuse_holdout_tuning()
    with pytest.raises((FusionError, ValidationError), match=FALLBACK_HOLDOUT_TUNING):
        FusionInput(
            requested_route="combined",
            effective_route="combined",
            tune_on_holdout=True,
        )
    with pytest.raises(HoldoutSealedError):
        run_ablation(
            (
                (
                    "x",
                    FusionInput(requested_route="hybrid", effective_route="hybrid"),
                    (),
                ),
            ),
            holdout_access=HoldoutAccess(allowed=True, purpose="eval", actor="tester"),
        )


def test_fusion_input_from_branches_rejects_hidden_counters() -> None:
    """Branch snapshots cannot smuggle a hidden LightRAG keyword call."""

    poisoned = BranchResult.model_construct(
        branch_id="g-0",
        kind=BranchKind.GRAPH_LOCAL,
        family=Phase6RouteFamily.COMBINED,
        run_id=uuid4(),
        reservation_id=uuid4(),
        query_text="atlas",
        keyword_extract_count=1,
        lightrag_answer_generate_count=0,
        hybrid_evidence=(),
        graph_paths=(),
        graph_passages=(),
    )
    with pytest.raises(FusionError, match=FALLBACK_HIDDEN_KEYWORD):
        fusion_input_from_branches(
            (poisoned,),
            requested_route="combined",
            effective_route="combined",
        )


def _ablation_cases() -> tuple[tuple[str, FusionInput, tuple[str, ...]], ...]:
    """Return development fixtures where fusion can beat naive union.

    Returns:
        ``(case_id, fusion_input, gold_chunk_ids)`` tuples. Holdout is unused.
    """

    refund = _hybrid(1, rank=1, doc=1, text="The refund period is 30 days.")
    atlas = _hybrid(
        90,
        rank=20,
        doc=90,
        text="Project Atlas ships the Atlas Controller.",
    )
    hop_a = _hybrid(
        91, rank=15, doc=91, text="Atlas Controller is a Project Atlas product."
    )
    hop_b = _hybrid(
        92, rank=16, doc=92, text="Supplier A manufactures the Atlas Controller."
    )
    return (
        (
            "refund-period",
            FusionInput(
                requested_route="hybrid",
                effective_route="hybrid",
                hybrid_passages=(refund,),
            ),
            (_uid(1),),
        ),
        (
            "project-atlas-product",
            FusionInput(
                requested_route="combined",
                effective_route="combined",
                hybrid_passages=(*_distractors(), atlas),
                graph_paths=(_path(90),),
                graph_passages=(_graph_passage(90, doc=90, text=atlas.citation_text),),
                graph_survival_ratio=1.0,
            ),
            (_uid(90),),
        ),
        (
            "atlas-to-supplier-multihop",
            FusionInput(
                requested_route="combined",
                effective_route="combined",
                hybrid_passages=(*_distractors(), hop_a, hop_b),
                graph_paths=(_path(91, 92, supports=(1.0, 0.9)),),
                graph_passages=(
                    _graph_passage(91, doc=91, text=hop_a.citation_text),
                    _graph_passage(92, doc=92, text=hop_b.citation_text),
                ),
                graph_survival_ratio=1.0,
            ),
            (_uid(91), _uid(92)),
        ),
    )


def test_resolved_path_fusion_beats_naive_union_on_dev_fixtures() -> None:
    """Keep fusion only when it beats union on success and citation completeness.

    Live QT-EVAL-009 Combined +10pp remains unverified. These fixtures are
    synthetic authorized IDs plus formula ranking, not holdout labels.
    """

    report = run_ablation(_ablation_cases(), holdout_access=HoldoutAccess.denied())
    assert report.holdout_used is False
    assert report.live_combined_gain_status == "unverified"
    assert report.fusion_success_rate > report.union_success_rate
    assert report.fusion_completeness + 1e-12 >= report.union_completeness
    assert report.fusion_beats_union is True
    assert report.selected_algorithm is FusionAlgorithm.RESOLVED_PATH_FUSION
    assert SELECTED_FUSION_ALGORITHM is FusionAlgorithm.RESOLVED_PATH_FUSION
    assert report.config_hash == fusion_config_hash(
        FusionAlgorithm.RESOLVED_PATH_FUSION
    )
    assert report.hybrid_success_rate == pytest.approx(1.0 / 3.0)
    assert report.union_success_rate == pytest.approx(1.0 / 3.0)
    assert report.fusion_success_rate == pytest.approx(1.0)
    assert report.combined_minus_hybrid_pp == pytest.approx(200.0 / 3.0)
    refund, atlas, multi = report.cases
    assert refund.hybrid_success is True
    assert atlas.fusion_success is True
    assert atlas.union_success is False
    assert atlas.hybrid_success is False
    assert multi.fusion_success is True
    assert multi.union_success is False
