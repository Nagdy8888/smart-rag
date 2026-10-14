"""Shared Hybrid spy and company-only node names for scope routing tests."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.security.identity import CallerContext

COMPANY_ONLY_NODES = {
    "company_scope",
    "apply_correction",
    "fuse_evidence",
    "compose_tables",
    "disclose_optional_tools",
    "generate_answer",
}


class SpyHybrid:
    """Record Hybrid retrieve calls and return empty authorized evidence."""

    query_budget: QueryRetrieveBudget | None = None

    def __init__(self) -> None:
        """Create a zero-call Hybrid spy."""

        self.calls = 0

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
        **_kwargs: object,
    ) -> object:
        """Count one retrieve and return an empty Hybrid payload.

        Args:
            query: Unused.
            caller: Unused.
            profile: Unused.
            deadline_seconds: Unused.
            **_kwargs: Unused retrieve keywords such as cache mode.

        Returns:
            Namespace matching Hybrid fields used by branch execution.
        """

        del query, caller, profile, deadline_seconds, _kwargs
        self.calls += 1
        return SimpleNamespace(
            ranked_ids=(UUID("00000000-0000-0000-0000-000000000001"),),
            evidence=(),
            coverage=SimpleNamespace(
                coverage_score=0.80,
                uncovered_headings=(),
                signal="ok",
                notes=(),
            ),
            fallback_reason="none",
        )
