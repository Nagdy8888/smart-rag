"""Graph Ready mapping/writer path and restricted LightRAG rejection."""

from __future__ import annotations

import asyncio
from typing import cast
from uuid import UUID, uuid4

import psycopg

from smart_rag_core.ingestion.chunking.normalize import content_hash
from smart_rag_core.jobs.graph_mapping_service import (
    GraphMappingService,
    GraphVendorReader,
)
from smart_rag_core.jobs.graph_writer import GraphWriterGuard
from smart_rag_core.release.errors import RestrictedGraphIndexError
from smart_rag_core.retrieval.graph import bind_graph_source_text
from smart_rag_core.retrieval.graph_mapping import expected_vendor_basename
from smart_rag_core.retrieval.lightrag_qualification import DocumentStatusView


class MappingWriterStub:
    """Writer stub matching Phase 5 mapping contracts.

    Occupying the live single-writer lease is not required to persist
    ``graph_ready`` through ``GraphMappingService``. Workspace ACTIVE is not
    claimed by this stub.

    Attributes:
        workspace_key: Application workspace key.
    """

    workspace_key = "company_default"

    def load_pointer_generation(self) -> int:
        """Return generation 1 for mapping persist.

        Returns:
            Pointer generation used by mapping telemetry.
        """

        return 1

    def transition_state(self, **_kwargs: object) -> UUID:
        """Ignore workspace transitions; version Graph Ready is the Packet 1 gate.

        Returns:
            Fresh UUID standing in for a workspace row id.
        """

        return uuid4()


class ProcessedVendorCatalog:
    """Application-owned processed vendor catalog for mapping-verified Graph Ready.

    Mock-model LightRAG ``ainsert`` is not used. Chunk text is bound with
    ``bind_graph_source_text`` so hash mapping matches canonical passages.
    """

    def __init__(
        self,
        *,
        version_id: UUID,
        chunk_text: str,
        vendor_chunk_id: str = "phase09-vendor-chunk",
    ) -> None:
        """Bind one processed vendor document.

        Args:
            version_id: Canonical version used as the vendor document id.
            chunk_text: Canonical raw text already persisted.
            vendor_chunk_id: Stable vendor chunk identifier.
        """

        enveloped = bind_graph_source_text(
            document_version_id=str(version_id),
            normalized_text=chunk_text,
        )
        self._version_id = version_id
        self._chunk_text = chunk_text
        self._vendor_chunk_id = vendor_chunk_id
        self._chunks: list[dict[str, object]] = [
            {
                "id": vendor_chunk_id,
                "full_doc_id": str(version_id),
                "content": enveloped,
            }
        ]
        self._nodes: list[dict[str, object]] = [
            {
                "id": "Alpha",
                "properties": {
                    "entity_name": "Alpha",
                    "entity_type": "ORG",
                    "source_id": vendor_chunk_id,
                },
            },
            {
                "id": "Beta",
                "properties": {
                    "entity_name": "Beta",
                    "entity_type": "ORG",
                    "source_id": vendor_chunk_id,
                },
            },
        ]
        self._edges: list[dict[str, object]] = [
            {
                "src_id": "Alpha",
                "tgt_id": "Beta",
                "properties": {
                    "keywords": "employs",
                    "source_id": vendor_chunk_id,
                },
            }
        ]

    async def vendor_document_status(self, document_id: str) -> DocumentStatusView:
        """Return processed vendor status for the canonical version id.

        Args:
            document_id: Vendor document id (canonical version).

        Returns:
            Processed status view.
        """

        return DocumentStatusView(
            document_id=document_id,
            status="processed",
            file_path=expected_vendor_basename(UUID(document_id)),
        )

    async def list_vendor_doc_chunks(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return configured vendor chunks."""

        return [dict(row) for row in self._chunks]

    async def list_vendor_entity_joins(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return no entity joins; nodes carry ``source_id``."""

        return []

    async def list_vendor_relation_joins(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return no relation joins; edges carry ``source_id``."""

        return []

    async def list_vendor_graph_nodes(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return configured nodes."""

        return [dict(row) for row in self._nodes]

    async def list_vendor_graph_edges(
        self, **_kwargs: object
    ) -> list[dict[str, object]]:
        """Return configured edges."""

        return [dict(row) for row in self._edges]


def reject_restricted_lightrag_input(
    *,
    visibility: str,
    graph_eligible: bool,
) -> None:
    """Reject restricted or ineligible documents as LightRAG inputs.

    Args:
        visibility: Canonical document visibility.
        graph_eligible: Document graph eligibility.

    Raises:
        RestrictedGraphIndexError: If the document must not enter LightRAG.
    """

    if visibility == "restricted" or not graph_eligible:
        raise RestrictedGraphIndexError(
            "restricted or ineligible documents must never be LightRAG-indexed"
        )


def assert_graph_index_rejected(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
) -> str:
    """Call ``app.assert_graph_index_allowed`` and require a rejection.

    Args:
        connection: Postgres connection.
        document_id: Restricted or ineligible document.
        version_id: Version offered to LightRAG.

    Returns:
        Database exception text proving the rejection.

    Raises:
        RestrictedGraphIndexError: If the gate unexpectedly allowed indexing.
    """

    connection.execute("SET ROLE app_worker")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT app.assert_graph_index_allowed(%s, %s)",
                (document_id, version_id),
            )
    except psycopg.errors.RaiseException as exc:
        return str(exc)
    raise RestrictedGraphIndexError(f"assert_graph_index_allowed allowed {document_id}")


def point_current_version(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
) -> None:
    """Write the current-version pointer used by mapping eligibility.

    First graph-eligible versions are not made current by
    ``finalize_hybrid_ready``. Phase 5 mapping contracts write this pointer
    before ``GraphMappingService``. This is not a ``graph_ready`` stamp.

    Args:
        connection: Superuser-capable connection.
        document_id: Canonical document.
        version_id: Version that must be current for Graph Ready.

    Side Effects:
        Updates ``is_current`` and ``documents.current_version_id``.
    """

    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.document_versions
            SET is_current = false, updated_at = timezone('utc', now())
            WHERE document_id = %s AND is_current = true AND id IS DISTINCT FROM %s
            """,
            (document_id, version_id),
        )
        cursor.execute(
            """
            UPDATE app.document_versions
            SET is_current = true, updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (version_id,),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s, updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (version_id, document_id),
        )


