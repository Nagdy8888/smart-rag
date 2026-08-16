"""Unit tests for structured graph query orchestration and adapter bounds."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from typing import Protocol, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.evaluation.schema import (
    DATE_PARSER_VERSION,
    DEFAULT_RETRIEVAL_PROFILE_ID,
    NORMALIZER_VERSION,
    PROFILE_MODEL_PLACEHOLDER,
    PROFILE_PROMPT_PLACEHOLDER,
    ExpectedProfile,
    det,
)
from smart_rag_core.jobs.graph_resolver import (
    QueryWorkspaceSnapshot,
    ResolveOutcome,
    VisibilityCounts,
)
from smart_rag_core.retrieval.graph import (
    GraphLeadEntity,
    GraphLeadRelation,
    GraphLeadSet,
    GraphLimitationCode,
    GraphQueryBounds,
    apply_query_bounds,
)
from smart_rag_core.retrieval.graph_results import (
    GraphCanonicalLocator,
    GraphResolvedCandidate,
    RollingSurvivalWindow,
)
from smart_rag_core.retrieval.graph_retriever import (
    GraphQueryError,
    inspect_graph_authorized,
    retrieve_graph,
)
from smart_rag_core.retrieval.lightrag_adapter import (
    LightRagAdapterError,
    LightRagRuntimeAdapter,
)
from smart_rag_core.retrieval.lightrag_callbacks import CallbackCounts
from smart_rag_core.retrieval.lightrag_structured import LightRagQueryFailure
from smart_rag_core.security.identity import CallerContext, UserRole

_CALLER = CallerContext(
    user_id="00000000-0000-4000-8000-000000000002",
    role=UserRole.MEMBER,
    authorization_version=1,
)


def _profile(*, as_of: bool = False, historical: bool = False) -> ExpectedProfile:
    """Build a frozen profile with both keyword lists.

    Args:
        as_of: When true, temporal intent is ``as_of``.
        historical: Historical relationship flag.

    Returns:
        Complete expected profile.
    """

    temporal = "as_of" if as_of else "latest"
    return ExpectedProfile(
        original_query="who owns Alpha",
        normalizer_version=NORMALIZER_VERSION,
        date_parser_version=DATE_PARSER_VERSION,
        prompt_version=PROFILE_PROMPT_PLACEHOLDER,
        model_version=PROFILE_MODEL_PLACEHOLDER,
        language=det("en"),
        locale_configuration=det("en-US"),
        query_type=det("relationship_multi_hop"),
        exact_terms=det([]),
        quoted_phrases=det([]),
        codes=det([]),
        numbers=det([]),
        dates=det([]),
        entities=det(["Alpha"]),
        approved_aliases=det([]),
        requested_sources=det([]),
        metadata_filters=det([]),
        temporal_intent=det(temporal),
        target_date=det(None),
        timezone=det("UTC"),
        authoritative_date_field=det("effective_at"),
        negation_scope=det("none"),
        document_scope=det("none"),
        media_dependence=det(False),
        historical_relationship=det(historical),
        relationship_intent=det(True),
        table_intent=det(False),
        table_operation_hints=det([]),
        rewrite_justified=det(False),
        subquestions=det([]),
        variants=det([]),
        hl_keywords=det(["ownership"]),
        ll_keywords=det(["Alpha"]),
        retrieval_profile_id=det(DEFAULT_RETRIEVAL_PROFILE_ID),
    )


def _active_snapshot() -> QueryWorkspaceSnapshot:
    """Return a queryable workspace snapshot.

    Returns:
        Active pointer snapshot.
    """

    return QueryWorkspaceSnapshot(
        workspace_key="company_default",
        workspace_id=uuid4(),
        state="active",
        pointer_attached=True,
        generation=1,
        config_generation="abc",
    )


def _bounds(*, deadline: float = 5.0) -> GraphQueryBounds:
    """Return adapter bounds for unit retrieval.

    Args:
        deadline: Remaining deadline seconds.

    Returns:
        Frozen query bounds.
    """

    return apply_query_bounds(
        top_k=12,
        chunk_top_k=12,
        max_entity_tokens=100,
        max_relation_tokens=100,
        max_total_tokens=100,
        deadline_seconds=deadline,
    )


class _FakeRetriever:
    """In-memory GraphRetriever for orchestration tests."""

    def __init__(self, leads: GraphLeadSet) -> None:
        """Bind one lead set.

        Args:
            leads: Structured leads returned by every mode.
        """

        self.leads = leads
        self.calls = 0

    async def retrieve_local(self, **_kwargs: object) -> GraphLeadSet:
        """Return local leads.

        Returns:
            Bound lead set.
        """

        self.calls += 1
        return self.leads

    async def retrieve_hybrid(self, **_kwargs: object) -> GraphLeadSet:
        """Return graph-hybrid leads.

        Returns:
            Bound lead set.
        """

        self.calls += 1
        return self.leads

    async def retrieve_global_steering(self, **_kwargs: object) -> GraphLeadSet:
        """Return global leads.

        Returns:
            Bound lead set.
        """

        self.calls += 1
        return self.leads


def _load_active_workspace(_connection: psycopg.Connection) -> QueryWorkspaceSnapshot:
    """Return an active pointer snapshot.

    Args:
        _connection: Unused retrieve connection.

    Returns:
        Active workspace snapshot.
    """

    del _connection
    return _active_snapshot()


def _workspace_loader(
    *,
    state: str,
    pointer_attached: bool,
    workspace_id: UUID | None,
    config_generation: str = "x",
    generation: int = 1,
) -> Callable[[psycopg.Connection], QueryWorkspaceSnapshot]:
    """Build a ``load_query_workspace`` stub for one workspace state.

    Args:
        state: Workspace state label.
        pointer_attached: Whether a pointer row is attached.
        workspace_id: Pointer workspace id, if any.
        config_generation: Mapping config digest.
        generation: Pointer generation.

    Returns:
        Loader that ignores the connection and returns the snapshot.
    """

    snapshot = QueryWorkspaceSnapshot(
        workspace_key="company_default",
        workspace_id=workspace_id,
        state=state,
        pointer_attached=pointer_attached,
        generation=generation,
        config_generation=config_generation,
    )

    def _load(_connection: psycopg.Connection) -> QueryWorkspaceSnapshot:
        """Return the bound snapshot.

        Args:
            _connection: Unused retrieve connection.

        Returns:
            Frozen workspace snapshot.
        """

        del _connection
        return snapshot

    return _load


def _zero_visibility(*_args: object, **_kwargs: object) -> VisibilityCounts:
    """Return empty authorized visibility counts.

    Returns:
        Zero partial-readiness and ACL-blindness.
    """

    return VisibilityCounts(0, 0)


def _skip_repairs(*_args: object, **_kwargs: object) -> None:
    """Skip query-time repair enqueue."""

    return None


def _no_locators(
    *_args: object, **_kwargs: object
) -> tuple[GraphCanonicalLocator, ...]:
    """Return no canonical locators.

    Returns:
        Empty locator tuple.
    """

    return ()


def _one_survival_sample(*_args: object, **_kwargs: object) -> RollingSurvivalWindow:
    """Return a single-sample survival window.

    Returns:
        Window with mean 1.0.
    """

    return RollingSurvivalWindow(sample_count=1, mean=1.0, below_alert_threshold=False)


def _empty_resolve(*_args: object, **_kwargs: object) -> ResolveOutcome:
    """Return an empty resolver outcome.

    Returns:
        No candidates, paths, or drops.
    """

    return ResolveOutcome(
        candidates=(),
        paths=(),
        dropped=(),
        diagnostics=(),
        returned_candidates=0,
        supported_candidates=0,
    )


class _StructuredQueryParam(Protocol):
    """LightRAG QueryParam fields asserted by the structured adapter contract."""

    enable_rerank: bool
    only_need_context: bool
    hl_keywords: list[str]
    ll_keywords: list[str]
    mode: str


def _patch_common(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> None:
    """Patch resolver helpers used by ``retrieve_graph``.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        **overrides: Optional replacements keyed by graph_retriever names.
    """

    import smart_rag_core.retrieval.graph_retriever as gr

    defaults: dict[str, object] = {
        "load_query_workspace": _load_active_workspace,
        "visibility_counts": _zero_visibility,
        "enqueue_query_repairs": _skip_repairs,
        "load_canonical_locators": _no_locators,
        "record_survival_sample": _one_survival_sample,
        "resolve_graph_leads": _empty_resolve,
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        monkeypatch.setattr(gr, name, value)


def test_historical_relationship_skips_vendor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Historical relationship queries emit temporal_graph_limitation."""

    retriever = _FakeRetriever(GraphLeadSet(mode="local"))
    _patch_common(monkeypatch)
    result = asyncio.run(
        retrieve_graph(
            retriever=retriever,
            connection=object(),  # type: ignore[arg-type]
            caller=_CALLER,
            query="q",
            profile=_profile(historical=True),
            mode="local",
            bounds=_bounds(),
            remaining_deadline_seconds=10.0,
        )
    )
    assert retriever.calls == 0
    assert result.limitations[0].code is GraphLimitationCode.TEMPORAL_GRAPH_LIMITATION


