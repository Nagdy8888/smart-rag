"""Unit tests for BM25 projection match rules including table-only versions."""

from __future__ import annotations

from smart_rag_core.retrieval.bm25_verifier import bm25_projection_matches


def test_bm25_projection_matches_representative_chunks() -> None:
    """Non-empty equal counts with no hash drift pass."""

    assert (
        bm25_projection_matches(
            supabase_row_count=3,
            parade_row_count=3,
            hash_mismatches=0,
            table_row_count=0,
        )
        is True
    )


def test_bm25_projection_rejects_empty_without_tables() -> None:
    """Zero chunks on both sides is not Hybrid Ready unless tables exist."""

    assert (
        bm25_projection_matches(
            supabase_row_count=0,
            parade_row_count=0,
            hash_mismatches=0,
            table_row_count=0,
        )
        is False
    )


def test_bm25_projection_matches_table_only_empty_chunks() -> None:
    """CSV/XLSX table artifacts allow an empty BM25 projection."""

    assert (
        bm25_projection_matches(
            supabase_row_count=0,
            parade_row_count=0,
            hash_mismatches=0,
            table_row_count=1,
        )
        is True
    )


def test_bm25_projection_rejects_count_or_hash_drift() -> None:
    """Count mismatch or hash disagreement still fail closed."""

    assert (
        bm25_projection_matches(
            supabase_row_count=2,
            parade_row_count=1,
            hash_mismatches=0,
            table_row_count=1,
        )
        is False
    )
    assert (
        bm25_projection_matches(
            supabase_row_count=2,
            parade_row_count=2,
            hash_mismatches=1,
            table_row_count=0,
        )
        is False
    )
