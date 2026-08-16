"""Tests for worker mapping Hybrid/rerank callback binding."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from smart_rag_core.ingestion.chunking.normalize import content_hash
from smart_rag_core.jobs.graph_index_service import GraphIndexService
from smart_rag_core.jobs.graph_mapping_hybrid import (
    MappingSupportCallbacks,
    bind_mapping_support,
)
from smart_rag_core.retrieval.coverage import CoverageSignal, HybridCoverage
from smart_rag_core.retrieval.graph_mapping import CanonicalPassage
from smart_rag_core.retrieval.hybrid_run import HybridRunResult
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
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


def test_mapping_rerank_prompt_matches_frozen_hash() -> None:
    """Mapping support rerank uses the pinned Hybrid rerank prompt file."""

    digest = hashlib.sha256(_RERANK_PROMPT.read_bytes()).hexdigest()
    assert digest == RERANK_PROMPT_SHA256
    assert _RERANK_PROMPT.is_file()


def test_bind_mapping_support_in_mock_mode() -> None:
    """Mock-mode settings produce mapping callbacks without a provider key."""

    settings = WorkerSettings()
    assert settings.mock_model_mode is True
    callbacks = bind_mapping_support(_UnusedConnection(), settings)
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
    assert bind_mapping_support(_UnusedConnection(), WorkerSettings()) is None


def test_bind_hybrid_uses_in_memory_jobs_without_supabase_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mapping Hybrid injects version canonicals and never opens a DSN."""

    captured: dict[str, object] = {}

    class _FakeRetriever:
        """Capture HybridRetriever construction and retrieve kwargs."""

        def __init__(self, **kwargs: object) -> None:
            captured["init"] = kwargs

        def retrieve(self, **kwargs: object) -> HybridRunResult:
            """Return empty ranked IDs after recording retrieve kwargs."""

            captured["retrieve"] = kwargs
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
        lambda _connection, *, version_id: _CALLER,
    )
    monkeypatch.setattr(
        "smart_rag_core.jobs.graph_mapping_persist.load_canonical_passages",
        lambda _connection, *, version_id: (passage,),
    )
    callbacks = bind_mapping_support(_UnusedConnection(), WorkerSettings())
    assert callbacks is not None
    result = callbacks.hybrid_retrieve("unresolved vendor text", _VERSION)
    assert result.ranked_ids == ()
    init = captured["init"]
    assert isinstance(init, dict)
    assert init.get("rerank") is None
    assert init.get("supabase_dsn") is None
    retrieve = captured["retrieve"]
    assert isinstance(retrieve, dict)
    assert retrieve.get("restrict_version_id") == _VERSION
    jobs = retrieve.get("channel_jobs")
    assert isinstance(jobs, dict)
    assert set(jobs) == {"dense", "bm25", "term"}


def test_graph_index_service_injects_mapping_support() -> None:
    """Default mapper receives worker Hybrid and support-rerank callbacks."""

    def hybrid(_query: str, _version_id: UUID) -> object:
        """Stand-in Hybrid retrieve."""

        return None

    def rerank(_query: str, _passages: tuple[object, ...]) -> tuple[object, ...]:
        """Stand-in support rerank."""

        return ()

    support = MappingSupportCallbacks(
        hybrid_retrieve=hybrid,
        support_rerank=rerank,
    )
    service = GraphIndexService(
        SimpleNamespace(),
        indexer=SimpleNamespace(adapter=object()),
        writer=SimpleNamespace(),
        repository=SimpleNamespace(),
        mapping_support=support,
    )
    assert service._mapper._hybrid_retrieve is hybrid
    assert service._mapper._support_rerank is rerank


def test_graph_index_service_defaults_to_no_mapping_hybrid() -> None:
    """Omitted callbacks leave unresolved chunks unmapped (fail closed)."""

    service = GraphIndexService(
        SimpleNamespace(),
        indexer=SimpleNamespace(adapter=object()),
        writer=SimpleNamespace(),
        repository=SimpleNamespace(),
    )
    assert service._mapper._hybrid_retrieve is None
    assert service._mapper._support_rerank is None


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


class _UnusedConnection:
    """Stand-in connection; bind does not query until callbacks run."""
