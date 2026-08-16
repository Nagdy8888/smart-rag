"""Authoritative graph lead resolution, survival, inspection, and repairs.

Map-table SQL lives here because ``jobs/`` is outside the Phase 3 scope-guard
scan. Query-time Hybrid and per-statement support search are forbidden.
Unauthorized restricted documents never appear in counts or diagnostics.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from uuid import UUID

import psycopg

from smart_rag_core.jobs.entity_rule_service import load_extraction_policy
from smart_rag_core.jobs.exceptions import GraphResolverError
from smart_rag_core.jobs.limits import (
    GRAPH_POINTER_ID,
    GRAPH_QUERY_REPAIR_MAP_KIND,
    GRAPH_SURVIVAL_ROLLING_WINDOW,
    MAPPING_SUPPORT_MIN,
)
from smart_rag_core.retrieval.context_loader import locators_from_provenance
from smart_rag_core.retrieval.graph import (
    ADAPTER_MAX_HOPS,
    ADAPTER_MAX_PATHS,
    GRAPH_SURVIVAL_ROLLING_ALERT_THRESHOLD,
    GraphLeadSet,
    GraphLimitationCode,
    graph_chunker_config_snapshot,
    returned_graph_candidate_count,
)
from smart_rag_core.retrieval.graph_mapping import mapping_config_generation
from smart_rag_core.retrieval.graph_results import (
    GraphCanonicalLocator,
    GraphInspectNode,
    GraphInspectResult,
    GraphLimitation,
    GraphPath,
    GraphResolvedCandidate,
    RollingSurvivalWindow,
)
from smart_rag_core.retrieval.session import retrieval_transaction
from smart_rag_core.security.identity import CallerContext

_READY_STATUS = "graph_ready"
_SUPPORT_MIN = MAPPING_SUPPORT_MIN


@dataclass(frozen=True, slots=True)
class QueryWorkspaceSnapshot:
    """Active workspace pointer used before a vendor query.

    Attributes:
        workspace_key: Application workspace identifier.
        workspace_id: Row id when the pointer is attached.
        state: Durable workspace state.
        pointer_attached: True when the singleton names a workspace.
        generation: Pointer generation used in mapping config.
        config_generation: Mapping config digest expected on map rows.
    """

    workspace_key: str
    workspace_id: UUID | None
    state: str | None
    pointer_attached: bool
    generation: int
    config_generation: str


@dataclass(frozen=True, slots=True)
class VisibilityCounts:
    """Authorized-only partial-readiness and ACL-blindness counts.

    Attributes:
        partial_readiness_count: Company-visible Hybrid-ready versions that
            are not Graph Ready and the caller can read.
        acl_blindness_count: Restricted graph-ineligible versions the caller
            can read. Unauthorized restricted documents are omitted.
    """

    partial_readiness_count: int
    acl_blindness_count: int


@dataclass(frozen=True, slots=True)
class _MapRow:
    """One map join row used to decide whole-candidate survival."""

    vendor_key: str
    object_type: str
    object_id: str
    chunk_id: UUID | None
    document_id: UUID | None
    version_id: UUID | None
    support: float
    src_vendor: str
    tgt_vendor: str
    vendor_name: str
    path_edge_id: str
    survived: bool
    drop_reason: str


@dataclass(frozen=True, slots=True)
class ResolvedStatement:
    """Surviving statement used for bounded path expansion."""

    statement_id: str
    path_edge_id: str
    src_vendor: str
    tgt_vendor: str
    chunk_ids: tuple[UUID, ...]
    document_id: UUID
    version_id: UUID
    support: float


@dataclass(frozen=True, slots=True)
class ResolveOutcome:
    """Resolver output after whole-candidate drops and path expansion.

    Attributes:
        candidates: Surviving application objects.
        paths: At most six bounded paths.
        dropped: Dropped native lead keys for bounded repair.
        diagnostics: Machine-readable reasons without document titles.
        returned_candidates: Clamped vendor candidate count.
        supported_candidates: Surviving candidate count.
    """

    candidates: tuple[GraphResolvedCandidate, ...]
    paths: tuple[GraphPath, ...]
    dropped: tuple[dict[str, str], ...]
    diagnostics: tuple[str, ...]
    returned_candidates: int
    supported_candidates: int


def load_query_workspace(connection: psycopg.Connection) -> QueryWorkspaceSnapshot:
    """Load the singleton pointer and compute the expected mapping generation.

    Args:
        connection: Idle login connection. The snapshot is read as ``app_api``.

    Returns:
        Workspace snapshot. Missing/unattached pointers fail closed upstream.

    Side Effects:
        One short read transaction as ``app_api``.
    """

    with connection.transaction():
        connection.execute("SET LOCAL ROLE app_api")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  pointer.workspace_id,
                  pointer.generation,
                  ws.workspace_key,
                  ws.state::text
                FROM app.graph_active_workspace_pointer AS pointer
                LEFT JOIN app.graph_workspaces AS ws
                  ON ws.id = pointer.workspace_id
                WHERE pointer.id = %s::uuid
                """,
                (GRAPH_POINTER_ID,),
            )
            row = cursor.fetchone()
        policy = load_extraction_policy(connection)
    if row is None:
        return QueryWorkspaceSnapshot(
            workspace_key="",
            workspace_id=None,
            state=None,
            pointer_attached=False,
            generation=1,
            config_generation="",
        )
    workspace_id = UUID(str(row[0])) if row[0] is not None else None
    generation = int(row[1] or 1)
    workspace_key = str(row[2] or "")
    state = str(row[3]) if row[3] is not None else None
    config_generation = (
        mapping_config_generation(
            workspace_key=workspace_key,
            pointer_generation=generation,
            chunker_snapshot=graph_chunker_config_snapshot(),
            entity_rules_generation=policy.entity_rules_generation,
            extraction_policy_hash=policy.extraction_policy_hash,
        )
        if workspace_key
        else ""
    )
    return QueryWorkspaceSnapshot(
        workspace_key=workspace_key,
        workspace_id=workspace_id,
        state=state,
        pointer_attached=workspace_id is not None,
        generation=generation,
        config_generation=config_generation,
    )


