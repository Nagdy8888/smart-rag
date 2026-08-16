"""Short application transactions for pointer and version CAS.

Callers must not hold this transaction across model or vendor work.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.jobs.exceptions import GraphLifecycleError
from smart_rag_core.jobs.graph_lifecycle import assert_homogeneous_embedding
from smart_rag_core.jobs.limits import GRAPH_POINTER_ID
from smart_rag_core.retrieval.graph import DEFAULT_GRAPH_WORKSPACE


@dataclass(frozen=True, slots=True)
class VersionSwitchResult:
    """Outcome of one document-version pointer transaction.

    Attributes:
        generation: Unchanged pointer generation after a same-workspace flip.
        workspace_id: Attached workspace, if any.
        switched: True when the transaction committed a single current version.
    """

    generation: int
    workspace_id: UUID | None
    switched: bool


@dataclass(frozen=True, slots=True)
class WorkspaceSwitchResult:
    """Outcome of one active-workspace pointer CAS.

    Attributes:
        new_generation: Bumped pointer generation.
        old_workspace_id: Previous workspace, if any.
        new_workspace_id: Newly attached workspace.
    """

    new_generation: int
    old_workspace_id: UUID | None
    new_workspace_id: UUID


def load_pointer_for_cas(
    connection: psycopg.Connection,
) -> tuple[int, UUID | None]:
    """Read the singleton pointer without locking.

    Args:
        connection: ``app_worker`` connection.

    Returns:
        ``(generation, workspace_id)``.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT generation, workspace_id
            FROM app.graph_active_workspace_pointer
            WHERE id = %s::uuid
            """,
            (GRAPH_POINTER_ID,),
        )
        row = cursor.fetchone()
    if row is None:
        return 1, None
    workspace = UUID(str(row[1])) if row[1] is not None else None
    return int(row[0] or 1), workspace


def switch_document_version(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    new_version_id: UUID,
    old_version_id: UUID,
    expected_generation: int,
    expected_workspace_key: str = DEFAULT_GRAPH_WORKSPACE,
) -> VersionSwitchResult:
    """Atomically expose exactly one current version.

    Rechecks deletion/ACL inside the SQL function. Does not bump generation.
    Does not call LightRAG.

    Args:
        connection: ``app_worker`` connection. Caller commits.
        document_id: Canonical document.
        new_version_id: Verified replacement version.
        old_version_id: Expected current version.
        expected_generation: Pointer generation CAS.
        expected_workspace_key: Workspace the pointer must already name.

    Returns:
        Switch result.

    Raises:
        GraphLifecycleError: On stale generation, mismatch, or ineligible rows.

    Side Effects:
        Flips ``current_version_id``, Hybrid/BM25 visibility, map eligibility,
        audit, and post-flip cleanup jobs. Caller must commit.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT new_generation, workspace_id, switched
                FROM app.switch_graph_document_version(%s, %s, %s, %s, %s)
                """,
                (
                    document_id,
                    new_version_id,
                    old_version_id,
                    expected_generation,
                    expected_workspace_key,
                ),
            )
            row = cursor.fetchone()
    except psycopg.errors.RaiseException as exc:
        raise GraphLifecycleError(_raise_reason(exc)) from exc
    if row is None:
        raise GraphLifecycleError("switch_returned_empty")
    workspace_raw = row["workspace_id"]
    return VersionSwitchResult(
        generation=int(row["new_generation"]),
        workspace_id=UUID(str(workspace_raw)) if workspace_raw is not None else None,
        switched=bool(row["switched"]),
    )


def switch_active_workspace(
    connection: psycopg.Connection,
    *,
    expected_generation: int,
    expected_workspace_key: str,
    target_workspace_key: str,
    target_embedding_model: str,
    target_embedding_dimensions: int,
    source_embedding_model: str | None = None,
    source_embedding_dimensions: int | None = None,
) -> WorkspaceSwitchResult:
    """CAS the singleton onto a verified parallel workspace.

    Embedding homogeneity is checked in Python before the SQL CAS so mixed
    configs never enter the pointer transaction.

    Args:
        connection: ``app_worker`` connection. Caller commits.
        expected_generation: Pointer generation CAS.
        expected_workspace_key: Currently attached workspace key.
        target_workspace_key: Isolated rebuild or named build workspace.
        target_embedding_model: Frozen target embedding model.
        target_embedding_dimensions: Frozen target dimensions.
        source_embedding_model: Live workspace model when known.
        source_embedding_dimensions: Live workspace dimensions when known.

    Returns:
        Bumped generation and workspace ids.

    Raises:
        GraphLifecycleError: On mixed embeddings, stale generation, or SQL refusal.

    Side Effects:
        Pointer CAS, retire old workspace, activate target, audit.
        Caller must commit. Vendor delete of the old workspace is after commit.
    """

    assert_homogeneous_embedding(
        model=target_embedding_model,
        dimensions=target_embedding_dimensions,
        other_model=source_embedding_model,
        other_dimensions=source_embedding_dimensions,
    )
    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT new_generation, old_workspace_id, new_workspace_id
                FROM app.switch_graph_active_workspace(%s, %s, %s)
                """,
                (
                    expected_generation,
                    expected_workspace_key,
                    target_workspace_key,
                ),
            )
            row = cursor.fetchone()
    except psycopg.errors.RaiseException as exc:
        raise GraphLifecycleError(_raise_reason(exc)) from exc
    if row is None:
        raise GraphLifecycleError("switch_returned_empty")
    old_raw = row["old_workspace_id"]
    return WorkspaceSwitchResult(
        new_generation=int(row["new_generation"]),
        old_workspace_id=UUID(str(old_raw)) if old_raw is not None else None,
        new_workspace_id=UUID(str(row["new_workspace_id"])),
    )


def disable_workspace(
    connection: psycopg.Connection,
    *,
    workspace_key: str,
    reason: str,
) -> UUID | None:
    """Disable a workspace. Resolver already emits ``graph_outage``.

    Args:
        connection: ``app_worker`` connection. Caller commits.
        workspace_key: Workspace to disable.
        reason: Bounded machine-readable reason.

    Returns:
        Workspace id when updated.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT app.disable_graph_workspace(%s, %s)",
            (workspace_key, reason[:512]),
        )
        row = cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return UUID(str(row[0]))


def _raise_reason(exc: BaseException) -> str:
    """Return a bounded SQL raise diagnostic without secrets.

    Args:
        exc: Postgres raise.

    Returns:
        First diagnostic token, default ``switch_failed``.
    """

    text = str(exc)
    if "stale_generation" in text:
        return "stale_generation"
    if "versions_not_distinct" in text:
        return "versions_not_distinct"
    if "current_version_mismatch" in text:
        return "current_version_mismatch"
    if "workspace_mismatch" in text:
        return "workspace_mismatch"
    if "in_place_mixed_embeddings_forbidden" in text:
        return "in_place_mixed_embeddings_forbidden"
    if "embedding_config_mismatch" in text:
        return "embedding_config_mismatch"
    token = text.split(":")[-1].strip()
    return token[:128] or "switch_failed"
