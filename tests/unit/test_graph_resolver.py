"""Unit tests for application-owned graph lead clamp, survival, and paths."""

from __future__ import annotations

from typing import Protocol, cast
from uuid import UUID, uuid4

import smart_rag_core.jobs.graph_resolver as graph_resolver_mod
from smart_rag_core.jobs.graph_resolver import (
    ResolvedStatement,
    VisibilityCounts,
    expand_bounded_paths,
    limitation_for_visibility,
)
from smart_rag_core.retrieval.graph import (
    ADAPTER_MAX_GRAPH_CANDIDATES,
    ADAPTER_MAX_HOPS,
    ADAPTER_MAX_PATHS,
    GLOBAL_STEERING_MAX,
    GraphLeadChunk,
    GraphLeadEntity,
    GraphLeadRelation,
    GraphLeadSet,
    GraphLimitationCode,
    ProseContextRejectedError,
    apply_query_bounds,
    clamp_global_steering,
    clamp_graph_leads,
    graph_survival_ratio,
    inspection_query_bounds,
    reject_rendered_context_parser,
    workspace_limitation_code,
)
from smart_rag_core.retrieval.graph_results import GraphPath, GraphResolvedCandidate


class _MapRowView(Protocol):
    """Constructor-compatible view of the resolver's private map row."""

    vendor_key: str
    object_type: str
    object_id: str
    chunk_id: UUID | None
    document_id: UUID | None
    version_id: UUID | None
    support: float
    src_vendor: str
    tgt_vendor: str
    vendor_name: str
    path_edge_id: str
    survived: bool
    drop_reason: str


class _MapRowFactory(Protocol):
    """Keyword constructor for the resolver's private map-row dataclass."""

    def __call__(
        self,
        *,
        vendor_key: str,
        object_type: str,
        object_id: str,
        chunk_id: UUID | None,
        document_id: UUID | None,
        version_id: UUID | None,
        support: float,
        src_vendor: str,
        tgt_vendor: str,
        vendor_name: str,
        path_edge_id: str,
        survived: bool,
        drop_reason: str,
    ) -> _MapRowView:
        """Build one map row.

        Returns:
            Frozen map-row view.
        """

        ...


class _ApplyWholeCandidateSurvival(Protocol):
    """Typed wrapper around the resolver's private whole-candidate helper."""

    def __call__(
        self,
        leads: GraphLeadSet,
        *,
        chunk_rows: tuple[_MapRowView, ...],
        evidence_rows: tuple[_MapRowView, ...],
    ) -> tuple[
        tuple[GraphResolvedCandidate, ...],
        tuple[GraphPath, ...],
        tuple[dict[str, str], ...],
        tuple[str, ...],
    ]:
        """Drop native leads that fail a required mapping.

        Args:
            leads: Clamped vendor leads.
            chunk_rows: Chunk-map joins.
            evidence_rows: Evidence-map joins.

        Returns:
            Candidates, paths, repair payloads, and diagnostics.
        """

        ...


_MapRow = cast(_MapRowFactory, object.__getattribute__(graph_resolver_mod, "_MapRow"))
_apply_whole_candidate_survival = cast(
    _ApplyWholeCandidateSurvival,
    object.__getattribute__(graph_resolver_mod, "_apply_whole_candidate_survival"),
)


def _survived_row(
    *,
    vendor_key: str,
    object_type: str,
    object_id: str,
    src: str = "",
    tgt: str = "",
    vendor_name: str = "",
    support: float = 0.9,
) -> _MapRowView:
    """Return one surviving map row for whole-candidate tests.

    Args:
        vendor_key: Vendor chunk or object key.
        object_type: chunk, entity, or statement.
        object_id: Application object id.
        src: Statement source vendor name.
        tgt: Statement target vendor name.
        vendor_name: Entity vendor name.
        support: Mapping support.

    Returns:
        Frozen map row marked survived.
    """

    chunk_id = uuid4()
    return _MapRow(
        vendor_key=vendor_key,
        object_type=object_type,
        object_id=object_id,
        chunk_id=chunk_id,
        document_id=uuid4(),
        version_id=uuid4(),
        support=support,
        src_vendor=src,
        tgt_vendor=tgt,
        vendor_name=vendor_name,
        path_edge_id="",
        survived=True,
        drop_reason="",
    )


