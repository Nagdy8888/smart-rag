"""Unit tests for Packet 4 canonical graph mapping identities and gates."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from smart_rag_core.ingestion.chunking.normalize import content_hash
from smart_rag_core.jobs.exceptions import GraphMappingError
from smart_rag_core.jobs.extraction_policy import ExtractionPolicySnapshot
from smart_rag_core.jobs.graph_mapping_service import GraphMappingService
from smart_rag_core.jobs.limits import (
    GRAPH_PIPELINE_VERSION,
    MAPPING_SUPPORT_MIN,
    MAX_MAPPING_ENTITIES,
    MAX_MAPPING_VENDOR_CHUNKS,
)
from smart_rag_core.retrieval.graph import (
    DEFAULT_MAX_SOURCE_IDS_PER_ENTITY,
    GRAPH_FIELD_SEP,
    SourceIdContractError,
    bind_graph_source_text,
    graph_chunker_config_snapshot,
    strip_graph_source_envelope,
)
from smart_rag_core.retrieval.graph_mapping import (
    CanonicalPassage,
    CoverageSlice,
    EntityRuleView,
    MappingBudgetError,
    MappingCallCounts,
    assert_mapping_budget,
    canonical_entity_key,
    canonical_source_identity,
    evaluate_coverage_gates,
    expected_vendor_basename,
    graph_path_edge_id,
    graph_statement_id,
    map_vendor_chunk,
    mapping_config_generation,
    normalize_relation_label,
    parse_object_source_ids,
    resolve_entity_name,
    run_support_rerank,
)
from smart_rag_core.retrieval.lightrag_qualification import DocumentStatusView
from smart_rag_core.retrieval.rerank import RerankPassage, RerankRanking
from smart_rag_core.retrieval.types import RetrievalCandidate

VERSION_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
VERSION_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


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


class _FakeVendor:
    """In-memory vendor catalog for mapping-service unit tests."""

    def __init__(
        self,
        *,
        status: str = "processed",
        file_path: str | None = None,
        chunks: list[dict[str, object]] | None = None,
        nodes: list[dict[str, object]] | None = None,
        edges: list[dict[str, object]] | None = None,
    ) -> None:
        self._status = status
        self._file_path = file_path
        self._chunks = chunks or []
        self._nodes = nodes or []
        self._edges = edges or []

    async def vendor_document_status(self, document_id: str) -> DocumentStatusView:
        """Return the configured vendor status view."""

        return DocumentStatusView(
            document_id=document_id,
            status=self._status,
            file_path=self._file_path or expected_vendor_basename(UUID(document_id)),
        )

    async def list_vendor_doc_chunks(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return configured vendor chunks."""

        return list(self._chunks)

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

        return list(self._nodes)

    async def list_vendor_graph_edges(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return configured edges."""

        return list(self._edges)


class _StubWriter:
    """Writer guard stub that records workspace transitions."""

    workspace_key = "company_default"

    def load_pointer_generation(self) -> int:
        """Return generation 1."""

        return 1

    def transition_state(self, **_kwargs: object) -> UUID:
        """No-op transition used when persist is patched."""

        return uuid4()


def _stub_extraction_policy(_connection: object) -> ExtractionPolicySnapshot:
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
    """Vendor PROCESSED without accepted maps cannot mark Graph Ready."""

    captured: dict[str, object] = {}

    def _load_canonicals(
        _connection: object, *, version_id: UUID
    ) -> tuple[CanonicalPassage, ...]:
        """Return one canonical that will not match empty vendor chunks."""

        del version_id
        return (_passage(text="canonical only"),)

    def _persist(self: GraphMappingService, **kwargs: object) -> object:
        """Capture the Graph Ready decision without touching Postgres."""

        captured.update(kwargs)
        return SimpleNamespace(
            ready=kwargs["ready"],
            maps_verified=kwargs["ready"],
            reason=kwargs["reason"],
            workspace_state="updating",
            hybrid_calls=self.counts.hybrid_retrieve,
            rerank_calls=self.counts.support_rerank,
            coverage=(),
        )

    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_canonical_passages",
        _load_canonicals,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_entity_rules",
        lambda _connection: (),
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_service.load_extraction_policy",
        _stub_extraction_policy,
    )
    monkeypatch.setattr(GraphMappingService, "_persist", _persist)
    monkeypatch.setattr(
        GraphMappingService,
        "_load_version_language",
        lambda self, _version_id: "en",
    )
    service = GraphMappingService(
        SimpleNamespace(),
        vendor_reader=_FakeVendor(chunks=[]),
        writer=_StubWriter(),
    )
    outcome = asyncio.run(
        service.map_after_vendor_success(
            document_id=uuid4(),
            version_id=VERSION_A,
        )
    )
    assert outcome.ready is False
    assert outcome.maps_verified is False
    assert captured["ready"] is False
    assert captured["reason"] == "coverage_empty"


def test_unresolved_batch_uses_one_hybrid_and_one_rerank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N relations still cause one Hybrid retrieve and one rerank batch."""

    body = "unresolved vendor text that will not hash"
    canonical_one = _passage(text="canonical alpha extra words here")
    canonical_two = _passage(text="canonical beta extra words here")
    hybrid_calls = {"count": 0}
    rerank_calls = {"count": 0}

    def hybrid(_query: str, _version_id: UUID) -> object:
        """Count Hybrid retrieve invocations."""

        hybrid_calls["count"] += 1
        return SimpleNamespace(ranked_ids=(canonical_one.chunk_id,))

    def rerank(
        _query: str, passages: tuple[RerankPassage, ...]
    ) -> tuple[RerankRanking, ...]:
        """Count support rerank batches and return set-equal IDs."""

        rerank_calls["count"] += 1
        return tuple(
            RerankRanking(
                chunk_id=item.candidate.chunk_id, rank=index + 1, support=0.91
            )
            for index, item in enumerate(passages)
        )

    def _load_canonicals(
        _connection: object, *, version_id: UUID
    ) -> tuple[CanonicalPassage, ...]:
        """Return two canonicals so rerank has a legal pool."""

        del version_id
        return (canonical_one, canonical_two)

    captured: dict[str, object] = {}

    def _persist(self: GraphMappingService, **kwargs: object) -> object:
        """Capture call counts without Postgres."""

        captured["hybrid"] = self.counts.hybrid_retrieve
        captured["rerank"] = self.counts.support_rerank
        captured["ready"] = kwargs["ready"]
        return SimpleNamespace(
            ready=False,
            maps_verified=False,
            reason=str(kwargs["reason"]),
            workspace_state="updating",
            hybrid_calls=self.counts.hybrid_retrieve,
            rerank_calls=self.counts.support_rerank,
            coverage=(),
        )

    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_canonical_passages",
        _load_canonicals,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_entity_rules",
        lambda _connection: (),
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_service.load_extraction_policy",
        _stub_extraction_policy,
    )
    monkeypatch.setattr(GraphMappingService, "_persist", _persist)
    monkeypatch.setattr(
        GraphMappingService,
        "_load_version_language",
        lambda self, _version_id: "en",
    )
    vendor_chunk = {
        "id": "vc-1",
        "full_doc_id": str(VERSION_A),
        "content": body,
    }
    nodes = [
        {
            "id": "Alpha",
            "properties": {
                "entity_name": "Alpha",
                "entity_type": "ORG",
                "source_id": "vc-1",
            },
        },
        {
            "id": "Beta",
            "properties": {
                "entity_name": "Beta",
                "entity_type": "ORG",
                "source_id": "vc-1",
            },
        },
    ]
    edges = [
        {
            "src_id": "Alpha",
            "tgt_id": "Beta",
            "properties": {"keywords": "employs", "source_id": "vc-1"},
        },
        {
            "src_id": "Beta",
            "tgt_id": "Alpha",
            "properties": {"keywords": "reports_to", "source_id": "vc-1"},
        },
    ]
    service = GraphMappingService(
        SimpleNamespace(),
        vendor_reader=_FakeVendor(chunks=[vendor_chunk], nodes=nodes, edges=edges),
        writer=_StubWriter(),
        hybrid_retrieve=hybrid,
        support_rerank=rerank,
    )
    outcome = asyncio.run(
        service.map_after_vendor_success(
            document_id=uuid4(),
            version_id=VERSION_A,
        )
    )
    assert hybrid_calls["count"] == 1
    assert rerank_calls["count"] == 1
    assert outcome.hybrid_calls == 1
    assert outcome.rerank_calls == 1
    assert captured["hybrid"] == 1
    assert captured["rerank"] == 1


def test_repair_must_not_query_hybrid() -> None:
    """Repair refuses to run when Hybrid or rerank callbacks are attached."""

    service = GraphMappingService(
        SimpleNamespace(),
        vendor_reader=_FakeVendor(),
        writer=_StubWriter(),
        hybrid_retrieve=lambda _query, _version_id: None,
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