def test_outage_skips_vendor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quarantined or unattached workspaces never call LightRAG."""

    retriever = _FakeRetriever(
        GraphLeadSet(mode="local", entities=(GraphLeadEntity(entity_name="A"),))
    )
    _patch_common(
        monkeypatch,
        load_query_workspace=_workspace_loader(
            state="quarantined",
            pointer_attached=False,
            workspace_id=None,
            config_generation="",
        ),
    )
    result = asyncio.run(
        retrieve_graph(
            retriever=retriever,
            connection=object(),  # type: ignore[arg-type]
            caller=_CALLER,
            query="q",
            profile=_profile(),
            mode="local",
            bounds=_bounds(),
            remaining_deadline_seconds=10.0,
        )
    )
    assert retriever.calls == 0
    assert result.limitations[0].code is GraphLimitationCode.GRAPH_OUTAGE
    assert result.counters.support_searches == 0
    assert result.counters.keyword_extract == 0
    assert result.counters.answer_generate == 0


def test_updating_and_filtered_dirty_typed_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Updating and filtered_dirty skip vendor and emit exact codes."""

    retriever = _FakeRetriever(GraphLeadSet(mode="local"))
    _patch_common(
        monkeypatch,
        load_query_workspace=_workspace_loader(
            state="updating",
            pointer_attached=True,
            workspace_id=uuid4(),
        ),
    )
    updating = asyncio.run(
        retrieve_graph(
            retriever=retriever,
            connection=object(),  # type: ignore[arg-type]
            caller=_CALLER,
            query="q",
            profile=_profile(),
            mode="hybrid",
            bounds=_bounds(),
            remaining_deadline_seconds=10.0,
        )
    )
    assert retriever.calls == 0
    assert updating.limitations[0].code is GraphLimitationCode.GRAPH_UPDATING
    _patch_common(
        monkeypatch,
        load_query_workspace=_workspace_loader(
            state="filtered_dirty",
            pointer_attached=True,
            workspace_id=uuid4(),
        ),
    )
    dirty = asyncio.run(
        retrieve_graph(
            retriever=retriever,
            connection=object(),  # type: ignore[arg-type]
            caller=_CALLER,
            query="q",
            profile=_profile(),
            mode="hybrid",
            bounds=_bounds(),
            remaining_deadline_seconds=10.0,
        )
    )
    assert dirty.limitations[0].code is GraphLimitationCode.GRAPH_FILTERED_DIRTY