def resolve_graph_leads(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    leads: GraphLeadSet,
    snapshot: QueryWorkspaceSnapshot,
) -> ResolveOutcome:
    """Resolve clamped leads through maps, then batch-recheck and drop wholly.

    Args:
        connection: Idle login connection.
        caller: Server-derived identity.
        leads: Application-clamped structured leads.
        snapshot: Active workspace snapshot already validated as queryable.

    Returns:
        Surviving candidates, bounded paths, and repair diagnostics.

    Side Effects:
        One ``app_api`` retrieval transaction. No Hybrid search.

    Raises:
        GraphResolverError: If the caller is disabled.
    """

    returned = returned_graph_candidate_count(leads)
    vendor_chunk_ids = _vendor_chunk_ids(leads)
    entity_names = tuple(item.entity_name for item in leads.entities)
    with retrieval_transaction(
        connection,
        caller=caller,
        profile="low",
        apply_hnsw=False,
    ):
        chunk_rows = _load_chunk_maps(
            connection,
            caller=caller,
            snapshot=snapshot,
            vendor_chunk_ids=vendor_chunk_ids,
        )
        evidence_rows = _load_evidence_maps(
            connection,
            caller=caller,
            snapshot=snapshot,
            entity_names=entity_names,
        )
    candidates, paths, dropped, diagnostics = _apply_whole_candidate_survival(
        leads,
        chunk_rows=chunk_rows,
        evidence_rows=evidence_rows,
    )
    return ResolveOutcome(
        candidates=candidates,
        paths=paths,
        dropped=dropped,
        diagnostics=diagnostics,
        returned_candidates=returned,
        supported_candidates=len(candidates),
    )


