"""Tests for worker mapping Hybrid/rerank callback binding."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.ingestion.chunking.normalize import content_hash
from smart_rag_core.jobs.graph_index_service import GraphIndexService
from smart_rag_core.jobs.graph_mapping_hybrid import (
    MappingSupportCallbacks,
    bind_mapping_support,
)
from smart_rag_core.jobs.graph_mapping_service import GraphMappingService
from smart_rag_core.jobs.graph_writer import GraphWriterGuard
from smart_rag_core.jobs.lightrag_repository import LightragIndexJobRepository
from smart_rag_core.retrieval.coverage import CoverageSignal, HybridCoverage
from smart_rag_core.retrieval.graph_mapping import CanonicalPassage
from smart_rag_core.retrieval.hybrid_run import HybridRunResult
from smart_rag_core.retrieval.lightrag_indexer import LightRagGraphIndexer
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.retrieval.rerank import RerankPassage, RerankRanking
from smart_rag_core.retrieval.rerank_versions import RERANK_PROMPT_SHA256
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.settings import WorkerSettings

_VERSION = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_CALLER = CallerContext(
    user_id="00000000-0000-4000-8000-000000000002",
    role=UserRole.MEMBER,
    authorization_version=1,
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RERANK_PROMPT = (
    _REPO_ROOT
    / "apps"
    / "agents"
    / "src"
    / "smart_rag_agents"
    / "prompts"
    / "rerank_v1.md"
)


class _UnusedConnection:
    """Stand-in connection; bind does not query until callbacks run."""


def _unused_connection() -> psycopg.Connection:
    """Return a connection-typed stand-in for mapping Hybrid bind.

    Returns:
        Connection stub. Callbacks do not query until invoked.
    """

    return cast(psycopg.Connection, _UnusedConnection())


def _object_map(value: object) -> dict[str, object]:
    """Treat a captured kwargs object as a string-key map.

    Args:
        value: Value stored in the capture dict.

    Returns:
        The value as an object map.
    """

    return cast(dict[str, object], value)


def _empty_hybrid_result() -> HybridRunResult:
    """Return an empty Hybrid retrieve used by mapping-support stubs.

    Returns:
        Empty ranked-ID Hybrid result.
    """

    return HybridRunResult(
        ranked_ids=(),
        evidence=(),
        coverage=HybridCoverage(signal=CoverageSignal.WEAK_EVIDENCE),
        fallback_reason=RetrievalFallbackReason.RETRIEVAL_EMPTY,
        deadline_exhausted=False,
        first_evidence_ms=0.0,
        embedding_call_count=0,
        rerank_call_count=0,
    )


def _load_mapping_caller(
    _connection: psycopg.Connection, *, version_id: UUID
) -> CallerContext:
    """Return the frozen mapping caller without querying Postgres.

    Args:
        _connection: Unused stand-in connection.
        version_id: Canonical version (unused in this stub).

    Returns:
        Active member caller.
    """

    del _connection, version_id
    return _CALLER


def _index_service(
    *, mapping_support: MappingSupportCallbacks | None = None
) -> GraphIndexService:
    """Build a GraphIndexService with constructor stubs.

    Args:
        mapping_support: Optional Hybrid/rerank callbacks.

    Returns:
        Service whose mapper stores the injected callbacks.
    """

    return GraphIndexService(
        cast(psycopg.Connection, SimpleNamespace()),
        indexer=cast(LightRagGraphIndexer, SimpleNamespace(adapter=object())),
        writer=cast(GraphWriterGuard, SimpleNamespace()),
        repository=cast(LightragIndexJobRepository, SimpleNamespace()),
        mapping_support=mapping_support,
    )


def _mapper_attr(service: GraphIndexService, name: str) -> object:
    """Read a private mapping-service attribute without a private import.

    Args:
        service: Index service under test.
        name: Private attribute on the nested mapping service.

    Returns:
        Attribute value.
    """

    mapper = cast(GraphMappingService, object.__getattribute__(service, "_mapper"))
    return object.__getattribute__(mapper, name)


def test_mapping_rerank_prompt_matches_frozen_hash() -> None:
    """Mapping support rerank uses the pinned Hybrid rerank prompt file."""

    digest = hashlib.sha256(_RERANK_PROMPT.read_bytes()).hexdigest()
    assert digest == RERANK_PROMPT_SHA256
    assert _RERANK_PROMPT.is_file()


def test_bind_mapping_support_in_mock_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock-mode settings produce mapping callbacks without a provider key."""

    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    settings = WorkerSettings()
    assert settings.mock_model_mode is True
    callbacks = bind_mapping_support(_unused_connection(), settings)
    assert callbacks is not None
    assert callable(callbacks.hybrid_retrieve)
    assert callable(callbacks.support_rerank)


