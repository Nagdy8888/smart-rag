"""ParadeDB BM25 projection writer using separate writer credentials."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.ingestion.limits import DEFAULT_BM25_UPSERT_BATCH_SIZE


@dataclass(frozen=True, slots=True)
class Bm25ProjectionRow:
    """One rebuildable ParadeDB projection row keyed by canonical chunk ID."""

    chunk_id: UUID
    version_id: UUID
    document_id: UUID
    title_search: str | None
    heading_search: str | None
    alias_search: str | None
    body_search: str
    language: str | None
    acl_scope_id: str
    is_current: bool
    visibility_generation: int
    normalization_version: str
    content_hash: str | None = None


class Bm25Indexer:
    """Upsert/delete bounded BM25 projection batches in private ParadeDB."""

    INDEX_SCHEMA_VERSION = "bm25_v1"

    def __init__(self, connection: psycopg.Connection) -> None:
        """Bind one ParadeDB writer connection."""

        self._connection = connection

    def ensure_projection_schema(self) -> None:
        """Ensure derived projection table and BM25 index exist."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bm25_index_meta (
                  id integer PRIMARY KEY DEFAULT 1,
                  index_version integer NOT NULL DEFAULT 1,
                  normalization_version text NOT NULL DEFAULT 'arabic_norm_v1',
                  index_schema_version text NOT NULL DEFAULT 'bm25_v1',
                  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
                  CONSTRAINT bm25_index_meta_singleton CHECK (id = 1)
                );
                INSERT INTO bm25_index_meta (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bm25_chunks (
                  chunk_id uuid PRIMARY KEY,
                  version_id uuid NOT NULL,
                  document_id uuid NOT NULL,
                  title_search text,
                  heading_search text,
                  alias_search text,
                  body_search text NOT NULL,
                  language text,
                  effective_at timestamptz,
                  tag text,
                  authority_rank smallint,
                  is_current boolean NOT NULL DEFAULT true,
                  visibility_generation bigint NOT NULL DEFAULT 1,
                  acl_scope_id text NOT NULL,
                  indexed_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
                  normalization_version text NOT NULL DEFAULT 'arabic_norm_v1',
                  content_hash text
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS bm25_chunks_version_id_idx
                  ON bm25_chunks (version_id);
                """
            )
            cursor.execute(
                """
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE indexname = 'bm25_chunks_search_idx'
                  ) THEN
                    EXECUTE $idx$
                      CREATE INDEX bm25_chunks_search_idx ON bm25_chunks
                      USING bm25 (
                        chunk_id,
                        (body_search::pdb.unicode_words),
                        (coalesce(title_search, '')::pdb.unicode_words),
                        (coalesce(heading_search, '')::pdb.unicode_words),
                        acl_scope_id,
                        visibility_generation
                      )
                      WITH (key_field = 'chunk_id');
                    $idx$;
                  END IF;
                END
                $$;
                """
            )

    def upsert_batch(self, rows: tuple[Bm25ProjectionRow, ...]) -> int:
        """Upsert one bounded batch keyed by canonical chunk IDs."""

        if not rows:
            return 0
        if len(rows) > DEFAULT_BM25_UPSERT_BATCH_SIZE:
            raise ValueError("bm25_batch_exceeds_limit")
        written = 0
        with self._connection.cursor() as cursor:
            for row in rows:
                cursor.execute(
                    """
                    INSERT INTO bm25_chunks (
                      chunk_id,
                      version_id,
                      document_id,
                      title_search,
                      heading_search,
                      alias_search,
                      body_search,
                      language,
                      acl_scope_id,
                      is_current,
                      visibility_generation,
                      normalization_version,
                      content_hash
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (chunk_id) DO UPDATE
                    SET
                      version_id = EXCLUDED.version_id,
                      document_id = EXCLUDED.document_id,
                      title_search = EXCLUDED.title_search,
                      heading_search = EXCLUDED.heading_search,
                      alias_search = EXCLUDED.alias_search,
                      body_search = EXCLUDED.body_search,
                      language = EXCLUDED.language,
                      acl_scope_id = EXCLUDED.acl_scope_id,
                      is_current = EXCLUDED.is_current,
                      visibility_generation = EXCLUDED.visibility_generation,
                      normalization_version = EXCLUDED.normalization_version,
                      content_hash = EXCLUDED.content_hash,
                      indexed_at = timezone('utc', now())
                    """,
                    (
                        row.chunk_id,
                        row.version_id,
                        row.document_id,
                        row.title_search,
                        row.heading_search,
                        row.alias_search,
                        row.body_search,
                        row.language,
                        row.acl_scope_id,
                        row.is_current,
                        row.visibility_generation,
                        row.normalization_version,
                        row.content_hash,
                    ),
                )
                written += 1
        return written

    def delete_version(self, version_id: UUID) -> int:
        """Delete all projection rows for one canonical version."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM bm25_chunks WHERE version_id = %s",
                (version_id,),
            )
            return int(cursor.rowcount)

    def fetch_meta(self) -> dict[str, Any]:
        """Return active ParadeDB projection metadata."""

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT index_version, normalization_version, index_schema_version
                FROM bm25_index_meta
                WHERE id = 1
                """
            )
            row = cursor.fetchone()
            return dict(row) if row else {}

    def count_rows_for_version(self, version_id: UUID) -> int:
        """Count projection rows for one version."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM bm25_chunks WHERE version_id = %s",
                (version_id,),
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def sample_query_ids(self, query: str, *, limit: int = 5) -> list[str]:
        """Run one deterministic BM25 sample query with canonical ID tie-break."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT chunk_id::text
                FROM bm25_chunks
                WHERE body_search ||| %s
                ORDER BY pdb.score(chunk_id) DESC, chunk_id ASC
                LIMIT %s
                """,
                (query, limit),
            )
            return [str(row[0]) for row in cursor.fetchall()]
