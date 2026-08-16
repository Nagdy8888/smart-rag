"""Embedding batch orchestration with ledger-backed idempotency."""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from smart_rag_core.gateways.embedding import EmbeddingGateway, EmbeddingRequest
from smart_rag_core.ingestion.chunking.types import CanonicalChunk
from smart_rag_core.ingestion.embeddings.contextual import (
    build_contextual_embedding_text,
)
from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    embedding_policy_hash,
)
from smart_rag_core.ingestion.limits import (
    DEFAULT_EMBEDDING_MAX_INPUTS,
)
from smart_rag_core.jobs.admission import JobAdmissionService
from smart_rag_core.security.external_processing import (
    ExternalProcessingDecisionInput,
    decide_external_processing,
)


class EmbeddingGateError(RuntimeError):
    """Report governance, budget, or provider failures before canonical write."""


@dataclass(frozen=True, slots=True)
class EmbeddingBatchInput:
    """Inputs required to embed one version's representative chunks."""

    version_id: UUID
    document_title: str
    chunks: tuple[CanonicalChunk, ...]
    chunking_config_hash: str
    operation_key: str
    governance: ExternalProcessingDecisionInput
    estimated_cost_usd: Decimal = Decimal("0.05")


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """One chunk with contextual text and embedding vector."""

    chunk: CanonicalChunk
    contextual_text: str
    embedding: list[float]


@dataclass(frozen=True, slots=True)
class EmbeddingBatchResult:
    """Closed embedding batch output."""

    version_id: UUID
    policy_hash: str
    chunk_set_hash: str
    embedded: tuple[EmbeddedChunk, ...]
    ledger_id: UUID
    provider_request_id: str
    actual_cost_usd: Decimal
    attempt_count: int


