"""Embedding batch orchestration with ledger-backed idempotency."""

from __future__ import annotations

import asyncio
import json
import math
import queue
import threading
from collections.abc import Callable
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
    DEFAULT_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_MAX_INPUTS,
)
from smart_rag_core.jobs.admission import JobAdmissionService
from smart_rag_core.security.external_processing import (
    ExternalProcessingDecisionInput,
    decide_external_processing,
)

EmbeddingProgressCallback = Callable[[str, dict[str, int]], None]


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

    def embed_version(
        self,
        batch: EmbeddingBatchInput,
        *,
        progress: EmbeddingProgressCallback | None = None,
    ) -> EmbeddingBatchResult:
        """Embed representative chunks after governance and ledger reservation.

        Args:
            batch: Version-scoped embedding inputs and governance evidence.
            progress: Optional count-only callback invoked once per gateway
                batch (``embed_batch`` with ``batch_index`` / ``batch_count`` /
                ``chunks``). Callers must not pass source text.

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
        completed = self._completed_ledger_vectors(
            version_id=batch.version_id,
            operation_key=batch.operation_key,
            chunk_set_hash=chunk_set_hash,
            expected_count=len(representatives),
        )
        if completed is not None:
            ledger_id, stored_vectors = completed
            contextual_inputs = [
                build_contextual_embedding_text(
                    document_title=batch.document_title,
                    chunk=chunk,
                )
                for chunk in representatives
            ]
            embedded = _embedded_from_stored_vectors(
                representatives, contextual_inputs, stored_vectors
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
                provider_request_id="ledger_replay",
                actual_cost_usd=Decimal("0"),
                attempt_count=attempt_count,
            )

        ledger_id = self._record_ledger(
            version_id=batch.version_id,
            operation_key=batch.operation_key,
            policy_hash=policy_hash,
            input_count=len(representatives),
            status="pending",
            reserved_usd=batch.estimated_cost_usd,
            result_ref={"chunk_set_hash": chunk_set_hash},
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
            response = _embed_inputs_in_batches(
                self._gateway,
                operation_key=batch.operation_key,
                contextual_inputs=tuple(contextual_inputs),
                progress=progress,
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
                "chunk_set_hash": chunk_set_hash,
                "vectors": [list(vector) for vector in response.vectors],
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

    def _completed_ledger_vectors(
        self,
        *,
        version_id: UUID,
        operation_key: str,
        chunk_set_hash: str,
        expected_count: int,
    ) -> tuple[UUID, tuple[tuple[float, ...], ...]] | None:
        """Return stored vectors for a completed matching ledger row.

        Args:
            version_id: Canonical document version.
            operation_key: Idempotent embedding operation key.
            chunk_set_hash: Hash of the current representative set.
            expected_count: Number of representative chunks.

        Returns:
            Ledger id and vectors when a completed row matches the hash, or
            ``None`` when no completed matching row exists (caller embeds).

        Raises:
            EmbeddingGateError: When the ledger is ``completed`` for this
                operation and hash but vectors are missing or the wrong size.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, status, result_ref
                FROM app.embedding_operation_ledger
                WHERE version_id = %s AND operation_key = %s
                """,
                (version_id, operation_key),
            )
            row = cursor.fetchone()
        if row is None or len(row) < 3 or row[0] is None:
            return None
        ledger_id = UUID(str(row[0]))
        status = str(row[1])
        raw_ref: object = row[2]
        if isinstance(raw_ref, str):
            try:
                raw_ref = json.loads(raw_ref)
            except json.JSONDecodeError:
                raw_ref = {}
        result_ref = raw_ref if isinstance(raw_ref, dict) else {}
        stored_hash = result_ref.get("chunk_set_hash")
        if status != "completed" or stored_hash != chunk_set_hash:
            return None
        raw_vectors = result_ref.get("vectors")
        if not isinstance(raw_vectors, list) or not raw_vectors:
            raise EmbeddingGateError("embedding_ledger_vectors_missing")
        if len(raw_vectors) != expected_count:
            raise EmbeddingGateError("embedding_ledger_vectors_missing")
        parsed: list[tuple[float, ...]] = []
        for vector in raw_vectors:
            if not isinstance(vector, list) or not vector:
                raise EmbeddingGateError("embedding_ledger_vectors_missing")
            parsed.append(tuple(float(value) for value in vector))
        return ledger_id, tuple(parsed)


def _embed_inputs_in_batches(
    gateway: EmbeddingGateway,
    *,
    operation_key: str,
    contextual_inputs: tuple[str, ...],
    progress: EmbeddingProgressCallback | None,
) -> Any:
    """Embed texts in ``DEFAULT_EMBEDDING_BATCH_SIZE`` gateway calls.

    Args:
        gateway: Shared embedding gateway.
        operation_key: Durable operation key copied onto each request.
        contextual_inputs: Representative contextual strings, never logged.
        progress: Optional count-only callback.

    Returns:
        Combined gateway response with concatenated vectors and summed cost.

    Raises:
        TimeoutError: When a provider client times out.
        EmbeddingGateError: When a batch returns the wrong vector count.
    """

    from smart_rag_core.gateways.embedding import EmbeddingResponse

    batch_size = DEFAULT_EMBEDDING_BATCH_SIZE
    batch_count = math.ceil(len(contextual_inputs) / batch_size)
    vectors: list[tuple[float, ...]] = []
    total_cost = Decimal("0")
    last_response: EmbeddingResponse | None = None
    for batch_index, start in enumerate(
        range(0, len(contextual_inputs), batch_size),
        start=1,
    ):
        chunk_inputs = contextual_inputs[start : start + batch_size]
        if progress is not None:
            progress(
                "embed_batch",
                {
                    "batch_index": batch_index,
                    "batch_count": batch_count,
                    "chunks": len(chunk_inputs),
                },
            )
        response = _run_embed_coroutine(
            lambda inputs=chunk_inputs: gateway.embed(
                EmbeddingRequest(
                    operation_key=operation_key,
                    inputs=inputs,
                    model=EMBEDDING_MODEL,
                    dimensions=EMBEDDING_DIMENSIONS,
                )
            )
        )
        if len(response.vectors) != len(chunk_inputs):
            raise EmbeddingGateError("embedding_vector_count_mismatch")
        vectors.extend(response.vectors)
        total_cost += response.estimated_cost_usd
        last_response = response
    if last_response is None:
        raise EmbeddingGateError("embedding_batch_empty")
    return last_response.model_copy(
        update={
            "vectors": tuple(vectors),
            "estimated_cost_usd": total_cost,
        }
    )


def _run_embed_coroutine(factory: Callable[[], Any]) -> Any:
    """Run one embedding coroutine off a running event loop when needed.

    ``asyncio.run`` cannot be called from a running loop. Worker threads that
    already have a loop execute the provider call on a dedicated thread with
    its own loop. The coroutine is created on that thread via ``factory``.

    Args:
        factory: Zero-argument callable that returns the embed coroutine.

    Returns:
        Gateway embed response.

    Raises:
        TimeoutError: When the provider client times out.
        Exception: Provider or gateway failures are propagated.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    outcome: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def _worker() -> None:
        """Create and run the embed coroutine on this thread's loop."""

        try:
            outcome.put(("ok", asyncio.run(factory())))
        except BaseException as exc:
            outcome.put(("err", exc))

    thread = threading.Thread(
        target=_worker,
        name="embedding-gateway-loop",
        daemon=True,
    )
    thread.start()
    thread.join()
    kind, payload = outcome.get()
    if kind == "err":
        if isinstance(payload, BaseException):
            raise payload
        raise RuntimeError(str(payload))
    return payload


def _embedded_from_stored_vectors(
    representatives: tuple[CanonicalChunk, ...],
    contextual_inputs: list[str],
    stored_vectors: tuple[tuple[float, ...], ...],
) -> list[EmbeddedChunk]:
    """Rebuild embedded chunks from a completed ledger payload.

    Args:
        representatives: Search-representative chunks in embed order.
        contextual_inputs: Contextual texts aligned with ``representatives``.
        stored_vectors: Vectors persisted on the completed ledger row.

    Returns:
        Embedded chunk list.

    Raises:
        EmbeddingGateError: When a stored vector is the wrong size or
            non-finite.
    """

    embedded: list[EmbeddedChunk] = []
    for chunk, contextual_text, vector in zip(
        representatives,
        contextual_inputs,
        stored_vectors,
        strict=True,
    ):
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise EmbeddingGateError("embedding_ledger_vectors_missing")
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingGateError("embedding_ledger_vectors_missing")
        embedded.append(
            EmbeddedChunk(
                chunk=chunk,
                contextual_text=contextual_text,
                embedding=list(vector),
            )
        )
    return embedded


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
