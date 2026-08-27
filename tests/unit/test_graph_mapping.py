"""Unit tests for Packet 4 canonical graph mapping identities and gates."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.ingestion.chunking.normalize import content_hash
from smart_rag_core.jobs.exceptions import GraphMappingError
from smart_rag_core.jobs.extraction_policy import ExtractionPolicySnapshot
from smart_rag_core.jobs.graph_mapping_service import (
    GraphMappingService,
    MappingOutcome,
)
from smart_rag_core.jobs.graph_writer import GraphWriterGuard
from smart_rag_core.jobs.limits import (
    GRAPH_PIPELINE_VERSION,
    LOCAL_DEMO_MAX_MAPPING_ENTITIES,
    LOCAL_DEMO_MAX_MAPPING_RELATIONS,
    MAPPING_SUPPORT_MIN,
    MAX_MAPPING_ENTITIES,
    MAX_MAPPING_VENDOR_CHUNKS,
)
from smart_rag_core.retrieval.graph import (
    DEFAULT_MAX_SOURCE_IDS_PER_ENTITY,
    GRAPH_FIELD_SEP,
    SourceIdContractError,
    bind_graph_source_text,
    canonical_passage_source_id,
    graph_chunker_config_snapshot,
    strip_graph_source_envelope,
)
from smart_rag_core.retrieval.graph_mapping import (
    CanonicalPassage,
    CoverageSlice,
    EntityRuleView,
    MappingBudgetError,
    MappingCallCounts,
    ObjectMapping,
    assert_mapping_budget,
    canonical_entity_key,
    canonical_source_identity,
    evaluate_coverage_gates,
    expected_vendor_basename,
    graph_path_edge_id,
    graph_statement_id,
    map_vendor_chunk,
    mapping_config_generation,
    mapping_content_digest,
    normalize_relation_label,
    parse_object_source_ids,
    resolve_entity_name,
    run_support_rerank,
    stitch_overlapping_texts,
)
from smart_rag_core.retrieval.lightrag_qualification import DocumentStatusView
from smart_rag_core.retrieval.rerank import RerankPassage, RerankRanking
from smart_rag_core.retrieval.types import RetrievalCandidate

from tests.unit.typed_attrs import typed_attr

VERSION_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
VERSION_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _mapping_connection() -> psycopg.Connection:
    """Return a non-connecting stand-in used only for constructor injection.

    Returns:
        Connection-typed stub. Persist and vendor reads are patched first.
    """

    return cast(psycopg.Connection, SimpleNamespace())


def _empty_entity_rules(_connection: psycopg.Connection) -> tuple[EntityRuleView, ...]:
    """Return no approved entity rules.

    Args:
        _connection: Unused mapping connection.

    Returns:
        Empty rule tuple.
    """

    del _connection
    return ()


def _english_language(_self: GraphMappingService, _version_id: UUID) -> str:
    """Return English so coverage gates do not query Postgres.

    Args:
        _self: Mapping service under test.
        _version_id: Canonical version.

    Returns:
        Language code ``en``.
    """

    del _self, _version_id
    return "en"


def _outcome_from_persist(
    service: GraphMappingService, **kwargs: object
) -> MappingOutcome:
    """Build a mapping outcome from patched persist kwargs.

    Args:
        service: Mapping service whose call counters are copied.
        **kwargs: Persist keyword arguments, including ``ready`` and ``reason``.

    Returns:
        Frozen outcome. Ready follows the persist decision.
    """

    ready = cast(bool, kwargs["ready"])
    return MappingOutcome(
        ready=ready,
        maps_verified=ready,
        reason=str(kwargs["reason"]),
        workspace_state="updating",
        hybrid_calls=service.counts.hybrid_retrieve,
        rerank_calls=service.counts.support_rerank,
        coverage=(),
    )


def unready_persist(self: GraphMappingService, **kwargs: object) -> MappingOutcome:  # pyright: ignore[reportUnusedFunction]
    """Return an unready persist outcome without touching Postgres.

    Args:
        self: Mapping service whose call counters are copied.
        **kwargs: Persist keyword arguments. ``reason`` is required.

    Returns:
        Frozen unready outcome.
    """

    return MappingOutcome(
        ready=False,
        maps_verified=False,
        reason=str(kwargs["reason"]),
        workspace_state="updating",
        hybrid_calls=self.counts.hybrid_retrieve,
        rerank_calls=self.counts.support_rerank,
        coverage=(),
    )


def _unused_hybrid(_query: str, _version_id: UUID) -> None:
    """Attached Hybrid callback that repair must refuse.

    Args:
        _query: Unused retrieve query.
        _version_id: Unused version.
    """

    del _query, _version_id


def _passage(
    *,
    text: str,
    version_id: UUID = VERSION_A,
    language: str = "en",
) -> CanonicalPassage:
    """Build one canonical passage using the ingest content hash.

    Args:
        text: Canonical ``raw_text``.
        version_id: Owning version.
        language: Version language.

    Returns:
        Canonical passage.
    """

    return CanonicalPassage(
        chunk_id=uuid4(),
        version_id=version_id,
        document_id=uuid4(),
        chunk_index=0,
        raw_text=text,
        content_hash=content_hash(text),
        language=language,
    )


def test_replay_yields_stable_application_ids() -> None:
    """Statement, path, entity, and source identities are deterministic."""

    config = mapping_config_generation(
        workspace_key="company_default",
        pointer_generation=1,
        chunker_snapshot=graph_chunker_config_snapshot(),
    )
    subject = canonical_entity_key(entity_type="ORG", canonical_name="Alpha")
    obj = canonical_entity_key(entity_type="ORG", canonical_name="Beta")
    relation = normalize_relation_label("employs,staffs")
    first = graph_statement_id(
        subject_key=subject,
        object_key=obj,
        relation_label_key=relation,
    )
    second = graph_statement_id(
        subject_key=subject,
        object_key=obj,
        relation_label_key=relation,
    )
    path_one = graph_path_edge_id(
        statement_ids=(first,),
        direction="src_to_tgt",
        version_id=VERSION_A,
    )
    path_two = graph_path_edge_id(
        statement_ids=(first,),
        direction="src_to_tgt",
        version_id=VERSION_A,
    )
    source_one = canonical_source_identity(
        version_id=VERSION_A,
        config_generation=config,
    )
    source_two = canonical_source_identity(
        version_id=VERSION_A,
        config_generation=config,
    )
    assert first == second
    assert path_one == path_two
    assert source_one == source_two
    assert (
        graph_chunker_config_snapshot()["graph_pipeline_version"]
        == GRAPH_PIPELINE_VERSION
    )
    assert expected_vendor_basename(VERSION_A) == f"g-{VERSION_A}.txt"


def test_duplicate_content_sources_stay_independent_after_envelope() -> None:
    """Identical raw text hashes match after strip, but source IDs differ."""

    body = "same canonical passage"
    first = bind_graph_source_text(
        document_version_id=str(VERSION_A),
        normalized_text=body,
    )
    second = bind_graph_source_text(
        document_version_id=str(VERSION_B),
        normalized_text=body,
    )
    assert first != second
    assert strip_graph_source_envelope(first) == body
    canonical = _passage(text=body, version_id=VERSION_A)
    match_a = map_vendor_chunk(first, (canonical,), version_id=VERSION_A)
    match_b = map_vendor_chunk(second, (canonical,), version_id=VERSION_B)
    assert match_a is not None
    assert match_a.method == "hash"
    assert match_a.source_hash == content_hash(body)
    assert match_b is None
    source_a = canonical_source_identity(
        version_id=VERSION_A,
        config_generation="cfg",
    )
    source_b = canonical_source_identity(
        version_id=VERSION_B,
        config_generation="cfg",
    )
    assert source_a != source_b


def test_stale_and_cross_version_chunks_are_rejected() -> None:
    """Hash matching ignores canonical rows from another version."""

    text = "version scoped passage"
    stale = _passage(text=text, version_id=VERSION_B)
    current = _passage(text=text, version_id=VERSION_A)
    match = map_vendor_chunk(text, (stale, current), version_id=VERSION_A)
    assert match is not None
    assert match.canonical.chunk_id == current.chunk_id
    foreign_only = map_vendor_chunk(text, (stale,), version_id=VERSION_A)
    assert foreign_only is None


def test_unsupported_relation_has_no_statement_id() -> None:
    """Empty structured keywords cannot mint a statement identity."""

    with pytest.raises(ValueError, match="unsupported_relation"):
        normalize_relation_label("")
    with pytest.raises(ValueError, match="unsupported_relation"):
        normalize_relation_label(None)
    with pytest.raises(ValueError, match="unsupported_relation"):
        normalize_relation_label("   ")


def test_ambiguous_entity_stays_unavailable() -> None:
    """Alias collisions and do-not-merge blocks do not auto-merge."""

    rules = (
        EntityRuleView(
            entity_type="ORG",
            canonical_name="Alpha Corp",
            aliases=("Acme",),
            do_not_merge=(),
        ),
        EntityRuleView(
            entity_type="ORG",
            canonical_name="Alpha LLC",
            aliases=("Acme",),
            do_not_merge=(),
        ),
    )
    assert resolve_entity_name("Acme", "ORG", rules) is None
    blocked = (
        EntityRuleView(
            entity_type="ORG",
            canonical_name="Acme",
            aliases=("Acme",),
            do_not_merge=("Acme",),
        ),
    )
    assert resolve_entity_name("Acme", "ORG", blocked) is None
    unique = (
        EntityRuleView(
            entity_type="ORG",
            canonical_name="Alpha Corp",
            aliases=("Acme",),
            do_not_merge=(),
        ),
    )
    assert resolve_entity_name("Acme", "ORG", unique) == "Alpha Corp"


def test_language_gate_not_hidden_by_english_aggregate() -> None:
    """Arabic coverage below 0.85 fails even when overall English is high."""

    english = CoverageSlice(
        language="en",
        object_type="chunk",
        method="hash",
        numerator=20,
        denominator=20,
        exclusion_count=0,
    )
    arabic = CoverageSlice(
        language="ar",
        object_type="chunk",
        method="hash",
        numerator=2,
        denominator=4,
        exclusion_count=2,
    )
    passed, reason = evaluate_coverage_gates((english, arabic))
    assert passed is False
    assert reason == "language_gate"
    all_arabic = CoverageSlice(
        language="ar",
        object_type="chunk",
        method="hash",
        numerator=17,
        denominator=20,
        exclusion_count=3,
    )
    passed_ar, reason_ar = evaluate_coverage_gates((all_arabic,))
    assert passed_ar is True
    assert reason_ar == ""


def test_source_truncation_fails_closed() -> None:
    """At-cap source-id lists are truncated, not silently complete."""

    tokens = GRAPH_FIELD_SEP.join(f"chunk-{index}" for index in range(200))
    with pytest.raises(SourceIdContractError, match="source_id_list_truncated"):
        parse_object_source_ids(tokens, kind="entity")
    assert DEFAULT_MAX_SOURCE_IDS_PER_ENTITY == 200


def test_mapping_budget_bounds() -> None:
    """Vendor object and model-call caps fail closed."""

    with pytest.raises(MappingBudgetError, match="mapping_budget_chunks"):
        assert_mapping_budget(
            vendor_chunks=MAX_MAPPING_VENDOR_CHUNKS + 1,
            entities=1,
            relations=1,
            hybrid_calls=0,
            rerank_calls=0,
        )
    with pytest.raises(MappingBudgetError, match="mapping_budget_entities"):
        assert_mapping_budget(
            vendor_chunks=1,
            entities=MAX_MAPPING_ENTITIES + 1,
            relations=1,
            hybrid_calls=0,
            rerank_calls=0,
        )
    with pytest.raises(MappingBudgetError, match="mapping_budget_hybrid"):
        assert_mapping_budget(
            vendor_chunks=1,
            entities=1,
            relations=1,
            hybrid_calls=2,
            rerank_calls=0,
        )
    assert_mapping_budget(
        vendor_chunks=1,
        entities=LOCAL_DEMO_MAX_MAPPING_ENTITIES,
        relations=LOCAL_DEMO_MAX_MAPPING_RELATIONS,
        hybrid_calls=0,
        rerank_calls=0,
        max_entities=LOCAL_DEMO_MAX_MAPPING_ENTITIES,
        max_relations=LOCAL_DEMO_MAX_MAPPING_RELATIONS,
    )
    with pytest.raises(MappingBudgetError, match="mapping_budget_relations"):
        assert_mapping_budget(
            vendor_chunks=1,
            entities=1,
            relations=LOCAL_DEMO_MAX_MAPPING_RELATIONS + 1,
            hybrid_calls=0,
            rerank_calls=0,
            max_entities=LOCAL_DEMO_MAX_MAPPING_ENTITIES,
            max_relations=LOCAL_DEMO_MAX_MAPPING_RELATIONS,
        )


def test_local_demo_caps_cover_canonical_passage_graph_200_flood() -> None:
    """Local demo ceilings must cover the measured isolate extract flood."""

    measured_entities = 1_779
    measured_relations = 1_531
    assert LOCAL_DEMO_MAX_MAPPING_ENTITIES >= measured_entities
    assert LOCAL_DEMO_MAX_MAPPING_RELATIONS >= measured_relations
    assert_mapping_budget(
        vendor_chunks=164,
        entities=measured_entities,
        relations=measured_relations,
        hybrid_calls=0,
        rerank_calls=0,
        max_entities=LOCAL_DEMO_MAX_MAPPING_ENTITIES,
        max_relations=LOCAL_DEMO_MAX_MAPPING_RELATIONS,
    )
    with pytest.raises(MappingBudgetError, match="mapping_budget_entities"):
        assert_mapping_budget(
            vendor_chunks=164,
            entities=measured_entities,
            relations=measured_relations,
            hybrid_calls=0,
            rerank_calls=0,
        )


def test_mapping_service_rejects_caps_above_local_demo() -> None:
    """Injected mapper caps cannot exceed the approved local ceiling."""

    with pytest.raises(ValueError, match="invalid_mapping_entity_limit"):
        GraphMappingService(
            _mapping_connection(),
            vendor_reader=_FakeVendor(),
            writer=_mapping_writer(),
            max_entities=LOCAL_DEMO_MAX_MAPPING_ENTITIES + 1,
        )


def test_support_threshold_is_eighty() -> None:
    """Accepted canonical support cannot be lowered below 0.80."""

    assert MAPPING_SUPPORT_MIN == 0.80


def test_hash_uses_ingest_normalizer_after_envelope_strip() -> None:
    """Mapping hash equals ingest ``content_hash`` after envelope strip."""

    body = "  Café  Policy \n"
    enveloped = bind_graph_source_text(
        document_version_id=str(VERSION_A),
        normalized_text=body,
    )
    canonical = _passage(text=body, version_id=VERSION_A)
    match = map_vendor_chunk(enveloped, (canonical,), version_id=VERSION_A)
    assert match is not None
    assert match.method == "hash"
    assert match.source_hash == content_hash(body)
    assert match.target_hash == canonical.content_hash


def test_stitch_overlapping_texts_drops_shared_suffix_prefix() -> None:
    """LightRAG overlap tails must reconstruct the original source text."""

    assert stitch_overlapping_texts(("hello world", "world!!")) == "hello world!!"
    assert stitch_overlapping_texts(("only",)) == "only"


def test_mapping_content_digest_unescapes_html_entities() -> None:
    """Vendor HTML-unescaped dashes still match the canonical passage."""

    canonical = "burns in the fire &mdash; now"
    vendor = "burns in the fire — now"
    assert mapping_content_digest(canonical) == mapping_content_digest(vendor)


class _FakeVendor:
    """In-memory vendor catalog for mapping-service unit tests."""

    def __init__(
        self,
        *,
        status: str = "processed",
        file_path: str | None = None,
        chunks: Sequence[Mapping[str, object]] | None = None,
        nodes: Sequence[Mapping[str, object]] | None = None,
        edges: Sequence[Mapping[str, object]] | None = None,
    ) -> None:
        """Bind in-memory vendor catalog rows.

        Args:
            status: Vendor document status label.
            file_path: Optional vendor file path.
            chunks: Vendor chunk rows.
            nodes: Vendor graph nodes.
            edges: Vendor graph edges.
        """

        self._status = status
        self._file_path = file_path
        self._chunks = list(chunks or ())
        self._nodes = list(nodes or ())
        self._edges = list(edges or ())

    async def vendor_document_status(self, document_id: str) -> DocumentStatusView:
        """Return the configured vendor status view for one source ID."""

        from smart_rag_core.retrieval.graph import (
            opaque_passage_source_basename,
            parse_canonical_passage_source_id,
        )

        if self._file_path is not None:
            file_path = self._file_path
        elif ":" in document_id:
            version_id, chunk_id = parse_canonical_passage_source_id(document_id)
            file_path = opaque_passage_source_basename(
                version_id=version_id,
                chunk_id=chunk_id,
            )
        else:
            file_path = expected_vendor_basename(UUID(document_id))
        return DocumentStatusView(
            document_id=document_id,
            status=self._status,
            file_path=file_path,
        )

    async def list_vendor_doc_chunks(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return configured vendor chunks."""

        return [dict(row) for row in self._chunks]

    async def list_vendor_doc_chunks_for_ids(
        self,
        *,
        document_ids: tuple[str, ...],
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        """Return vendor chunks whose ``full_doc_id`` is in ``document_ids``."""

        wanted = set(document_ids)
        return [
            dict(row)
            for row in self._chunks
            if str(row.get("full_doc_id") or "") in wanted
        ]

    async def list_vendor_entity_joins(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return no entity joins."""

        return []

    async def list_vendor_relation_joins(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return no relation joins."""

        return []

    async def list_vendor_graph_nodes(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return configured nodes."""

        return [dict(row) for row in self._nodes]

    async def list_vendor_graph_edges(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return configured edges."""

        return [dict(row) for row in self._edges]


class _StubWriter:
    """Writer guard stub that records workspace transitions."""

    workspace_key = "company_default"

    def load_pointer_generation(self) -> int:
        """Return generation 1."""

        return 1

    def transition_state(self, **_kwargs: object) -> UUID:
        """No-op transition used when persist is patched."""

        return uuid4()


def _mapping_writer() -> GraphWriterGuard:
    """Return a writer stub that records no Postgres transitions.

    Returns:
        Writer-typed stub for mapping-service construction.
    """

    return cast(GraphWriterGuard, _StubWriter())


def _stub_extraction_policy(
    _connection: psycopg.Connection,
) -> ExtractionPolicySnapshot:
    """Return generation-1 policy so Packet 4 unit tests need no Postgres.

    Args:
        _connection: Unused fake mapping connection.

    Returns:
        Snapshot with an empty hash so mapping digests stay stable.
    """

    del _connection
    return ExtractionPolicySnapshot(
        entity_rules_generation=1, extraction_policy_hash=""
    )


def test_processed_only_is_not_graph_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vendor PROCESSED without matching passage chunks cannot mark Graph Ready."""

    persist_called = {"count": 0}

    def _load_canonicals(
        _connection: psycopg.Connection, *, version_id: UUID
    ) -> tuple[CanonicalPassage, ...]:
        """Return one canonical that will not match empty vendor chunks."""

        del version_id
        return (_passage(text="canonical only"),)

    def _persist(self: GraphMappingService, **kwargs: object) -> MappingOutcome:
        """Capture an unexpected persist call."""

        persist_called["count"] += 1
        return _outcome_from_persist(self, **kwargs)

    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_canonical_passages",
        _load_canonicals,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_entity_rules",
        _empty_entity_rules,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_service.load_extraction_policy",
        _stub_extraction_policy,
    )
    monkeypatch.setattr(GraphMappingService, "_persist", _persist)
    monkeypatch.setattr(
        GraphMappingService,
        "_load_version_language",
        _english_language,
    )

    def _skip_repair(self: GraphMappingService, **_kwargs: object) -> None:
        """Skip repair enqueue in this test.

        Args:
            self: Mapping service.
            **_kwargs: Unused repair kwargs.
        """

        return None

    monkeypatch.setattr(
        GraphMappingService,
        "_enqueue_repair_only",
        _skip_repair,
    )
    service = GraphMappingService(
        _mapping_connection(),
        vendor_reader=_FakeVendor(chunks=[]),
        writer=_mapping_writer(),
    )
    outcome = asyncio.run(
        service.map_after_vendor_success(
            document_id=uuid4(),
            version_id=VERSION_A,
        )
    )
    assert outcome.ready is False
    assert outcome.maps_verified is False
    assert outcome.reason == "graph_source_snapshot_mismatch"
    assert persist_called["count"] == 0
    assert outcome.hybrid_calls == 0


def test_exact_hash_bijection_skips_hybrid(monkeypatch: pytest.MonkeyPatch) -> None:
    """One canonical passage maps by hash to one vendor chunk without Hybrid."""

    canonical = _passage(text="canonical passage body")
    source_id = canonical_passage_source_id(
        version_id=VERSION_A,
        chunk_id=canonical.chunk_id,
    )
    enveloped = bind_graph_source_text(
        document_version_id=source_id,
        normalized_text=canonical.raw_text,
    )
    hybrid_calls = {"count": 0}

    def hybrid(_query: str, _version_id: UUID) -> object:
        """Fail if Hybrid is invoked on the exact path."""

        hybrid_calls["count"] += 1
        raise AssertionError("hybrid must not run on exact mapping")

    def _load_canonicals(
        _connection: psycopg.Connection, *, version_id: UUID
    ) -> tuple[CanonicalPassage, ...]:
        """Return the single canonical passage under test."""

        del version_id
        return (canonical,)

    captured: dict[str, object] = {}

    def _persist(self: GraphMappingService, **kwargs: object) -> MappingOutcome:
        """Capture mapped rows without Postgres."""

        captured["ready"] = kwargs["ready"]
        captured["chunk_rows"] = kwargs["chunk_rows"]
        return _outcome_from_persist(self, **kwargs)

    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_canonical_passages",
        _load_canonicals,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_entity_rules",
        _empty_entity_rules,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_service.load_extraction_policy",
        _stub_extraction_policy,
    )
    monkeypatch.setattr(GraphMappingService, "_persist", _persist)
    monkeypatch.setattr(
        GraphMappingService,
        "_load_version_language",
        _english_language,
    )
    vendor_chunk = {
        "id": "vc-1",
        "full_doc_id": source_id,
        "content": enveloped,
    }
    service = GraphMappingService(
        _mapping_connection(),
        vendor_reader=_FakeVendor(chunks=[vendor_chunk]),
        writer=_mapping_writer(),
        hybrid_retrieve=hybrid,
    )
    outcome = asyncio.run(
        service.map_after_vendor_success(
            document_id=uuid4(),
            version_id=VERSION_A,
        )
    )
    assert hybrid_calls["count"] == 0
    assert outcome.hybrid_calls == 0
    assert captured["ready"] is True
    chunk_rows = cast(list[object], captured["chunk_rows"])
    assert len(chunk_rows) == 1


def test_exact_mapping_stitches_overlapping_vendor_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Split LightRAG chunks still map when reconstruction hashes match."""

    body = "alpha beta gamma delta epsilon"
    canonical = _passage(text=body, version_id=VERSION_A)
    source_id = canonical_passage_source_id(
        version_id=VERSION_A,
        chunk_id=canonical.chunk_id,
    )
    enveloped = bind_graph_source_text(
        document_version_id=source_id,
        normalized_text=body,
    )
    first = enveloped[: max(len(enveloped) // 2, 8)]
    second = enveloped[len(first) - 6 :]
    assert stitch_overlapping_texts((first, second)) == enveloped

    def _load_canonicals(
        _connection: psycopg.Connection, *, version_id: UUID
    ) -> tuple[CanonicalPassage, ...]:
        """Return the single canonical passage under test."""

        del version_id
        return (canonical,)

    captured: dict[str, object] = {}

    def _persist(self: GraphMappingService, **kwargs: object) -> MappingOutcome:
        """Capture mapped rows without Postgres."""

        captured["ready"] = kwargs["ready"]
        captured["chunk_rows"] = kwargs["chunk_rows"]
        return _outcome_from_persist(self, **kwargs)

    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_canonical_passages",
        _load_canonicals,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_entity_rules",
        _empty_entity_rules,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_service.load_extraction_policy",
        _stub_extraction_policy,
    )
    monkeypatch.setattr(GraphMappingService, "_persist", _persist)
    monkeypatch.setattr(
        GraphMappingService,
        "_load_version_language",
        _english_language,
    )
    service = GraphMappingService(
        _mapping_connection(),
        vendor_reader=_FakeVendor(
            chunks=[
                {
                    "id": "vc-a",
                    "full_doc_id": source_id,
                    "content": first,
                    "chunk_order_index": 0,
                },
                {
                    "id": "vc-b",
                    "full_doc_id": source_id,
                    "content": second,
                    "chunk_order_index": 1,
                },
            ]
        ),
        writer=_mapping_writer(),
    )
    outcome = asyncio.run(
        service.map_after_vendor_success(
            document_id=uuid4(),
            version_id=VERSION_A,
        )
    )
    assert outcome.reason == ""
    assert captured["ready"] is True
    chunk_rows = cast(list[object], captured["chunk_rows"])
    assert len(chunk_rows) == 1
    row = chunk_rows[0]
    assert typed_attr(row, "vendor_chunk_id") == "vc-a"
    assert typed_attr(row, "vendor_piece_ids") == ("vc-a", "vc-b")


def test_multi_source_entity_keeps_all_passage_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepted entity support persists every referenced canonical passage."""

    first = _passage(text="first canonical passage")
    second = _passage(text="second canonical passage")
    source_one = canonical_passage_source_id(
        version_id=VERSION_A,
        chunk_id=first.chunk_id,
    )
    source_two = canonical_passage_source_id(
        version_id=VERSION_A,
        chunk_id=second.chunk_id,
    )

    def _load_canonicals(
        _connection: psycopg.Connection, *, version_id: UUID
    ) -> tuple[CanonicalPassage, ...]:
        """Return two canonical passages."""

        del version_id
        return (first, second)

    captured: dict[str, object] = {}

    def _persist(self: GraphMappingService, **kwargs: object) -> MappingOutcome:
        """Capture object mappings."""

        captured["objects"] = kwargs["objects"]
        return _outcome_from_persist(self, **kwargs)

    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_canonical_passages",
        _load_canonicals,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_entity_rules",
        _empty_entity_rules,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_service.load_extraction_policy",
        _stub_extraction_policy,
    )
    monkeypatch.setattr(GraphMappingService, "_persist", _persist)
    monkeypatch.setattr(
        GraphMappingService,
        "_load_version_language",
        _english_language,
    )
    vendor = _FakeVendor(
        chunks=[
            {
                "id": "vc-1",
                "full_doc_id": source_one,
                "content": bind_graph_source_text(
                    document_version_id=source_one,
                    normalized_text=first.raw_text,
                ),
            },
            {
                "id": "vc-2",
                "full_doc_id": source_two,
                "content": bind_graph_source_text(
                    document_version_id=source_two,
                    normalized_text=second.raw_text,
                ),
            },
        ],
        nodes=[
            {
                "id": "Alpha",
                "properties": {
                    "entity_name": "Alpha",
                    "entity_type": "ORG",
                    "source_id": GRAPH_FIELD_SEP.join(("vc-1", "vc-2")),
                },
            }
        ],
    )
    service = GraphMappingService(
        _mapping_connection(),
        vendor_reader=vendor,
        writer=_mapping_writer(),
    )
    asyncio.run(
        service.map_after_vendor_success(
            document_id=uuid4(),
            version_id=VERSION_A,
        )
    )
    objects = cast(list[ObjectMapping], captured["objects"])
    entities = [item for item in objects if item.object_type == "entity"]
    assert len(entities) == 1
    assert entities[0].available is True
    assert entities[0].support_matches
    assert {
        entities[0].chunk_id,
        entities[0].support_matches[0].canonical.chunk_id,
    } == {
        first.chunk_id,
        second.chunk_id,
    }


def test_unresolved_batch_does_not_use_hybrid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hash mismatch is terminal snapshot mismatch; Hybrid is not a fallback."""

    body = "unresolved vendor text that will not hash"
    canonical_one = _passage(text="canonical alpha extra words here")
    hybrid_calls = {"count": 0}
    rerank_calls = {"count": 0}

    def hybrid(_query: str, _version_id: UUID) -> object:
        """Count illegal Hybrid retrieve invocations."""

        hybrid_calls["count"] += 1
        return SimpleNamespace(ranked_ids=(canonical_one.chunk_id,))

    def rerank(
        _query: str, passages: tuple[RerankPassage, ...]
    ) -> tuple[RerankRanking, ...]:
        """Count illegal support rerank batches."""

        del passages
        rerank_calls["count"] += 1
        return ()

    def _load_canonicals(
        _connection: psycopg.Connection, *, version_id: UUID
    ) -> tuple[CanonicalPassage, ...]:
        """Return one canonical that cannot hash-match the vendor body."""

        del version_id
        return (canonical_one,)

    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_canonical_passages",
        _load_canonicals,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_entity_rules",
        _empty_entity_rules,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_service.load_extraction_policy",
        _stub_extraction_policy,
    )
    monkeypatch.setattr(
        GraphMappingService,
        "_load_version_language",
        _english_language,
    )

    def _skip_repair(self: GraphMappingService, **_kwargs: object) -> None:
        """Skip repair enqueue in this test.

        Args:
            self: Mapping service.
            **_kwargs: Unused repair kwargs.
        """

        return None

    monkeypatch.setattr(
        GraphMappingService,
        "_enqueue_repair_only",
        _skip_repair,
    )
    source_id = canonical_passage_source_id(
        version_id=VERSION_A,
        chunk_id=canonical_one.chunk_id,
    )
    vendor_chunk = {
        "id": "vc-1",
        "full_doc_id": source_id,
        "content": body,
    }
    service = GraphMappingService(
        _mapping_connection(),
        vendor_reader=_FakeVendor(chunks=[vendor_chunk]),
        writer=_mapping_writer(),
        hybrid_retrieve=hybrid,
        support_rerank=rerank,
    )
    outcome = asyncio.run(
        service.map_after_vendor_success(
            document_id=uuid4(),
            version_id=VERSION_A,
        )
    )
    assert hybrid_calls["count"] == 0
    assert rerank_calls["count"] == 0
    assert outcome.hybrid_calls == 0
    assert outcome.rerank_calls == 0
    assert outcome.reason == "graph_source_snapshot_mismatch"


def test_repair_must_not_query_hybrid() -> None:
    """Repair refuses to run when Hybrid or rerank callbacks are attached."""

    service = GraphMappingService(
        _mapping_connection(),
        vendor_reader=_FakeVendor(),
        writer=_mapping_writer(),
        hybrid_retrieve=_unused_hybrid,
    )
    with pytest.raises(GraphMappingError, match="repair_must_not_query_hybrid"):
        asyncio.run(
            service.repair_stored(
                workspace_key="company_default",
                config_generation="cfg",
            )
        )


def test_rerank_rejects_unknown_ids() -> None:
    """Support rerank must return exactly the supplied candidate set."""

    counts = MappingCallCounts()
    passage = RerankPassage(
        candidate=RetrievalCandidate(
            chunk_id=uuid4(),
            document_id=uuid4(),
            version_id=VERSION_A,
            channel_rank=1,
            channel_score=1.0,
        ),
        raw_text="one",
    )
    other = RerankPassage(
        candidate=RetrievalCandidate(
            chunk_id=uuid4(),
            document_id=uuid4(),
            version_id=VERSION_A,
            channel_rank=2,
            channel_score=1.0,
        ),
        raw_text="two",
    )

    def _bad(
        _query: str, _passages: tuple[RerankPassage, ...]
    ) -> tuple[RerankRanking, ...]:
        """Return an unknown chunk id."""

        return (
            RerankRanking(chunk_id=uuid4(), rank=1, support=0.9),
            RerankRanking(chunk_id=passage.candidate.chunk_id, rank=2, support=0.9),
        )

    with pytest.raises(ValueError, match="rerank_unknown_or_missing_id"):
        run_support_rerank(
            _bad,
            query="q",
            passages=(passage, other),
            counts=counts,
        )
    assert counts.support_rerank == 1
