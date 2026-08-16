"""Immediate graph-map invalidation and rebuild scheduling for entity rules.

Lives under ``jobs/`` because ``apps/``, ``ingestion/``, and ``retrieval/``
must not mention mapping table names. Packet 7 performs the atomic workspace
pointer switch; this module only stamps maps stale and enqueues isolation.
"""

from __future__ import annotations

import json
from uuid import UUID

import psycopg

from smart_rag_core.jobs.extraction_policy import ExtractionPolicySnapshot
from smart_rag_core.jobs.limits import (
    GRAPH_PIPELINE_VERSION,
    MAPPING_REPAIR_JOB_KIND,
)
from smart_rag_core.retrieval.graph import (
    DEFAULT_GRAPH_WORKSPACE,
    graph_chunker_config_snapshot,
)
from smart_rag_core.schema.enums import LightragJobOperation

INVALIDATED_CONFIG_PREFIX = "invalidated:"
ENTITY_RULES_REPAIR_OBJECT_TYPE = "policy"
ENTITY_RULES_REPAIR_OBJECT_ID = "entity_rules"
REBUILD_WORKSPACE_SUFFIX = "__rebuild"

INVALIDATE_SOURCE_MAP_SQL = """
UPDATE app.lightrag_source_map
SET
  config_generation = %s || left(config_generation, 200),
  mapped_at = timezone('utc', now())
WHERE workspace_key = %s
  AND config_generation IS NOT NULL
  AND btrim(config_generation) <> ''
  AND config_generation NOT LIKE %s
"""

INVALIDATE_CHUNK_MAP_SQL = """
UPDATE app.lightrag_chunk_map
SET
  config_generation = %s || left(config_generation, 200),
  mapped_at = timezone('utc', now())
WHERE workspace_key = %s
  AND config_generation IS NOT NULL
  AND btrim(config_generation) <> ''
  AND config_generation NOT LIKE %s
"""

INVALIDATE_EVIDENCE_MAP_SQL = """
UPDATE app.graph_evidence_map
SET
  config_generation = %s || left(config_generation, 200),
  mapped_at = timezone('utc', now())
WHERE workspace_key = %s
  AND config_generation IS NOT NULL
  AND btrim(config_generation) <> ''
  AND config_generation NOT LIKE %s
"""

MARK_VERSIONS_NOT_GRAPH_READY_SQL = """
UPDATE app.document_versions
SET
  status = 'graph_pending'::app.document_status,
  updated_at = timezone('utc', now())
WHERE status = 'graph_ready'::app.document_status
"""

ENSURE_REBUILD_WORKSPACE_SQL = """
INSERT INTO app.graph_workspaces (
  workspace_key,
  state,
  config_snapshot
)
VALUES (
  %s,
  'building'::app.graph_workspace_state,
  %s::jsonb
)
ON CONFLICT (workspace_key) DO UPDATE
SET
  config_snapshot = app.graph_workspaces.config_snapshot || EXCLUDED.config_snapshot,
  updated_at = timezone('utc', now())
WHERE app.graph_workspaces.state IS DISTINCT FROM 'retired'::app.graph_workspace_state
RETURNING id
"""

ENQUEUE_REPAIR_SQL = """
INSERT INTO app.graph_map_repair_jobs (
  workspace_key, graph_object_type, graph_object_id, map_kind,
  config_generation, reason
)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (
  workspace_key, graph_object_type, graph_object_id, map_kind, config_generation
) DO UPDATE SET
  reason = EXCLUDED.reason,
  status = 'pending'::app.job_status,
  updated_at = timezone('utc', now())
RETURNING id
"""

ENQUEUE_REBUILD_SQL = """
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
"""

BUMP_POLICY_SQL = """
UPDATE app.graph_extraction_policy
SET
  entity_rules_generation = entity_rules_generation + 1,
  extraction_policy_hash = CASE
    WHEN btrim(COALESCE(%s, '')) = '' THEN extraction_policy_hash
    ELSE %s
  END,
  updated_at = timezone('utc', now())
WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
RETURNING entity_rules_generation, extraction_policy_hash
"""

SELECT_REBUILD_JOB_SQL = """
SELECT id
FROM app.lightrag_index_jobs
WHERE idempotency_key = %s
"""