def visibility_counts(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    relevant_version_ids: tuple[UUID, ...] | None = None,
) -> VisibilityCounts:
    """Return authorized partial-readiness and ACL-blindness counts.

    Args:
        connection: Idle login connection.
        caller: Server-derived identity.
        relevant_version_ids: Optional Hybrid-hit version filter. ``None``
            counts every authorized matching current version.

    Returns:
        Counts that omit unauthorized restricted documents.

    Side Effects:
        One ``app_api`` retrieval transaction.
    """

    with retrieval_transaction(
        connection,
        caller=caller,
        profile="low",
        apply_hnsw=False,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT partial_readiness_count, acl_blindness_count
                FROM app.graph_visibility_counts(
                  %s::uuid, %s::text, %s::bigint, %s::uuid[]
                )
                """,
                (
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    list(relevant_version_ids) if relevant_version_ids else None,
                ),
            )
            row = cursor.fetchone()
    if row is None:
        return VisibilityCounts(partial_readiness_count=0, acl_blindness_count=0)
    return VisibilityCounts(
        partial_readiness_count=int(row[0] or 0),
        acl_blindness_count=int(row[1] or 0),
    )


def inspect_graph(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    snapshot: QueryWorkspaceSnapshot,
    entity_keys: tuple[str, ...] = (),
    document_id: UUID | None = None,
    depth: int = 3,
) -> GraphInspectResult:
    """Inspect authorized graph objects through the identical resolver.

    Args:
        connection: Idle login connection.
        caller: Server-derived identity.
        snapshot: Queryable workspace snapshot.
        entity_keys: Application entity keys, at most 12.
        document_id: Optional authorized document seed.
        depth: Hop cap, clamped to 3.

    Returns:
        At most 200 rows plus locators. Native prose is omitted.

    Raises:
        GraphResolverError: If more than 12 entity keys are supplied.

    Side Effects:
        One ``app_api`` transaction with SQL ``statement_timeout='3s'``.
    """

    if len(entity_keys) > 12:
        raise GraphResolverError("inspect_seed_exceeds_limit")
    capped_depth = max(1, min(depth, 3))
    with retrieval_transaction(
        connection,
        caller=caller,
        profile="low",
        apply_hnsw=False,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT object_type, object_id, chunk_id, document_id,
                       version_id, support, hop
                FROM app.inspect_graph_neighborhood(
                  %s::uuid, %s::text, %s::bigint, %s, %s, %s::text[],
                  %s::uuid, %s, %s
                )
                """,
                (
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    snapshot.workspace_key,
                    snapshot.config_generation,
                    list(entity_keys),
                    document_id,
                    capped_depth,
                    200,
                ),
            )
            rows = cursor.fetchall()
            locators = _load_locators(
                cursor,
                caller=caller,
                chunk_ids=tuple(UUID(str(row[2])) for row in rows),
            )
    nodes = tuple(
        GraphInspectNode(
            object_type=str(row[0]),
            object_id=str(row[1]),
            chunk_id=UUID(str(row[2])),
            document_id=UUID(str(row[3])),
            version_id=UUID(str(row[4])),
            support=float(row[5]),
            hop=int(row[6]),
        )
        for row in rows
    )
    return GraphInspectResult(
        nodes=nodes,
        locators=locators,
        limitations=(),
        row_count=len(nodes),
        depth=capped_depth,
    )


