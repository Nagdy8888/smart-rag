"""Targeted LightRAG document deletion, ACL cleanup, and tombstone SLAs.

Canonical exclusion is immediate. Vendor ``adelete_by_doc_id`` runs outside
the pointer transaction. Failures quarantine and emit deletion-cleanup-failed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.jobs.exceptions import GraphLifecycleError
from smart_rag_core.jobs.graph_lifecycle import (
    CleanupReason,
    CleanupRecoveryPhase,
)
from smart_rag_core.jobs.limits import (
    DEFAULT_GRAPH_MAINTENANCE_ESTIMATE_USD,
    DEFAULT_MONTHLY_GRAPH_MAINTENANCE_BUDGET_USD,
    DELETION_CLEANUP_FAILED_KIND,
)
from smart_rag_core.retrieval.graph import (
    DEFAULT_GRAPH_WORKSPACE,
    GraphIndexDeleteResult,
)
from smart_rag_core.schema.enums import GraphWorkspaceState


class GraphDeleteAdapter(Protocol):
    """Narrow delete/status/chunk reads used after canonical exclusion."""

    async def delete_document(
        self,
        *,
        document_id: str,
        delete_llm_cache: bool = True,
    ) -> GraphIndexDeleteResult:
        """Delete one vendor document with privacy cache deletion."""

        ...

    async def vendor_document_status(self, document_id: str) -> object | None:
        """Return vendor status or ``None`` when the row is gone."""

        ...

    async def list_vendor_doc_chunks(
        self,
        *,
        workspace: str,
        document_id: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return remaining vendor chunks for residue checks."""

        ...


@dataclass(frozen=True, slots=True)
class CanonicalExclusion:
    """Phase 3 exclusion snapshot rechecked before vendor mutation.

    Attributes:
        excluded: True when the version is retrieval-ineligible or deleted.
        reason: Machine-readable detail.
        document_id: Canonical document.
        version_id: Canonical version.
        graph_eligible: Document graph eligibility after exclusion.
    """

    excluded: bool
    reason: str
    document_id: UUID
    version_id: UUID
    graph_eligible: bool


@dataclass(frozen=True, slots=True)
class CleanupVerifyResult:
    """Post-delete residue check.

    Attributes:
        clean: True when vendor status/chunks and eligible maps are gone.
        residue: Bounded diagnostic when not clean.
    """

    clean: bool
    residue: str


def recheck_canonical_exclusion(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
) -> CanonicalExclusion:
    """Recheck Phase 3 canonical exclusion before vendor mutation.

    Args:
        connection: ``app_worker`` connection.
        document_id: Canonical document.
        version_id: Version to delete from the vendor graph.

    Returns:
        Exclusion snapshot. ``excluded`` is the immediate authority.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              dv.retrieval_eligible,
              dv.deleted_at,
              dv.graph_eligible,
              d.graph_eligible,
              d.deleted_at,
              d.visibility::text,
              COALESCE(sm.retrieval_eligible, false)
            FROM app.document_versions AS dv
            JOIN app.documents AS d ON d.id = dv.document_id
            LEFT JOIN app.lightrag_source_map AS sm
              ON sm.version_id = dv.id
            WHERE dv.id = %s AND d.id = %s
            """,
            (version_id, document_id),
        )
        row = cursor.fetchone()
    if row is None:
        return CanonicalExclusion(
            excluded=True,
            reason="version_missing",
            document_id=document_id,
            version_id=version_id,
            graph_eligible=False,
        )
    (
        retrieval_eligible,
        version_deleted,
        version_elig,
        doc_elig,
        doc_deleted,
        visibility,
        map_eligible,
    ) = row
    restricted = str(visibility) == "restricted"
    excluded = (
        retrieval_eligible is False
        or version_deleted is not None
        or doc_deleted is not None
        or version_elig is not True
        or doc_elig is not True
        or restricted
        or map_eligible is not True
    )
    reason = "eligible"
    if not excluded:
        reason = "canonical_not_excluded"
    elif version_deleted is not None or doc_deleted is not None:
        reason = "deleted"
    elif restricted:
        reason = "restricted"
    elif retrieval_eligible is False:
        reason = "retrieval_ineligible"
    elif map_eligible is not True:
        reason = "source_map_ineligible"
    else:
        reason = "graph_ineligible"
    return CanonicalExclusion(
        excluded=excluded,
        reason=reason,
        document_id=document_id,
        version_id=version_id,
        graph_eligible=bool(doc_elig),
    )


