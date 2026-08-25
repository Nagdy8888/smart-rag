"""Map vendor graph objects to canonical passages and mark Graph Ready.

Lives under ``jobs/`` so worker code can call ``GraphMappingService`` without
embedding mapping-table names. Hybrid and rerank are injected and counted.
Repair never performs query-time Hybrid and never lowers thresholds.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast
from uuid import UUID

import psycopg

from smart_rag_core.jobs import graph_mapping_persist as persist
from smart_rag_core.jobs.entity_rule_service import load_extraction_policy
from smart_rag_core.jobs.exceptions import GraphMappingError
from smart_rag_core.jobs.graph_writer import GraphWriterGuard, load_workspace_row
from smart_rag_core.jobs.limits import (
    LOCAL_DEMO_MAX_MAPPING_ENTITIES,
    LOCAL_DEMO_MAX_MAPPING_RELATIONS,
    MAPPING_SUPPORT_MIN,
    MAX_MAPPING_ENTITIES,
    MAX_MAPPING_RELATIONS,
    MAX_MAPPING_RERANK_POOL,
    MAX_MAPPING_VENDOR_CHUNKS,
)
from smart_rag_core.retrieval.graph import (
    GRAPH_FIELD_SEP,
    SourceIdContractError,
    canonical_passage_source_id,
    graph_chunker_config_snapshot,
    parse_canonical_passage_source_id,
    strip_graph_source_envelope,
)
from smart_rag_core.retrieval.graph_mapping import (
    CanonicalPassage,
    ChunkMatch,
    CoverageSlice,
    EntityRuleView,
    GraphObjectType,
    MappingBudgetError,
    MappingCallCounts,
    ObjectMapping,
    SupportRerankFn,
    assert_mapping_budget,
    assign_hybrid_support,
    canonical_entity_key,
    canonical_source_identity,
    evaluate_coverage_gates,
    expected_passage_basename,
    graph_path_edge_id,
    graph_statement_id,
    internal_chunk_key,
    mapping_config_generation,
    mapping_content_digest,
    normalize_relation_label,
    ordered_statement_endpoints,
    parse_object_source_ids,
    resolve_entity_name,
    run_support_rerank,
    stitch_overlapping_texts,
)
from smart_rag_core.retrieval.profiles import MAX_NORMALIZED_QUERY_CHARS
from smart_rag_core.retrieval.rerank import RerankPassage, excerpt_text
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.schema.enums import GraphWorkspaceState


class GraphVendorReader(Protocol):
    """Adapter-owned vendor catalog reads. Implementations live on the adapter."""

    async def vendor_document_status(self, document_id: str) -> Any:
        """Return vendor status for one canonical version ID."""

        ...

    async def list_vendor_doc_chunks(
        self,
        *,
        workspace: str,
        document_id: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return vendor document chunks for one source id."""

        ...

    async def list_vendor_doc_chunks_for_ids(
        self,
        *,
        workspace: str,
        document_ids: tuple[str, ...],
        limit: int,
    ) -> list[dict[str, object]]:
        """Return vendor document chunks for an exact source-ID set."""

        ...

    async def list_vendor_entity_joins(
        self,
        *,
        workspace: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return entity-to-chunk joins for one workspace."""

        ...

    async def list_vendor_relation_joins(
        self,
        *,
        workspace: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return relation-to-chunk joins for one workspace."""

        ...

    async def list_vendor_graph_nodes(
        self,
        *,
        workspace: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return graph nodes including source_id properties."""

        ...

    async def list_vendor_graph_edges(
        self,
        *,
        workspace: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return graph edges including structured relation fields."""

        ...


@dataclass(frozen=True, slots=True)
class MappingOutcome:
    """Result of one document mapping attempt.

    Attributes:
        ready: True only when every Graph Ready gate passed.
        maps_verified: Coverage gates passed, including pending-switch maps.
        reason: Machine-readable failure, empty on success.
        workspace_state: Workspace state after the attempt.
        hybrid_calls: Hybrid retrieve count (0 or 1).
        rerank_calls: Support rerank count (0 or 1).
        coverage: Per-language/type slices persisted as telemetry.
        pending_switch: True when maps are verified but current_version waits.
    """

    ready: bool
    maps_verified: bool
    reason: str
    workspace_state: str
    hybrid_calls: int
    rerank_calls: int
    coverage: tuple[CoverageSlice, ...] = ()
    pending_switch: bool = False


@dataclass
class _ChunkMapRow:
    """Internal vendor-chunk mapping row used before persistence."""

    vendor_chunk_id: str
    vendor_doc_id: str
    match: ChunkMatch | None
    internal_key: str
    vendor_piece_ids: tuple[str, ...] = ()


def _vendor_chunk_order(raw: Mapping[str, object]) -> int:
    """Return LightRAG ``chunk_order_index`` for stitch order.

    Args:
        raw: Vendor chunk row.

    Returns:
        Non-negative order, or ``0`` when the field is missing.
    """

    value = raw.get("chunk_order_index")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


class GraphMappingService:
    """Enumerate vendor objects, map them, and commit Graph Ready in one txn."""

    def __init__(
        self,
        connection: psycopg.Connection,
        *,
        vendor_reader: GraphVendorReader,
        writer: GraphWriterGuard,
        hybrid_retrieve: Any | None = None,
        support_rerank: SupportRerankFn | None = None,
        max_entities: int = MAX_MAPPING_ENTITIES,
        max_relations: int = MAX_MAPPING_RELATIONS,
    ) -> None:
        """Bind application connection, vendor reader, and optional retrievers.

        Args:
            connection: ``app_worker`` connection for canonical writes.
            vendor_reader: Adapter catalog reads (SET ROLE ``app_lightrag``).
            writer: Occupied writer guard on the same connection.
            hybrid_retrieve: Optional ``(query, version_id) -> HybridRunResult``.
            support_rerank: Optional OpenAI-only support rerank batch.
            max_entities: Effective entity enumeration cap. Production default
                is 200; the fixed local synthetic-demo ceiling is 2,000.
            max_relations: Effective relation enumeration cap. Production
                default is 200; the fixed local synthetic-demo ceiling is 1,800.

        Raises:
            ValueError: If an injected cap is non-positive or exceeds the
                approved local synthetic-demo ceiling.
        """

        if not 1 <= max_entities <= LOCAL_DEMO_MAX_MAPPING_ENTITIES:
            raise ValueError("invalid_mapping_entity_limit")
        if not 1 <= max_relations <= LOCAL_DEMO_MAX_MAPPING_RELATIONS:
            raise ValueError("invalid_mapping_relation_limit")
        self._connection = connection
        self._vendor = vendor_reader
        self._writer = writer
        self._hybrid_retrieve = hybrid_retrieve
        self._support_rerank = support_rerank
        self._max_entities = max_entities
        self._max_relations = max_relations
        self.counts = MappingCallCounts()
        self._map_workspace_key: str | None = None

    def set_map_workspace_key(self, workspace_key: str | None) -> None:
        """Bind maps and vendor reads to a candidate or live workspace.

        Args:
            workspace_key: Isolated rebuild key, or ``None`` to use the
                writer lock workspace.
        """

        stripped = workspace_key.strip() if workspace_key else None
        self._map_workspace_key = stripped or None

    def _mapping_workspace_key(self) -> str:
        """Return the workspace maps and vendor reads use for this job.

        Returns:
            Candidate rebuild key when isolating, otherwise the writer key.
        """

        return self._map_workspace_key or self._writer.workspace_key

    async def map_after_vendor_success(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
    ) -> MappingOutcome:
        """Map one processed vendor document and maybe mark Graph Ready.

        Args:
            document_id: Canonical document id.
            version_id: Canonical version used as the vendor document id.

        Returns:
            Mapping outcome. Job completion is the caller's concern.

        Side Effects:
            May upsert maps, repair rows, telemetry, version status, and
            workspace state. Commits one application transaction at the end
            of persistence. Does not call Hybrid during repair.
        """

        self.counts = MappingCallCounts()
        try:
            return await self._map_document(
                document_id=document_id,
                version_id=version_id,
            )
        except MappingBudgetError as exc:
            self._enqueue_repair_only(
                document_id=document_id,
                version_id=version_id,
                reason=str(exc),
            )
            return self._failed_outcome(str(exc))
        except GraphMappingError as exc:
            self._enqueue_repair_only(
                document_id=document_id,
                version_id=version_id,
                reason=exc.reason,
            )
            return self._failed_outcome(exc.reason)

    def _failed_outcome(self, reason: str) -> MappingOutcome:
        """Return a non-ready outcome that keeps the workspace updating.

        Args:
            reason: Machine-readable mapping failure.

        Returns:
            Failed mapping outcome.
        """

        return MappingOutcome(
            ready=False,
            maps_verified=False,
            reason=reason,
            workspace_state=GraphWorkspaceState.UPDATING.value,
            hybrid_calls=self.counts.hybrid_retrieve,
            rerank_calls=self.counts.support_rerank,
        )

    async def repair_stored(
        self,
        *,
        workspace_key: str,
        config_generation: str,
    ) -> int:
        """Re-check stored maps without Hybrid or threshold changes.

        Args:
            workspace_key: Workspace that owns the repair keys.
            config_generation: Mapping config generation.

        Returns:
            Count of still-failing repair rows.

        Raises:
            GraphMappingError: If a Hybrid/rerank callback is attached.
        """

        if self._hybrid_retrieve is not None or self._support_rerank is not None:
            raise GraphMappingError("repair_must_not_query_hybrid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM app.graph_map_repair_jobs
                WHERE workspace_key = %s
                  AND config_generation = %s
                  AND status = 'pending'::app.job_status
                """,
                (workspace_key, config_generation),
            )
            row = cursor.fetchone()
        return int(row[0]) if row is not None else 0

    async def _map_document(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
    ) -> MappingOutcome:
        """Run vendor enumeration, mapping, and the Graph Ready transaction.

        Args:
            document_id: Canonical document.
            version_id: Canonical version used as the vendor document id.

        Returns:
            Mapping outcome after one application transaction.
        """

        workspace_key = self._mapping_workspace_key()
        policy = load_extraction_policy(self._connection)
        config_generation = mapping_config_generation(
            workspace_key=workspace_key,
            pointer_generation=self._writer.load_pointer_generation(),
            chunker_snapshot=graph_chunker_config_snapshot(),
            entity_rules_generation=policy.entity_rules_generation,
            extraction_policy_hash=policy.extraction_policy_hash,
        )
        source_identity = canonical_source_identity(
            version_id=version_id,
            config_generation=config_generation,
        )
        canonicals = persist.load_canonical_passages(
            self._connection,
            version_id=version_id,
        )
        if not canonicals:
            raise GraphMappingError("graph_source_snapshot_mismatch")
        expected_source_ids = tuple(
            canonical_passage_source_id(
                version_id=version_id,
                chunk_id=item.chunk_id,
            )
            for item in canonicals
        )
        await self._assert_sources_processed(expected_source_ids)
        vendor_chunks = await self._vendor.list_vendor_doc_chunks_for_ids(
            workspace=workspace_key,
            document_ids=expected_source_ids,
            limit=MAX_MAPPING_VENDOR_CHUNKS + 1,
        )
        nodes = await self._vendor.list_vendor_graph_nodes(
            workspace=workspace_key,
            limit=self._max_entities + 1,
        )
        edges = await self._vendor.list_vendor_graph_edges(
            workspace=workspace_key,
            limit=self._max_relations + 1,
        )
        entity_joins = await self._vendor.list_vendor_entity_joins(
            workspace=workspace_key,
            limit=self._max_entities + 1,
        )
        relation_joins = await self._vendor.list_vendor_relation_joins(
            workspace=workspace_key,
            limit=self._max_relations + 1,
        )
        assert_mapping_budget(
            vendor_chunks=len(vendor_chunks),
            entities=len(nodes),
            relations=len(edges),
            hybrid_calls=0,
            rerank_calls=0,
            max_entities=self._max_entities,
            max_relations=self._max_relations,
        )
        in_version_chunks = [
            row
            for row in vendor_chunks
            if str(row.get("full_doc_id") or "") in expected_source_ids
        ]
        extra_sources = {
            str(row.get("full_doc_id") or "")
            for row in vendor_chunks
            if str(row.get("full_doc_id") or "") not in expected_source_ids
        }
        if extra_sources:
            raise GraphMappingError("graph_source_snapshot_mismatch")
        language = canonicals[0].language if canonicals else ""
        if not language:
            language = self._load_version_language(version_id)
        chunk_rows = self._map_exact_passages(
            in_version_chunks,
            canonicals,
            expected_source_ids=expected_source_ids,
            version_id=version_id,
            workspace_key=workspace_key,
            config_generation=config_generation,
        )
        known_chunk_ids = {
            row.vendor_chunk_id for row in chunk_rows if row.match is not None
        }
        known_chunk_ids.update(
            row.vendor_doc_id for row in chunk_rows if row.match is not None
        )
        for row in chunk_rows:
            if row.match is None:
                continue
            known_chunk_ids.update(row.vendor_piece_ids)
        assert_mapping_budget(
            vendor_chunks=len(vendor_chunks),
            entities=len(nodes),
            relations=len(edges),
            hybrid_calls=self.counts.hybrid_retrieve,
            rerank_calls=self.counts.support_rerank,
            max_entities=self._max_entities,
            max_relations=self._max_relations,
        )
        rules = persist.load_entity_rules(self._connection)
        chunk_by_vendor = {
            row.vendor_chunk_id: row for row in chunk_rows if row.match is not None
        }
        for row in chunk_rows:
            if row.match is None:
                continue
            chunk_by_vendor.setdefault(row.vendor_doc_id, row)
        objects: list[ObjectMapping] = []
        objects.extend(
            self._map_entities(
                nodes,
                entity_joins,
                chunk_by_vendor,
                known_chunk_ids,
                rules=rules,
                language=language,
            )
        )
        entity_keys = {
            item.provenance.get("vendor_name"): item.object_id
            for item in objects
            if item.available and item.object_type == "entity"
        }
        objects.extend(
            self._map_statements(
                edges,
                relation_joins,
                chunk_by_vendor,
                known_chunk_ids,
                entity_keys=entity_keys,
                language=language,
                version_id=version_id,
                relation_label_policy=policy.relation_label_policy,
            )
        )
        coverage = _coverage_slices(chunk_rows, objects, language=language)
        gates_ok, gate_reason = evaluate_coverage_gates(coverage)
        repairs = _repair_rows(chunk_rows, objects)
        if not gates_ok:
            return self._persist(
                document_id=document_id,
                version_id=version_id,
                workspace_key=workspace_key,
                language=language,
                config_generation=config_generation,
                source_identity=source_identity,
                chunk_rows=chunk_rows,
                objects=objects,
                coverage=coverage,
                repairs=repairs,
                ready=False,
                reason=gate_reason,
                expected_source_ids=expected_source_ids,
            )
        return self._persist(
            document_id=document_id,
            version_id=version_id,
            workspace_key=workspace_key,
            language=language,
            config_generation=config_generation,
            source_identity=source_identity,
            chunk_rows=chunk_rows,
            objects=objects,
            coverage=coverage,
            repairs=repairs,
            ready=True,
            reason="",
            expected_source_ids=expected_source_ids,
        )

    async def _assert_sources_processed(
        self,
        source_ids: tuple[str, ...],
    ) -> None:
        """Require every passage source to be processed with its basename.

        Args:
            source_ids: Deterministic ``{version_id}:{chunk_id}`` vendor IDs.

        Raises:
            GraphMappingError: If any source is missing, not processed, or
                uses the wrong opaque basename.
        """

        for source_id in source_ids:
            status = await self._vendor.vendor_document_status(source_id)
            if (
                status is None
                or str(getattr(status, "status", "")).lower() != "processed"
            ):
                raise GraphMappingError("vendor_not_processed")
            version_id, chunk_id = parse_canonical_passage_source_id(source_id)
            expected = expected_passage_basename(
                version_id=version_id,
                chunk_id=chunk_id,
            )
            raw_path = getattr(status, "file_path", None)
            if raw_path is None or not str(raw_path).strip():
                raise GraphMappingError("vendor_basename_missing")
            basename = str(raw_path).replace("\\", "/").rsplit("/", 1)[-1]
            if basename != expected:
                raise GraphMappingError("vendor_basename_mismatch")

    def _load_version_language(self, version_id: UUID) -> str:
        """Return the version language column.

        Args:
            version_id: Canonical version.

        Returns:
            Language code or empty string.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT language
                FROM app.document_versions
                WHERE id = %s
                """,
                (version_id,),
            )
            row = cursor.fetchone()
        if row is None or row[0] is None:
            return ""
        return str(row[0])

    def _map_exact_passages(
        self,
        vendor_chunks: Sequence[Mapping[str, object]],
        canonicals: Sequence[CanonicalPassage],
        *,
        expected_source_ids: tuple[str, ...],
        version_id: UUID,
        workspace_key: str,
        config_generation: str,
    ) -> list[_ChunkMapRow]:
        """Require a reconstructed-hash bijection between passages and sources.

        LightRAG may emit more than one overlapping vendor chunk per
        processed passage source. Those pieces are stitched in
        ``chunk_order_index`` order. The reconstructed, envelope-stripped,
        HTML-unescaped hash must equal the unescaped canonical passage.
        One map row is persisted per canonical passage (table PK is
        ``chunk_id``). Overlap piece IDs stay on the row so entity joins
        still resolve.

        Args:
            vendor_chunks: Vendor rows whose ``full_doc_id`` is a passage
                source ID.
            canonicals: Canonical passages in chunk order.
            expected_source_ids: Ordered source IDs matching ``canonicals``.
            version_id: Mapping version.
            workspace_key: Application workspace.
            config_generation: Mapping config digest.

        Returns:
            One mapped row per canonical passage.

        Raises:
            GraphMappingError: If any source is missing, empty, or the
                reconstructed hash does not match the passage.
        """

        by_source: dict[str, list[Mapping[str, object]]] = {}
        for raw in vendor_chunks:
            source_id = str(raw.get("full_doc_id") or "")
            by_source.setdefault(source_id, []).append(raw)
        by_chunk = {item.chunk_id: item for item in canonicals}
        rows: list[_ChunkMapRow] = []
        for source_id, canonical in zip(expected_source_ids, canonicals, strict=True):
            vendor_rows = sorted(
                by_source.get(source_id, []),
                key=_vendor_chunk_order,
            )
            if not vendor_rows:
                raise GraphMappingError("graph_source_snapshot_mismatch")
            piece_ids = tuple(
                str(raw.get("id") or "")
                for raw in vendor_rows
                if str(raw.get("id") or "")
            )
            if len(piece_ids) != len(vendor_rows) or not piece_ids[0]:
                raise GraphMappingError("graph_source_snapshot_mismatch")
            stitched = stitch_overlapping_texts(
                tuple(str(raw.get("content") or "") for raw in vendor_rows)
            )
            stripped = strip_graph_source_envelope(stitched)
            source_hash = mapping_content_digest(stripped)
            target_hash = mapping_content_digest(canonical.raw_text)
            if source_hash != target_hash:
                raise GraphMappingError("graph_source_snapshot_mismatch")
            parsed_version, parsed_chunk = parse_canonical_passage_source_id(source_id)
            if parsed_version != version_id or parsed_chunk != canonical.chunk_id:
                raise GraphMappingError("graph_source_snapshot_mismatch")
            if parsed_chunk not in by_chunk:
                raise GraphMappingError("graph_source_snapshot_mismatch")
            match = ChunkMatch(
                canonical=canonical,
                method="hash",
                score=1.0,
                source_hash=source_hash,
                target_hash=target_hash,
                source_span={"start": 0, "end": len(stripped)},
                target_span={"start": 0, "end": len(canonical.raw_text)},
            )
            vendor_chunk_id = piece_ids[0]
            rows.append(
                _ChunkMapRow(
                    vendor_chunk_id=vendor_chunk_id,
                    vendor_doc_id=source_id,
                    match=match,
                    internal_key=internal_chunk_key(
                        workspace_key=workspace_key,
                        config_generation=config_generation,
                        vendor_chunk_id=vendor_chunk_id,
                    ),
                    vendor_piece_ids=piece_ids,
                )
            )
        vendor_chunk_ids = [row.vendor_chunk_id for row in rows]
        if len(set(vendor_chunk_ids)) != len(vendor_chunk_ids):
            raise GraphMappingError("graph_source_snapshot_mismatch")
        return rows

    async def _assign_unresolved_support(
        self,
        unresolved: Sequence[Mapping[str, object]],
        chunk_rows: list[_ChunkMapRow],
        canonicals: Sequence[CanonicalPassage],
        *,
        version_id: UUID,
    ) -> None:
        """Run at most one Hybrid retrieve and one support rerank batch.

        Hybrid ``ranked_ids`` order and cap the support-rerank pool. Empty
        ranked IDs or fewer than two survivors skip rerank rather than
        scoring every canonical in the version.

        Args:
            unresolved: Vendor chunks still unmatched after hash/span/overlap.
            chunk_rows: Mutable per-chunk mapping rows.
            canonicals: Canonical passages for this version.
            version_id: Mapping version.

        Side Effects:
            Increments Hybrid/rerank counters at most once each and may attach
            ``hybrid_support`` matches onto unresolved chunk rows. Hybrid and
            rerank callbacks that use ``asyncio.run`` run on a worker thread.
        """

        if not unresolved:
            return
        if self._hybrid_retrieve is None:
            return
        query = build_unresolved_support_query(unresolved)
        if not query.strip():
            return
        self.counts.hybrid_retrieve += 1
        assert_mapping_budget(
            vendor_chunks=0,
            entities=0,
            relations=0,
            hybrid_calls=self.counts.hybrid_retrieve,
            rerank_calls=self.counts.support_rerank,
        )
        result = await _invoke_maybe_threaded(self._hybrid_retrieve, query, version_id)
        ranked_ids = _ranked_chunk_ids(result)
        by_id = {item.chunk_id: item for item in canonicals}
        ordered = tuple(
            by_id[chunk_id] for chunk_id in ranked_ids if chunk_id in by_id
        )[:MAX_MAPPING_RERANK_POOL]
        support_rerank = self._support_rerank
        if len(ordered) < 2 or support_rerank is None:
            return
        passages = tuple(
            RerankPassage(
                candidate=RetrievalCandidate(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    version_id=item.version_id,
                    channel_rank=index + 1,
                    channel_score=1.0,
                ),
                raw_text=item.raw_text,
                excerpt=excerpt_text(item.raw_text),
                chunk_index=item.chunk_index,
            )
            for index, item in enumerate(ordered)
        )
        rankings = await _invoke_maybe_threaded(
            lambda: run_support_rerank(
                support_rerank,
                query=query,
                passages=passages,
                counts=self.counts,
            )
        )
        accepted = assign_hybrid_support(rankings, canonicals)
        unused = list(accepted.values())
        unused.sort(key=lambda item: item.score, reverse=True)
        for index, row in enumerate(chunk_rows):
            if row.match is not None or not unused:
                continue
            chosen = unused.pop(0)
            chunk_rows[index] = _ChunkMapRow(
                vendor_chunk_id=row.vendor_chunk_id,
                vendor_doc_id=row.vendor_doc_id,
                match=chosen,
                internal_key=row.internal_key,
            )

    def _map_entities(
        self,
        nodes: Sequence[Mapping[str, object]],
        joins: Sequence[Mapping[str, object]],
        chunk_by_vendor: Mapping[str, _ChunkMapRow],
        known_chunk_ids: set[str],
        *,
        rules: Sequence[EntityRuleView],
        language: str,
    ) -> list[ObjectMapping]:
        """Derive canonical entity keys and attach accepted chunk support.

        Args:
            nodes: Vendor graph nodes.
            joins: Entity-to-chunk join rows.
            chunk_by_vendor: Mapped vendor chunks.
            known_chunk_ids: Vendor chunk ids for this version.
            rules: Active entity rules.
            language: Version language.

        Returns:
            Entity object mappings.
        """

        join_by_id = {str(row.get("id") or ""): row for row in joins}
        mapped: list[ObjectMapping] = []
        for node in nodes:
            vendor_name = _node_name(node)
            properties = _as_mapping(node.get("properties"))
            vendor_type = str(properties.get("entity_type") or "unknown")
            raw_sources = _source_id_raw(properties, join_by_id.get(vendor_name))
            mapping = _object_from_sources(
                object_type="entity",
                object_id="",
                language=language,
                raw_sources=raw_sources,
                kind="entity",
                known_chunk_ids=known_chunk_ids,
                chunk_by_vendor=chunk_by_vendor,
            )
            if not mapping.available and mapping.reason:
                mapping.provenance["vendor_name"] = vendor_name
                mapped.append(mapping)
                continue
            resolved = resolve_entity_name(vendor_name, vendor_type, rules)
            if resolved is None:
                mapped.append(
                    ObjectMapping(
                        object_type="entity",
                        object_id="",
                        language=language,
                        available=False,
                        reason="ambiguous_entity",
                        provenance={"vendor_name": vendor_name},
                    )
                )
                continue
            entity_id = canonical_entity_key(
                entity_type=vendor_type,
                canonical_name=resolved,
            )
            mapping.object_id = entity_id
            mapping.provenance["vendor_name"] = vendor_name
            mapped.append(mapping)
        return mapped

    def _map_statements(
        self,
        edges: Sequence[Mapping[str, object]],
        joins: Sequence[Mapping[str, object]],
        chunk_by_vendor: Mapping[str, _ChunkMapRow],
        known_chunk_ids: set[str],
        *,
        entity_keys: Mapping[object, object],
        language: str,
        version_id: UUID,
        relation_label_policy: str = "directed",
    ) -> list[ObjectMapping]:
        """Derive statement and path-edge IDs from structured relation fields.

        Args:
            edges: Vendor graph edges.
            joins: Relation-to-chunk join rows.
            chunk_by_vendor: Mapped vendor chunks.
            known_chunk_ids: Vendor chunk ids for this version.
            entity_keys: Vendor name to canonical entity key for available
                entities.
            language: Version language.
            version_id: Canonical version.
            relation_label_policy: Directed or symmetric endpoint ordering.

        Returns:
            Statement and path-edge mappings.
        """

        join_by_id = {str(row.get("id") or ""): row for row in joins}
        mapped: list[ObjectMapping] = []
        for edge in edges:
            src = str(edge.get("src_id") or "")
            tgt = str(edge.get("tgt_id") or "")
            properties = _as_mapping(edge.get("properties"))
            try:
                relation_key = normalize_relation_label(
                    str(properties.get("keywords") or "") or None
                )
            except ValueError:
                mapped.append(
                    ObjectMapping(
                        object_type="statement",
                        object_id="",
                        language=language,
                        available=False,
                        reason="unsupported_relation",
                        provenance={"src": src, "tgt": tgt},
                    )
                )
                continue
            subject = entity_keys.get(src)
            obj = entity_keys.get(tgt)
            if not isinstance(subject, str) or not isinstance(obj, str):
                mapped.append(
                    ObjectMapping(
                        object_type="statement",
                        object_id="",
                        language=language,
                        available=False,
                        reason="endpoint_unavailable",
                        provenance={"src": src, "tgt": tgt},
                    )
                )
                continue
            ordered_subject, ordered_object = ordered_statement_endpoints(
                subject,
                obj,
                relation_label_policy=relation_label_policy,
            )
            statement_id = graph_statement_id(
                subject_key=ordered_subject,
                object_key=ordered_object,
                relation_label_key=relation_key,
            )
            rel_join_key = GRAPH_FIELD_SEP.join(sorted((src, tgt)))
            raw_sources = _source_id_raw(properties, join_by_id.get(rel_join_key))
            statement = _object_from_sources(
                object_type="statement",
                object_id=statement_id,
                language=language,
                raw_sources=raw_sources,
                kind="relation",
                known_chunk_ids=known_chunk_ids,
                chunk_by_vendor=chunk_by_vendor,
            )
            mapped.append(statement)
            if statement.available:
                path_id = graph_path_edge_id(
                    statement_ids=(statement_id,),
                    direction="src_to_tgt",
                    version_id=version_id,
                )
                mapped.append(
                    ObjectMapping(
                        object_type="path_edge",
                        object_id=path_id,
                        language=language,
                        chunk_id=statement.chunk_id,
                        match=statement.match,
                        available=True,
                        method=statement.method,
                        support_matches=statement.support_matches,
                        provenance={
                            "statement_id": statement_id,
                            "direction": "src_to_tgt",
                        },
                    )
                )
            else:
                mapped.append(
                    ObjectMapping(
                        object_type="path_edge",
                        object_id="",
                        language=language,
                        available=False,
                        reason=statement.reason or "path_unsupported",
                        provenance={"statement_id": statement_id},
                    )
                )
        return mapped

    def _persist(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        workspace_key: str,
        language: str,
        config_generation: str,
        source_identity: str,
        chunk_rows: Sequence[_ChunkMapRow],
        objects: Sequence[ObjectMapping],
        coverage: Sequence[CoverageSlice],
        repairs: Sequence[Mapping[str, str]],
        ready: bool,
        reason: str,
        expected_source_ids: tuple[str, ...] = (),
    ) -> MappingOutcome:
        """Commit maps, repairs, telemetry, and optional Graph Ready.

        Args:
            document_id: Canonical document.
            version_id: Canonical version.
            workspace_key: Application workspace.
            language: Version language.
            config_generation: Mapping config digest.
            source_identity: Application source identity.
            chunk_rows: Vendor-chunk mapping rows.
            objects: Entity/statement/path mappings.
            coverage: Telemetry slices.
            repairs: Unavailable-object diagnostics.
            ready: True when every gate passed before the txn.
            reason: Failure reason when not ready.
            expected_source_ids: Passage source IDs that must persist 1:1
                before Graph Ready.

        Returns:
            Mapping outcome after commit.

        Side Effects:
            One application transaction. Workspace becomes ``active`` only when
            ready, the pointer already names this workspace, and no other gate
            failed. A null pointer still allows Graph Ready on the version.
        """

        drift = persist.load_eligibility_reason(
            self._connection,
            document_id=document_id,
            version_id=version_id,
        )
        pending_switch = drift == "pending_switch"
        coverage_passed = ready
        if drift is not None:
            ready = False
            reason = drift
        pointer = persist.load_pointer_workspace_id(self._connection)
        this_workspace: UUID | None = None
        try:
            this_workspace = persist.load_workspace_uuid(
                self._connection,
                workspace_key=workspace_key,
            )
        except GraphMappingError:
            this_workspace = None
        if (
            pointer is not None
            and this_workspace is not None
            and pointer != this_workspace
        ):
            pending_switch = True
            if coverage_passed:
                ready = False
                reason = "pending_switch"
        retrieval_eligible = ready
        persist.delete_version_maps(
            self._connection,
            version_id=version_id,
            workspace_key=workspace_key,
        )
        persist.upsert_source_map(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            workspace_key=workspace_key,
            language=language,
            config_generation=config_generation,
            source_identity=source_identity,
            retrieval_eligible=retrieval_eligible,
        )
        for row in chunk_rows:
            if row.match is None:
                continue
            persist.insert_chunk_map(
                self._connection,
                version_id=version_id,
                workspace_key=workspace_key,
                language=language,
                config_generation=config_generation,
                vendor_doc_id=row.vendor_doc_id,
                vendor_chunk_id=row.vendor_chunk_id,
                internal_key=row.internal_key,
                match=row.match,
                retrieval_eligible=retrieval_eligible,
            )
        for item in objects:
            persist.insert_evidence_row(
                self._connection,
                version_id=version_id,
                workspace_key=workspace_key,
                language=language,
                config_generation=config_generation,
                item=item,
                retrieval_eligible=retrieval_eligible,
            )
        persist.insert_telemetry(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            workspace_key=workspace_key,
            config_generation=config_generation,
            coverage=coverage,
        )
        if ready:
            try:
                persist.assert_persisted_readiness(
                    self._connection,
                    version_id=version_id,
                    workspace_key=workspace_key,
                    expected_source_ids=expected_source_ids,
                    expected_vendor_chunk_ids=tuple(
                        row.vendor_chunk_id
                        for row in chunk_rows
                        if row.match is not None
                    ),
                )
            except GraphMappingError as exc:
                ready = False
                reason = exc.reason
                coverage_passed = False
        repair_rows = list(repairs)
        if not ready and not repair_rows:
            repair_rows.append(
                {
                    "object_type": "document",
                    "object_id": str(version_id),
                    "map_kind": "source",
                    "reason": reason or "coverage_empty",
                }
            )
        persist.insert_repairs(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            workspace_key=workspace_key,
            config_generation=config_generation,
            repairs=repair_rows,
        )
        workspace_state = GraphWorkspaceState.UPDATING.value
        if ready:
            try:
                persist.mark_version_graph_ready(
                    self._connection,
                    version_id=version_id,
                )
                pointer = persist.load_pointer_workspace_id(self._connection)
                this_workspace = persist.load_workspace_uuid(
                    self._connection,
                    workspace_key=workspace_key,
                )
                if pointer is not None and pointer == this_workspace:
                    current = str(
                        load_workspace_row(
                            self._connection, workspace_key=workspace_key
                        ).get("state")
                        or ""
                    )
                    if current == GraphWorkspaceState.ACTIVE.value:
                        workspace_state = GraphWorkspaceState.ACTIVE.value
                    else:
                        self._writer.transition_state(
                            from_states=(
                                GraphWorkspaceState.BUILDING,
                                GraphWorkspaceState.UPDATING,
                            ),
                            to_state=GraphWorkspaceState.ACTIVE,
                            snapshot={"maps_verified": True},
                            workspace_key=workspace_key,
                        )
                        workspace_state = GraphWorkspaceState.ACTIVE.value
            except GraphMappingError:
                self._connection.rollback()
                raise
        self._connection.commit()
        maps_verified = coverage_passed and (ready or pending_switch)
        return MappingOutcome(
            ready=ready,
            maps_verified=maps_verified,
            reason=reason,
            workspace_state=workspace_state,
            hybrid_calls=self.counts.hybrid_retrieve,
            rerank_calls=self.counts.support_rerank,
            coverage=tuple(coverage),
            pending_switch=pending_switch and coverage_passed,
        )

    def _enqueue_repair_only(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        reason: str,
    ) -> None:
        """Persist a document-level repair row and keep Graph Ready closed.

        Args:
            document_id: Canonical document.
            version_id: Canonical version.
            reason: Machine-readable failure.

        Side Effects:
            Upserts one repair job and commits. Does not mark Graph Ready.
        """

        persist.insert_repairs(
            self._connection,
            document_id=document_id,
            version_id=version_id,
            workspace_key=self._mapping_workspace_key(),
            config_generation="unverified",
            repairs=(
                {
                    "object_type": "document",
                    "object_id": str(version_id),
                    "map_kind": "source",
                    "reason": reason,
                },
            ),
        )
        self._connection.commit()


def _as_mapping(value: object) -> Mapping[str, object]:
    """Return a mapping from jsonb or an empty mapping.

    Args:
        value: Vendor properties payload.

    Returns:
        String-keyed mapping.
    """

    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return cast(dict[str, object], parsed)
    return {}


def _chunk_ids_payload(value: object) -> tuple[str, ...]:
    """Normalize a jsonb chunk-id list to strings.

    Args:
        value: Vendor ``chunk_ids`` jsonb.

    Returns:
        Chunk id tokens.
    """

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item) for item in cast(Sequence[object], value) if item)
    return ()


def _source_id_raw(
    properties: Mapping[str, object],
    join_row: Mapping[str, object] | None,
) -> str | None:
    """Prefer structured ``source_id``, then join ``chunk_ids``.

    Args:
        properties: Node or edge properties.
        join_row: Optional entity/relation chunk join.

    Returns:
        Delimiter-joined source tokens, or ``None``.
    """

    raw = properties.get("source_id")
    if raw is not None and str(raw).strip():
        return str(raw)
    if join_row is None:
        return None
    tokens = _chunk_ids_payload(join_row.get("chunk_ids"))
    if not tokens:
        return None
    return GRAPH_FIELD_SEP.join(tokens)


def _node_name(node: Mapping[str, object]) -> str:
    """Return the vendor entity name from id or properties.

    Args:
        node: Vendor graph node row.

    Returns:
        Entity name token.
    """

    properties = _as_mapping(node.get("properties"))
    named = properties.get("entity_name")
    if named:
        return str(named)
    return str(node.get("id") or "")


def _object_from_sources(
    *,
    object_type: GraphObjectType,
    object_id: str,
    language: str,
    raw_sources: str | None,
    kind: Literal["entity", "relation"],
    known_chunk_ids: set[str],
    chunk_by_vendor: Mapping[str, _ChunkMapRow],
) -> ObjectMapping:
    """Parse source ids, reject foreign versions, and require support ≥ 0.80.

    Args:
        object_type: entity or statement.
        object_id: Application object id when already known.
        language: Version language.
        raw_sources: Vendor source_id scalar.
        kind: entity or relation cap.
        known_chunk_ids: Vendor chunk ids for this version.
        chunk_by_vendor: Mapped vendor chunks.

    Returns:
        Object mapping, unavailable when truncated, foreign, or below threshold.
    """

    try:
        source_ids = parse_object_source_ids(raw_sources, kind=kind)
    except SourceIdContractError as exc:
        reason = str(exc)
        if reason == "source_id_list_truncated":
            reason = "source_truncated"
        elif reason == "source_id_list_ambiguous":
            reason = "source_ambiguous"
        else:
            reason = "source_empty"
        return ObjectMapping(
            object_type=object_type,
            object_id=object_id,
            language=language,
            available=False,
            reason=reason,
        )
    if any(token not in known_chunk_ids for token in source_ids):
        return ObjectMapping(
            object_type=object_type,
            object_id=object_id,
            language=language,
            available=False,
            reason="cross_version_source",
        )
    accepted: list[tuple[str, ChunkMatch]] = []
    seen_chunks: set[UUID] = set()
    for token in source_ids:
        row = chunk_by_vendor.get(token)
        if row is None or row.match is None:
            continue
        if row.match.score < MAPPING_SUPPORT_MIN:
            continue
        chunk_id = row.match.canonical.chunk_id
        if chunk_id in seen_chunks:
            continue
        seen_chunks.add(chunk_id)
        accepted.append((row.vendor_chunk_id, row.match))
    accepted.sort(key=lambda item: (-item[1].score, str(item[1].canonical.chunk_id)))
    if not accepted:
        return ObjectMapping(
            object_type=object_type,
            object_id=object_id,
            language=language,
            available=False,
            reason="below_threshold",
        )
    best_vendor, best_match = accepted[0]
    return ObjectMapping(
        object_type=object_type,
        object_id=object_id,
        language=language,
        chunk_id=best_match.canonical.chunk_id,
        match=best_match,
        available=True,
        method=best_match.method,
        provenance={"vendor_chunk_id": best_vendor},
        support_matches=tuple(match for _vendor, match in accepted[1:]),
    )


def build_unresolved_support_query(
    unresolved: Sequence[Mapping[str, object]],
) -> str:
    """Build one bounded query that samples every unresolved vendor chunk.

    Args:
        unresolved: Vendor chunk rows still unmatched deterministically.

    Returns:
        At most ``MAX_NORMALIZED_QUERY_CHARS`` characters. Each non-empty
        chunk contributes balanced head/tail text, preventing early chunks
        from consuming the entire one-call support budget.
    """

    texts = tuple(
        text
        for row in unresolved
        if (text := strip_graph_source_envelope(str(row.get("content") or "")).strip())
    )
    if not texts:
        return ""
    separator_chars = max(len(texts) - 1, 0)
    per_chunk = max(
        1,
        (MAX_NORMALIZED_QUERY_CHARS - separator_chars) // len(texts),
    )
    snippets: list[str] = []
    for text in texts:
        if len(text) <= per_chunk:
            snippets.append(text)
            continue
        head_chars = (per_chunk + 1) // 2
        tail_chars = per_chunk - head_chars
        snippets.append(text[:head_chars] + (text[-tail_chars:] if tail_chars else ""))
    return " ".join(snippets)[:MAX_NORMALIZED_QUERY_CHARS]


def _coverage_slices(
    chunk_rows: Sequence[_ChunkMapRow],
    objects: Sequence[ObjectMapping],
    *,
    language: str,
) -> list[CoverageSlice]:
    """Build per-type coverage slices for telemetry and language gates.

    Args:
        chunk_rows: Vendor-chunk mapping rows.
        objects: Entity/statement/path mappings.
        language: Version language.

    Returns:
        Coverage slices including exclusions and truncation counts.
    """

    slices: list[CoverageSlice] = []
    chunk_ok = sum(1 for row in chunk_rows if row.match is not None)
    slices.append(
        CoverageSlice(
            language=language or "en",
            object_type="chunk",
            method="",
            numerator=chunk_ok,
            denominator=len(chunk_rows),
            exclusion_count=len(chunk_rows) - chunk_ok,
        )
    )
    by_type: dict[str, list[ObjectMapping]] = {
        "entity": [],
        "statement": [],
        "path_edge": [],
    }
    for item in objects:
        by_type.setdefault(item.object_type, []).append(item)
    for object_type, rows in by_type.items():
        accepted = sum(1 for item in rows if item.available)
        truncated = sum(1 for item in rows if item.reason == "source_truncated")
        slices.append(
            CoverageSlice(
                language=language or "en",
                object_type=object_type,
                method="",
                numerator=accepted,
                denominator=len(rows),
                exclusion_count=len(rows) - accepted,
                truncation_count=truncated,
                failure_reason=next(
                    (
                        item.reason
                        for item in rows
                        if not item.available and item.reason
                    ),
                    "",
                ),
            )
        )
    return slices


def _repair_rows(
    chunk_rows: Sequence[_ChunkMapRow],
    objects: Sequence[ObjectMapping],
) -> list[dict[str, str]]:
    """Collect repair diagnostics for unmapped or unavailable objects.

    Args:
        chunk_rows: Vendor-chunk mapping rows.
        objects: Entity/statement/path mappings.

    Returns:
        Repair payloads keyed later by workspace/object/config.
    """

    repairs: list[dict[str, str]] = []
    for row in chunk_rows:
        if row.match is not None:
            continue
        repairs.append(
            {
                "object_type": "chunk",
                "object_id": row.vendor_chunk_id,
                "map_kind": "chunk",
                "reason": "unmapped_chunk",
            }
        )
    for item in objects:
        if item.available:
            continue
        repairs.append(
            {
                "object_type": item.object_type,
                "object_id": item.object_id
                or str(item.provenance.get("vendor_name") or "")
                or str(item.provenance.get("src") or item.reason or "unavailable"),
                "map_kind": item.object_type,
                "reason": item.reason or "unavailable",
            }
        )
    return repairs


async def _invoke_maybe_threaded(func: Any, *args: Any) -> Any:
    """Call a sync mapping callback off the running event loop.

    Hybrid retrieve and support rerank use ``asyncio.run`` internally. Mapping
    already runs on the worker's long-lived LightRAG loop, so those
    callbacks must execute on a worker thread.

    Args:
        func: Sync or async callable.
        *args: Positional arguments.

    Returns:
        Callback result.
    """

    if inspect.iscoroutinefunction(func):
        return await func(*args)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return func(*args)
    return await asyncio.to_thread(func, *args)


def _ranked_chunk_ids(result: object) -> tuple[UUID, ...]:
    """Extract Hybrid ranked chunk IDs from a retrieve result.

    Args:
        result: ``HybridRunResult`` or a test double with ``ranked_ids``.

    Returns:
        Ordered canonical chunk IDs. Empty when Hybrid found nothing.
    """

    ranked = getattr(result, "ranked_ids", None)
    if ranked is None:
        return ()
    ids: list[UUID] = []
    for item in ranked:
        try:
            ids.append(item if isinstance(item, UUID) else UUID(str(item)))
        except (TypeError, ValueError):
            continue
    return tuple(ids)
