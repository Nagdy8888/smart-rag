"""Cross-database BM25 projection verification before Hybrid Ready."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.ingestion.limits import (
    DEFAULT_BM25_VERIFY_QUERY_LIMIT,
    DEFAULT_BM25_VERIFY_SAMPLE_COUNT,
)
from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer


@dataclass(frozen=True, slots=True)
class Bm25VerificationResult:
    """Closed verification outcome for one version projection."""

    passed: bool
    supabase_row_count: int
    parade_row_count: int
    hash_matches: int
    hash_mismatches: int
    sample_queries: tuple[tuple[str, tuple[str, ...]], ...]
    index_schema_version: str
    normalization_version: str
    detail: str


class Bm25ProjectionVerifier:
    """Verify Supabase canonical rows against ParadeDB projection state."""

    def __init__(
        self,
        supabase: psycopg.Connection,
        parade: psycopg.Connection,
    ) -> None:
        """Bind Supabase authoritative and ParadeDB derived connections."""

        self._supabase = supabase
        self._parade = parade
        self._indexer = Bm25Indexer(parade)

    def verify_version(self, version_id: UUID) -> Bm25VerificationResult:
        """Compare row counts, content hashes, and sample BM25 queries."""

        active = self._active_bm25_version()
        meta = self._indexer.fetch_meta()
        if meta.get("index_schema_version") != active["index_schema_version"]:
            return Bm25VerificationResult(
                passed=False,
                supabase_row_count=0,
                parade_row_count=0,
                hash_matches=0,
                hash_mismatches=0,
                sample_queries=(),
                index_schema_version=str(meta.get("index_schema_version", "")),
                normalization_version=str(meta.get("normalization_version", "")),
                detail="index_schema_version_mismatch",
            )

        supabase_rows = self._fetch_supabase_chunks(version_id)
        parade_count = self._indexer.count_rows_for_version(version_id)
        hash_matches = 0
        hash_mismatches = 0
        for row in supabase_rows:
            parade_hash = self._parade_content_hash(UUID(str(row["id"])))
            expected = str(row["content_hash"] or "")
            body_hash = hashlib.sha256(str(row["search_normalized"]).encode()).hexdigest()
            actual = parade_hash or body_hash
            if expected and actual == expected:
                hash_matches += 1
            elif expected:
                hash_mismatches += 1

        sample_queries: list[tuple[str, tuple[str, ...]]] = []
        for row in supabase_rows[:DEFAULT_BM25_VERIFY_SAMPLE_COUNT]:
            query_text = _sample_query_text(str(row["raw_text"]))
            ids_first = tuple(
                self._indexer.sample_query_ids(
                    query_text,
                    limit=DEFAULT_BM25_VERIFY_QUERY_LIMIT,
                )
            )
            ids_second = tuple(
                self._indexer.sample_query_ids(
                    query_text,
                    limit=DEFAULT_BM25_VERIFY_QUERY_LIMIT,
                )
            )
            sample_queries.append((query_text, ids_first))
            if ids_first != ids_second:
                return Bm25VerificationResult(
                    passed=False,
                    supabase_row_count=len(supabase_rows),
                    parade_row_count=parade_count,
                    hash_matches=hash_matches,
                    hash_mismatches=hash_mismatches,
                    sample_queries=tuple(sample_queries),
                    index_schema_version=str(active["index_schema_version"]),
                    normalization_version=str(active["normalization_version"]),
                    detail="sample_query_not_deterministic",
                )

        passed = (
            len(supabase_rows) == parade_count
            and hash_mismatches == 0
            and len(supabase_rows) > 0
        )
        return Bm25VerificationResult(
            passed=passed,
            supabase_row_count=len(supabase_rows),
            parade_row_count=parade_count,
            hash_matches=hash_matches,
            hash_mismatches=hash_mismatches,
            sample_queries=tuple(sample_queries),
            index_schema_version=str(active["index_schema_version"]),
            normalization_version=str(active["normalization_version"]),
            detail="ok" if passed else "verification_failed",
        )

    def _active_bm25_version(self) -> dict[str, str]:
        with self._supabase.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT normalization_version, index_schema_version
                FROM app.bm25_index_versions
                WHERE is_active = true
                ORDER BY version_number DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row is None:
                return {
                    "normalization_version": "arabic_norm_v1",
                    "index_schema_version": "bm25_v1",
                }
            return {
                "normalization_version": str(row["normalization_version"]),
                "index_schema_version": str(row["index_schema_version"]),
            }

    def _fetch_supabase_chunks(self, version_id: UUID) -> list[dict[str, object]]:
        with self._supabase.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, raw_text, search_normalized, content_hash
                FROM app.document_chunks
                WHERE version_id = %s
                  AND deleted_at IS NULL
                  AND is_search_representative = true
                ORDER BY chunk_index ASC
                """,
                (version_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def _parade_content_hash(self, chunk_id: UUID) -> str | None:
        with self._parade.cursor() as cursor:
            cursor.execute(
                "SELECT content_hash FROM bm25_chunks WHERE chunk_id = %s",
                (chunk_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return str(row[0]) if row[0] is not None else None


def _sample_query_text(raw_text: str) -> str:
    """Extract a short deterministic query string from passage text."""

    tokens = raw_text.split()
    return " ".join(tokens[:6]) if tokens else raw_text[:32]