def persist_recovery_phase(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
    workspace_key: str,
    reason: CleanupReason,
    phase: CleanupRecoveryPhase,
    vendor_status: str | None = None,
    status: str = "pending",
    payload: dict[str, object] | None = None,
) -> UUID:
    """Upsert the open tombstone with a recovery phase.

    Args:
        connection: ``app_worker`` connection. Caller commits.
        document_id: Canonical document.
        version_id: Version under cleanup.
        workspace_key: Application workspace.
        reason: Tombstone reason.
        phase: Persisted recovery phase.
        vendor_status: Last vendor deletion status.
        status: Tombstone status.
        payload: Extra diagnostics without corpus text.

    Returns:
        Tombstone id.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT app.upsert_graph_cleanup_tombstone(
              %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            """,
            (
                document_id,
                version_id,
                workspace_key,
                reason.value,
                phase.value,
                vendor_status,
                status,
                json.dumps(payload or {}),
            ),
        )
        row = cursor.fetchone()
    if row is None or row[0] is None:
        raise GraphLifecycleError("tombstone_missing")
    return UUID(str(row[0]))


def verify_application_residue(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
    workspace_key: str,
) -> CleanupVerifyResult:
    """Fail closed when eligible maps or Graph Ready still name the version.

    Args:
        connection: ``app_worker`` connection.
        version_id: Version that must not survive resolution.
        workspace_key: Active or cleaning workspace.

    Returns:
        Residue diagnostic. Shared-entity maps may remain if they point at
        surviving current versions; this check is version-scoped.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              EXISTS (
                SELECT 1
                FROM app.lightrag_source_map
                WHERE version_id = %s
                  AND workspace_key = %s
                  AND retrieval_eligible IS TRUE
              ),
              EXISTS (
                SELECT 1
                FROM app.lightrag_chunk_map
                WHERE version_id = %s
                  AND workspace_key = %s
                  AND retrieval_eligible IS TRUE
              ),
              EXISTS (
                SELECT 1
                FROM app.graph_evidence_map
                WHERE version_id = %s
                  AND workspace_key = %s
                  AND retrieval_eligible IS TRUE
              )
            """,
            (
                version_id,
                workspace_key,
                version_id,
                workspace_key,
                version_id,
                workspace_key,
            ),
        )
        row = cursor.fetchone()
    if row is None:
        return CleanupVerifyResult(clean=False, residue="verify_query_empty")
    if any(bool(flag) for flag in row):
        return CleanupVerifyResult(clean=False, residue="source_residue")
    return CleanupVerifyResult(clean=True, residue="")


def surviving_shared_entity_contamination(
    connection: psycopg.Connection,
    *,
    deleted_version_id: UUID,
    workspace_key: str,
) -> bool:
    """Return True if an eligible evidence row still cites the deleted version.

    Shared entities may keep other surviving source versions. The deleted
    version must not remain retrieval-eligible.

    Args:
        connection: ``app_worker`` connection.
        deleted_version_id: Version that must not survive.
        workspace_key: Workspace under inspection.

    Returns:
        True when contamination remains.
    """

    result = verify_application_residue(
        connection,
        version_id=deleted_version_id,
        workspace_key=workspace_key,
    )
    return not result.clean


async def verify_vendor_removed(
    adapter: GraphDeleteAdapter,
    *,
    version_id: UUID,
    workspace_key: str,
    document_ids: tuple[str, ...] | None = None,
) -> CleanupVerifyResult:
    """Verify vendor full-doc/chunk/status removal.

    Args:
        adapter: Runtime adapter or test double.
        version_id: Canonical version. Used when ``document_ids`` is omitted.
        workspace_key: LightRAG constructor workspace.
        document_ids: Explicit vendor IDs including legacy whole-version and
            per-passage sources. Defaults to ``(str(version_id),)``.

    Returns:
        Residue diagnostic. Missing status is clean.
    """

    vendor_ids = document_ids if document_ids is not None else (str(version_id),)
    for vendor_id in vendor_ids:
        status = await adapter.vendor_document_status(vendor_id)
        if status is not None:
            return CleanupVerifyResult(clean=False, residue="vendor_status_residue")
        chunks = await adapter.list_vendor_doc_chunks(
            workspace=workspace_key,
            document_id=vendor_id,
            limit=2,
        )
        if chunks:
            return CleanupVerifyResult(clean=False, residue="vendor_chunk_residue")
    return CleanupVerifyResult(clean=True, residue="")


def emit_deletion_cleanup_failed(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
    detail: str,
) -> UUID | None:
    """Emit the durable deletion-cleanup-failed admin notification.

    Args:
        connection: ``app_worker`` connection. Caller commits.
        document_id: Canonical document.
        version_id: Version whose cleanup failed.
        detail: Bounded diagnostic without corpus text.

    Returns:
        Notification id when inserted.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT app.emit_admin_notification(
              %s, 'critical', %s, %s, %s::jsonb
            )
            """,
            (
                DELETION_CLEANUP_FAILED_KIND,
                "Deletion cleanup failed",
                detail[:512],
                json.dumps(
                    {
                        "document_id": str(document_id),
                        "version_id": str(version_id),
                    }
                ),
            ),
        )
        row = cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return UUID(str(row[0]))


