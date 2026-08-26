"""Branch graph locators must load canonical text and drop empty citations."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

from smart_rag_core.query_routing.branches import execute_branches
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.models import BranchKind
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.security.identity import CallerContext

from tests.support.query_runtime import authorized_runtime as _runtime


def _context(
    chunk_id: UUID, *, text: str, document_id: UUID, version_id: UUID
) -> ChunkContext:
    """Build one authorized context row.

    Args:
        chunk_id: Canonical chunk.
        text: Canonical raw_text.
        document_id: Document.
        version_id: Version.

    Returns:
        Frozen chunk context.
    """

    return ChunkContext(
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
        parent_chunk_id=None,
        chunk_index=0,
        page_number=1,
        section_path=("Policy",),
        token_count=8,
        raw_text=text,
        is_search_representative=True,
    )


class _FakeHybrid:
    """Hybrid double that supplies an authorized chunk loader."""

    def __init__(self, rows: dict[UUID, ChunkContext]) -> None:
        """Bind fixture rows.

        Args:
            rows: Authorized contexts keyed by chunk id.
        """

        self._rows = rows
        self.query_budget = None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
    ) -> object:
        """Return an empty Hybrid retrieve so graph locators stand alone.

        Args:
            query: Unused.
            caller: Unused.
            profile: Unused.
            deadline_seconds: Unused.

        Returns:
            Namespace with empty ranked ids.
        """

        del query, caller, profile, deadline_seconds
        return SimpleNamespace(
            ranked_ids=(),
            evidence=(),
            coverage=None,
            fallback_reason="none",
        )

    def authorized_chunk_loader(self, caller: CallerContext) -> object:
        """Return a loader over fixture rows.

        Args:
            caller: Unused identity.

        Returns:
            Context loader.
        """

        del caller
        rows = self._rows

        def _load(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
            """Return matching fixture rows.

            Args:
                ids: Requested chunk ids.

            Returns:
                Authorized rows present in the fixture.
            """

            return tuple(rows[item] for item in ids if item in rows)

        return _load


class _FakeGraph:
    """Async graph double that returns one locator without citation text."""

    def __init__(self, chunk_id: UUID, document_id: UUID, version_id: UUID) -> None:
        """Bind locator identity.

        Args:
            chunk_id: Canonical chunk.
            document_id: Document.
            version_id: Version.
        """

        self._chunk_id = chunk_id
        self._document_id = document_id
        self._version_id = version_id
        self.query_budget = None

    async def retrieve_local(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Return one locator with empty citation text.

        Args:
            query: Unused.
            hl_keywords: Unused.
            ll_keywords: Unused.
            bounds: Unused.

        Returns:
            Lead-set namespace.
        """

        del query, hl_keywords, ll_keywords, bounds
        locator = SimpleNamespace(
            chunk_id=self._chunk_id,
            document_id=self._document_id,
            version_id=self._version_id,
            section_path=(),
            page_number=None,
            sheet_name=None,
            range_ref=None,
            source_url=None,
        )
        return SimpleNamespace(
            entities=(),
            counters=SimpleNamespace(keyword_extract=0, answer_generate=0),
            locators=(locator,),
            paths=(),
            limitations=(),
            acl_blindness_count=None,
            graph_survival_ratio=1.0,
        )

    async def retrieve_hybrid(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Delegate unused hybrid mode to the local fixture.

        Args:
            query: Original query.
            hl_keywords: High-level keywords.
            ll_keywords: Low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Same lead-set as ``retrieve_local``.
        """

        return await self.retrieve_local(
            query=query,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            bounds=bounds,
        )

    async def retrieve_global_steering(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Delegate unused steering mode to the local fixture.

        Args:
            query: Original query.
            hl_keywords: High-level keywords.
            ll_keywords: Low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Same lead-set as ``retrieve_local``.
        """

        return await self.retrieve_local(
            query=query,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            bounds=bounds,
        )


def test_empty_graph_locator_text_is_dropped() -> None:
    """Locators whose canonical raw_text is empty never become graph passages."""

    chunk_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    hybrid = _FakeHybrid(
        {
            chunk_id: _context(
                chunk_id, text="   ", document_id=document_id, version_id=version_id
            )
        }
    )
    runtime = _runtime()
    query = "Which team owns INV-SR-1001 related to procurement?"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    assert any(branch.kind is BranchKind.GRAPH_LOCAL for branch in plan.branches)
    results = execute_branches(
        plan,
        prep,
        runtime,
        hybrid_retriever=hybrid,
        graph_retriever=_FakeGraph(chunk_id, document_id, version_id),
    )
    graph = next(item for item in results if item.kind is BranchKind.GRAPH_LOCAL)
    assert graph.graph_passages == ()


def test_graph_locator_loads_canonical_raw_text() -> None:
    """Authorized chunk context fills citation_text on graph passages."""

    chunk_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    canonical = "Project Atlas is owned by the procurement team."
    hybrid = _FakeHybrid(
        {
            chunk_id: _context(
                chunk_id,
                text=canonical,
                document_id=document_id,
                version_id=version_id,
            )
        }
    )
    runtime = _runtime()
    query = "Which team owns INV-SR-1001 related to procurement?"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    results = execute_branches(
        plan,
        prep,
        runtime,
        hybrid_retriever=hybrid,
        graph_retriever=_FakeGraph(chunk_id, document_id, version_id),
    )
    graph = next(item for item in results if item.kind is BranchKind.GRAPH_LOCAL)
    assert len(graph.graph_passages) == 1
    assert graph.graph_passages[0].citation_text == canonical


def test_async_graph_retrieve_from_running_loop() -> None:
    """Graph retrieve does not crash with nested asyncio.run under a live loop."""

    chunk_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    hybrid = _FakeHybrid({})
    runtime = _runtime()
    query = "Which team owns INV-SR-1001 related to procurement?"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)

    async def _inside() -> int:
        """Execute branches while this loop is running.

        Returns:
            Number of graph passages after empty-text drop.
        """

        results = execute_branches(
            plan,
            prep,
            runtime,
            hybrid_retriever=hybrid,
            graph_retriever=_FakeGraph(chunk_id, document_id, version_id),
        )
        graph = next(item for item in results if item.kind is BranchKind.GRAPH_LOCAL)
        return len(graph.graph_passages)

    assert asyncio.run(_inside()) == 0