class EmbeddingService:
    """Governed embedding batches with durable ledger and budget reservation."""

    def __init__(
        self,
        connection: psycopg.Connection,
        *,
        gateway: EmbeddingGateway,
        admission: JobAdmissionService | None = None,
    ) -> None:
        """Bind Postgres connection and shared embedding gateway."""

        self._connection = connection
        self._gateway = gateway
        self._admission = admission or JobAdmissionService(connection)

    def embed_version(self, batch: EmbeddingBatchInput) -> EmbeddingBatchResult:
        """Embed representative chunks after governance and ledger reservation.

        Args:
            batch: Version-scoped embedding inputs and governance evidence.

        Returns:
            Embedded chunks with stable ledger metadata.

        Raises:
            EmbeddingGateError: When governance denies external processing or
                provider output is invalid.
        """

        decision = decide_external_processing(batch.governance)
        if not decision.allowed:
            raise EmbeddingGateError(decision.reason_code)

        policy_hash = embedding_policy_hash(
            chunking_config_hash=batch.chunking_config_hash
        )
        representatives = tuple(
            chunk for chunk in batch.chunks if chunk.is_search_representative
        )
        if not representatives:
            raise EmbeddingGateError("no_search_representatives")

        if len(representatives) > DEFAULT_EMBEDDING_MAX_INPUTS:
            raise EmbeddingGateError("embedding_batch_over_limit")

        chunk_set_hash = _chunk_set_hash(representatives)
        ledger_id = self._record_ledger(
            version_id=batch.version_id,
            operation_key=batch.operation_key,
            policy_hash=policy_hash,
            input_count=len(representatives),
            status="pending",
            reserved_usd=batch.estimated_cost_usd,
        )

        contextual_inputs = [
            build_contextual_embedding_text(
                document_title=batch.document_title,
                chunk=chunk,
            )
            for chunk in representatives
        ]

        self._admission.assert_can_enqueue_ingestion(
            estimated_size_bytes=0,
            estimated_cost_usd=batch.estimated_cost_usd,
        )

        try:
            response = asyncio.run(
                self._gateway.embed(
                    EmbeddingRequest(
                        operation_key=batch.operation_key,
                        inputs=tuple(contextual_inputs),
                        model=EMBEDDING_MODEL,
                        dimensions=EMBEDDING_DIMENSIONS,
                    )
                )
            )
        except TimeoutError as exc:
            self._record_ledger(
                version_id=batch.version_id,
                operation_key=batch.operation_key,
                policy_hash=policy_hash,
                input_count=len(representatives),
                status="failed",
                result_ref={"reason": "timeout_after_provider"},
            )
            raise EmbeddingGateError("embedding_timeout_after_provider") from exc

        if len(response.vectors) != len(representatives):
            self._record_ledger(
                version_id=batch.version_id,
                operation_key=batch.operation_key,
                policy_hash=policy_hash,
                input_count=len(representatives),
                status="failed",
                reserved_usd=batch.estimated_cost_usd,
                result_ref={"error": "vector_count_mismatch"},
            )
            raise EmbeddingGateError("embedding_vector_count_mismatch")

        embedded: list[EmbeddedChunk] = []
        for chunk, contextual_text, vector in zip(
            representatives,
            contextual_inputs,
            response.vectors,
            strict=True,
        ):
            if len(vector) != EMBEDDING_DIMENSIONS:
                raise EmbeddingGateError("embedding_dimension_mismatch")
            if not all(math.isfinite(value) for value in vector):
                raise EmbeddingGateError("embedding_non_finite")
            embedded.append(
                EmbeddedChunk(
                    chunk=chunk,
                    contextual_text=contextual_text,
                    embedding=list(vector),
                )
            )

        self._record_ledger(
            version_id=batch.version_id,
            operation_key=batch.operation_key,
            policy_hash=policy_hash,
            input_count=len(representatives),
            status="completed",
            provider_request_id=response.provider_request_id,
            reserved_usd=batch.estimated_cost_usd,
            actual_usd=response.estimated_cost_usd,
            result_ref={
                "mode": response.mode,
                "fixture_provenance": response.fixture_provenance,
            },
        )

        attempt_count = self._ledger_attempt_count(
            batch.version_id, batch.operation_key
        )
        return EmbeddingBatchResult(
            version_id=batch.version_id,
            policy_hash=policy_hash,
            chunk_set_hash=chunk_set_hash,
            embedded=tuple(embedded),
            ledger_id=ledger_id,
            provider_request_id=response.provider_request_id,
            actual_cost_usd=response.estimated_cost_usd,
            attempt_count=attempt_count,
        )

    def _record_ledger(
        self,
        *,
        version_id: UUID,
        operation_key: str,
        policy_hash: str,
        input_count: int,
        status: str,
        provider_request_id: str | None = None,
        reserved_usd: Decimal | None = None,
        actual_usd: Decimal | None = None,
        result_ref: dict[str, Any] | None = None,
    ) -> UUID:
        """Insert one embedding ledger row and return its identifier.

        Args:
            version_id: Canonical document version.
            operation_key: Idempotent embedding operation key.
            policy_hash: Embedding policy hash recorded on the ledger.
            input_count: Number of texts in this attempt.
            status: Ledger status written by ``record_embedding_ledger``.
            provider_request_id: Optional provider request id.
            reserved_usd: Optional reserved cost.
            actual_usd: Optional settled cost.
            result_ref: Optional JSON result payload.

        Returns:
            Ledger row identifier.

        Raises:
            EmbeddingGateError: When the ledger RPC returns no id.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.record_embedding_ledger(
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                """,
                (
                    version_id,
                    operation_key,
                    policy_hash,
                    EMBEDDING_MODEL,
                    EMBEDDING_DIMENSIONS,
                    input_count,
                    status,
                    provider_request_id,
                    reserved_usd,
                    actual_usd,
                    json.dumps(result_ref or {}),
                ),
            )
            row = cursor.fetchone()
            if row is None or row[0] is None:
                raise EmbeddingGateError("embedding_ledger_write_failed")
            return UUID(str(row[0]))

    def _ledger_attempt_count(self, version_id: UUID, operation_key: str) -> int:
        """Return the stored attempt count for one embedding operation.

        Args:
            version_id: Canonical document version.
            operation_key: Idempotent embedding operation key.

        Returns:
            Attempt count, or ``1`` when no ledger row exists yet.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT attempt_count
                FROM app.embedding_operation_ledger
                WHERE version_id = %s AND operation_key = %s
                """,
                (version_id, operation_key),
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 1


def _chunk_set_hash(chunks: tuple[CanonicalChunk, ...]) -> str:
    """Hash stable chunk IDs and normalized content for cross-system verification."""

    import hashlib

    payload = [
        {
            "chunk_id": str(chunk.chunk_id),
            "content_hash": chunk.provenance.normalized_content_hash,
            "chunk_index": chunk.chunk_index,
        }
        for chunk in sorted(chunks, key=lambda item: item.chunk_index)
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