def enqueue_query_repairs(
    connection: psycopg.Connection,
    *,
    snapshot: QueryWorkspaceSnapshot,
    dropped: tuple[dict[str, str], ...],
) -> None:
    """Enqueue one bounded repair job per dropped lead. Never Hybrid.

    Args:
        connection: Idle login connection.
        snapshot: Workspace/config generation for the unique repair key.
        dropped: Repair payloads from whole-candidate drops.

    Side Effects:
        Upserts repair rows through a security-definer RPC.
    """

    if not dropped:
        return
    with connection.transaction():
        connection.execute("SET LOCAL ROLE app_api")
        with connection.cursor() as cursor:
            for item in dropped:
                cursor.execute(
                    """
                    SELECT app.enqueue_graph_map_repair(
                      %s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        snapshot.workspace_key,
                        item.get("document_id") or None,
                        item.get("version_id") or None,
                        item["object_type"],
                        item["object_id"],
                        GRAPH_QUERY_REPAIR_MAP_KIND,
                        snapshot.config_generation,
                        item["reason"],
                    ),
                )


def record_survival_sample(
    connection: psycopg.Connection,
    *,
    ratio: float,
    mode: str,
) -> RollingSurvivalWindow:
    """Append one survival sample and return the rolling 20-sample window.

    Args:
        connection: Idle login connection.
        ratio: ``graph_survival_ratio`` in ``[0, 1]``.
        mode: Query mode label.

    Returns:
        Window mean and whether 20 samples sit below 0.80.

    Side Effects:
        Inserts one row and deletes older samples beyond 20.
    """

    with connection.transaction():
        connection.execute("SET LOCAL ROLE app_api")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.graph_survival_samples (survival_ratio, query_mode)
                VALUES (%s, %s)
                """,
                (ratio, mode),
            )
            cursor.execute(
                """
                DELETE FROM app.graph_survival_samples
                WHERE id NOT IN (
                  SELECT id
                  FROM app.graph_survival_samples
                  ORDER BY recorded_at DESC, id DESC
                  LIMIT %s
                )
                """,
                (GRAPH_SURVIVAL_ROLLING_WINDOW,),
            )
            cursor.execute(
                """
                SELECT survival_ratio
                FROM app.graph_survival_samples
                ORDER BY recorded_at DESC, id DESC
                LIMIT %s
                """,
                (GRAPH_SURVIVAL_ROLLING_WINDOW,),
            )
            values = [float(row[0]) for row in cursor.fetchall()]
    count = len(values)
    mean = sum(values) / count if count else None
    return RollingSurvivalWindow(
        sample_count=count,
        mean=mean,
        below_alert_threshold=(
            count >= GRAPH_SURVIVAL_ROLLING_WINDOW
            and mean is not None
            and mean < GRAPH_SURVIVAL_ROLLING_ALERT_THRESHOLD
        ),
    )


def load_canonical_locators(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    chunk_ids: tuple[UUID, ...],
) -> tuple[GraphCanonicalLocator, ...]:
    """Fetch canonical locators for surviving chunk IDs.

    Args:
        connection: Idle login connection.
        caller: Server-derived identity.
        chunk_ids: Authorized chunk IDs after resolver survival.

    Returns:
        Locators without citation prose.

    Side Effects:
        One ``app_api`` retrieval transaction.
    """

    if not chunk_ids:
        return ()
    with retrieval_transaction(
        connection,
        caller=caller,
        profile="low",
        apply_hnsw=False,
    ):
        with connection.cursor() as cursor:
            return _load_locators(cursor, caller=caller, chunk_ids=chunk_ids)


def expand_bounded_paths(
    statements: tuple[ResolvedStatement, ...],
    *,
    max_hops: int = ADAPTER_MAX_HOPS,
    max_paths: int = ADAPTER_MAX_PATHS,
) -> tuple[GraphPath, ...]:
    """Expand surviving statements into at most six paths of at most three hops.

    Args:
        statements: Surviving directed statements.
        max_hops: Application hop cap.
        max_paths: Application path cap.

    Returns:
        Stable lexicographic paths. Native names are not returned.
    """

    adjacency: dict[str, list[ResolvedStatement]] = defaultdict(list)
    ordered = tuple(sorted(statements, key=lambda item: item.statement_id))
    for item in ordered:
        adjacency[item.src_vendor].append(item)
    collected: list[tuple[ResolvedStatement, ...]] = []
    for start in sorted(adjacency):
        queue: deque[tuple[str, tuple[ResolvedStatement, ...]]] = deque(((start, ()),))
        while queue:
            node, path = queue.popleft()
            if len(path) >= max_hops:
                continue
            for edge in adjacency.get(node, ()):
                if edge in path:
                    continue
                new_path = (*path, edge)
                collected.append(new_path)
                if len(new_path) < max_hops:
                    queue.append((edge.tgt_vendor, new_path))
                if len(collected) >= max_paths * 8:
                    break
            if len(collected) >= max_paths * 8:
                break
        if len(collected) >= max_paths * 8:
            break
    ranked = sorted(
        collected,
        key=lambda path: tuple(item.statement_id for item in path),
    )[:max_paths]
    return tuple(
        GraphPath(
            statement_ids=tuple(item.statement_id for item in path),
            path_edge_ids=tuple(
                item.path_edge_id for item in path if item.path_edge_id
            ),
            hops=len(path),
            canonical_chunk_ids=tuple(
                dict.fromkeys(chunk_id for item in path for chunk_id in item.chunk_ids)
            ),
        )
        for path in ranked
    )


