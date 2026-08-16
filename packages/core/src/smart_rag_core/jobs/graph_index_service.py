"""Process one claimed LightRAG job under the single-writer guard.

Work runs outside the claim transaction. Vendor ``processed`` never writes
mapping tables or public Graph Ready by itself. After a successful index the
mapper runs in this service; workspace ``updating`` becomes ``active`` only
when maps verify and the pointer already names this workspace.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, TypeAlias
from uuid import UUID

import psycopg
from pydantic import BaseModel, ConfigDict

from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.jobs.exceptions import (
    GraphMappingError,
    GraphWriterLostError,
    JobAdmissionError,
    JobLeaseError,
)
from smart_rag_core.jobs.graph_mapping_service import GraphMappingService
from smart_rag_core.jobs.graph_source_text import (
    GraphSourceTextError,
    load_version_graph_text,
)
from smart_rag_core.jobs.graph_writer import (
    GraphWriterGuard,
    allowed_index_from_states,
)
from smart_rag_core.jobs.lightrag_repository import LightragIndexJobRepository
from smart_rag_core.jobs.limits import (
    DEFAULT_GRAPH_INDEX_ESTIMATE_USD,
    DEFAULT_GRAPH_MAINTENANCE_ESTIMATE_USD,
    GRAPH_PIPELINE_VERSION,
    LIGHTRAG_HANDOFF_VERSION,
)
from smart_rag_core.retrieval.graph import (
    LIGHTRAG_PINNED_VERSION,
    opaque_graph_source_basename,
)
from smart_rag_core.retrieval.lightrag_indexer import (
    GraphIndexerError,
    LightRagGraphIndexer,
)
from smart_rag_core.schema.enums import (
    DocumentStatus,
    GraphWorkspaceState,
    JobErrorCategory,
    LightragJobOperation,
)

GraphJobOutcomeKind: TypeAlias = Literal["completed", "failed", "quarantined"]

GRAPH_VALIDATION_REASONS = {
    "hybrid_not_ready",
    "not_graph_eligible",
    "content_hash_mismatch",
    "chunk_set_hash_mismatch",
    "lightrag_pin_mismatch",
    "pipeline_version_mismatch",
    "embedding_pin_mismatch",
    "workspace_generation_mismatch",
    "version_missing",
    "job_missing_version",
    "version_text_empty",
    "graph_budget_exhausted",
    "invalid_estimated_cost",
}


class GraphJobOutcome(BaseModel):
    """Result of one graph writer attempt.

    Attributes:
        kind: Terminal handler result.
        error_category: Set when ``kind`` is not ``completed``.
        last_error: Bounded machine-readable detail.
        vendor_status: Vendor document status when known.
        reservation_id: Graph budget reservation when created.
        reservation_kind: ``graph_index`` or ``graph_maintenance``.
        workspace_state: Workspace state after the attempt.
        maps_verified: True only when Packet 4 mapping gates passed.
        mapping_reason: Mapping failure reason when maps are not verified.
    """

    model_config = ConfigDict(frozen=True)

    kind: GraphJobOutcomeKind
    error_category: JobErrorCategory | None = None
    last_error: str = ""
    vendor_status: str | None = None
    reservation_id: UUID | None = None
    reservation_kind: str | None = None
    workspace_state: str | None = None
    maps_verified: bool = False
    mapping_reason: str = ""


class GraphIndexService:
    """Revalidate eligibility, mutate LightRAG, and persist workspace state."""

    def __init__(
        self,
        connection: psycopg.Connection,
        *,
        indexer: LightRagGraphIndexer,
        writer: GraphWriterGuard,
        repository: LightragIndexJobRepository,
        mapper: GraphMappingService | None = None,
    ) -> None:
        """Bind application connection, indexer, and writer guard.

        Args:
            connection: ``app_worker`` connection for short transactions.
            indexer: Concrete graph indexer.
            writer: Occupied writer guard holding the session lock.
            repository: LightRAG job repository on the same connection.
            mapper: Optional mapping service. Defaults to one bound to the
                indexer adapter. Mapping runs after vendor terminal success
                and before job complete.
        """

        self._connection = connection
        self._indexer = indexer
        self._writer = writer
        self._repository = repository
        self._mapper = mapper or GraphMappingService(
            connection,
            vendor_reader=indexer.adapter,
            writer=writer,
        )

    async def process_claimed_job(
        self,
        job: dict[str, Any],
        *,
        job_lease_token: str,
    ) -> GraphJobOutcome:
        """Process one claimed job without holding a DB transaction.

        Args:
            job: Claimed ``lightrag_index_jobs`` row mapping.
            job_lease_token: Job lease token from claim.

        Returns:
            Outcome used by the worker to complete or fail the job.

        Side Effects:
            May call LightRAG insert/delete, update workspace state, and
            reserve graph budgets. Commits short status transactions only.
        """

        job_id = UUID(str(job["id"]))
        operation = LightragJobOperation(str(job["operation"]))
        payload = dict(job.get("payload_ref") or {})
        reservation_kind = (
            "graph_index"
            if operation is LightragJobOperation.INDEX
            else "graph_maintenance"
        )
        estimate = (
            Decimal(str(DEFAULT_GRAPH_INDEX_ESTIMATE_USD))
            if reservation_kind == "graph_index"
            else Decimal(str(DEFAULT_GRAPH_MAINTENANCE_ESTIMATE_USD))
        )
        reservation_id: UUID | None = None
        try:
            self._writer.verify_lock_and_lease(
                job_id=job_id,
                job_lease_token=job_lease_token,
            )
            self._connection.commit()
            if payload.get("reconciliation") is True:
                return await self._reconcile(
                    job_id=job_id,
                    job_lease_token=job_lease_token,
                    payload=payload,
                )
            if operation is LightragJobOperation.REBUILD:
                return self._isolate_rebuild_workspace(
                    job_id=job_id,
                    job_lease_token=job_lease_token,
                )
            reservation_id = self._reserve(reservation_kind, estimate)
            self._connection.commit()
            if operation is LightragJobOperation.INDEX:
                outcome = await self._index(
                    job=job,
                    payload=payload,
                    job_id=job_id,
                    job_lease_token=job_lease_token,
                    reservation_id=reservation_id,
                )
            else:
                outcome = await self._delete(
                    job=job,
                    job_id=job_id,
                    job_lease_token=job_lease_token,
                    reservation_id=reservation_id,
                    reservation_kind=reservation_kind,
                )
            return outcome
        except GraphWriterLostError as exc:
            return self._quarantine_outcome(
                job_id=job_id,
                reason=exc.reason,
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
            )
        except JobAdmissionError as exc:
            if reservation_id is not None:
                self._repository.admission.release_graph_reservation(
                    reservation_id,
                    reservation_kind=reservation_kind,
                )
                self._connection.commit()
            return GraphJobOutcome(
                kind="failed",
                error_category=JobErrorCategory.BUDGET,
                last_error=exc.reason,
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
            )
        except (GraphIndexerError, GraphSourceTextError) as exc:
            reason = getattr(exc, "reason", str(exc))
            if reason in GRAPH_VALIDATION_REASONS or reason.startswith("graph_budget"):
                if reservation_id is not None:
                    self._repository.admission.release_graph_reservation(
                        reservation_id,
                        reservation_kind=reservation_kind,
                    )
                    self._connection.commit()
                return GraphJobOutcome(
                    kind="failed",
                    error_category=JobErrorCategory.VALIDATION,
                    last_error=reason[:4000],
                    reservation_id=reservation_id,
                    reservation_kind=reservation_kind,
                )
            return self._quarantine_outcome(
                job_id=job_id,
                reason=reason[:512],
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
            )
        except JobLeaseError as exc:
            return self._quarantine_outcome(
                job_id=job_id,
                reason=str(exc)[:512],
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
            )

    def _reserve(self, reservation_kind: str, estimate: Decimal) -> UUID:
        return self._repository.admission.create_graph_budget_reservation(
            reservation_kind=reservation_kind,
            estimated_cost_usd=estimate,
        )

    async def _index(
        self,
        *,
        job: dict[str, Any],
        payload: dict[str, Any],
        job_id: UUID,
        job_lease_token: str,
        reservation_id: UUID,
    ) -> GraphJobOutcome:
        document_id, version_id = _require_ids(job)
        self._revalidate_index_eligibility(
            document_id=document_id,
            version_id=version_id,
            payload=payload,
        )
        self._writer.attach_default_pointer_if_null()
        self._writer.transition_state(
            from_states=allowed_index_from_states(),
            to_state=GraphWorkspaceState.UPDATING,
        )
        self._connection.commit()
        self._writer.verify_lock_and_lease(
            job_id=job_id,
            job_lease_token=job_lease_token,
        )
        self._connection.commit()
        text = load_version_graph_text(self._connection, version_id=version_id)
        self._connection.commit()
        identity = str(version_id)
        result = await self._indexer.enqueue_insert(
            document_id=identity,
            text=text,
            source_token=opaque_graph_source_basename(identity),
        )
        self._writer.verify_lock_and_lease(
            job_id=job_id,
            job_lease_token=job_lease_token,
        )
        self._assert_version_still_pending(version_id)
        maps_verified = False
        mapping_reason = ""
        workspace_state = GraphWorkspaceState.UPDATING.value
        try:
            mapping = await self._mapper.map_after_vendor_success(
                document_id=document_id,
                version_id=version_id,
            )
            maps_verified = mapping.maps_verified
            mapping_reason = mapping.reason
            workspace_state = mapping.workspace_state
        except GraphMappingError as exc:
            maps_verified = False
            mapping_reason = exc.reason
            workspace_state = GraphWorkspaceState.UPDATING.value
        if workspace_state != GraphWorkspaceState.ACTIVE.value:
            self._writer.transition_state(
                from_states=(GraphWorkspaceState.UPDATING,),
                to_state=GraphWorkspaceState.UPDATING,
                snapshot={
                    "last_vendor_status": result.status,
                    "last_indexed_version_id": identity,
                    "maps_verified": maps_verified,
                    "mapping_reason": mapping_reason,
                },
            )
        self._repository.admission.true_up_graph_reservation(
            reservation_id,
            reservation_kind="graph_index",
            actual_cost_usd=_actual_from_callbacks(self._indexer, estimate_floor=True),
        )
        self._connection.commit()
        return GraphJobOutcome(
            kind="completed",
            vendor_status=result.status,
            reservation_id=reservation_id,
            reservation_kind="graph_index",
            workspace_state=workspace_state,
            maps_verified=maps_verified,
            mapping_reason=mapping_reason,
        )

    async def _delete(
        self,
        *,
        job: dict[str, Any],
        job_id: UUID,
        job_lease_token: str,
        reservation_id: UUID,
        reservation_kind: str,
    ) -> GraphJobOutcome:
        _document_id, version_id = _require_ids(job)
        self._writer.verify_lock_and_lease(
            job_id=job_id,
            job_lease_token=job_lease_token,
        )
        self._connection.commit()
        result = await self._indexer.delete_document(document_id=str(version_id))
        if result.status == "not_allowed":
            raise GraphIndexerError("vendor_delete_not_allowed")
        self._writer.verify_lock_and_lease(
            job_id=job_id,
            job_lease_token=job_lease_token,
        )
        self._writer.transition_state(
            from_states=(
                GraphWorkspaceState.ACTIVE,
                GraphWorkspaceState.UPDATING,
                GraphWorkspaceState.FILTERED_DIRTY,
                GraphWorkspaceState.BUILDING,
            ),
            to_state=GraphWorkspaceState.FILTERED_DIRTY,
            snapshot={"last_vendor_delete_status": result.status},
        )
        self._repository.admission.true_up_graph_reservation(
            reservation_id,
            reservation_kind=reservation_kind,
            actual_cost_usd=Decimal("0.01"),
        )
        self._connection.commit()
        return GraphJobOutcome(
            kind="completed",
            vendor_status=result.status,
            reservation_id=reservation_id,
            reservation_kind=reservation_kind,
            workspace_state=GraphWorkspaceState.FILTERED_DIRTY.value,
        )

    async def _reconcile(
        self,
        *,
        job_id: UUID,
        job_lease_token: str,
        payload: dict[str, Any],
    ) -> GraphJobOutcome:
        self._writer.verify_lock_and_lease(
            job_id=job_id,
            job_lease_token=job_lease_token,
        )
        version_raw = payload.get("version_id")
        vendor_status = None
        if isinstance(version_raw, str) and version_raw:
            view = await self._indexer.adapter.vendor_document_status(version_raw)
            vendor_status = view.status if view is not None else None
        self._connection.commit()
        return GraphJobOutcome(
            kind="completed",
            vendor_status=vendor_status,
            workspace_state=GraphWorkspaceState.QUARANTINED.value,
            last_error="reconciliation_inspected",
        )

    def _isolate_rebuild_workspace(
        self,
        *,
        job_id: UUID,
        job_lease_token: str,
    ) -> GraphJobOutcome:
        self._writer.verify_lock_and_lease(
            job_id=job_id,
            job_lease_token=job_lease_token,
        )
        isolated_id = self._writer.ensure_building_rebuild_workspace()
        self._connection.commit()
        return GraphJobOutcome(
            kind="completed",
            last_error=f"rebuild_isolation_only:{isolated_id}",
            workspace_state=GraphWorkspaceState.BUILDING.value,
        )

    def _revalidate_index_eligibility(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        with self._connection.cursor() as cursor:
            try:
                cursor.execute(
                    "SELECT app.assert_graph_index_allowed(%s, %s)",
                    (document_id, version_id),
                )
            except psycopg.errors.RaiseException as exc:
                raise GraphIndexerError("not_graph_eligible") from exc
            cursor.execute(
                """
                SELECT
                  dv.content_hash,
                  dv.chunk_set_hash,
                  dv.status,
                  dv.hybrid_verified_at,
                  dv.graph_eligible,
                  d.graph_eligible,
                  ws.embedding_model,
                  ws.embedding_dimensions
                FROM app.document_versions AS dv
                JOIN app.documents AS d ON d.id = dv.document_id
                JOIN app.graph_workspaces AS ws
                  ON ws.workspace_key = %s
                WHERE dv.id = %s
                """,
                (self._writer.workspace_key, version_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise GraphIndexerError("version_missing")
        (
            content_hash,
            chunk_set_hash,
            status,
            hybrid_verified_at,
            version_graph_eligible,
            document_graph_eligible,
            embedding_model,
            embedding_dimensions,
        ) = row
        if (
            hybrid_verified_at is None
            or str(status) != DocumentStatus.GRAPH_PENDING.value
        ):
            raise GraphIndexerError("hybrid_not_ready")
        if not version_graph_eligible or not document_graph_eligible:
            raise GraphIndexerError("not_graph_eligible")
        expected_hash = payload.get("content_hash")
        if expected_hash and str(content_hash) != str(expected_hash):
            raise GraphIndexerError("content_hash_mismatch")
        expected_chunk = payload.get("chunk_set_hash")
        if expected_chunk and str(chunk_set_hash) != str(expected_chunk):
            raise GraphIndexerError("chunk_set_hash_mismatch")
        expected_lightrag = payload.get("lightrag_version", LIGHTRAG_HANDOFF_VERSION)
        expected_pipeline = payload.get(
            "graph_pipeline_version", GRAPH_PIPELINE_VERSION
        )
        if expected_lightrag not in {LIGHTRAG_HANDOFF_VERSION, LIGHTRAG_PINNED_VERSION}:
            raise GraphIndexerError("lightrag_pin_mismatch")
        if expected_pipeline != GRAPH_PIPELINE_VERSION:
            raise GraphIndexerError("pipeline_version_mismatch")
        if (
            str(embedding_model) != EMBEDDING_MODEL
            or int(embedding_dimensions) != EMBEDDING_DIMENSIONS
        ):
            raise GraphIndexerError("embedding_pin_mismatch")
        expected_generation = payload.get("expected_generation")
        if expected_generation is not None:
            current = self._writer.load_pointer_generation()
            if int(expected_generation) != current:
                raise GraphIndexerError("workspace_generation_mismatch")

    def _assert_version_still_pending(self, version_id: UUID) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT status
                FROM app.document_versions
                WHERE id = %s
                """,
                (version_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise GraphIndexerError("version_missing")
        if str(row[0]) != DocumentStatus.GRAPH_PENDING.value:
            raise GraphIndexerError("version_status_drift")

    def _quarantine_outcome(
        self,
        *,
        job_id: UUID,
        reason: str,
        reservation_id: UUID | None,
        reservation_kind: str | None,
    ) -> GraphJobOutcome:
        if reservation_id is not None and reservation_kind is not None:
            self._repository.admission.release_graph_reservation(
                reservation_id,
                reservation_kind=reservation_kind,
            )
        self._writer.quarantine(reason=reason, source_job_id=job_id)
        self._connection.commit()
        return GraphJobOutcome(
            kind="quarantined",
            error_category=JobErrorCategory.TRANSIENT,
            last_error=reason[:4000],
            reservation_id=reservation_id,
            reservation_kind=reservation_kind,
            workspace_state=GraphWorkspaceState.QUARANTINED.value,
        )


def _require_ids(job: dict[str, Any]) -> tuple[UUID, UUID]:
    document_raw = job.get("document_id")
    version_raw = job.get("version_id")
    if document_raw is None or version_raw is None:
        raise GraphIndexerError("job_missing_version")
    return UUID(str(document_raw)), UUID(str(version_raw))


def _actual_from_callbacks(
    indexer: LightRagGraphIndexer,
    *,
    estimate_floor: bool,
) -> Decimal:
    counts = indexer.adapter.callbacks.counts
    units = counts.embed + counts.entity_extract + counts.other
    actual = Decimal("0.01") * Decimal(str(max(units, 1 if estimate_floor else 0)))
    if actual <= 0:
        actual = Decimal("0.01")
    return actual
