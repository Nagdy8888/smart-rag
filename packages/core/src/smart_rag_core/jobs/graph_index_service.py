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

from smart_rag_core.gateways.embedding import EmbeddingProviderError
from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.jobs.entity_rule_invalidation import rebuild_workspace_key
from smart_rag_core.jobs.exceptions import (
    GraphLifecycleError,
    GraphMappingError,
    GraphWriterLostError,
    JobAdmissionError,
    JobLeaseError,
)
from smart_rag_core.jobs.graph_cleanup import (
    CleanupReason,
    CleanupRecoveryPhase,
    allowed_delete_from_states,
    emit_deletion_cleanup_failed,
    enqueue_surviving_rebuild,
    graph_maintenance_rebuild_funded,
    persist_recovery_phase,
    recheck_canonical_exclusion,
    verify_application_residue,
    verify_vendor_removed,
)
from smart_rag_core.jobs.graph_lifecycle import delete_status_fails_closed
from smart_rag_core.jobs.graph_mapping_hybrid import MappingSupportCallbacks
from smart_rag_core.jobs.graph_mapping_service import GraphMappingService
from smart_rag_core.jobs.graph_pointer_switch import (
    switch_active_workspace,
    switch_document_version,
)
from smart_rag_core.jobs.graph_source_batches import (
    insert_passage_batches,
    parse_processed_source_ids,
)
from smart_rag_core.jobs.graph_source_text import (
    GraphSourceTextError,
    load_version_passage_manifest,
    load_version_vendor_deletion_ids,
)
from smart_rag_core.jobs.graph_writer import (
    GraphWriterGuard,
    allowed_index_from_states,
    load_workspace_row,
)
from smart_rag_core.jobs.lightrag_repository import LightragIndexJobRepository
from smart_rag_core.jobs.limits import (
    DEFAULT_GRAPH_INDEX_ESTIMATE_USD,
    DEFAULT_GRAPH_MAINTENANCE_ESTIMATE_USD,
    GRAPH_PIPELINE_VERSION,
    GRAPH_SOURCE_INSERT_BATCH_SIZE,
    LIGHTRAG_HANDOFF_VERSION,
    MAX_MAPPING_ENTITIES,
    MAX_MAPPING_RELATIONS,
)
from smart_rag_core.jobs.maintenance_pause import (
    MaintenancePauseController,
    pause_error_code,
)
from smart_rag_core.observability.ingest_progress import log_ingest_progress
from smart_rag_core.repositories.notifications import (
    AdminNotificationError,
    AdminNotificationRepository,
)
from smart_rag_core.retrieval.graph import (
    LIGHTRAG_PINNED_VERSION,
    GraphIndexDeleteResult,
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
    "graph_source_too_many_passages",
    "graph_source_empty_passage",
    "graph_source_passage_too_large",
    "graph_source_duplicate_chunk",
    "graph_source_snapshot_mismatch",
    "chunk_map_collision",
    "ainsert_source_arity",
    "graph_source_batch_too_large",
    "graph_budget_exhausted",
    "invalid_estimated_cost",
    "canonical_not_excluded",
    "stale_generation",
    "current_version_mismatch",
}

