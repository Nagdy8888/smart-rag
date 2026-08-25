"""Complete deterministic route and limitation matrix for packet 2."""

from __future__ import annotations

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.extract import extract_deterministic
from smart_rag_core.query_profile.phase6_map import (
    Phase6Limitation,
    Phase6RouteFamily,
    map_query_type_to_phase6_family,
)
from smart_rag_core.query_routing.constants import (
    BRANCH_CONCURRENCY,
    MAX_GRAPH_EXPANSIONS,
    PROVISIONAL_COVERAGE_THRESHOLD,
    SUBQUESTION_CEILING,
    WHOLE_DOCUMENT_SECTION_COVERAGE,
)
from smart_rag_core.query_routing.envelope import (
    clamp_family_to_reservation,
    reject_production_manual_override,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.knowledge_scope import no_retrieval_mode_for_scope
from smart_rag_core.query_routing.models import (
    BranchKind,
    BranchSpec,
    Phase6Extension,
    QueryPreparation,
    RetrievalPlan,
    RoutingSurface,
)
from smart_rag_core.query_routing.signals import (
    comparison_wants_relationship,
    comparison_wants_table,
    is_current_relationship,
    media_has_caption_or_ocr,
)
from smart_rag_core.retrieval.frozen_profile import coverage_threshold_for


def evaluation_class_for(prep: QueryPreparation) -> QueryClass:
    """Map a preparation onto a frozen evaluation class for coverage lookup.

    Args:
        prep: Typed preparation.

    Returns:
        Frozen ``QueryClass``. Unknown types use ``semantic_factual``.
    """

    if prep.media_intent:
        return QueryClass.MEDIA_LIMITATION
    if prep.negation_scope != "none":
        return QueryClass.NEGATION
    if prep.whole_document_summary:
        return QueryClass.DOCUMENT_SUMMARY
    if prep.table_intent:
        return QueryClass.TABULAR_AGGREGATION
    if prep.historical_relationship or prep.relationship_intent:
        return QueryClass.RELATIONSHIP
    try:
        query_type = QueryType(prep.query_type)
    except ValueError:
        return QueryClass.SEMANTIC_FACTUAL
    mapping = {
        QueryType.EXACT_IDENTIFIER: QueryClass.EXACT_CODE,
        QueryType.FACTUAL: QueryClass.SEMANTIC_FACTUAL,
        QueryType.SEMANTIC_CONCEPTUAL: QueryClass.SEMANTIC_FACTUAL,
        QueryType.MULTI_PART: QueryClass.MULTI_PART,
        QueryType.RELATIONSHIP_MULTI_HOP: QueryClass.RELATIONSHIP,
        QueryType.BROAD_SUMMARY: QueryClass.BROAD_SYNTHESIS,
        QueryType.STRUCTURED_TABULAR: QueryClass.TABULAR_AGGREGATION,
    }
    return mapping.get(query_type, QueryClass.SEMANTIC_FACTUAL)


def frozen_coverage_threshold(prep: QueryPreparation) -> float:
    """Return the frozen per-class coverage threshold. Never retuned here.

    Args:
        prep: Typed preparation.

    Returns:
        Frozen threshold. Provisionally ``0.65`` for every class.

    Raises:
        QueryRoutingError: If a caller attempts to use a different value.
    """

    threshold = coverage_threshold_for(evaluation_class_for(prep))
    if abs(threshold - PROVISIONAL_COVERAGE_THRESHOLD) > 1e-12:
        raise QueryRoutingError("holdout_driven_threshold_change")
    return threshold


def _query_type(prep: QueryPreparation) -> QueryType:
    """Parse the frozen query type, defaulting to factual.

    Args:
        prep: Typed preparation.

    Returns:
        Phase 4 ``QueryType``.
    """

    try:
        return QueryType(prep.query_type)
    except ValueError:
        return QueryType.FACTUAL


def _hybrid_branch(
    prep: QueryPreparation,
    *,
    branch_id: str,
    query_text: str,
    group: int,
) -> BranchSpec:
    """Build one Hybrid branch inheriting packet 1 authorization.

    Args:
        prep: Typed preparation.
        branch_id: Stable id.
        query_text: Original or subquestion text.
        group: Parallel group.

    Returns:
        Hybrid ``BranchSpec``.
    """

    return BranchSpec(
        branch_id=branch_id,
        kind=BranchKind.HYBRID,
        family=Phase6RouteFamily.HYBRID,
        query_text=query_text,
        parallel_group=group,
        hl_keywords=prep.hl_keywords,
        ll_keywords=prep.ll_keywords,
    )


def _graph_branch(
    prep: QueryPreparation,
    *,
    branch_id: str,
    kind: BranchKind,
    family: Phase6RouteFamily,
    group: int,
) -> BranchSpec:
    """Build one graph lead branch with precomputed keywords only.

    Args:
        prep: Typed preparation.
        branch_id: Stable id.
        kind: Local, hybrid, or global steering.
        family: Combined or inspection.
        group: Parallel group.

    Returns:
        Graph ``BranchSpec``. Empty keywords are left for execute to fail closed.
    """

    return BranchSpec(
        branch_id=branch_id,
        kind=kind,
        family=family,
        query_text=prep.original,
        parallel_group=group,
        hl_keywords=prep.hl_keywords,
        ll_keywords=prep.ll_keywords,
        max_graph_expansions=MAX_GRAPH_EXPANSIONS,
    )


def _citation_branch(prep: QueryPreparation, *, group: int) -> BranchSpec:
    """Build ID-resolution-only citation lookup.

    Args:
        prep: Typed preparation.
        group: Parallel group.

    Returns:
        Citation lookup spec. Not a catalog tool.
    """

    return BranchSpec(
        branch_id="cite-0",
        kind=BranchKind.CITATION_LOOKUP,
        family=Phase6RouteFamily.HYBRID,
        query_text=prep.original,
        parallel_group=group,
        hl_keywords=prep.hl_keywords,
        ll_keywords=prep.ll_keywords,
    )


def _assert_subquestions(items: tuple[str, ...]) -> tuple[str, ...]:
    """Reject a fourth subquestion instead of silently truncating.

    Args:
        items: Candidate subquestions.

    Returns:
        The items when length is at most three.

    Raises:
        QueryRoutingError: ``fourth_subquestion``.
    """

    if len(items) > SUBQUESTION_CEILING:
        raise QueryRoutingError("fourth_subquestion")
    return items


def compile_retrieval_plan(
    prep: QueryPreparation,
    runtime: AuthorizedRuntimeContext,
    *,
    requested_manual_route: str | None = None,
    section_coverage_ratio: float | None = None,
) -> RetrievalPlan:
    """Compile the allow-listed route/limitation matrix.

    Core routes are deterministic. Catalog-search LLMs are never consulted.
    Production manual routing is rejected. The planner never exceeds the
    packet 1 reserved envelope.

    Args:
        prep: Typed preparation. Original query is required.
        runtime: Packet 1 authorized runtime. ``route_family`` is the envelope.
        requested_manual_route: Diagnostic-only override.
        section_coverage_ratio: Known whole-document ratio when already scored.

    Returns:
        Frozen retrieval plan with bounded branches.

    Raises:
        QueryRoutingError: Production manual override, fourth subquestion,
            unproved complement, graph-only answer, or NoRetrieval claim.
    """

    reject_production_manual_override(
        surface=prep.routing_surface.value,
        requested_manual_route=requested_manual_route,
    )
    query_type = _query_type(prep)
    query_class = evaluation_class_for(prep)
    mapped = map_query_type_to_phase6_family(
        query_type,
        query_class,
        historical_relationship=prep.historical_relationship,
        comparison=prep.comparison and query_type is QueryType.MULTI_PART,
        scoped_summary_incomplete=(
            prep.whole_document_summary
            and section_coverage_ratio is not None
            and section_coverage_ratio < WHOLE_DOCUMENT_SECTION_COVERAGE
        ),
    )
    threshold = frozen_coverage_threshold(prep)
    surface = prep.routing_surface
    manual = prep.manual_mode
    desired, limitations, branches, flags = _matrix_case(
        prep,
        extract_query_type=query_type,
        mapped_family=mapped.phase6_family,
        mapped_limitation=mapped.limitation,
        section_coverage_ratio=section_coverage_ratio,
    )
    if surface is RoutingSurface.DIAGNOSTIC and requested_manual_route and manual:
        try:
            desired = Phase6RouteFamily(requested_manual_route)
        except ValueError as exc:
            raise QueryRoutingError("unknown_manual_route") from exc
    effective, envelope_reason = clamp_family_to_reservation(desired, runtime)
    if envelope_reason:
        limitations = (*limitations, envelope_reason)
        branches = _degrade_branches_to_hybrid(prep, branches)
        flags["relationship_signal_retained"] = bool(
            flags.get("relationship_signal_retained") or prep.relationship_intent
        )
    if effective is Phase6RouteFamily.COMPOSITE:
        families = {
            branch.family
            for branch in branches
            if branch.kind
            not in {
                BranchKind.CITATION_LOOKUP,
                BranchKind.NO_RETRIEVAL,
                BranchKind.SCOPED_REFUSAL,
            }
        }
        if len(families) <= 1:
            effective = next(iter(families), Phase6RouteFamily.HYBRID)
    return RetrievalPlan(
        requested_route=runtime.route_family,
        effective_route=effective,
        corrected_route=None,
        branches=branches,
        limitations=tuple(dict.fromkeys(limitations)),
        historical_relationship=prep.historical_relationship,
        temporal_graph_limitation="temporal_graph_limitation" in limitations,
        whole_document_summary=prep.whole_document_summary,
        section_coverage_required=WHOLE_DOCUMENT_SECTION_COVERAGE,
        coverage_threshold=threshold,
        company_claim_forbidden=flags["company_claim_forbidden"],
        graph_as_answer_forbidden=flags["graph_as_answer_forbidden"],
        prove_complement=False,
        media_answer_forbidden=flags["media_answer_forbidden"],
        manual_mode=manual,
        routing_surface=surface,
        hybrid_prose_composition=flags["hybrid_prose_composition"],
        relationship_signal_retained=flags["relationship_signal_retained"],
        fallback_reason=envelope_reason,
        branch_concurrency=BRANCH_CONCURRENCY,
        max_subquestions=SUBQUESTION_CEILING,
        catalog_llm_call_count=0,
        knowledge_scope=prep.knowledge_scope,
        no_retrieval_answer_mode=no_retrieval_mode_for_scope(prep.knowledge_scope),
    )


def _degrade_branches_to_hybrid(
    prep: QueryPreparation,
    branches: tuple[BranchSpec, ...],
) -> tuple[BranchSpec, ...]:
    """Drop graph branches when the reserved envelope cannot enlarge.

    Args:
        prep: Typed preparation.
        branches: Planned branches.

    Returns:
        Hybrid/table/refusal branches only.
    """

    kept: list[BranchSpec] = []
    for branch in branches:
        if branch.kind in {
            BranchKind.GRAPH_LOCAL,
            BranchKind.GRAPH_HYBRID,
            BranchKind.GRAPH_GLOBAL_STEERING,
        }:
            continue
        kept.append(branch)
    if not any(item.kind is BranchKind.HYBRID for item in kept):
        kept.insert(
            0,
            _hybrid_branch(prep, branch_id="hyb-0", query_text=prep.original, group=0),
        )
    return tuple(kept)


def _matrix_case(
    prep: QueryPreparation,
    *,
    extract_query_type: QueryType,
    mapped_family: Phase6RouteFamily,
    mapped_limitation: Phase6Limitation | None,
    section_coverage_ratio: float | None,
) -> tuple[
    Phase6RouteFamily,
    tuple[str, ...],
    tuple[BranchSpec, ...],
    dict[str, bool],
]:
    """Select one matrix row: family, limitations, branches, and flags.

    Args:
        prep: Typed preparation.
        extract_query_type: Frozen query type.
        mapped_family: Phase 4 map result before packet 2 extensions.
        mapped_limitation: Optional temporal limitation from the map.
        section_coverage_ratio: Known whole-document ratio.

    Returns:
        Desired family, limitation codes, branches, and boolean flags.
    """

    flags = {
        "company_claim_forbidden": False,
        "graph_as_answer_forbidden": False,
        "media_answer_forbidden": False,
        "hybrid_prose_composition": False,
        "relationship_signal_retained": prep.low_confidence_relationship
        or prep.relationship_intent,
    }
    original = prep.original
    if prep.phase6_extension is Phase6Extension.NO_RETRIEVAL:
        flags["company_claim_forbidden"] = True
        flags["relationship_signal_retained"] = False
        return (
            Phase6RouteFamily.NO_RETRIEVAL,
            ("no_retrieval",),
            (
                BranchSpec(
                    branch_id="none-0",
                    kind=BranchKind.NO_RETRIEVAL,
                    family=Phase6RouteFamily.NO_RETRIEVAL,
                    query_text=original,
                    parallel_group=0,
                ),
            ),
            flags,
        )
    if prep.phase6_extension is Phase6Extension.GRAPH_INSPECTION:
        flags["graph_as_answer_forbidden"] = True
        flags["relationship_signal_retained"] = False
        return (
            Phase6RouteFamily.GRAPH_INSPECTION,
            ("graph_inspection_only",),
            (
                BranchSpec(
                    branch_id="insp-0",
                    kind=BranchKind.GRAPH_INSPECTION,
                    family=Phase6RouteFamily.GRAPH_INSPECTION,
                    query_text=original,
                    parallel_group=0,
                    hl_keywords=prep.hl_keywords,
                    ll_keywords=prep.ll_keywords,
                ),
            ),
            flags,
        )
    if prep.media_intent and not media_has_caption_or_ocr(original):
        flags["media_answer_forbidden"] = True
        flags["relationship_signal_retained"] = False
        return (
            Phase6RouteFamily.SCOPED_REFUSAL,
            ("media_limitation",),
            (
                BranchSpec(
                    branch_id="media-0",
                    kind=BranchKind.SCOPED_REFUSAL,
                    family=Phase6RouteFamily.SCOPED_REFUSAL,
                    query_text=original,
                    parallel_group=0,
                ),
            ),
            flags,
        )
    if prep.negation_scope != "none":
        flags["relationship_signal_retained"] = False
        return (
            Phase6RouteFamily.HYBRID,
            ("negation_unscoped",),
            (
                _hybrid_branch(prep, branch_id="hyb-neg", query_text=original, group=0),
                _citation_branch(prep, group=1),
            ),
            flags,
        )
    if prep.historical_relationship:
        flags["relationship_signal_retained"] = False
        return (
            Phase6RouteFamily.HYBRID,
            (Phase6Limitation.TEMPORAL_GRAPH_LIMITATION.value,),
            (
                _hybrid_branch(
                    prep, branch_id="hyb-hist", query_text=original, group=0
                ),
                _citation_branch(prep, group=1),
            ),
            flags,
        )
    if prep.whole_document_summary:
        if (
            section_coverage_ratio is not None
            and section_coverage_ratio < WHOLE_DOCUMENT_SECTION_COVERAGE
        ):
            return (
                Phase6RouteFamily.SCOPED_REFUSAL,
                ("scoped_summary", "section_coverage_below_1"),
                (
                    BranchSpec(
                        branch_id="sum-refuse",
                        kind=BranchKind.SCOPED_REFUSAL,
                        family=Phase6RouteFamily.SCOPED_REFUSAL,
                        query_text=original,
                        parallel_group=0,
                    ),
                ),
                flags,
            )
        return (
            Phase6RouteFamily.HYBRID,
            ("whole_document_section_coverage",),
            (
                _hybrid_branch(prep, branch_id="hyb-sum", query_text=original, group=0),
                _citation_branch(prep, group=1),
            ),
            flags,
        )
    if prep.corpus_wide_theme:
        return (
            Phase6RouteFamily.COMBINED,
            ("global_steering_only",),
            (
                _hybrid_branch(
                    prep, branch_id="hyb-theme", query_text=original, group=0
                ),
                _graph_branch(
                    prep,
                    branch_id="steer-0",
                    kind=BranchKind.GRAPH_GLOBAL_STEERING,
                    family=Phase6RouteFamily.COMBINED,
                    group=0,
                ),
                _citation_branch(prep, group=1),
            ),
            flags,
        )
    extract = extract_deterministic(original)
    if prep.comparison or extract_query_type is QueryType.MULTI_PART:
        return _comparison_or_multipart(prep, extract=extract, flags=flags)
    if prep.table_intent or extract_query_type is QueryType.STRUCTURED_TABULAR:
        flags["hybrid_prose_composition"] = "explain" in original.lower()
        return (
            Phase6RouteFamily.STRUCTURED_TABLE,
            (),
            (
                BranchSpec(
                    branch_id="tbl-0",
                    kind=BranchKind.STRUCTURED_TABLE,
                    family=Phase6RouteFamily.STRUCTURED_TABLE,
                    query_text=original,
                    parallel_group=0,
                    hl_keywords=prep.hl_keywords,
                    ll_keywords=prep.ll_keywords,
                ),
            ),
            flags,
        )
    if is_current_relationship(original, extract):
        return (
            Phase6RouteFamily.COMBINED,
            (),
            (
                _hybrid_branch(prep, branch_id="hyb-rel", query_text=original, group=0),
                _graph_branch(
                    prep,
                    branch_id="graph-local",
                    kind=BranchKind.GRAPH_LOCAL,
                    family=Phase6RouteFamily.COMBINED,
                    group=0,
                ),
                _citation_branch(prep, group=1),
            ),
            flags,
        )
    if prep.low_confidence_relationship:
        flags["relationship_signal_retained"] = True
        return (
            Phase6RouteFamily.HYBRID,
            ("low_confidence_relationship",),
            (
                _hybrid_branch(prep, branch_id="hyb-low", query_text=original, group=0),
                _citation_branch(prep, group=1),
            ),
            flags,
        )
    family = mapped_family
    limitations: tuple[str, ...] = ()
    if mapped_limitation is not None:
        limitations = (mapped_limitation.value,)
    return (
        family,
        limitations,
        (
            _hybrid_branch(prep, branch_id="hyb-0", query_text=original, group=0),
            _citation_branch(prep, group=1),
        ),
        flags,
    )


def _comparison_or_multipart(
    prep: QueryPreparation,
    *,
    extract: object,
    flags: dict[str, bool],
) -> tuple[
    Phase6RouteFamily,
    tuple[str, ...],
    tuple[BranchSpec, ...],
    dict[str, bool],
]:
    """Decompose comparison/multi-part into at most three family branches.

    Args:
        prep: Typed preparation.
        extract: Deterministic extract (typed as object to avoid a cycle).
        flags: Mutable flag dict.

    Returns:
        Family, limitations, branches, and flags.
    """

    from smart_rag_core.query_profile.extract import DeterministicExtract

    det = (
        extract
        if isinstance(extract, DeterministicExtract)
        else extract_deterministic(prep.original)
    )
    subs = _assert_subquestions(prep.decomposition or det.subquestions)
    wants_table = comparison_wants_table(prep.original, det)
    wants_rel = comparison_wants_relationship(prep.original, det)
    families: list[Phase6RouteFamily] = []
    branches: list[BranchSpec] = []
    group = 0
    if wants_table:
        families.append(Phase6RouteFamily.STRUCTURED_TABLE)
        branches.append(
            BranchSpec(
                branch_id="tbl-cmp",
                kind=BranchKind.STRUCTURED_TABLE,
                family=Phase6RouteFamily.STRUCTURED_TABLE,
                query_text=prep.original,
                parallel_group=group,
                hl_keywords=prep.hl_keywords,
                ll_keywords=prep.ll_keywords,
            )
        )
        group += 1
    if wants_rel and not prep.historical_relationship:
        families.append(Phase6RouteFamily.COMBINED)
        branches.append(
            _hybrid_branch(
                prep, branch_id="hyb-cmp-rel", query_text=prep.original, group=group
            )
        )
        branches.append(
            _graph_branch(
                prep,
                branch_id="graph-cmp",
                kind=BranchKind.GRAPH_HYBRID,
                family=Phase6RouteFamily.COMBINED,
                group=group,
            )
        )
        group += 1
        flags["relationship_signal_retained"] = True
    texts = subs or (prep.original,)
    if len(texts) > SUBQUESTION_CEILING:
        raise QueryRoutingError("fourth_subquestion")
    if not wants_rel or wants_table or len(texts) > 1:
        families.append(Phase6RouteFamily.HYBRID)
        for index, text in enumerate(texts[:SUBQUESTION_CEILING]):
            branches.append(
                _hybrid_branch(
                    prep,
                    branch_id=f"hyb-cmp-{index}",
                    query_text=text,
                    group=group,
                )
            )
        group += 1
    unique_families = tuple(dict.fromkeys(families))
    if len(unique_families) > 1:
        effective = Phase6RouteFamily.COMPOSITE
    elif unique_families:
        effective = unique_families[0]
    else:
        effective = Phase6RouteFamily.HYBRID
        branches.append(
            _hybrid_branch(
                prep, branch_id="hyb-cmp-0", query_text=prep.original, group=0
            )
        )
    branches.append(_citation_branch(prep, group=group))
    return effective, (), tuple(branches), flags
