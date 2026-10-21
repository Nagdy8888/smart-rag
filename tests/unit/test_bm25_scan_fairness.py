"""Pre-recheck SQL bounds preserve narrow variants when dense search is unavailable."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import psycopg
import pytest
from smart_rag_core.retrieval.bm25 import Bm25Retriever
from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer
from smart_rag_core.retrieval.profiles import (
    BM25_FIELD_PRIORITY,
    BM25_INDEX_SCHEMA_VERSION,
    NORMALIZATION_VERSION,
    Bm25Operator,
)
from smart_rag_core.security.identity import CallerContext


@pytest.mark.parametrize("count,quota", [(1, 300), (2, 150), (3, 100)])
def test_each_variant_is_bounded_then_interleaved_before_authoritative_recheck(
    count: int, quota: int
) -> None:
    """The canonical 75-survivor cap must see each query's best scan rows first."""
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    caller = CallerContext.from_profile_row(
        user_id="00000000-0000-4000-8000-000000000001",
        role="viewer",
        authorization_version=1,
    )
    with (
        patch(
            "smart_rag_core.retrieval.bm25.recheck_retrieval_candidates",
            return_value=(),
        ) as recheck,
        patch.object(
            Bm25Indexer,
            "fetch_meta",
            return_value={
                "normalization_version": NORMALIZATION_VERSION,
                "index_schema_version": BM25_INDEX_SCHEMA_VERSION,
            },
        ),
        patch.object(Bm25Indexer, "search_index_exists", return_value=True),
    ):
        result = Bm25Retriever(cast(psycopg.Connection, connection)).retrieve_variants(
            supabase=cast(psycopg.Connection, connection),
            caller=caller,
            texts=tuple(f"needle{i}" for i in range(count)),
            operator=Bm25Operator.MATCH_DISJUNCTION,
            language=None,
            acl_scope_id=None,
            version_id=None,
            fields=BM25_FIELD_PRIORITY,
        )
    statement, params = cursor.execute.call_args.args
    text = statement.as_string()
    assert text.count(f"LIMIT {quota}") == count
    assert "PARTITION BY variant_ordinal" in text
    assert "ORDER BY variant_rank ASC, variant_ordinal ASC" in text
    assert params[-1] == 300
    assert "needle0" not in text and "needle0" in params
    assert result.candidates == ()
    recheck.assert_called_once()
    assert recheck.call_args.kwargs["caller"] is caller
