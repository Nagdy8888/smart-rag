"""HTTP adapter for authorized graph inspection."""

from __future__ import annotations

import psycopg
from smart_rag_core.jobs.exceptions import GraphResolverError
from smart_rag_core.retrieval.graph_retriever import (
    GraphQueryError,
    inspect_graph_authorized,
)
from smart_rag_core.security.identity import CallerContext

from smart_rag_api.schemas.graph_inspect import (
    GraphInspectLimitation,
    GraphInspectLocator,
    GraphInspectNodeResponse,
    GraphInspectRequest,
    GraphInspectResponse,
)


def inspect_graph_for_caller(
    postgres_url: str,
    *,
    caller: CallerContext,
    body: GraphInspectRequest,
    remaining_deadline_seconds: float,
) -> GraphInspectResponse:
    """Run inspection as the authenticated caller.

    Args:
        postgres_url: Database URL used as ``app_api``.
        caller: Server-derived identity.
        body: Validated inspection seed and depth.
        remaining_deadline_seconds: Remaining 10-second inspection deadline.

    Returns:
        ACL-filtered inspection rows. Restricted documents the caller cannot
        read are omitted rather than named.

    Raises:
        GraphQueryError: Deadline, seed, or workspace failures that the
            router maps to sanitized HTTP errors.
    """

    try:
        with psycopg.connect(postgres_url) as connection:
            result = inspect_graph_authorized(
                connection=connection,
                caller=caller,
                entity_keys=body.entity_keys,
                document_id=body.document_id,
                depth=body.depth,
                remaining_deadline_seconds=remaining_deadline_seconds,
            )
    except GraphResolverError as exc:
        raise GraphQueryError(exc.reason) from exc
    return GraphInspectResponse(
        nodes=tuple(
            GraphInspectNodeResponse(
                object_type=node.object_type,
                object_id=node.object_id,
                chunk_id=node.chunk_id,
                document_id=node.document_id,
                version_id=node.version_id,
                support=node.support,
                hop=node.hop,
            )
            for node in result.nodes
        ),
        locators=tuple(
            GraphInspectLocator(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                version_id=item.version_id,
                page_number=item.page_number,
                section_path=item.section_path,
                sheet_name=item.sheet_name,
                range_ref=item.range_ref,
                source_url=item.source_url,
            )
            for item in result.locators
        ),
        limitations=tuple(
            GraphInspectLimitation(code=item.code.value, count=item.count)
            for item in result.limitations
        ),
        row_count=result.row_count,
        depth=result.depth,
    )
