"""Ordered named matrix rules. Precedence is the tuple order, not names."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.query_profile.extract import extract_deterministic
from smart_rag_core.query_profile.phase6_map import Phase6Limitation, Phase6RouteFamily
from smart_rag_core.query_routing.branch_specs import (
    citation_branch,
    graph_branch,
    hybrid_branch,
)
from smart_rag_core.query_routing.constants import (
    SUBQUESTION_CEILING,
    WHOLE_DOCUMENT_SECTION_COVERAGE,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.models import (
    BranchKind,
    BranchSpec,
    Phase6Extension,
    QueryPreparation,
)
from smart_rag_core.query_routing.signals import (
    comparison_wants_relationship,
    comparison_wants_table,
    is_current_relationship,
)


@dataclass(frozen=True, slots=True)
class MatrixDecision:
    """One matrix-row result.

    Attributes:
        family: Desired route family before envelope clamp.
        limitations: Named limitation codes.
        branches: Planned branch specs.
    """

    family: Phase6RouteFamily
    limitations: tuple[str, ...]
    branches: tuple[BranchSpec, ...]


@dataclass(slots=True)
class MatrixContext:
    """Inputs shared by every named matrix rule.

    Attributes:
        prep: Typed preparation.
        extract_query_type: Frozen query type.
        mapped_family: Phase 4 map result before packet 2 extensions.
        mapped_limitation: Optional temporal limitation from the map.
        section_coverage_ratio: Known whole-document ratio.
        flags: Mutable boolean flags written by the matching rule.
    """

    prep: QueryPreparation
    extract_query_type: QueryType
    mapped_family: Phase6RouteFamily
    mapped_limitation: Phase6Limitation | None
    section_coverage_ratio: float | None
    flags: dict[str, bool]


MatrixRuleFn = Callable[[MatrixContext], MatrixDecision | None]


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


def rule_web_research(ctx: MatrixContext) -> MatrixDecision | None:
    """Select a Web-only branch when the Phase 6 extension is set.

    A Web plan cannot contain Hybrid, Combined, StructuredTable, graph,
    correction, fusion, or optional-tool branches.

    Args:
        ctx: Shared matrix context.

    Returns:
        Web-research decision, or None when this rule does not apply.
    """

    if ctx.prep.phase6_extension is not Phase6Extension.WEB_RESEARCH:
        return None
    ctx.flags["company_claim_forbidden"] = True
    ctx.flags["relationship_signal_retained"] = False
    return MatrixDecision(
        Phase6RouteFamily.WEB_RESEARCH,
        ("web_research",),
        (
            BranchSpec(
                branch_id="web-0",
                kind=BranchKind.WEB_RESEARCH,
                family=Phase6RouteFamily.WEB_RESEARCH,
                query_text=ctx.prep.original,
                parallel_group=0,
            ),
        ),
    )


def rule_no_retrieval(ctx: MatrixContext) -> MatrixDecision | None:
    """Select NoRetrieval when the Phase 6 extension is set.

    Args:
        ctx: Shared matrix context.

    Returns:
        NoRetrieval decision, or None when this rule does not apply.
    """

    if ctx.prep.phase6_extension is not Phase6Extension.NO_RETRIEVAL:
        return None
    ctx.flags["company_claim_forbidden"] = True
    ctx.flags["relationship_signal_retained"] = False
    return MatrixDecision(
        Phase6RouteFamily.NO_RETRIEVAL,
        ("no_retrieval",),
        (
            BranchSpec(
                branch_id="none-0",
                kind=BranchKind.NO_RETRIEVAL,
                family=Phase6RouteFamily.NO_RETRIEVAL,
                query_text=ctx.prep.original,
                parallel_group=0,
            ),
        ),
    )


def rule_graph_inspection(ctx: MatrixContext) -> MatrixDecision | None:
    """Select graph inspection when the Phase 6 extension is set.

    Args:
        ctx: Shared matrix context.

    Returns:
        Inspection decision, or None when this rule does not apply.
    """

    if ctx.prep.phase6_extension is not Phase6Extension.GRAPH_INSPECTION:
        return None
    ctx.flags["graph_as_answer_forbidden"] = True
    ctx.flags["relationship_signal_retained"] = False
    return MatrixDecision(
        Phase6RouteFamily.GRAPH_INSPECTION,
        ("graph_inspection_only",),
        (
            BranchSpec(
                branch_id="insp-0",
                kind=BranchKind.GRAPH_INSPECTION,
                family=Phase6RouteFamily.GRAPH_INSPECTION,
                query_text=ctx.prep.original,
                parallel_group=0,
                hl_keywords=ctx.prep.hl_keywords,
                ll_keywords=ctx.prep.ll_keywords,
            ),
        ),
    )


def rule_unsupported_media(ctx: MatrixContext) -> MatrixDecision | None:
    """Let figure questions retrieve. Refusal happens after evidence.

    Stored figures are described and shown. A question that needs a
    figure and retrieves none still receives ``media_limitation`` from
    hybrid coverage. This rule no longer refuses before search.

    Args:
        ctx: Shared matrix context.

    Returns:
        None. Kept in the matrix so the rule name stays stable.
    """

    del ctx
    return None


def rule_negation(ctx: MatrixContext) -> MatrixDecision | None:
    """Keep negation on Hybrid and never prove a complement.

    Args:
        ctx: Shared matrix context.

    Returns:
        Hybrid limitation decision, or None when this rule does not apply.
    """

    if ctx.prep.negation_scope == "none":
        return None
    ctx.flags["relationship_signal_retained"] = False
    return MatrixDecision(
        Phase6RouteFamily.HYBRID,
        ("negation_unscoped",),
        (
            hybrid_branch(
                ctx.prep, branch_id="hyb-neg", query_text=ctx.prep.original, group=0
            ),
            citation_branch(ctx.prep, group=1),
        ),
    )


def rule_historical_relationship(ctx: MatrixContext) -> MatrixDecision | None:
    """Keep historical/as-of relationships on Hybrid.

    Args:
        ctx: Shared matrix context.

    Returns:
        Hybrid temporal limitation, or None when this rule does not apply.
    """

    if not ctx.prep.historical_relationship:
        return None
    ctx.flags["relationship_signal_retained"] = False
    return MatrixDecision(
        Phase6RouteFamily.HYBRID,
        (Phase6Limitation.TEMPORAL_GRAPH_LIMITATION.value,),
        (
            hybrid_branch(
                ctx.prep, branch_id="hyb-hist", query_text=ctx.prep.original, group=0
            ),
            citation_branch(ctx.prep, group=1),
        ),
    )


def rule_whole_document_summary(ctx: MatrixContext) -> MatrixDecision | None:
    """Require full section coverage for whole-document summaries.

    Args:
        ctx: Shared matrix context.

    Returns:
        Hybrid or scoped-refusal decision, or None when this rule does not apply.
    """

    if not ctx.prep.whole_document_summary:
        return None
    if (
        ctx.section_coverage_ratio is not None
        and ctx.section_coverage_ratio < WHOLE_DOCUMENT_SECTION_COVERAGE
    ):
        return MatrixDecision(
            Phase6RouteFamily.SCOPED_REFUSAL,
            ("scoped_summary", "section_coverage_below_1"),
            (
                BranchSpec(
                    branch_id="sum-refuse",
                    kind=BranchKind.SCOPED_REFUSAL,
                    family=Phase6RouteFamily.SCOPED_REFUSAL,
                    query_text=ctx.prep.original,
                    parallel_group=0,
                ),
            ),
        )
    return MatrixDecision(
        Phase6RouteFamily.HYBRID,
        ("whole_document_section_coverage",),
        (
            hybrid_branch(
                ctx.prep, branch_id="hyb-sum", query_text=ctx.prep.original, group=0
            ),
            citation_branch(ctx.prep, group=1),
        ),
    )


def rule_global_steering(ctx: MatrixContext) -> MatrixDecision | None:
    """Steer corpus-wide themes through Combined global graph.

    Args:
        ctx: Shared matrix context.

    Returns:
        Combined steering decision, or None when this rule does not apply.
    """

    if not ctx.prep.corpus_wide_theme:
        return None
    return MatrixDecision(
        Phase6RouteFamily.COMBINED,
        ("global_steering_only",),
        (
            hybrid_branch(
                ctx.prep, branch_id="hyb-theme", query_text=ctx.prep.original, group=0
            ),
            graph_branch(
                ctx.prep,
                branch_id="steer-0",
                kind=BranchKind.GRAPH_GLOBAL_STEERING,
                family=Phase6RouteFamily.COMBINED,
                group=0,
            ),
            citation_branch(ctx.prep, group=1),
        ),
    )


def rule_comparison_or_multipart(ctx: MatrixContext) -> MatrixDecision | None:
    """Decompose comparison/multi-part into at most three family branches.

    Args:
        ctx: Shared matrix context.

    Returns:
        Composite or single-family decision, or None when this rule does not apply.
    """

    if not (ctx.prep.comparison or ctx.extract_query_type is QueryType.MULTI_PART):
        return None

    extract = extract_deterministic(ctx.prep.original)
    det = extract
    subs = _assert_subquestions(ctx.prep.decomposition or det.subquestions)
    wants_table = comparison_wants_table(ctx.prep.original, det)
    wants_rel = comparison_wants_relationship(ctx.prep.original, det)
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
                query_text=ctx.prep.original,
                parallel_group=group,
                hl_keywords=ctx.prep.hl_keywords,
                ll_keywords=ctx.prep.ll_keywords,
            )
        )
        group += 1
    if wants_rel and not ctx.prep.historical_relationship:
        families.append(Phase6RouteFamily.COMBINED)
        branches.append(
            hybrid_branch(
                ctx.prep,
                branch_id="hyb-cmp-rel",
                query_text=ctx.prep.original,
                group=group,
            )
        )
        branches.append(
            graph_branch(
                ctx.prep,
                branch_id="graph-cmp",
                kind=BranchKind.GRAPH_HYBRID,
                family=Phase6RouteFamily.COMBINED,
                group=group,
            )
        )
        group += 1
        ctx.flags["relationship_signal_retained"] = True
    texts = subs or (ctx.prep.original,)
    if len(texts) > SUBQUESTION_CEILING:
        raise QueryRoutingError("fourth_subquestion")
    if not wants_rel or wants_table or len(texts) > 1:
        families.append(Phase6RouteFamily.HYBRID)
        for index, text in enumerate(texts[:SUBQUESTION_CEILING]):
            branches.append(
                hybrid_branch(
                    ctx.prep,
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
            hybrid_branch(
                ctx.prep, branch_id="hyb-cmp-0", query_text=ctx.prep.original, group=0
            )
        )
    branches.append(citation_branch(ctx.prep, group=group))
    return MatrixDecision(effective, (), tuple(branches))


def rule_structured_table(ctx: MatrixContext) -> MatrixDecision | None:
    """Select StructuredTable for table intent or tabular query types.

    Args:
        ctx: Shared matrix context.

    Returns:
        Table decision, or None when this rule does not apply.
    """

    if not (
        ctx.prep.table_intent or ctx.extract_query_type is QueryType.STRUCTURED_TABULAR
    ):
        return None
    ctx.flags["hybrid_prose_composition"] = "explain" in ctx.prep.original.lower()
    return MatrixDecision(
        Phase6RouteFamily.STRUCTURED_TABLE,
        (),
        (
            BranchSpec(
                branch_id="tbl-0",
                kind=BranchKind.STRUCTURED_TABLE,
                family=Phase6RouteFamily.STRUCTURED_TABLE,
                query_text=ctx.prep.original,
                parallel_group=0,
                hl_keywords=ctx.prep.hl_keywords,
                ll_keywords=ctx.prep.ll_keywords,
            ),
        ),
    )


def rule_current_relationship(ctx: MatrixContext) -> MatrixDecision | None:
    """Select Combined for current relationship or multi-hop questions.

    Args:
        ctx: Shared matrix context.

    Returns:
        Combined decision, or None when this rule does not apply.
    """

    extract = extract_deterministic(ctx.prep.original)
    if not is_current_relationship(ctx.prep.original, extract):
        return None
    return MatrixDecision(
        Phase6RouteFamily.COMBINED,
        (),
        (
            hybrid_branch(
                ctx.prep, branch_id="hyb-rel", query_text=ctx.prep.original, group=0
            ),
            graph_branch(
                ctx.prep,
                branch_id="graph-local",
                kind=BranchKind.GRAPH_LOCAL,
                family=Phase6RouteFamily.COMBINED,
                group=0,
            ),
            citation_branch(ctx.prep, group=1),
        ),
    )


def rule_low_confidence_relationship(ctx: MatrixContext) -> MatrixDecision | None:
    """Keep low-confidence relationships on Hybrid for later correction.

    Args:
        ctx: Shared matrix context.

    Returns:
        Hybrid decision, or None when this rule does not apply.
    """

    if not ctx.prep.low_confidence_relationship:
        return None
    ctx.flags["relationship_signal_retained"] = True
    return MatrixDecision(
        Phase6RouteFamily.HYBRID,
        ("low_confidence_relationship",),
        (
            hybrid_branch(
                ctx.prep, branch_id="hyb-low", query_text=ctx.prep.original, group=0
            ),
            citation_branch(ctx.prep, group=1),
        ),
    )


def rule_ordinary_hybrid(ctx: MatrixContext) -> MatrixDecision:
    """Default Hybrid/default handling using the Phase 4 mapped family.

    Args:
        ctx: Shared matrix context.

    Returns:
        Mapped-family Hybrid decision. This rule always matches.
    """

    limitations: tuple[str, ...] = ()
    if ctx.mapped_limitation is not None:
        limitations = (ctx.mapped_limitation.value,)
    return MatrixDecision(
        ctx.mapped_family,
        limitations,
        (
            hybrid_branch(
                ctx.prep, branch_id="hyb-0", query_text=ctx.prep.original, group=0
            ),
            citation_branch(ctx.prep, group=1),
        ),
    )


MATRIX_RULES: tuple[tuple[str, MatrixRuleFn], ...] = (
    ("web_research", rule_web_research),
    ("no_retrieval", rule_no_retrieval),
    ("graph_inspection", rule_graph_inspection),
    ("unsupported_media", rule_unsupported_media),
    ("negation", rule_negation),
    ("historical_relationship", rule_historical_relationship),
    ("whole_document_summary", rule_whole_document_summary),
    ("global_steering", rule_global_steering),
    ("comparison_or_multipart", rule_comparison_or_multipart),
    ("structured_table", rule_structured_table),
    ("current_relationship", rule_current_relationship),
    ("low_confidence_relationship", rule_low_confidence_relationship),
    ("ordinary_hybrid", rule_ordinary_hybrid),
)
"""Immutable precedence: first matching named rule wins."""


def apply_matrix_rules(ctx: MatrixContext) -> tuple[str, MatrixDecision]:
    """Apply the ordered rule tuple and return the winning name and decision.

    Args:
        ctx: Shared matrix context.

    Returns:
        Winning rule name and decision.

    Raises:
        RuntimeError: If the terminal ordinary-hybrid rule is missing.
    """

    for name, rule in MATRIX_RULES:
        decision = rule(ctx)
        if decision is not None:
            return name, decision
    raise RuntimeError("ordinary_hybrid_rule_missing")
