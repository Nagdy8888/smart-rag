"""Assemble canonical passage sources for graph insertion.

There is no ``document_versions.normalized_text`` column. Packet 3 used to
concatenate ``app.document_chunks.raw_text``. Production indexing now inserts
one LightRAG source per canonical passage so mapping is a hash bijection.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

import psycopg

from smart_rag_core.ingestion.chunking.normalize import content_hash
from smart_rag_core.jobs.limits import (
    GRAPH_PIPELINE_VERSION,
    MAX_GRAPH_PASSAGE_CHARS,
    MAX_GRAPH_PASSAGE_SOURCES,
)
from smart_rag_core.retrieval.graph import (
    bind_graph_source_text,
    canonical_passage_source_id,
    opaque_passage_source_basename,
    version_vendor_source_ids,
)


class GraphSourceTextError(ValueError):
    """Raised when version text cannot be assembled for graph insert."""

    def __init__(self, reason: str) -> None:
        """Initialize with a stable machine-readable reason.

        Args:
            reason: Short reason such as ``version_text_empty``.
        """

        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class CanonicalGraphSource:
    """One immutable canonical passage prepared as a LightRAG source.

    Attributes:
        version_id: Canonical document version.
        chunk_id: Canonical chunk UUID used in the source ID.
        chunk_index: Order within the version.
        raw_text: Canonical ``document_chunks.raw_text``.
        content_hash: Ingest SHA-256 of ``normalize_for_dedup(raw_text)``.
        source_id: Deterministic ``{version_id}:{chunk_id}``.
        source_token: Opaque basename ``g-{version_id}-{chunk_id}.txt``.
    """

    version_id: UUID
    chunk_id: UUID
    chunk_index: int
    raw_text: str
    content_hash: str
    source_id: str
    source_token: str

    def enveloped_text(self) -> str:
        """Return envelope-bound passage text for LightRAG insert.

        Returns:
            Identity envelope plus the canonical raw text.
        """

        return bind_graph_source_text(
            document_version_id=self.source_id,
            normalized_text=self.raw_text,
        )


@dataclass(frozen=True, slots=True)
class GraphSourceManifest:
    """Frozen preflight of every canonical passage for one version job.

    Attributes:
        version_id: Canonical version being indexed.
        sources: Ordered passage sources. Empty is rejected at build time.
        snapshot_digest: SHA-256 of ordered source IDs and content hashes.
    """

    version_id: UUID
    sources: tuple[CanonicalGraphSource, ...]
    snapshot_digest: str

    @property
    def source_ids(self) -> tuple[str, ...]:
        """Return ordered LightRAG source IDs."""

        return tuple(item.source_id for item in self.sources)

    @property
    def chunk_ids(self) -> tuple[UUID, ...]:
        """Return ordered canonical chunk IDs."""

        return tuple(item.chunk_id for item in self.sources)

    @property
    def deletion_ids(self) -> tuple[str, ...]:
        """Return legacy whole-version ID plus every passage source ID."""

        return version_vendor_source_ids(self.version_id, self.chunk_ids)

    def source_by_id(self) -> dict[str, CanonicalGraphSource]:
        """Return a source-id lookup.

        Returns:
            Mapping of LightRAG source ID to the frozen source row.
        """

        return {item.source_id: item for item in self.sources}


def load_version_graph_text(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
) -> str:
    """Return ordered canonical chunk text for one document version.

    Kept for diagnostics. Production insert uses
    ``load_version_passage_manifest``.

    Args:
        connection: ``app_worker`` connection.
        version_id: Canonical version whose chunks are concatenated.

    Returns:
        Version text joined with blank lines.

    Raises:
        GraphSourceTextError: If no undeleted chunks exist.
    """

    manifest = load_version_passage_manifest(connection, version_id=version_id)
    return "\n\n".join(item.raw_text for item in manifest.sources)


def load_version_passage_manifest(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
) -> GraphSourceManifest:
    """Load and preflight canonical passages as LightRAG sources.

    Args:
        connection: ``app_worker`` connection.
        version_id: Canonical version whose current undeleted chunks are
            indexed.

    Returns:
        Frozen manifest. Callers must not mutate passage text after this
        snapshot.

    Raises:
        GraphSourceTextError: If passages are missing, empty, oversized,
            duplicated, or exceed the bounded source cap.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, chunk_index, raw_text, content_hash
            FROM app.document_chunks
            WHERE version_id = %s
              AND deleted_at IS NULL
            ORDER BY chunk_index ASC
            """,
            (version_id,),
        )
        rows = cursor.fetchall()
    if not rows:
        raise GraphSourceTextError("version_text_empty")
    if len(rows) > MAX_GRAPH_PASSAGE_SOURCES:
        raise GraphSourceTextError("graph_source_too_many_passages")
    sources: list[CanonicalGraphSource] = []
    seen_chunks: set[UUID] = set()
    seen_source_ids: set[str] = set()
    for row in rows:
        chunk_id = UUID(str(row[0]))
        raw_text = str(row[2] or "")
        if not raw_text.strip():
            raise GraphSourceTextError("graph_source_empty_passage")
        if len(raw_text) > MAX_GRAPH_PASSAGE_CHARS:
            raise GraphSourceTextError("graph_source_passage_too_large")
        if chunk_id in seen_chunks:
            raise GraphSourceTextError("graph_source_duplicate_chunk")
        stored_hash = str(row[3]) if row[3] is not None else ""
        digest = stored_hash or content_hash(raw_text)
        if stored_hash and stored_hash != content_hash(raw_text):
            raise GraphSourceTextError("graph_source_snapshot_mismatch")
        source_id = canonical_passage_source_id(
            version_id=version_id,
            chunk_id=chunk_id,
        )
        if source_id in seen_source_ids:
            raise GraphSourceTextError("graph_source_duplicate_chunk")
        seen_chunks.add(chunk_id)
        seen_source_ids.add(source_id)
        sources.append(
            CanonicalGraphSource(
                version_id=version_id,
                chunk_id=chunk_id,
                chunk_index=int(row[1]),
                raw_text=raw_text,
                content_hash=digest,
                source_id=source_id,
                source_token=opaque_passage_source_basename(
                    version_id=version_id,
                    chunk_id=chunk_id,
                ),
            )
        )
    return GraphSourceManifest(
        version_id=version_id,
        sources=tuple(sources),
        snapshot_digest=_snapshot_digest(tuple(sources)),
    )


def _snapshot_digest(sources: tuple[CanonicalGraphSource, ...]) -> str:
    """Hash ordered source IDs and content hashes.

    Args:
        sources: Frozen passage sources.

    Returns:
        Lowercase SHA-256 hex digest.
    """

    payload = [
        {
            "source_id": item.source_id,
            "chunk_id": str(item.chunk_id),
            "chunk_index": item.chunk_index,
            "content_hash": item.content_hash,
            "pipeline": GRAPH_PIPELINE_VERSION,
        }
        for item in sources
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_version_vendor_deletion_ids(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
) -> tuple[str, ...]:
    """Return every vendor ID that must be deleted for one version.

    Includes the legacy whole-version ID, IDs derived from every stored
    chunk (deleted or not), and any ``lightrag_doc_id`` already mapped.

    Args:
        connection: ``app_worker`` connection.
        version_id: Canonical version being removed from LightRAG.

    Returns:
        Unique vendor document IDs in stable order.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM app.document_chunks
            WHERE version_id = %s
            ORDER BY chunk_index ASC
            """,
            (version_id,),
        )
        chunk_ids = tuple(UUID(str(row[0])) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT DISTINCT lightrag_doc_id
            FROM app.lightrag_chunk_map
            WHERE version_id = %s
            ORDER BY lightrag_doc_id
            """,
            (version_id,),
        )
        mapped = tuple(str(row[0]) for row in cursor.fetchall() if row[0])
    derived = version_vendor_source_ids(version_id, chunk_ids)
    extra = tuple(item for item in mapped if item not in derived)
    return derived + extra
