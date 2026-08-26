"""Shared routing-matrix preparation and plan builders."""

from __future__ import annotations

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_routing.matrix import (
    compile_retrieval_plan,
)
from smart_rag_core.query_routing.models import (
    BranchKind,
    QueryPreparation,
    RetrievalPlan,
)
from smart_rag_core.query_routing.preparation import (
    prepare_query,
)

from tests.support.query_runtime import authorized_runtime as _runtime


def _prep(query: str) -> QueryPreparation:
    """Prepare one query with the deterministic zero-call path.

    Args:
        query: Original user text.

    Returns:
        Typed preparation.
    """

    return prepare_query(query, runtime=_runtime())


def _plan(query: str, **kwargs: object) -> RetrievalPlan:
    """Compile a plan for one query using a Composite reservation.

    Args:
        query: Original user text.
        **kwargs: Extra ``compile_retrieval_plan`` arguments.

    Returns:
        Frozen retrieval plan.
    """

    runtime = kwargs.pop("runtime", None)
    context = runtime if isinstance(runtime, AuthorizedRuntimeContext) else _runtime()
    return compile_retrieval_plan(_prep(query), context, **kwargs)  # pyright: ignore[reportArgumentType]


def _kinds(plan: RetrievalPlan) -> set[BranchKind]:
    """Return the set of branch kinds.

    Args:
        plan: Compiled plan.

    Returns:
        Branch kinds present on the plan.
    """

    return {branch.kind for branch in plan.branches}


_NO_LIMITATIONS: set[str] = set()