def test_temporal_as_of_skips_vendor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit as_of never queries superseded graph paths."""

    retriever = _FakeRetriever(GraphLeadSet(mode="local"))
    _patch_common(monkeypatch)
    result = asyncio.run(
        retrieve_graph(
            retriever=retriever,
            connection=object(),  # type: ignore[arg-type]
            caller=_CALLER,
            query="q",
            profile=_profile(as_of=True),
            mode="local",
            bounds=_bounds(),
            remaining_deadline_seconds=10.0,
        )
    )
    assert retriever.calls == 0
    assert result.limitations[0].code is GraphLimitationCode.TEMPORAL_GRAPH_LIMITATION


def test_global_steering_is_not_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Global mode returns at most three topics and no locators."""

    leads = GraphLeadSet(
        mode="global",
        entities=tuple(GraphLeadEntity(entity_name=f"t{index}") for index in range(5)),
        relations=(GraphLeadRelation(src_id="a", tgt_id="b"),),
    )
    retriever = _FakeRetriever(leads)
    _patch_common(monkeypatch)
    result = asyncio.run(
        retrieve_graph(
            retriever=retriever,
            connection=object(),  # type: ignore[arg-type]
            caller=_CALLER,
            query="q",
            profile=_profile(),
            mode="global",
            bounds=_bounds(),
            remaining_deadline_seconds=10.0,
        )
    )
    assert retriever.calls == 1
    assert len(result.steering) == 3
    assert result.candidates == ()
    assert result.locators == ()
    assert result.limitations[0].code is GraphLimitationCode.GLOBAL_STEERING_ONLY
    assert result.counters.support_searches == 0


