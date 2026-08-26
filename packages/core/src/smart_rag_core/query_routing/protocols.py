"""Retriever adapter protocols used by branch execution."""

from __future__ import annotations

from typing import Protocol

from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.query_routing.models import BranchSpec
from smart_rag_core.security.identity import CallerContext


class HybridRetrieveLike(Protocol):
    """Minimal Hybrid retrieve surface used by packet 2 tests and runtime."""

    query_budget: QueryRetrieveBudget | None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
    ) -> object:
        """Run one Hybrid retrieve.

        Args:
            query: Branch query text.
            caller: Server-derived caller.
            profile: Typed query profile.
            deadline_seconds: Remaining retrieval slice.

        Returns:
            Object with ``ranked_ids`` and ``coverage`` attributes.
        """


class GraphRetrieveLike(Protocol):
    """Minimal async GraphRetriever used by packet 2 tests and runtime."""

    query_budget: QueryRetrieveBudget | None

    async def retrieve_local(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Return local graph leads.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Structured leads. Never evidence.
        """

    async def retrieve_hybrid(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Return graph-hybrid leads.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Structured leads.
        """

    async def retrieve_global_steering(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Return at most three steering expansions.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Steering leads. Never evidence.
        """


class TableExecuteLike(Protocol):
    """Minimal structured-table executor."""

    def __call__(self, spec: BranchSpec, caller: CallerContext) -> object:
        """Execute one table branch.

        Args:
            spec: Table branch spec.
            caller: Server-derived caller.

        Returns:
            Table result or raises.
        """