def graph_maintenance_rebuild_funded(
    connection: psycopg.Connection,
    *,
    estimated_cost_usd: Decimal | None = None,
) -> bool:
    """Return whether a surviving rebuild can still reserve maintenance budget.

    Peeks only. Does not insert a reservation. Never consults
    ``ingestion_daily``.

    Args:
        connection: ``app_worker`` connection.
        estimated_cost_usd: Rebuild estimate. Defaults to the maintenance floor.

    Returns:
        True when used monthly maintenance plus the estimate is within cap.
    """

    estimate = estimated_cost_usd or Decimal(
        str(DEFAULT_GRAPH_MAINTENANCE_ESTIMATE_USD)
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(cs.monthly_graph_maintenance_budget_usd, %s)
            FROM app.company_settings AS cs
            WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid
            """,
            (DEFAULT_MONTHLY_GRAPH_MAINTENANCE_BUDGET_USD,),
        )
        budget_row = cursor.fetchone()
        cap = (
            Decimal(str(budget_row[0]))
            if budget_row
            else Decimal(str(DEFAULT_MONTHLY_GRAPH_MAINTENANCE_BUDGET_USD))
        )
        cursor.execute(
            """
            SELECT COALESCE(sum(amount_usd), 0)
            FROM app.budget_reservations
            WHERE reservation_kind = 'graph_maintenance'
              AND status IN (
                'reserved'::app.budget_reservation_status,
                'committed'::app.budget_reservation_status
              )
              AND created_at >= date_trunc('month', timezone('utc', now()))
            """
        )
        used_row = cursor.fetchone()
    used = Decimal(str(used_row[0])) if used_row else Decimal("0")
    return used + estimate <= cap


def enqueue_surviving_rebuild(
    connection: psycopg.Connection,
    *,
    workspace_key: str = DEFAULT_GRAPH_WORKSPACE,
    funded: bool,
) -> UUID | None:
    """Schedule a clean rebuild from surviving current graph-eligible versions.

    Args:
        connection: ``app_worker`` connection. Caller commits.
        workspace_key: Live workspace.
        funded: False when the maintenance reserve is exhausted.

    Returns:
        Rebuild job id when funded and inserted.

    Raises:
        GraphLifecycleError: When unfunded; caller must quarantine.
    """

    if not funded:
        raise GraphLifecycleError("unfunded_rebuild")
    rebuild_key = f"{workspace_key}__rebuild"
    idempotency = f"graph_cleanup_rebuild:{workspace_key}"
    payload = {
        "reason": "filtered_dirty_consolidation",
        "workspace_key": workspace_key,
        "rebuild_workspace_key": rebuild_key,
        "isolate_only": True,
        "surviving_current_only": True,
    }
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.lightrag_index_jobs (
              operation,
              priority,
              idempotency_key,
              payload_ref
            )
            VALUES (
              'rebuild'::app.lightrag_job_operation,
              'normal'::app.job_priority,
              %s,
              %s::jsonb
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (idempotency, json.dumps(payload)),
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "SELECT id FROM app.lightrag_index_jobs WHERE idempotency_key = %s",
                (idempotency,),
            )
            row = cursor.fetchone()
    if row is None:
        return None
    return UUID(str(row[0]))


def load_workspace_embedding(
    connection: psycopg.Connection,
    *,
    workspace_key: str,
) -> tuple[str, int, str]:
    """Load embedding pin and state for a workspace.

    Args:
        connection: ``app_worker`` connection.
        workspace_key: Application workspace.

    Returns:
        ``(embedding_model, embedding_dimensions, state)``.

    Raises:
        GraphLifecycleError: If the workspace is missing.
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT embedding_model, embedding_dimensions, state::text
            FROM app.graph_workspaces
            WHERE workspace_key = %s
            """,
            (workspace_key,),
        )
        row = cursor.fetchone()
    if row is None:
        raise GraphLifecycleError("workspace_missing")
    return (
        str(row["embedding_model"]),
        int(row["embedding_dimensions"]),
        str(row["state"]),
    )


def allowed_delete_from_states() -> tuple[GraphWorkspaceState, ...]:
    """Return states from which targeted delete may enter ``updating``.

    Returns:
        Active, updating, filtered_dirty, and building.
    """

    return (
        GraphWorkspaceState.ACTIVE,
        GraphWorkspaceState.UPDATING,
        GraphWorkspaceState.FILTERED_DIRTY,
        GraphWorkspaceState.BUILDING,
    )