def test_survival_below_threshold_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supported/returned below 0.50 emits graph_survival_below_threshold."""

    chunk_id = uuid4()
    retriever = _FakeRetriever(
        GraphLeadSet(
            mode="local",
            relations=tuple(
                GraphLeadRelation(src_id=f"s{index}", tgt_id="t") for index in range(3)
            ),
        )
    )
    outcome = ResolveOutcome(
        candidates=(
            GraphResolvedCandidate(
                kind="statement",
                object_id="stmt-1",
                canonical_chunk_ids=(chunk_id,),
                document_id=uuid4(),
                version_id=uuid4(),
                support=0.9,
                confidence=0.9,
            ),
        ),
        paths=(),
        dropped=(),
        diagnostics=("candidate_dropped",),
        returned_candidates=3,
        supported_candidates=1,
    )

    def _resolve(*_args: object, **_kwargs: object) -> ResolveOutcome:
        """Return the low-survival fixture outcome."""

        return outcome

    _patch_common(monkeypatch, resolve_graph_leads=_resolve)
    result = asyncio.run(
        retrieve_graph(
            retriever=retriever,
            connection=object(),  # type: ignore[arg-type]
            caller=_CALLER,
            query="q",
            profile=_profile(),
            mode="local",
            bounds=_bounds(),
            remaining_deadline_seconds=10.0,
        )
    )
    assert result.graph_survival_ratio == pytest.approx(1 / 3)
    codes = {item.code for item in result.limitations}
    assert GraphLimitationCode.GRAPH_SURVIVAL_BELOW_THRESHOLD in codes
    assert result.counters.support_searches == 0
    assert result.counters.repair_hybrid_searches == 0
    assert result.counters.vendor_queries == 1


def test_hidden_keyword_callback_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A keyword-extract callback during query raises GraphQueryError."""

    class _HiddenRetriever(_FakeRetriever):
        """Retriever that increments the forbidden keyword-extract counter."""

        async def retrieve_local(self, **_kwargs: object) -> GraphLeadSet:
            """Increment the hidden keyword-extract counter, then return leads."""

            self.calls += 1
            callbacks.counts.keyword_extract += 1
            return self.leads

    callbacks = SimpleNamespace(counts=CallbackCounts())
    retriever = _HiddenRetriever(GraphLeadSet(mode="local"))
    _patch_common(monkeypatch)
    with pytest.raises(GraphQueryError, match="hidden_keyword_or_answer_call"):
        asyncio.run(
            retrieve_graph(
                retriever=retriever,
                connection=object(),  # type: ignore[arg-type]
                caller=_CALLER,
                query="q",
                profile=_profile(),
                mode="local",
                bounds=_bounds(),
                remaining_deadline_seconds=10.0,
                callbacks=callbacks,  # type: ignore[arg-type]
            )
        )


