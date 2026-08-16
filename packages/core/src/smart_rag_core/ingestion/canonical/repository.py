"""Authoritative canonical chunk and table persistence."""

from __future__ import annotations

import json
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg

from smart_rag_core.ingestion.chunking.types import CanonicalChunk, ChunkingResult
from smart_rag_core.ingestion.embeddings.contextual import (
    extract_deterministic_search_terms,
)
from smart_rag_core.ingestion.embeddings.policy import EMBEDDING_MODEL
from smart_rag_core.ingestion.embeddings.service import (
    EmbeddedChunk,
    EmbeddingBatchResult,
)
from smart_rag_core.ingestion.tables.bundle import TableArtifactBundle


class CanonicalWriteError(RuntimeError):
    """Report canonical persistence or outbox enqueue failures."""


class CanonicalRepository:
    """Write canonical chunks, search terms, tables, and BM25 outbox atomically."""

    def __init__(self, connection: psycopg.Connection) -> None:
        """Bind one worker-role Postgres connection."""

        self._connection = connection

    def persist_version_indexing(
        self,
        *,
        version_id: UUID,
        document_id: UUID,
        document_title: str,
        filename: str | None,
        chunking: ChunkingResult,
        embedding: EmbeddingBatchResult,
        embedded: tuple[EmbeddedChunk, ...],
        table_artifacts: tuple[TableArtifactBundle, ...],
        is_current: bool = False,
    ) -> UUID:
        """Batch-write chunks, vectors, terms, tables, and BM25 outbox in one txn.

        Args:
            version_id: Target version identifier.
            document_id: Owning document identifier.
            document_title: Title for search-term extraction.
            filename: Original filename when available.
            chunking: Closed chunking output.
            embedding: Completed embedding batch metadata.
            embedded: Representative embedded passages.
            table_artifacts: Typed table artifact bundles.
            is_current: Whether this version becomes the current pointer.

        Returns:
            Enqueued or existing BM25 projection job identifier.

        Raises:
            CanonicalWriteError: When required RPC writes fail.
        """

        embedded_by_id = {item.chunk.chunk_id: item for item in embedded}
        search_terms = extract_deterministic_search_terms(
            document_title=document_title,
            filename=filename,
            chunks=chunking.chunks,
        )

        for chunk in _chunks_in_fk_order(chunking.chunks):
            embedded_row = embedded_by_id.get(chunk.chunk_id)
            vector_literal = None
            contextual_text = None
            if embedded_row is not None:
                vector_literal = _vector_literal(embedded_row.embedding)
                contextual_text = embedded_row.contextual_text

            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO app.document_chunks (
                      id,
                      document_id,
                      version_id,
                      chunk_index,
                      raw_text,
                      embedding,
                      token_count,
                      page_number,
                      section_path,
                      provenance,
                      parent_chunk_id,
                      contextual_text,
                      content_hash,
                      duplicate_of_chunk_id,
                      is_search_representative
                    )
                    VALUES (
                      %s, %s, %s, %s, %s,
                      %s::extensions.vector,
                      %s, %s, %s, %s::jsonb, %s,
                      %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE
                    SET
                      raw_text = EXCLUDED.raw_text,
                      embedding = EXCLUDED.embedding,
                      token_count = EXCLUDED.token_count,
                      section_path = EXCLUDED.section_path,
                      provenance = EXCLUDED.provenance,
                      contextual_text = EXCLUDED.contextual_text,
                      content_hash = EXCLUDED.content_hash,
                      duplicate_of_chunk_id = EXCLUDED.duplicate_of_chunk_id,
                      is_search_representative = EXCLUDED.is_search_representative,
                      updated_at = timezone('utc', now())
                    """,
                    (
                        chunk.chunk_id,
                        document_id,
                        version_id,
                        chunk.chunk_index,
                        chunk.raw_text,
                        vector_literal,
                        chunk.token_count,
                        chunk.page_number,
                        chunk.section_path,
                        json.dumps(chunk.provenance.model_dump(mode="json")),
                        chunk.parent_chunk_id,
                        contextual_text,
                        chunk.provenance.normalized_content_hash,
                        chunk.duplicate_of_chunk_id,
                        chunk.is_search_representative,
                    ),
                )

            for term in search_terms.get(chunk.chunk_id, ()):
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO app.document_search_terms (chunk_id, term)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (chunk.chunk_id, term),
                    )

        for artifact in table_artifacts:
            self._persist_table_artifact(
                document_id=document_id,
                version_id=version_id,
                artifact=artifact,
            )

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.document_versions
                SET
                  chunk_set_hash = %s,
                  embedding_model = %s,
                  embedding_policy_hash = %s,
                  is_current = %s,
                  updated_at = timezone('utc', now())
                WHERE id = %s
                """,
                (
                    embedding.chunk_set_hash,
                    EMBEDDING_MODEL,
                    embedding.policy_hash,
                    is_current,
                    version_id,
                ),
            )

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.enqueue_bm25_projection_for_version(%s, %s, %s)
                """,
                (
                    version_id,
                    embedding.chunk_set_hash,
                    f"bm25:upsert:{version_id}:{embedding.chunk_set_hash}",
                ),
            )
            row = cursor.fetchone()
            if row is None or row[0] is None:
                raise CanonicalWriteError("bm25_outbox_enqueue_failed")
            return UUID(str(row[0]))

    def _persist_table_artifact(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        artifact: TableArtifactBundle,
    ) -> None:
        """Upsert one table artifact row for a canonical document version.

        Args:
            document_id: Parent document identifier.
            version_id: Canonical version that owns the table.
            artifact: Parquet bundle and column manifest to persist.
        """

        manifest = artifact.manifest
        table_id = uuid5(NAMESPACE_URL, manifest.manifest_hash())
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.document_tables (
                  id,
                  document_id,
                  version_id,
                  table_name,
                  sheet_name,
                  parquet_bucket,
                  parquet_path,
                  row_count,
                  column_count,
                  provenance
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET
                  parquet_bucket = EXCLUDED.parquet_bucket,
                  parquet_path = EXCLUDED.parquet_path,
                  row_count = EXCLUDED.row_count,
                  column_count = EXCLUDED.column_count,
                  provenance = EXCLUDED.provenance,
                  updated_at = timezone('utc', now())
                """,
                (
                    table_id,
                    document_id,
                    version_id,
                    manifest.table_name,
                    manifest.sheet_name,
                    artifact.bucket,
                    manifest.parquet_path,
                    manifest.row_count,
                    manifest.column_count,
                    json.dumps(manifest.model_dump(mode="json")),
                ),
            )


def _chunks_in_fk_order(
    chunks: tuple[CanonicalChunk, ...],
) -> tuple[CanonicalChunk, ...]:
    """Order chunks so parent and duplicate FKs resolve during insert.

    Args:
        chunks: Chunking output in builder order.

    Returns:
        The same chunks with parents and duplicate representatives first.
    """

    remaining = list(chunks)
    inserted: set[UUID] = set()
    ordered: list[CanonicalChunk] = []
    while remaining:
        progressed = False
        blocked: list[CanonicalChunk] = []
        for chunk in remaining:
            parent_ok = (
                chunk.parent_chunk_id is None or chunk.parent_chunk_id in inserted
            )
            duplicate_ok = (
                chunk.duplicate_of_chunk_id is None
                or chunk.duplicate_of_chunk_id in inserted
            )
            if parent_ok and duplicate_ok:
                ordered.append(chunk)
                inserted.add(chunk.chunk_id)
                progressed = True
            else:
                blocked.append(chunk)
        if not progressed:
            ordered.extend(blocked)
            break
        remaining = blocked
    return tuple(ordered)


def _vector_literal(values: list[float]) -> str:
    """Format one pgvector literal from a Python float list."""

    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