def test_apply_query_bounds_independent_of_vendor_defaults() -> None:
    """Application maxima win over oversized caller values."""

    bounds = apply_query_bounds(
        top_k=10_000,
        chunk_top_k=10_000,
        max_entity_tokens=99_000,
        max_relation_tokens=99_000,
        max_total_tokens=99_000,
        deadline_seconds=9_000.0,
    )
    assert bounds.top_k == ADAPTER_MAX_GRAPH_CANDIDATES
    assert bounds.chunk_top_k == ADAPTER_MAX_GRAPH_CANDIDATES
    assert bounds.deadline_seconds == 45.0


def test_inspection_bounds_use_ten_second_deadline() -> None:
    """Inspection clamps the adapter deadline to 10 seconds."""

    bounds = inspection_query_bounds()
    assert bounds.deadline_seconds == 10.0
    assert bounds.top_k == ADAPTER_MAX_GRAPH_CANDIDATES


def test_clamp_graph_leads_caps_twelve_and_stable_sort() -> None:
    """Relation candidates cap at 12 with lexicographic tie-breaks."""

    relations = tuple(
        GraphLeadRelation(src_id=f"s{index:02d}", tgt_id="t", source_ids=("c1",))
        for index in range(20, 0, -1)
    )
    leads = GraphLeadSet(
        mode="local",
        entities=(
            GraphLeadEntity(entity_name="s01", source_ids=("c1",)),
            GraphLeadEntity(entity_name="zzz", source_ids=("c9",)),
        ),
        relations=relations,
        chunks=(
            GraphLeadChunk(chunk_id="c1"),
            GraphLeadChunk(chunk_id="c9"),
        ),
    )
    bounds = apply_query_bounds(
        top_k=12,
        chunk_top_k=12,
        max_entity_tokens=100,
        max_relation_tokens=100,
        max_total_tokens=100,
        deadline_seconds=5.0,
    )
    clamped = clamp_graph_leads(leads, bounds)
    assert len(clamped.relations) == 12
    assert clamped.relations[0].src_id == "s01"
    names = {item.entity_name for item in clamped.entities}
    assert "s01" in names
    assert "zzz" not in names
    assert tuple(item.chunk_id for item in clamped.chunks) == ("c1",)


def test_clamp_global_steering_never_evidence() -> None:
    """Global steering keeps at most three topics and drops relations."""

    leads = GraphLeadSet(
        mode="global",
        entities=tuple(
            GraphLeadEntity(entity_name=f"topic-{index}") for index in range(6)
        ),
        relations=(GraphLeadRelation(src_id="a", tgt_id="b", source_ids=("c1",)),),
        chunks=(GraphLeadChunk(chunk_id="c1"),),
    )
    steered = clamp_global_steering(leads)
    assert len(steered.entities) == GLOBAL_STEERING_MAX
    assert steered.relations == ()
    assert steered.chunks == ()


def test_graph_survival_ratio_null_and_below_threshold() -> None:
    """Survival is null when none returned and 0.33 when 1 of 3 survive."""

    assert graph_survival_ratio(supported=0, returned=0) is None
    assert graph_survival_ratio(supported=1, returned=3) == 1 / 3


def test_workspace_limitation_codes() -> None:
    """Non-active workspaces fail closed with typed codes."""

    assert (
        workspace_limitation_code(None, pointer_attached=False)
        is GraphLimitationCode.GRAPH_OUTAGE
    )
    assert workspace_limitation_code("active", pointer_attached=True) is None
    assert (
        workspace_limitation_code("updating", pointer_attached=True)
        is GraphLimitationCode.GRAPH_UPDATING
    )
    assert (
        workspace_limitation_code("filtered_dirty", pointer_attached=True)
        is GraphLimitationCode.GRAPH_FILTERED_DIRTY
    )
    assert (
        workspace_limitation_code("quarantined", pointer_attached=True)
        is GraphLimitationCode.GRAPH_OUTAGE
    )


def test_visibility_limitations_omit_names() -> None:
    """Partial-readiness and ACL-blindness carry counts only."""

    limits = limitation_for_visibility(
        VisibilityCounts(partial_readiness_count=2, acl_blindness_count=1)
    )
    dumped = " ".join(item.model_dump_json() for item in limits)
    assert "graph_partial_readiness" in dumped
    assert "graph_acl_blindness" in dumped
    assert "restricted" not in dumped.lower()
    assert "title" not in dumped.lower()


