"""Unit tests for governed mock embeddings."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from smart_rag_core.gateways.embedding import (
    EmbeddingGateway,
    EmbeddingRequest,
    MockEmbeddingAdapter,
)
from smart_rag_core.ingestion.chunking.types import (
    CanonicalChunk,
    ChunkKind,
    ChunkProvenance,
)
from smart_rag_core.ingestion.embeddings.mock_vectors import mock_embedding_vector
from smart_rag_core.ingestion.embeddings.policy import EMBEDDING_DIMENSIONS
from smart_rag_core.ingestion.embeddings.service import (
    EmbeddingBatchInput,
    EmbeddingService,
)
from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    ExternalProcessingDecisionInput,
)


def _chunk(text: str) -> CanonicalChunk:
    return CanonicalChunk(
        chunk_id=uuid4(),
        chunk_index=0,
        kind=ChunkKind.PASSAGE,
        raw_text=text,
        token_count=10,
        provenance=ChunkProvenance(
            parser_version="parser_v1",
            cleaning_version="cleaning_v1",
            chunking_version="chunking_v1",
            tokenizer_version="cl100k_base_v1",
            dedup_policy_version="dedup_v1",
            normalized_content_hash="abc123",
        ),
    )


def test_mock_embedding_is_deterministic_and_finite() -> None:
    """Mock vectors are stable, sized, and finite."""

    first = mock_embedding_vector("annual leave policy")
    second = mock_embedding_vector("annual leave policy")
    assert len(first) == EMBEDDING_DIMENSIONS
    assert first == second
    assert all(abs(value) <= 1.0 for value in first)


def test_embedding_gateway_replay_is_stable() -> None:
    """Gateway replay returns identical vectors and request IDs for same inputs."""

    async def _run() -> None:
        gateway = EmbeddingGateway(MockEmbeddingAdapter(fixture_id="test"))
        request = EmbeddingRequest(
            operation_key="op-1",
            inputs=("annual leave policy", "warehouse safety"),
            model="text-embedding-3-large",
            dimensions=EMBEDDING_DIMENSIONS,
        )
        first = await gateway.embed(request)
        second = await gateway.embed(request)
        assert first.vectors == second.vectors
        assert first.provider_request_id == second.provider_request_id

    asyncio.run(_run())


def test_embedding_service_denies_real_company_without_provider_verification() -> None:
    """Governance gate blocks real company content when provider settings unverified."""

    gateway = EmbeddingGateway(MockEmbeddingAdapter(fixture_id="test"))

    class _Connection:
        def cursor(self):
            raise AssertionError("database should not be reached")

    service = EmbeddingService(_Connection(), gateway=gateway)  # type: ignore[arg-type]
    batch = EmbeddingBatchInput(
        version_id=uuid4(),
        document_title="Policy",
        chunks=(_chunk("annual leave policy"),),
        chunking_config_hash="cfg",
        operation_key="embed:1",
        governance=ExternalProcessingDecisionInput(
            attestation_present=True,
            category=CategoryDisposition.ALLOWED,
            review_approved=True,
            scan_evidence_current=True,
            provider_settings_verified=False,
            policy_version_matches=True,
            content_class=ContentClass.REAL_COMPANY,
        ),
    )
    with pytest.raises(Exception, match="unverified_provider_settings"):
        service.embed_version(batch)


def test_embedding_gateway_sync_wrapper() -> None:
    """Synchronous ingestion nodes can await gateway batches via asyncio.run."""

    gateway = EmbeddingGateway(MockEmbeddingAdapter(fixture_id="test"))
    response = asyncio.run(
        gateway.embed(
            EmbeddingRequest(
                operation_key="sync",
                inputs=("probe",),
                model="text-embedding-3-large",
                dimensions=EMBEDDING_DIMENSIONS,
            )
        )
    )
    assert len(response.vectors) == 1
    assert response.estimated_cost_usd == Decimal("0")
