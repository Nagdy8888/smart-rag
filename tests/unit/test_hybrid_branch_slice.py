"""Hybrid branch slice clamp against the answer-stage reserve."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.branch_channels.hybrid import run_hybrid
from smart_rag_core.query_routing.models import BranchKind, BranchSpec
from smart_rag_core.security.identity import CallerContext, UserRole

from tests.support.query_routing import routing_prep
from tests.support.query_runtime import authorized_runtime


class _RecordingRetriever:
    """Records the deadline passed into Hybrid retrieve."""

    query_budget: QueryRetrieveBudget | None = None

    def __init__(self) -> None:
        """Start with no observed slice."""

        self.deadlines: list[float | None] = []

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
    ) -> SimpleNamespace:
        """Record ``deadline_seconds`` and return an empty Hybrid outcome.

        Args:
            query: Branch query.
            caller: Server-derived caller.
            profile: Typed profile, unused.
            deadline_seconds: Slice under test.

        Returns:
            Outcome with no ranked IDs.
        """

        del query, caller, profile
        self.deadlines.append(deadline_seconds)
        return SimpleNamespace(
            ranked_ids=(),
            coverage=None,
            source_resolution="unscoped",
            retrieval_profile_id="hybrid_default_v1",
            rerank_fallback="none",
        )


def test_hybrid_branch_slice_keeps_answer_reserve() -> None:
    """Retrieve slice is 10s, 4s, or the 2s floor as remaining shrinks."""

    spec = BranchSpec(
        branch_id="hybrid-slice",
        kind=BranchKind.HYBRID,
        family=Phase6RouteFamily.HYBRID,
        query_text="Which monitoring stacks are named?",
        parallel_group=0,
    )
    prep = routing_prep("Which monitoring stacks are named?")
    runtime = authorized_runtime()
    caller = CallerContext(
        user_id=str(uuid4()),
        role=UserRole.MEMBER,
        authorization_version=1,
    )
    retriever = _RecordingRetriever()
    for remaining, expected in ((30.0, 10.0), (12.0, 4.0), (9.0, 2.0)):
        retriever.deadlines.clear()
        run_hybrid(
            spec,
            prep=prep,
            runtime=runtime,
            caller=caller,
            remaining=remaining,
            hybrid_retriever=retriever,
            whole_document=False,
            chunk_loader=None,
        )
        assert retriever.deadlines == [expected]