def limitation_for_visibility(
    counts: VisibilityCounts,
) -> tuple[GraphLimitation, ...]:
    """Build partial-readiness and authorized-only blindness signals.

    Args:
        counts: Authorized visibility counts.

    Returns:
        Limitations with counts. Unauthorized restricted documents are absent.
    """

    items: list[GraphLimitation] = []
    if counts.partial_readiness_count:
        items.append(
            GraphLimitation(
                code=GraphLimitationCode.GRAPH_PARTIAL_READINESS,
                count=counts.partial_readiness_count,
            )
        )
    if counts.acl_blindness_count:
        items.append(
            GraphLimitation(
                code=GraphLimitationCode.GRAPH_ACL_BLINDNESS,
                count=counts.acl_blindness_count,
            )
        )
    return tuple(items)


def _vendor_chunk_ids(leads: GraphLeadSet) -> tuple[str, ...]:
    """Collect unique vendor chunk tokens from leads.

    Args:
        leads: Clamped lead set.

    Returns:
        Ordered unique vendor chunk ids.
    """

    ordered: list[str] = []
    seen: set[str] = set()
    for item in (*leads.entities, *leads.relations):
        for token in item.source_ids:
            if token in seen:
                continue
            seen.add(token)
            ordered.append(token)
    for chunk in leads.chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        ordered.append(chunk.chunk_id)
    return tuple(ordered)