def test_whole_candidate_drops_when_any_required_piece_fails() -> None:
    """A relation is dropped wholly if one required chunk is unauthorized."""

    chunk_ok = _survived_row(
        vendor_key="c-ok", object_type="chunk", object_id=str(uuid4())
    )
    chunk_bad = _MapRow(
        vendor_key="c-bad",
        object_type="chunk",
        object_id="",
        chunk_id=None,
        document_id=None,
        version_id=None,
        support=0.0,
        src_vendor="",
        tgt_vendor="",
        vendor_name="",
        path_edge_id="",
        survived=False,
        drop_reason="unauthorized",
    )
    statement = _survived_row(
        vendor_key="stmt",
        object_type="statement",
        object_id="stmt-keep",
        src="Alpha",
        tgt="Beta",
    )
    src = _survived_row(
        vendor_key="Alpha",
        object_type="entity",
        object_id="ent-a",
        vendor_name="Alpha",
    )
    tgt = _survived_row(
        vendor_key="Beta",
        object_type="entity",
        object_id="ent-b",
        vendor_name="Beta",
    )
    leads = GraphLeadSet(
        mode="hybrid",
        entities=(
            GraphLeadEntity(entity_name="Alpha", source_ids=("c-ok",)),
            GraphLeadEntity(entity_name="Beta", source_ids=("c-bad",)),
        ),
        relations=(
            GraphLeadRelation(
                src_id="Alpha",
                tgt_id="Beta",
                source_ids=("c-ok", "c-bad"),
            ),
        ),
    )
    candidates, paths, dropped, diagnostics = _apply_whole_candidate_survival(
        leads,
        chunk_rows=(chunk_ok, chunk_bad),
        evidence_rows=(statement, src, tgt),
    )
    assert candidates == ()
    assert paths == ()
    assert diagnostics == ("candidate_dropped",)
    assert dropped[0]["reason"] == "candidate_dropped"
    assert "unauthorized" not in dropped[0]["object_id"]


def test_whole_candidate_keeps_relation_when_every_piece_survives() -> None:
    """Surviving maps yield one statement candidate and no drop."""

    chunk = _survived_row(vendor_key="c1", object_type="chunk", object_id=str(uuid4()))
    statement = _survived_row(
        vendor_key="stmt",
        object_type="statement",
        object_id="stmt-ok",
        src="Alpha",
        tgt="Beta",
        support=0.88,
    )
    src = _survived_row(
        vendor_key="Alpha",
        object_type="entity",
        object_id="ent-a",
        vendor_name="Alpha",
        support=0.91,
    )
    tgt = _survived_row(
        vendor_key="Beta",
        object_type="entity",
        object_id="ent-b",
        vendor_name="Beta",
        support=0.93,
    )
    leads = GraphLeadSet(
        mode="local",
        entities=(
            GraphLeadEntity(entity_name="Alpha", source_ids=("c1",)),
            GraphLeadEntity(entity_name="Beta", source_ids=("c1",)),
        ),
        relations=(
            GraphLeadRelation(src_id="Alpha", tgt_id="Beta", source_ids=("c1",)),
        ),
    )
    candidates, _paths, dropped, diagnostics = _apply_whole_candidate_survival(
        leads,
        chunk_rows=(chunk,),
        evidence_rows=(statement, src, tgt),
    )
    assert len(candidates) == 1
    assert candidates[0].object_id == "stmt-ok"
    assert candidates[0].support == 0.88
    assert dropped == ()
    assert diagnostics == ()


def test_expand_bounded_paths_caps_hops_and_path_count() -> None:
    """Path expansion stops at three hops and six stable paths."""

    statements = tuple(
        ResolvedStatement(
            statement_id=f"s{index}",
            path_edge_id=f"p{index}",
            src_vendor=f"n{index}",
            tgt_vendor=f"n{index + 1}",
            chunk_ids=(uuid4(),),
            document_id=uuid4(),
            version_id=uuid4(),
            support=0.9,
        )
        for index in range(8)
    )
    paths = expand_bounded_paths(
        statements,
        max_hops=ADAPTER_MAX_HOPS,
        max_paths=ADAPTER_MAX_PATHS,
    )
    assert len(paths) == ADAPTER_MAX_PATHS
    assert all(item.hops <= ADAPTER_MAX_HOPS for item in paths)
    ids = [item.statement_ids for item in paths]
    assert ids == sorted(ids)


def test_reject_rendered_context_parser_still_fails_closed() -> None:
    """Rendered vendor prose cannot be parsed as evidence."""

    try:
        reject_rendered_context_parser("Entities: Alpha")
    except ProseContextRejectedError:
        return
    raise AssertionError("prose parser must fail closed")
