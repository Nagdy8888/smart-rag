"""Resolve bounded native table rows adjoining an already authorized exact caption."""

from __future__ import annotations

import re
from dataclasses import replace
from uuid import UUID

import psycopg

from smart_rag_core.retrieval.context_loader import fetch_authorized_chunk_context
from smart_rag_core.retrieval.hybrid_run.types import (
    EvidenceLocator,
    EvidenceUnit,
    HybridRunResult,
)
from smart_rag_core.retrieval.rerank import named_table_captions
from smart_rag_core.retrieval.session import retrieval_transaction
from smart_rag_core.security.identity import CallerContext


def with_named_table_neighbors(
    result: HybridRunResult,
    connection: psycopg.Connection,
    caller: CallerContext,
    query: str,
) -> HybridRunResult:
    """Recheck caption and at most two same-parent table fragments on this/next page."""
    captions = named_table_captions(query)
    if len(captions) != 1:
        return result
    pattern = re.compile(rf"(?im)^\s*{re.escape(captions[0])}\.")
    anchors = tuple(
        item.chunk_id for item in result.evidence if pattern.search(item.citation_text)
    )[:2]
    if not anchors:
        return result
    with retrieval_transaction(
        connection, caller=caller, profile="low", apply_hnsw=False
    ):
        rows = connection.execute(
            """
            WITH anchors AS (
              SELECT * FROM app.fetch_authorized_chunk_context(%s::uuid, %s::text, %s::bigint, %s::uuid[])
            )
            SELECT DISTINCT native.id, native.chunk_index
            FROM anchors AS anchor
            JOIN app.document_chunks AS native
              ON native.version_id = anchor.version_id
              AND native.document_id = anchor.document_id
              AND (native.parent_chunk_id = anchor.chunk_id
                OR native.chunk_index BETWEEN anchor.chunk_index + 1 AND anchor.chunk_index + 2)
              AND native.page_number BETWEEN anchor.page_number AND anchor.page_number + 1
            WHERE native.deleted_at IS NULL
              AND native.provenance->>'content_kind' = 'table'
            ORDER BY native.chunk_index, native.id
            LIMIT 2
            """,
            (
                caller.rpc_user_id(),
                caller.rpc_role(),
                caller.rpc_authorization_version(),
                list(anchors),
            ),
        ).fetchall()
    ids = tuple(UUID(str(row[0])) for row in rows)
    if not ids:
        return result
    # This second RPC rechecks current-version/ACL state for every discovered ID.
    native = fetch_authorized_chunk_context(connection, caller=caller, chunk_ids=ids)
    if not native:
        return result
    anchor_units = [unit for unit in result.evidence if unit.chunk_id in anchors]
    neighbors = [
        EvidenceUnit(
            chunk_id=record.chunk_id,
            document_id=record.document_id,
            version_id=record.version_id,
            citation_text=record.raw_text,
            locator=EvidenceLocator(
                page_number=record.page_number, section_path=record.section_path
            ),
        )
        for record in native
        if record.content_kind == "table"
    ]
    pinned = {unit.chunk_id for unit in [*anchor_units, *neighbors]}
    ordered = [
        *anchor_units,
        *neighbors,
        *(unit for unit in result.evidence if unit.chunk_id not in pinned),
    ]
    selected: list[EvidenceUnit] = []
    chars = 0
    for unit in ordered:
        if len(selected) >= 12 or chars + len(unit.citation_text) > 24000:
            continue
        selected.append(unit)
        chars += len(unit.citation_text)
    chosen = tuple(unit.chunk_id for unit in selected)
    return replace(
        result, evidence=tuple(selected), ranked_ids=chosen, selected_ids=chosen
    )