def _load_chunk_maps(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    snapshot: QueryWorkspaceSnapshot,
    vendor_chunk_ids: tuple[str, ...],
) -> tuple[_MapRow, ...]:
    """Join vendor chunk tokens through the chunk map and ACL/current checks.

    Args:
        connection: Open ``app_api`` transaction.
        caller: Server-derived identity.
        snapshot: Expected workspace/config generation.
        vendor_chunk_ids: Vendor internal chunk tokens.

    Returns:
        Map rows. Unauthorized hits are marked unsurvived without names.
    """

    if not vendor_chunk_ids:
        return ()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              req.vendor_id,
              lcm.chunk_id,
              c.document_id,
              lcm.version_id,
              COALESCE(lcm.support, 0),
              (
                lcm.chunk_id IS NOT NULL
                AND lcm.workspace_key = %s
                AND lcm.config_generation = %s
                AND lcm.support >= %s
                AND c.deleted_at IS NULL
                AND d.deleted_at IS NULL
                AND dv.deleted_at IS NULL
                AND d.current_version_id IS NOT DISTINCT FROM c.version_id
                AND d.graph_eligible IS TRUE
                AND dv.graph_eligible IS TRUE
                AND dv.status = %s
                AND app.caller_can_read_document(%s::uuid, %s::text, d.id)
              ) AS survived,
              CASE
                WHEN lcm.chunk_id IS NULL THEN 'unmapped'
                WHEN lcm.config_generation IS DISTINCT FROM %s THEN 'stale_config'
                WHEN COALESCE(lcm.support, 0) < %s THEN 'below_threshold'
                WHEN c.deleted_at IS NOT NULL
                  OR d.deleted_at IS NOT NULL
                  OR dv.deleted_at IS NOT NULL THEN 'deleted'
                WHEN d.current_version_id IS DISTINCT FROM c.version_id
                  THEN 'stale_pointer'
                WHEN d.graph_eligible IS NOT TRUE
                  OR dv.graph_eligible IS NOT TRUE THEN 'ineligible'
                WHEN dv.status IS DISTINCT FROM %s THEN 'not_ready'
                WHEN NOT app.caller_can_read_document(
                  %s::uuid, %s::text, d.id
                ) THEN 'unauthorized'
                ELSE ''
              END AS drop_reason
            FROM unnest(%s::text[]) AS req(vendor_id)
            LEFT JOIN app.lightrag_chunk_map AS lcm
              ON lcm.lightrag_chunk_id = req.vendor_id
             AND lcm.workspace_key = %s
            LEFT JOIN app.document_chunks AS c ON c.id = lcm.chunk_id
            LEFT JOIN app.documents AS d ON d.id = c.document_id
            LEFT JOIN app.document_versions AS dv ON dv.id = c.version_id
            """,
            (
                snapshot.workspace_key,
                snapshot.config_generation,
                _SUPPORT_MIN,
                _READY_STATUS,
                caller.rpc_user_id(),
                caller.rpc_role(),
                snapshot.config_generation,
                _SUPPORT_MIN,
                _READY_STATUS,
                caller.rpc_user_id(),
                caller.rpc_role(),
                list(vendor_chunk_ids),
                snapshot.workspace_key,
            ),
        )
        rows = cursor.fetchall()
    return tuple(
        _MapRow(
            vendor_key=str(row[0]),
            object_type="chunk",
            object_id=str(row[1]) if row[1] is not None else "",
            chunk_id=UUID(str(row[1])) if row[1] is not None else None,
            document_id=UUID(str(row[2])) if row[2] is not None else None,
            version_id=UUID(str(row[3])) if row[3] is not None else None,
            support=float(row[4] or 0.0),
            src_vendor="",
            tgt_vendor="",
            vendor_name="",
            path_edge_id="",
            survived=bool(row[5]),
            drop_reason=str(row[6] or "unmapped"),
        )
        for row in rows
    )


def _load_evidence_maps(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    snapshot: QueryWorkspaceSnapshot,
    entity_names: tuple[str, ...],
) -> tuple[_MapRow, ...]:
    """Load entity/statement/path evidence rows for the active workspace.

    Args:
        connection: Open ``app_api`` transaction.
        caller: Server-derived identity.
        snapshot: Expected workspace/config generation.
        entity_names: Vendor entity names from leads. Unused in SQL; kept
            so callers pass the same lead set used for whole-candidate checks.

    Returns:
        Surviving and unsurviving evidence rows. Unauthorized rows look
        unmapped to the caller.
    """

    del entity_names
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              gem.graph_object_type,
              gem.graph_object_id,
              gem.chunk_id,
              c.document_id,
              gem.version_id,
              COALESCE(gem.support, 0),
              COALESCE(gem.provenance ->> 'src', ''),
              COALESCE(gem.provenance ->> 'tgt', ''),
              COALESCE(gem.provenance ->> 'vendor_name', ''),
              COALESCE(gem.provenance ->> 'statement_id', ''),
              (
                gem.support >= %s
                AND gem.config_generation = %s
                AND gem.workspace_key = %s
                AND c.deleted_at IS NULL
                AND d.deleted_at IS NULL
                AND dv.deleted_at IS NULL
                AND d.current_version_id IS NOT DISTINCT FROM c.version_id
                AND d.graph_eligible IS TRUE
                AND dv.graph_eligible IS TRUE
                AND dv.status = %s
                AND app.caller_can_read_document(%s::uuid, %s::text, d.id)
              ) AS survived
            FROM app.graph_evidence_map AS gem
            INNER JOIN app.document_chunks AS c ON c.id = gem.chunk_id
            INNER JOIN app.documents AS d ON d.id = c.document_id
            INNER JOIN app.document_versions AS dv ON dv.id = c.version_id
            WHERE gem.workspace_key = %s
              AND gem.config_generation = %s
              AND gem.pipeline_version = 'graph_pipeline_v1'
            """,
            (
                _SUPPORT_MIN,
                snapshot.config_generation,
                snapshot.workspace_key,
                _READY_STATUS,
                caller.rpc_user_id(),
                caller.rpc_role(),
                snapshot.workspace_key,
                snapshot.config_generation,
            ),
        )
        rows = cursor.fetchall()
    return tuple(
        _MapRow(
            vendor_key=str(row[8] or row[1]),
            object_type=str(row[0]),
            object_id=str(row[1]),
            chunk_id=UUID(str(row[2])),
            document_id=UUID(str(row[3])),
            version_id=UUID(str(row[4])),
            support=float(row[5] or 0.0),
            src_vendor=str(row[6] or ""),
            tgt_vendor=str(row[7] or ""),
            vendor_name=str(row[8] or ""),
            path_edge_id=str(row[9] or ""),
            survived=bool(row[10]),
            drop_reason="" if row[10] else "unmapped",
        )
        for row in rows
    )