ISOLATE_TRANSIENT_REASONS = frozenset(
    {
        "embedding_timeout",
        "embedding_rate_limited",
        "vendor_status_failed",
        "pipeline_status_uninitialized",
    }
)


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
        mapping_support: MappingSupportCallbacks | None = None,
        pause_controller: MaintenancePauseController | None = None,
        mapping_max_entities: int = MAX_MAPPING_ENTITIES,
        mapping_max_relations: int = MAX_MAPPING_RELATIONS,
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
            mapping_support: Optional Hybrid retrieve plus support rerank
                callbacks from ``bind_mapping_support``. When omitted,
                unresolved chunks stay unmapped. Repair must not attach these
                callbacks.
            pause_controller: User-load pause for clean rebuilds. Defaults
                to fail-closed missing telemetry.
            mapping_max_entities: Effective entity mapping cap passed to the
                default mapper. Production default is 200; the local
                synthetic-demo ceiling is 2,000.
            mapping_max_relations: Effective relation mapping cap passed to
                the default mapper. Production default is 200; the local
                synthetic-demo ceiling is 1,800.
        """

        self._connection = connection
        self._indexer = indexer
        self._writer = writer
        self._repository = repository
        self._pause_controller = pause_controller or (
            MaintenancePauseController.fail_closed()
        )
        if mapper is not None:
            self._mapper = mapper
        else:
            hybrid = (
                mapping_support.hybrid_retrieve if mapping_support is not None else None
            )
            rerank = (
                mapping_support.support_rerank if mapping_support is not None else None
            )
            self._mapper = GraphMappingService(
                connection,
                vendor_reader=indexer.adapter,
                writer=writer,
                hybrid_retrieve=hybrid,
                support_rerank=rerank,
                max_entities=mapping_max_entities,
                max_relations=mapping_max_relations,
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
        isolate_candidate = payload.get("isolate_candidate") is True
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
                return self._handle_rebuild(
                    job_id=job_id,
                    job_lease_token=job_lease_token,
                    payload=payload,
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
            if isolate_candidate:
                return self._fail_isolated_job(
                    reason=exc.reason,
                    reservation_id=reservation_id,
                    reservation_kind=reservation_kind,
                )
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
        except (GraphIndexerError, GraphSourceTextError, EmbeddingProviderError) as exc:
            reason = getattr(exc, "reason", str(exc))
            if isolate_candidate and reason in ISOLATE_TRANSIENT_REASONS:
                return self._fail_isolated_job(
                    reason=reason[:4000],
                    reservation_id=reservation_id,
                    reservation_kind=reservation_kind,
                )
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
        except GraphLifecycleError as exc:
            if (
                exc.reason in GRAPH_VALIDATION_REASONS
                or exc.reason == "unfunded_rebuild"
            ):
                if reservation_id is not None:
                    self._repository.admission.release_graph_reservation(
                        reservation_id,
                        reservation_kind=reservation_kind,
                    )
                    self._connection.commit()
                if exc.reason == "unfunded_rebuild":
                    return self._quarantine_outcome(
                        job_id=job_id,
                        reason=exc.reason,
                        reservation_id=reservation_id,
                        reservation_kind=reservation_kind,
                    )
                return GraphJobOutcome(
                    kind="failed",
                    error_category=JobErrorCategory.VALIDATION,
                    last_error=exc.reason,
                    reservation_id=reservation_id,
                    reservation_kind=reservation_kind,
                )
            return self._quarantine_outcome(
                job_id=job_id,
                reason=exc.reason[:512],
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
            )
        except (JobLeaseError, TimeoutError) as exc:
            reason = str(exc)[:512]
            if isolate_candidate:
                return self._fail_isolated_job(
                    reason=reason,
                    reservation_id=reservation_id,
                    reservation_kind=reservation_kind,
                )
            return self._quarantine_outcome(
                job_id=job_id,
                reason=reason,
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
            )

    def _reserve(self, reservation_kind: str, estimate: Decimal) -> UUID:
        """Reserve graph index or maintenance budget for this job.

        Args:
            reservation_kind: ``graph_index`` or ``graph_maintenance``.
            estimate: Positive estimated spend.

        Returns:
            New reservation id.
        """

        return self._repository.admission.create_graph_budget_reservation(
            reservation_kind=reservation_kind,
            estimated_cost_usd=estimate,
        )

    async def _bind_index_workspace(
        self,
        adapter: object,
        workspace: str,
    ) -> None:
        """Retarget vendor storage and initialize in-memory pipeline status.

        LightRAG 1.5.6 keeps ``{workspace}:pipeline_status`` in process
        memory. Binding ``{live}__rebuild`` without this init makes the
        first ``ainsert`` raise ``PipelineNotInitializedError``. This is
        not vendor DDL.

        Args:
            adapter: Attached LightRAG adapter, or ``None``.
            workspace: Constructor workspace to bind.

        Side Effects:
            Updates storage ``workspace`` attributes and calls
            ``ensure_pipeline_status`` when present.
        """

        if adapter is None:
            return
        bind = getattr(adapter, "bind_workspace", None)
        if callable(bind):
            bind(workspace)
        ensure = getattr(adapter, "ensure_pipeline_status", None)
        if callable(ensure):
            await ensure()

    async def _index(
        self,
        *,
        job: dict[str, Any],
        payload: dict[str, Any],
        job_id: UUID,
        job_lease_token: str,
        reservation_id: UUID,
    ) -> GraphJobOutcome:
        """Insert one version outside the pointer transaction, then maybe switch.

        Args:
            job: Claimed index job row.
            payload: Job payload including optional ``switch_after_verify``.
            job_id: Claimed job id.
            job_lease_token: Job lease token.
            reservation_id: ``graph_index`` reservation.

        Returns:
            Completed outcome, or mapping-unverified ``updating``.
        """

        document_id, version_id = _require_ids(job)
        isolate_candidate = payload.get("isolate_candidate") is True
        candidate_key = str(
            payload.get("rebuild_workspace_key")
            or rebuild_workspace_key(self._writer.workspace_key)
        )
        self._revalidate_index_eligibility(
            document_id=document_id,
            version_id=version_id,
            payload=payload,
        )
        self._writer.attach_default_pointer_if_null()
        if isolate_candidate:
            self._writer.ensure_building_rebuild_workspace()
        else:
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
        manifest = load_version_passage_manifest(
            self._connection,
            version_id=version_id,
        )
        self._connection.commit()
        adapter = getattr(self._indexer, "adapter", None)
        live_workspace = self._writer.workspace_key
        try:
            if isolate_candidate:
                await self._bind_index_workspace(adapter, candidate_key)
            if hasattr(self._mapper, "set_map_workspace_key"):
                self._mapper.set_map_workspace_key(
                    candidate_key if isolate_candidate else None
                )
            processed_ids = parse_processed_source_ids(payload)
            result = await insert_passage_batches(
                self._indexer,
                texts=tuple(item.enveloped_text() for item in manifest.sources),
                document_ids=manifest.source_ids,
                source_tokens=tuple(item.source_token for item in manifest.sources),
                processed_ids=processed_ids,
                batch_size=GRAPH_SOURCE_INSERT_BATCH_SIZE,
                isolate_workspace_key=candidate_key if isolate_candidate else None,
                on_lease_check=lambda: self._verify_index_lease(
                    job_id=job_id, job_lease_token=job_lease_token
                ),
                on_checkpoint=lambda patch: self._checkpoint_index_payload(
                    job_id=job_id,
                    job_lease_token=job_lease_token,
                    patch=patch,
                ),
                on_alert=lambda kind, size, latency_ms: self._emit_index_alert(
                    kind=kind,
                    batch_size=size,
                    latency_ms=latency_ms,
                    job_id=job_id,
                ),
            )
        finally:
            if hasattr(self._mapper, "set_map_workspace_key") and not isolate_candidate:
                self._mapper.set_map_workspace_key(None)
            if isolate_candidate is False:
                await self._bind_index_workspace(adapter, live_workspace)
        self._writer.verify_lock_and_lease(
            job_id=job_id,
            job_lease_token=job_lease_token,
        )
        self._assert_version_still_pending(version_id)
        maps_verified = False
        mapping_reason = ""
        workspace_state = (
            GraphWorkspaceState.BUILDING.value
            if isolate_candidate
            else GraphWorkspaceState.UPDATING.value
        )
        try:
            if isolate_candidate and hasattr(self._mapper, "set_map_workspace_key"):
                self._mapper.set_map_workspace_key(candidate_key)
            mapping = await self._mapper.map_after_vendor_success(
                document_id=document_id,
                version_id=version_id,
            )
            maps_verified = mapping.maps_verified
            mapping_reason = mapping.reason
            workspace_state = mapping.workspace_state
            if isolate_candidate and mapping.maps_verified and mapping.pending_switch:
                self._switch_rebuild_workspace(
                    payload={
                        **payload,
                        "workspace_key": live_workspace,
                        "rebuild_workspace_key": candidate_key,
                    }
                )
                mapping = await self._mapper.map_after_vendor_success(
                    document_id=document_id,
                    version_id=version_id,
                )
                maps_verified = mapping.maps_verified
                mapping_reason = mapping.reason
                workspace_state = mapping.workspace_state
            elif (
                mapping.pending_switch
                and mapping.maps_verified
                and payload.get("switch_after_verify") is True
            ):
                self._switch_pending_version(
                    document_id=document_id,
                    new_version_id=version_id,
                )
                workspace_state = GraphWorkspaceState.ACTIVE.value
                mapping_reason = "version_switched"
        except GraphMappingError as exc:
            maps_verified = False
            mapping_reason = exc.reason
            workspace_state = (
                GraphWorkspaceState.BUILDING.value
                if isolate_candidate
                else GraphWorkspaceState.UPDATING.value
            )
        finally:
            if hasattr(self._mapper, "set_map_workspace_key"):
                self._mapper.set_map_workspace_key(None)
            bind_key = (
                candidate_key if isolate_candidate and maps_verified else live_workspace
            )
            await self._bind_index_workspace(adapter, bind_key)
        if (
            not isolate_candidate
            and workspace_state != GraphWorkspaceState.ACTIVE.value
        ):
            self._writer.transition_state(
                from_states=(GraphWorkspaceState.UPDATING,),
                to_state=GraphWorkspaceState.UPDATING,
                snapshot={
                    "last_vendor_status": result.status,
                    "last_indexed_version_id": str(version_id),
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
        """Delete one vendor document after canonical exclusion recheck.

        Args:
            job: Claimed ``remove`` or ``graph_acl_remove`` row.
            job_id: Claimed job id.
            job_lease_token: Job lease token.
            reservation_id: ``graph_maintenance`` reservation.
            reservation_kind: Must be ``graph_maintenance``.

        Returns:
            ``filtered_dirty`` on verified cleanup, or quarantined on failure.

        Raises:
            GraphIndexerError: When canonical exclusion is not already true.
        """

        document_id, version_id = _require_ids(job)
        payload = dict(job.get("payload_ref") or {})
        reason = (
            CleanupReason.ACL_DOWNGRADE
            if str(job.get("operation")) == LightragJobOperation.GRAPH_ACL_REMOVE.value
            else CleanupReason.DELETION
        )
        if payload.get("reason") == "version_supersede":
            reason = CleanupReason.VERSION_SUPERSEDE
        workspace_key = self._writer.workspace_key
        exclusion = recheck_canonical_exclusion(
            self._connection,
            document_id=document_id,
            version_id=version_id,
        )
        if not exclusion.excluded:
            raise GraphIndexerError("canonical_not_excluded")
        persist_recovery_phase(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            workspace_key=workspace_key,
            reason=reason,
            phase=CleanupRecoveryPhase.PRECHECK,
        )
        self._writer.transition_state(
            from_states=allowed_delete_from_states(),
            to_state=GraphWorkspaceState.UPDATING,
            snapshot={"cleanup_phase": CleanupRecoveryPhase.PRECHECK.value},
        )
        self._connection.commit()
        self._writer.verify_lock_and_lease(
            job_id=job_id,
            job_lease_token=job_lease_token,
        )
        self._connection.commit()
        persist_recovery_phase(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            workspace_key=workspace_key,
            reason=reason,
            phase=CleanupRecoveryPhase.VENDOR_DELETE,
        )
        self._connection.commit()
        try:
            deletion_ids = load_version_vendor_deletion_ids(
                self._connection,
                version_id=version_id,
            )
            result = GraphIndexDeleteResult(
                document_id=str(version_id),
                status="not_found",
                message="",
            )
            for vendor_id in deletion_ids:
                result = await self._indexer.delete_document(document_id=vendor_id)
        except (TimeoutError, OSError, GraphIndexerError) as exc:
            return self._cleanup_failed(
                job_id=job_id,
                document_id=document_id,
                version_id=version_id,
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
                reason=reason,
                detail=getattr(exc, "reason", str(exc))[:512],
            )
        if delete_status_fails_closed(result.status):
            return self._cleanup_failed(
                job_id=job_id,
                document_id=document_id,
                version_id=version_id,
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
                reason=reason,
                detail=f"vendor_delete_{result.status}",
            )
        persist_recovery_phase(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            workspace_key=workspace_key,
            reason=reason,
            phase=CleanupRecoveryPhase.VENDOR_VERIFY,
            vendor_status=result.status,
        )
        self._connection.commit()
        vendor_check = await verify_vendor_removed(
            self._indexer.adapter,
            version_id=version_id,
            workspace_key=workspace_key,
            document_ids=deletion_ids,
        )
        if not vendor_check.clean and result.status != "not_found":
            return self._cleanup_failed(
                job_id=job_id,
                document_id=document_id,
                version_id=version_id,
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
                detail=vendor_check.residue,
                reason=reason,
            )
        if not vendor_check.clean and result.status == "not_found":
            return self._cleanup_failed(
                job_id=job_id,
                document_id=document_id,
                version_id=version_id,
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
                reason=reason,
                detail="not_found_with_residue",
            )
        persist_recovery_phase(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            workspace_key=workspace_key,
            reason=reason,
            phase=CleanupRecoveryPhase.MAP_FILTER,
            vendor_status=result.status,
        )
        self._connection.commit()
        maps = verify_application_residue(
            self._connection,
            version_id=version_id,
            workspace_key=workspace_key,
        )
        if not maps.clean:
            return self._cleanup_failed(
                job_id=job_id,
                document_id=document_id,
                version_id=version_id,
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
                detail=maps.residue,
                reason=reason,
            )
        persist_recovery_phase(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            workspace_key=workspace_key,
            reason=reason,
            phase=CleanupRecoveryPhase.TOMBSTONE,
            vendor_status=result.status,
        )
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
        funded = graph_maintenance_rebuild_funded(self._connection)
        if not funded:
            persist_recovery_phase(
                self._connection,
                document_id=document_id,
                version_id=version_id,
                workspace_key=workspace_key,
                reason=reason,
                phase=CleanupRecoveryPhase.TOMBSTONE,
                vendor_status=result.status,
                status="unfunded",
            )
            self._repository.admission.true_up_graph_reservation(
                reservation_id,
                reservation_kind=reservation_kind,
                actual_cost_usd=Decimal("0.01"),
            )
            self._connection.commit()
            return self._quarantine_outcome(
                job_id=job_id,
                reason="unfunded_rebuild",
                reservation_id=reservation_id,
                reservation_kind=reservation_kind,
            )
        rebuild_id = enqueue_surviving_rebuild(
            self._connection,
            workspace_key=workspace_key,
            funded=True,
        )
        persist_recovery_phase(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            workspace_key=workspace_key,
            reason=reason,
            phase=CleanupRecoveryPhase.VERIFIED,
            vendor_status=result.status,
            status="rebuild_scheduled",
            payload={"rebuild_job_id": str(rebuild_id) if rebuild_id else ""},
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

    def _cleanup_failed(
        self,
        *,
        job_id: UUID,
        document_id: UUID,
        version_id: UUID,
        reservation_id: UUID,
        reservation_kind: str,
        reason: CleanupReason,
        detail: str,
    ) -> GraphJobOutcome:
        """Quarantine after unverifiable vendor/map cleanup.

        Args:
            job_id: Claimed job id.
            document_id: Canonical document.
            version_id: Version whose cleanup failed.
            reservation_id: Maintenance reservation to release.
            reservation_kind: ``graph_maintenance``.
            reason: Tombstone reason.
            detail: Bounded diagnostic without corpus text.

        Returns:
            Quarantined outcome. Combined/inspection already emit
            ``graph_outage``.
        """

        persist_recovery_phase(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            workspace_key=self._writer.workspace_key,
            reason=reason,
            phase=CleanupRecoveryPhase.TOMBSTONE,
            status="failed",
            payload={"detail": detail[:512]},
        )
        emit_deletion_cleanup_failed(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            detail=detail,
        )
        return self._quarantine_outcome(
            job_id=job_id,
            reason=detail[:512],
            reservation_id=reservation_id,
            reservation_kind=reservation_kind,
        )

    async def _reconcile(
        self,
        *,
        job_id: UUID,
        job_lease_token: str,
        payload: dict[str, Any],
    ) -> GraphJobOutcome:
        """Inspect vendor status after lock/lease loss. Stay quarantined.

        Args:
            job_id: Claimed reconciliation job id.
            job_lease_token: Job lease token.
            payload: May include ``version_id`` for status inspection.

        Returns:
            Completed inspection that does not clear quarantine.
        """

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

    def _handle_rebuild(
        self,
        *,
        job_id: UUID,
        job_lease_token: str,
        payload: dict[str, Any],
    ) -> GraphJobOutcome:
        """Isolate a rebuild workspace or perform a verified pointer switch.

        Args:
            job_id: Claimed rebuild job id.
            job_lease_token: Job lease token.
            payload: ``isolate_only`` (default) or ``verified_switch``.

        Returns:
            Isolation-only ``building`` or switched ``active``. Paused
            rebuilds return transient ``maintenance_paused`` without
            isolating or switching.
        """

        self._writer.verify_lock_and_lease(
            job_id=job_id,
            job_lease_token=job_lease_token,
        )
        decision = self._pause_controller.decide()
        if decision.paused:
            return GraphJobOutcome(
                kind="failed",
                error_category=JobErrorCategory.TRANSIENT,
                last_error=pause_error_code(decision),
                reservation_kind="graph_maintenance",
            )
        if payload.get("verified_switch") is True:
            return self._switch_rebuild_workspace(payload=payload)
        isolated_id = self._writer.ensure_building_rebuild_workspace()
        self._connection.commit()
        return GraphJobOutcome(
            kind="completed",
            last_error=f"rebuild_isolation_only:{isolated_id}",
            workspace_state=GraphWorkspaceState.BUILDING.value,
        )

    def _switch_rebuild_workspace(self, *, payload: dict[str, Any]) -> GraphJobOutcome:
        """CAS the singleton onto a verified rebuild workspace.

        Args:
            payload: Expected generation and workspace keys.

        Returns:
            Switched ``active`` outcome.

        Raises:
            GraphLifecycleError: Stale generation or mixed embeddings.
        """

        expected_generation = int(payload.get("expected_generation") or 0)
        if expected_generation < 1:
            expected_generation = self._writer.load_pointer_generation()
        live_key = str(payload.get("workspace_key") or self._writer.workspace_key)
        target_key = str(payload.get("rebuild_workspace_key") or f"{live_key}__rebuild")
        live = load_workspace_row(self._connection, workspace_key=live_key)
        target = load_workspace_row(self._connection, workspace_key=target_key)
        result = switch_active_workspace(
            self._connection,
            expected_generation=expected_generation,
            expected_workspace_key=live_key,
            target_workspace_key=target_key,
            target_embedding_model=str(target["embedding_model"]),
            target_embedding_dimensions=_as_int(target["embedding_dimensions"]),
            source_embedding_model=str(live["embedding_model"]),
            source_embedding_dimensions=_as_int(live["embedding_dimensions"]),
        )
        self._connection.commit()
        return GraphJobOutcome(
            kind="completed",
            last_error=f"workspace_switched:{result.new_generation}",
            workspace_state=GraphWorkspaceState.ACTIVE.value,
        )

    def _switch_pending_version(
        self,
        *,
        document_id: UUID,
        new_version_id: UUID,
    ) -> None:
        """Flip exactly one current version after maps verify.

        Args:
            document_id: Canonical document.
            new_version_id: Verified replacement version.

        Raises:
            GraphLifecycleError: Missing current version or SQL CAS refusal.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT current_version_id
                FROM app.documents
                WHERE id = %s
                """,
                (document_id,),
            )
            row = cursor.fetchone()
        if row is None or row[0] is None:
            raise GraphLifecycleError("current_version_mismatch")
        old_version_id = UUID(str(row[0]))
        switch_document_version(
            self._connection,
            document_id=document_id,
            new_version_id=new_version_id,
            old_version_id=old_version_id,
            expected_generation=self._writer.load_pointer_generation(),
            expected_workspace_key=self._writer.workspace_key,
        )

    def _isolate_rebuild_workspace(
        self,
        *,
        job_id: UUID,
        job_lease_token: str,
    ) -> GraphJobOutcome:
        """Create ``{workspace_key}__rebuild`` in ``building`` without switching.

        Args:
            job_id: Claimed rebuild job id.
            job_lease_token: Job lease token.

        Returns:
            Isolation-only outcome.
        """

        return self._handle_rebuild(
            job_id=job_id,
            job_lease_token=job_lease_token,
            payload={"isolate_only": True},
        )

    def _revalidate_index_eligibility(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        """Recheck Hybrid/graph gates before vendor insert.

        Non-current versions use the build gate so pending-switch index can
        land in the target workspace. Live query still uses current_version_id.

        Args:
            document_id: Canonical document.
            version_id: Version being indexed.
            payload: May include expected hashes, pin, and generation.

        Raises:
            GraphIndexerError: Eligibility, pin, or generation mismatch.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_version_id FROM app.documents WHERE id = %s",
                (document_id,),
            )
            current_row = cursor.fetchone()
            current_id = (
                UUID(str(current_row[0]))
                if current_row is not None and current_row[0]
                else None
            )
            try:
                if current_id is not None and current_id != version_id:
                    cursor.execute(
                        "SELECT app.assert_graph_build_index_allowed(%s, %s)",
                        (document_id, version_id),
                    )
                else:
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
        """Refuse insert when the version left ``graph_pending``.

        Args:
            version_id: Version just inserted.

        Raises:
            GraphIndexerError: Missing version or status drift.
        """

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

    def _verify_index_lease(self, *, job_id: UUID, job_lease_token: str) -> None:
        """Fail closed when the writer lock or job lease was cancelled.

        Args:
            job_id: Claimed job id.
            job_lease_token: Job lease token.

        Raises:
            GraphWriterLostError: Lock or lease loss. Stops further batches.

        Side Effects:
            Short lease-validation transaction. Caller must not hold a
            transaction across vendor work.
        """

        self._writer.verify_lock_and_lease(
            job_id=job_id,
            job_lease_token=job_lease_token,
        )
        self._connection.commit()

    def _checkpoint_index_payload(
        self,
        *,
        job_id: UUID,
        job_lease_token: str,
        patch: dict[str, object],
    ) -> None:
        """Persist processed source IDs after a successful insert batch.

        Args:
            job_id: Claimed job id.
            job_lease_token: Job lease token.
            patch: JSON merged into ``payload_ref``.

        Raises:
            JobLeaseError: If the lease cannot be validated.

        Side Effects:
            Updates ``payload_ref`` and commits.
        """

        self._repository.merge_payload(job_id, job_lease_token, dict(patch))
        self._connection.commit()

    def _emit_index_alert(
        self,
        *,
        kind: str,
        batch_size: int,
        latency_ms: int,
        job_id: UUID,
    ) -> None:
        """Record a batch-size or embedding-latency operator alert.

        Args:
            kind: ``graph_source_batch_size`` or ``graph_embedding_latency``.
            batch_size: Sources or embed inputs in the batch.
            latency_ms: Last embedding wall time.
            job_id: Claimed job id.

        Side Effects:
            One ingest-progress line and one admin notification. Notification
            failure is swallowed so indexing continues.
        """

        log_ingest_progress(
            "graph",
            kind,
            job_id,
            batch_size=batch_size,
            latency_ms=latency_ms,
        )
        try:
            AdminNotificationRepository(self._connection).emit(
                kind=kind,
                severity="warning",
                title=f"Graph index {kind}",
                body="Bounded graph insert exceeded latency or batch-size alert.",
                metadata={
                    "job_id": str(job_id),
                    "batch_size": batch_size,
                    "latency_ms": latency_ms,
                },
            )
            self._connection.commit()
        except AdminNotificationError:
            self._connection.rollback()

    def _fail_isolated_job(
        self,
        *,
        reason: str,
        reservation_id: UUID | None,
        reservation_kind: str | None,
    ) -> GraphJobOutcome:
        """Fail a candidate rebuild without quarantining the live workspace.

        Args:
            reason: Machine-readable failure.
            reservation_id: Optional reservation to release.
            reservation_kind: Reservation kind when releasing.

        Returns:
            Transient ``failed`` outcome. Live pointer and live workspace
            state are unchanged.

        Side Effects:
            Releases an unused reservation when present.
        """

        if reservation_id is not None and reservation_kind is not None:
            self._repository.admission.release_graph_reservation(
                reservation_id,
                reservation_kind=reservation_kind,
            )
            self._connection.commit()
        return GraphJobOutcome(
            kind="failed",
            error_category=JobErrorCategory.TRANSIENT,
            last_error=reason[:4000],
            reservation_id=reservation_id,
            reservation_kind=reservation_kind,
        )

    def _quarantine_outcome(
        self,
        *,
        job_id: UUID,
        reason: str,
        reservation_id: UUID | None,
        reservation_kind: str | None,
    ) -> GraphJobOutcome:
        """Persist ``quarantined`` and release an unused reservation.

        Args:
            job_id: Claimed job id.
            reason: Machine-readable quarantine reason.
            reservation_id: Optional reservation to release.
            reservation_kind: Reservation kind when releasing.

        Returns:
            Quarantined outcome.
        """

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
    """Return document and version ids from a claimed job row.

    Args:
        job: Claimed ``lightrag_index_jobs`` mapping.

    Returns:
        ``(document_id, version_id)``.

    Raises:
        GraphIndexerError: When either id is missing.
    """

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
    """Derive a positive actual cost from counted gateway callbacks.

    Args:
        indexer: Indexer whose adapter callbacks were used.
        estimate_floor: When true, charge at least one unit.

    Returns:
        Positive USD amount for true-up.
    """

    counts = indexer.adapter.callbacks.counts
    units = counts.embed + counts.entity_extract + counts.other
    actual = Decimal("0.01") * Decimal(str(max(units, 1 if estimate_floor else 0)))
    if actual <= 0:
        actual = Decimal("0.01")
    return actual


def _as_int(value: object) -> int:
    """Coerce a workspace numeric column to int.

    Args:
        value: Database number, numeric string, or already an int.

    Returns:
        Integer form of ``value``.
    """

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return int(str(value))
