"""Citation-lookup branch conversion from Hybrid ranked IDs."""

from __future__ import annotations

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_routing.models import BranchKind, BranchResult, BranchSpec


def run_citation_lookups(
    specs: list[BranchSpec],
    results: list[BranchResult],
    runtime: AuthorizedRuntimeContext,
) -> None:
    """Append citation-lookup results that reuse Hybrid ranked IDs.

    Args:
        specs: Citation lookup specs.
        results: Already executed independent branch results.
        runtime: Authorized context whose run/reservation ids are copied.
    """

    hybrid_ids = tuple(
        item.ranked_ids for item in results if item.kind is BranchKind.HYBRID
    )
    resolved = hybrid_ids[0] if hybrid_ids else ()
    for spec in specs:
        results.append(
            BranchResult(
                branch_id=spec.branch_id,
                kind=spec.kind,
                family=spec.family,
                run_id=runtime.run_id,
                reservation_id=runtime.reservation_id,
                query_text=spec.query_text,
                ranked_ids=resolved,
                status="ok",
            )
        )