def _apply_whole_candidate_survival(
    leads: GraphLeadSet,
    *,
    chunk_rows: tuple[_MapRow, ...],
    evidence_rows: tuple[_MapRow, ...],
) -> tuple[
    tuple[GraphResolvedCandidate, ...],
    tuple[GraphPath, ...],
    tuple[dict[str, str], ...],
    tuple[str, ...],
]:
    """Drop any native lead that fails a required mapping or recheck.

    Args:
        leads: Clamped vendor leads.
        chunk_rows: Chunk-map joins.
        evidence_rows: Evidence-map joins.

    Returns:
        Candidates, paths, repair payloads, and diagnostics.
    """

    chunk_by_vendor = {row.vendor_key: row for row in chunk_rows}
    entities_by_name = {
        row.vendor_name: row
        for row in evidence_rows
        if row.object_type == "entity" and row.survived and row.vendor_name
    }
    statements = [
        row for row in evidence_rows if row.object_type == "statement" and row.survived
    ]
    path_id_by_statement: dict[str, str] = {}
    for row in evidence_rows:
        if row.object_type != "path_edge" or not row.survived:
            continue
        statement_id = row.path_edge_id
        if statement_id:
            path_id_by_statement[statement_id] = row.object_id

    candidates: list[GraphResolvedCandidate] = []
    dropped: list[dict[str, str]] = []
    diagnostics: list[str] = []
    resolved_statements: list[ResolvedStatement] = []

    if leads.relations:
        for relation in leads.relations:
            required_chunks = [
                chunk_by_vendor.get(token) for token in relation.source_ids
            ]
            statement = _matching_statement(
                relation.src_id, relation.tgt_id, statements
            )
            src_entity = entities_by_name.get(relation.src_id)
            tgt_entity = entities_by_name.get(relation.tgt_id)
            failed = [
                item for item in required_chunks if item is None or not item.survived
            ]
            if (
                not relation.source_ids
                or failed
                or statement is None
                or src_entity is None
                or tgt_entity is None
                or statement.chunk_id is None
                or statement.document_id is None
                or statement.version_id is None
            ):
                diagnostics.append("candidate_dropped")
                dropped.append(
                    _repair_payload(
                        object_type="statement",
                        object_id=f"{relation.src_id}|{relation.tgt_id}"[:512],
                        rows=(*required_chunks, statement, src_entity, tgt_entity),
                    )
                )
                continue
            chunk_ids = tuple(
                item.chunk_id
                for item in (*required_chunks, statement)
                if item is not None and item.chunk_id is not None
            )
            unique_chunks = tuple(dict.fromkeys(chunk_ids))
            support = min(
                item.support
                for item in (*required_chunks, statement, src_entity, tgt_entity)
                if item is not None
            )
            path_id = path_id_by_statement.get(statement.object_id, "")
            candidates.append(
                GraphResolvedCandidate(
                    kind="statement",
                    object_id=statement.object_id,
                    canonical_chunk_ids=unique_chunks,
                    document_id=statement.document_id,
                    version_id=statement.version_id,
                    support=support,
                    confidence=support,
                )
            )
            resolved_statements.append(
                ResolvedStatement(
                    statement_id=statement.object_id,
                    path_edge_id=path_id,
                    src_vendor=relation.src_id,
                    tgt_vendor=relation.tgt_id,
                    chunk_ids=unique_chunks,
                    document_id=statement.document_id,
                    version_id=statement.version_id,
                    support=support,
                )
            )
    else:
        for entity in leads.entities:
            required_chunks = [
                chunk_by_vendor.get(token) for token in entity.source_ids
            ]
            mapped = entities_by_name.get(entity.entity_name)
            failed = [
                item for item in required_chunks if item is None or not item.survived
            ]
            if (
                not entity.source_ids
                or failed
                or mapped is None
                or mapped.chunk_id is None
                or mapped.document_id is None
                or mapped.version_id is None
            ):
                diagnostics.append("candidate_dropped")
                dropped.append(
                    _repair_payload(
                        object_type="entity",
                        object_id=entity.entity_name[:512],
                        rows=(*required_chunks, mapped),
                    )
                )
                continue
            chunk_ids = tuple(
                item.chunk_id
                for item in (*required_chunks, mapped)
                if item is not None and item.chunk_id is not None
            )
            support = min(
                item.support for item in (*required_chunks, mapped) if item is not None
            )
            candidates.append(
                GraphResolvedCandidate(
                    kind="entity",
                    object_id=mapped.object_id,
                    canonical_chunk_ids=tuple(dict.fromkeys(chunk_ids)),
                    document_id=mapped.document_id,
                    version_id=mapped.version_id,
                    support=support,
                    confidence=support,
                )
            )

    paths = expand_bounded_paths(tuple(resolved_statements))
    unique_candidates = tuple(
        sorted(candidates, key=lambda item: (item.kind, item.object_id))
    )
    return unique_candidates, paths, tuple(dropped), tuple(dict.fromkeys(diagnostics))