def test_vendor_timeout_cancels_query_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outer wait_for raises graph_deadline when the vendor hangs."""

    class _SlowRetriever(_FakeRetriever):
        """Retriever that sleeps past the query deadline."""

        async def retrieve_local(self, **_kwargs: object) -> GraphLeadSet:
            """Sleep long enough to trip the outer wait_for deadline.

            Args:
                **_kwargs: Unused retrieve_local keyword arguments.

            Returns:
                The fixture lead set if the sleep is not cancelled.
            """

            self.calls += 1
            await asyncio.sleep(5)
            return self.leads

    retriever = _SlowRetriever(GraphLeadSet(mode="local"))
    _patch_common(monkeypatch)
    with pytest.raises(GraphQueryError, match="graph_deadline"):
        asyncio.run(
            retrieve_graph(
                retriever=retriever,
                connection=object(),  # type: ignore[arg-type]
                caller=_CALLER,
                query="q",
                profile=_profile(),
                mode="local",
                bounds=_bounds(deadline=0.05),
                remaining_deadline_seconds=0.05,
            )
        )


def test_vendor_empty_emits_graph_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """LightRagQueryFailure degrades to graph_empty without Hybrid."""

    class _EmptyRetriever(_FakeRetriever):
        """Retriever that surfaces a vendor empty-result failure."""

        async def retrieve_local(self, **_kwargs: object) -> GraphLeadSet:
            """Raise LightRagQueryFailure so the adapter emits graph_empty.

            Args:
                **_kwargs: Unused retrieve_local keyword arguments.

            Returns:
                Never returns; always raises.

            Raises:
                LightRagQueryFailure: Simulated vendor empty result.
            """

            self.calls += 1
            raise LightRagQueryFailure("no_results")

    retriever = _EmptyRetriever(GraphLeadSet(mode="local"))
    _patch_common(monkeypatch)
    result = asyncio.run(
        retrieve_graph(
            retriever=retriever,
            connection=object(),  # type: ignore[arg-type]
            caller=_CALLER,
            query="q",
            profile=_profile(),
            mode="local",
            bounds=_bounds(),
            remaining_deadline_seconds=10.0,
        )
    )
    assert result.limitations[0].code is GraphLimitationCode.GRAPH_EMPTY
    assert result.counters.support_searches == 0


def test_inspect_deadline_and_seed_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inspection respects the 10s deadline and 12-key seed cap."""

    import smart_rag_core.retrieval.graph_retriever as gr

    monkeypatch.setattr(gr, "load_query_workspace", _load_active_workspace)
    deadline = inspect_graph_authorized(
        connection=object(),  # type: ignore[arg-type]
        caller=_CALLER,
        entity_keys=("a",),
        remaining_deadline_seconds=0.0,
    )
    assert deadline.limitations[0].code is GraphLimitationCode.GRAPH_DEADLINE
    with pytest.raises(GraphQueryError, match="inspect_seed_exceeds_limit"):
        inspect_graph_authorized(
            connection=object(),  # type: ignore[arg-type]
            caller=_CALLER,
            entity_keys=tuple(f"k{index:02d}" for index in range(13)),
            remaining_deadline_seconds=10.0,
        )


def test_aquery_data_structured_sets_query_param_contract() -> None:
    """Adapter QueryParam requires both keyword lists and disables rerank."""

    captured: dict[str, object] = {}

    class _Rag:
        """LightRAG double that captures QueryParam for contract assertions."""

        async def aquery_data(self, query: str, param: object) -> dict[str, object]:
            """Capture QueryParam and return a successful structured envelope."""

            captured["query"] = query
            captured["param"] = param
            return {
                "status": "success",
                "data": {
                    "entities": [{"entity_name": "Alpha", "source_id": "chunk-1"}],
                    "relationships": [],
                    "chunks": [{"chunk_id": "chunk-1"}],
                },
                "metadata": {
                    "query_mode": "local",
                    "keywords": {
                        "high_level": ["ownership"],
                        "low_level": ["Alpha"],
                    },
                },
            }

    adapter = LightRagRuntimeAdapter.__new__(LightRagRuntimeAdapter)
    adapter.rag = _Rag()  # type: ignore[assignment]
    leads = asyncio.run(
        adapter.aquery_data_structured(
            query="who owns Alpha",
            mode="local",
            hl_keywords=("ownership",),
            ll_keywords=("Alpha",),
            bounds=_bounds(),
        )
    )
    param = cast(_StructuredQueryParam, captured["param"])
    assert param.enable_rerank is False
    assert param.only_need_context is True
    assert param.hl_keywords == ["ownership"]
    assert param.ll_keywords == ["Alpha"]
    assert param.mode == "local"
    assert leads.entities[0].entity_name == "Alpha"
    with pytest.raises(LightRagAdapterError, match="unsupported_graph_mode"):
        asyncio.run(
            adapter.aquery_data_structured(
                query="q",
                mode="naive",  # type: ignore[arg-type]
                hl_keywords=("a",),
                ll_keywords=("b",),
                bounds=_bounds(),
            )
        )
    with pytest.raises(LightRagAdapterError, match="both_keyword_lists_required"):
        asyncio.run(
            adapter.aquery_data_structured(
                query="q",
                mode="hybrid",
                hl_keywords=(),
                ll_keywords=("b",),
                bounds=_bounds(),
            )
        )