def rebuild_workspace_key(workspace_key: str = DEFAULT_GRAPH_WORKSPACE) -> str:
    """Return the isolated rebuild workspace key. Pointer is unchanged.

    Args:
        workspace_key: Live workspace such as ``company_default``.

    Returns:
        ``{workspace_key}__rebuild``.
    """

    return f"{workspace_key}{REBUILD_WORKSPACE_SUFFIX}"


def invalidate_maps_and_schedule_rebuild(
    connection: psycopg.Connection,
    *,
    workspace_key: str = DEFAULT_GRAPH_WORKSPACE,
    reason: str = "entity_rules_changed",
    policy: ExtractionPolicySnapshot | None = None,
) -> tuple[int, UUID | None, UUID | None]:
    """Stamp maps stale, mark versions not Graph Ready, enqueue rebuild.

    Does not switch the active workspace pointer. Does not UPDATE vendor
    ``lightrag`` tables or ``search_aliases``.

    Args:
        connection: Privileged or worker connection inside a transaction.
        workspace_key: Live application workspace.
        reason: Bounded machine-readable invalidation reason.
        policy: Optional overlay stored on the rebuild workspace snapshot.

    Returns:
        Tuple of ``(entity_rules_generation, repair_id, rebuild_job_id)``.

    Side Effects:
        Updates application maps and ``document_versions.status``, inserts
        repair and rebuild jobs, ensures ``{workspace}__rebuild`` exists.
        Caller must commit. Pointer generation is unchanged.
    """

    like_pattern = f"{INVALIDATED_CONFIG_PREFIX}%"
    with connection.cursor() as cursor:
        policy_hash = policy.extraction_policy_hash if policy is not None else ""
        cursor.execute(BUMP_POLICY_SQL, (policy_hash, policy_hash))
        bumped = cursor.fetchone()
        generation = int(bumped[0]) if bumped is not None else 1
        cursor.execute(
            INVALIDATE_SOURCE_MAP_SQL,
            (INVALIDATED_CONFIG_PREFIX, workspace_key, like_pattern),
        )
        cursor.execute(
            INVALIDATE_CHUNK_MAP_SQL,
            (INVALIDATED_CONFIG_PREFIX, workspace_key, like_pattern),
        )
        cursor.execute(
            INVALIDATE_EVIDENCE_MAP_SQL,
            (INVALIDATED_CONFIG_PREFIX, workspace_key, like_pattern),
        )
        cursor.execute(MARK_VERSIONS_NOT_GRAPH_READY_SQL)
        snapshot = dict(graph_chunker_config_snapshot())
        snapshot["entity_rules_generation"] = generation
        snapshot["graph_pipeline_version"] = GRAPH_PIPELINE_VERSION
        if policy is not None:
            snapshot["extraction_policy_hash"] = policy.extraction_policy_hash
            snapshot["relation_label_policy"] = policy.relation_label_policy
        rebuild_key = rebuild_workspace_key(workspace_key)
        cursor.execute(
            ENSURE_REBUILD_WORKSPACE_SQL,
            (rebuild_key, json.dumps(snapshot)),
        )
        cursor.execute(
            ENQUEUE_REPAIR_SQL,
            (
                workspace_key,
                ENTITY_RULES_REPAIR_OBJECT_TYPE,
                ENTITY_RULES_REPAIR_OBJECT_ID,
                MAPPING_REPAIR_JOB_KIND,
                f"{INVALIDATED_CONFIG_PREFIX}{generation}",
                reason[:512],
            ),
        )
        repair_row = cursor.fetchone()
        repair_id = UUID(str(repair_row[0])) if repair_row is not None else None
        idempotency = f"graph_entity_rules_rebuild:{workspace_key}:{generation}"
        payload = {
            "reason": reason[:512],
            "workspace_key": workspace_key,
            "rebuild_workspace_key": rebuild_key,
            "entity_rules_generation": generation,
            "isolate_only": True,
            "operation": LightragJobOperation.REBUILD.value,
            "graph_pipeline_version": GRAPH_PIPELINE_VERSION,
            "live_pointer_unchanged": True,
        }
        cursor.execute(ENQUEUE_REBUILD_SQL, (idempotency, json.dumps(payload)))
        rebuild_row = cursor.fetchone()
        if rebuild_row is None:
            cursor.execute(SELECT_REBUILD_JOB_SQL, (idempotency,))
            rebuild_row = cursor.fetchone()
        rebuild_id = UUID(str(rebuild_row[0])) if rebuild_row is not None else None
    return generation, repair_id, rebuild_id