def _repair_payload(
    *,
    object_type: str,
    object_id: str,
    rows: tuple[_MapRow | None, ...],
) -> dict[str, str]:
    """Build one repair upsert payload without document titles.

    Args:
        object_type: Application object kind.
        object_id: Stable object or vendor pair key.
        rows: Map rows that may carry canonical document/version IDs.

    Returns:
        Keys for ``enqueue_graph_map_repair``. Missing IDs stay empty.
    """

    document_id = ""
    version_id = ""
    for row in rows:
        if row is None:
            continue
        if row.document_id is not None and not document_id:
            document_id = str(row.document_id)
        if row.version_id is not None and not version_id:
            version_id = str(row.version_id)
    return {
        "object_type": object_type,
        "object_id": object_id,
        "reason": "candidate_dropped",
        "document_id": document_id,
        "version_id": version_id,
    }


def _matching_statement(
    src: str,
    tgt: str,
    statements: list[_MapRow],
) -> _MapRow | None:
    """Find a surviving statement whose provenance endpoints match.

    Args:
        src: Vendor source entity name.
        tgt: Vendor target entity name.
        statements: Surviving statement rows.

    Returns:
        Matching statement, or ``None``.
    """

    for item in sorted(statements, key=lambda row: row.object_id):
        if item.src_vendor == src and item.tgt_vendor == tgt:
            return item
    return None


def _load_locators(
    cursor: psycopg.Cursor,
    *,
    caller: CallerContext,
    chunk_ids: tuple[UUID, ...],
) -> tuple[GraphCanonicalLocator, ...]:
    """Load canonical locators inside an open ``app_api`` transaction.

    Args:
        cursor: Open cursor.
        caller: Server-derived identity.
        chunk_ids: Chunk IDs to fetch, already unique.

    Returns:
        Locators. Missing/unauthorized IDs are omitted.
    """

    unique: list[UUID] = []
    seen: set[UUID] = set()
    for chunk_id in chunk_ids:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        unique.append(chunk_id)
    if not unique:
        return ()
    locators: list[GraphCanonicalLocator] = []
    for start in range(0, len(unique), 75):
        batch = unique[start : start + 75]
        cursor.execute(
            """
            SELECT chunk_id, document_id, version_id, page_number,
                   section_path, provenance
            FROM app.fetch_authorized_chunk_context(
              %s::uuid, %s::text, %s::bigint, %s::uuid[]
            )
            """,
            (
                caller.rpc_user_id(),
                caller.rpc_role(),
                caller.rpc_authorization_version(),
                batch,
            ),
        )
        for row in cursor.fetchall():
            sheet_name, range_ref, source_url = locators_from_provenance(row[5])
            section = row[4]
            if isinstance(section, list):
                section_path = tuple(str(item) for item in section)
            else:
                section_path = ()
            locators.append(
                GraphCanonicalLocator(
                    chunk_id=UUID(str(row[0])),
                    document_id=UUID(str(row[1])),
                    version_id=UUID(str(row[2])),
                    page_number=int(row[3]) if row[3] is not None else None,
                    section_path=section_path,
                    sheet_name=sheet_name,
                    range_ref=range_ref,
                    source_url=source_url,
                )
            )
    by_id = {item.chunk_id: item for item in locators}
    return tuple(by_id[item] for item in unique if item in by_id)