def load_first_chunk_text(connection: psycopg.Connection, version_id: UUID) -> str:
    """Return the first canonical chunk raw text for mapping.

    Args:
        connection: Postgres connection.
        version_id: Canonical version.

    Returns:
        Raw chunk text.

    Raises:
        RuntimeError: If the version has no chunks.
    """

    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT raw_text
            FROM app.document_chunks
            WHERE version_id = %s
            ORDER BY chunk_index ASC
            LIMIT 1
            """,
            (version_id,),
        )
        row = cursor.fetchone()
    if row is None or row[0] is None:
        raise RuntimeError(f"no chunks for version {version_id}")
    return str(row[0])


def drive_graph_ready(
    connection: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
    visibility: str,
    graph_eligible: bool,
) -> str:
    """Run ``GraphMappingService`` and return the public version status.

    Args:
        connection: Worker-capable connection. Caller commits on success.
        document_id: Company-visible document.
        version_id: Graph-pending version.
        visibility: Must be ``company_visible``.
        graph_eligible: Must be true.

    Returns:
        Public ``document_versions.status`` after mapping.

    Raises:
        RestrictedGraphIndexError: If restricted input is offered.
        RuntimeError: If mapping does not mark Graph Ready.
    """

    reject_restricted_lightrag_input(
        visibility=visibility,
        graph_eligible=graph_eligible,
    )
    chunk_text = load_first_chunk_text(connection, version_id)
    _ = content_hash(chunk_text)
    point_current_version(
        connection,
        document_id=document_id,
        version_id=version_id,
    )
    connection.commit()
    connection.execute("SET ROLE app_worker")
    vendor: GraphVendorReader = ProcessedVendorCatalog(
        version_id=version_id,
        chunk_text=chunk_text,
    )
    service = GraphMappingService(
        connection,
        vendor_reader=vendor,
        writer=cast(GraphWriterGuard, MappingWriterStub()),
    )
    outcome = asyncio.run(
        service.map_after_vendor_success(
            document_id=document_id,
            version_id=version_id,
        )
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT status FROM app.document_versions WHERE id = %s",
            (version_id,),
        )
        row = cursor.fetchone()
    status = str(row[0]) if row is not None else "missing"
    if not outcome.maps_verified or status != "graph_ready":
        raise RuntimeError(
            f"graph_ready not reached: status={status} reason={outcome.reason}"
        )
    return status