def test_bind_mapping_support_returns_none_when_prompt_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing pinned prompt fails closed so hash/span/overlap still run."""

    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_hybrid._RERANK_PROMPT",
        tmp_path / "missing.md",
    )
    assert bind_mapping_support(_unused_connection(), WorkerSettings()) is None


def test_bind_hybrid_uses_in_memory_jobs_without_supabase_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mapping Hybrid injects version canonicals and never opens a DSN."""

    captured: dict[str, object] = {}

    class _FakeRetriever:
        """Capture HybridRetriever construction and retrieve kwargs."""

        def __init__(self, **kwargs: object) -> None:
            """Capture HybridRetriever constructor kwargs."""

            captured["init"] = kwargs

        def retrieve(self, **kwargs: object) -> HybridRunResult:
            """Return empty ranked IDs after recording retrieve kwargs."""

            captured["retrieve"] = kwargs
            return _empty_hybrid_result()

    passage = CanonicalPassage(
        chunk_id=uuid4(),
        version_id=_VERSION,
        document_id=uuid4(),
        chunk_index=0,
        raw_text="canonical mapping passage text",
        content_hash=content_hash("canonical mapping passage text"),
        language="en",
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_hybrid.HybridRetriever",
        _FakeRetriever,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_hybrid.load_mapping_caller",
        _load_mapping_caller,
    )

    def _load_canonicals(
        _connection: psycopg.Connection, *, version_id: UUID
    ) -> tuple[CanonicalPassage, ...]:
        """Return the in-memory canonical for this version-scoped retrieve."""

        del version_id
        return (passage,)

    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_canonical_passages",
        _load_canonicals,
    )
    callbacks = bind_mapping_support(_unused_connection(), WorkerSettings())
    assert callbacks is not None
    result = callbacks.hybrid_retrieve("unresolved vendor text", _VERSION)
    assert result.ranked_ids == ()
    init = captured["init"]
    assert isinstance(init, dict)
    init_map = _object_map(captured["init"])
    assert init_map.get("rerank") is None
    assert init_map.get("supabase_dsn") is None
    retrieve = captured["retrieve"]
    assert isinstance(retrieve, dict)
    retrieve_map = _object_map(captured["retrieve"])
    assert retrieve_map.get("restrict_version_id") == _VERSION
    jobs = retrieve_map.get("channel_jobs")
    assert isinstance(jobs, dict)
    assert set(_object_map(retrieve_map.get("channel_jobs"))) == {
        "dense",
        "bm25",
        "term",
    }


def test_graph_index_service_injects_mapping_support() -> None:
    """Default mapper receives worker Hybrid and support-rerank callbacks."""

    def hybrid(_query: str, _version_id: UUID) -> HybridRunResult:
        """Stand-in Hybrid retrieve."""

        return _empty_hybrid_result()

    def rerank(
        _query: str, _passages: tuple[RerankPassage, ...]
    ) -> tuple[RerankRanking, ...]:
        """Stand-in support rerank."""

        return ()

    support = MappingSupportCallbacks(
        hybrid_retrieve=hybrid,
        support_rerank=rerank,
    )
    service = _index_service(mapping_support=support)
    assert _mapper_attr(service, "_hybrid_retrieve") is hybrid
    assert _mapper_attr(service, "_support_rerank") is rerank


def test_graph_index_service_defaults_to_no_mapping_hybrid() -> None:
    """Omitted callbacks leave unresolved chunks unmapped (fail closed)."""

    service = _index_service()
    assert _mapper_attr(service, "_hybrid_retrieve") is None
    assert _mapper_attr(service, "_support_rerank") is None


def test_graph_runner_binds_mapping_support_without_map_tables() -> None:
    """Worker loop injects jobs callbacks and never names map tables."""

    text = (
        _REPO_ROOT / "apps" / "worker" / "src" / "smart_rag_worker" / "graph_runner.py"
    ).read_text(encoding="utf-8")
    assert "bind_mapping_support" in text
    assert "mapping_support=" in text
    assert "HybridRetriever" not in text
    assert "lightrag_source_map" not in text
    assert "lightrag_chunk_map" not in text
    assert "graph_evidence_map" not in text
