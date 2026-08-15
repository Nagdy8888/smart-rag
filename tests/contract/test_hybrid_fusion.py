"""Contract tests that fused Hybrid IDs stay authorized and capped."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import psycopg
import pytest
from smart_rag_core.ingestion.embeddings.mock_vectors import mock_embedding_vector
from smart_rag_core.retrieval.bm25 import Bm25Retriever
from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer, Bm25ProjectionRow
from smart_rag_core.retrieval.dense import DenseRetriever
from smart_rag_core.retrieval.hybrid import assemble_hybrid
from smart_rag_core.retrieval.profiles import (
    BM25_SCAN_ID_CAP,
    PREFUSION_UNION_CAP,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.recheck import recheck_retrieval_candidates
from smart_rag_core.retrieval.terms import TermRetriever
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

from tests.contract.hybrid_retrieval_seed import (
    HybridRetrievalSeed,
    seed_hybrid_retrieval_fixture,
)
from tests.contract.integration_support import (
    ensure_paradedb_arabic_normalizer,
    ensure_paradedb_bm25_index,
    packet8_paradedb_url,
    paradedb_host_reachable,
    paradedb_reachable,
    resolve_supabase_db_url,
    try_connect,
)


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield Postgres or skip when local Supabase is unreachable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def seed(db_connection: psycopg.Connection) -> HybridRetrievalSeed:
    """Commit one retrieval fixture on the live local database."""

    return seed_hybrid_retrieval_fixture(db_connection)


def _assert_no_seed_leaks(
    seed: HybridRetrievalSeed,
    chunk_ids: tuple[UUID, ...],
) -> None:
    """Reject this seed's restricted, stale, and deleted IDs.

    Args:
        seed: Fixture whose leak IDs must be absent.
        chunk_ids: Candidate IDs under test.
    """

    forbidden = {
        seed.restricted_chunk_id,
        seed.stale_chunk_id,
        seed.deleted_chunk_id,
    }
    assert set(chunk_ids).isdisjoint(forbidden)


def test_fused_ids_are_authorized_and_capped(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Dense+term fusion returns only authorized IDs and stays inside 205."""

    dense = DenseRetriever(db_connection).retrieve(
        caller=seed.member,
        query_embedding=mock_embedding_vector(seed.dense_query_text),
    )
    terms = TermRetriever(db_connection).retrieve(
        caller=seed.member,
        query_text=seed.code_term,
    )
    dense_ids = tuple(item.chunk_id for item in dense.candidates)
    term_ids = tuple(item.chunk_id for item in terms.candidates)
    _assert_no_seed_leaks(seed, dense_ids)
    _assert_no_seed_leaks(seed, term_ids)
    assert seed.visible_chunk_ids[0] in set(dense_ids)
    assert seed.code_chunk_id in set(term_ids)
    result = assemble_hybrid(
        dense_variants=(dense.candidates,),
        bm25_variants=(),
        term_variants=(terms.candidates,),
        bm25_fallback=RetrievalFallbackReason.BM25_UNAVAILABLE,
        principal_scope_hash="contract",
        query_normalized=normalize_arabic_v1(seed.dense_query_text),
        visibility_generation=1,
    )
    fused_ids = tuple(item.chunk_id for item in result.fused)
    _assert_no_seed_leaks(seed, fused_ids)
    assert len(result.fused) <= PREFUSION_UNION_CAP
    assert result.fallback_reason is RetrievalFallbackReason.BM25_UNAVAILABLE
    assert seed.restricted_chunk_id not in set(fused_ids)


def test_live_bm25_recheck_drops_restricted_before_fusion(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """ParadeDB may scan a restricted ID; recheck and fusion must drop it."""

    if not paradedb_host_reachable() and not paradedb_reachable():
        pytest.skip("ParadeDB unreachable")
    parade_url = packet8_paradedb_url()
    if parade_url is None:
        pytest.skip("ParadeDB writer URL unavailable")
    ensure_paradedb_arabic_normalizer()
    ensure_paradedb_bm25_index()
    shared = f"delivery invoice {seed.token}"
    with psycopg.connect(parade_url) as parade:
        indexer = Bm25Indexer(parade)
        indexer.upsert_batch(
            (
                Bm25ProjectionRow(
                    chunk_id=seed.code_chunk_id,
                    version_id=seed.visible_version_id,
                    document_id=seed.visible_document_id,
                    title_search=normalize_arabic_v1("Visible Policy"),
                    heading_search=None,
                    alias_search=None,
                    body_search=normalize_arabic_v1(shared),
                    language="en",
                    acl_scope_id="scope-visible",
                    is_current=True,
                    visibility_generation=1,
                    normalization_version="arabic_norm_v1",
                    content_hash="fixture-visible",
                ),
                Bm25ProjectionRow(
                    chunk_id=seed.restricted_chunk_id,
                    version_id=seed.restricted_version_id,
                    document_id=seed.restricted_document_id,
                    title_search=normalize_arabic_v1("Restricted Ledger"),
                    heading_search=None,
                    alias_search=None,
                    body_search=normalize_arabic_v1(shared),
                    language="en",
                    acl_scope_id="scope-restricted",
                    is_current=True,
                    visibility_generation=1,
                    normalization_version="arabic_norm_v1",
                    content_hash="fixture-restricted",
                ),
            )
        )
        parade.commit()
        bm25 = Bm25Retriever(parade).retrieve(
            supabase=db_connection,
            caller=seed.member,
            query_text=shared,
        )
    assert len(bm25.scanned_ids) <= BM25_SCAN_ID_CAP
    assert seed.restricted_chunk_id not in {item.chunk_id for item in bm25.candidates}
    rechecked = recheck_retrieval_candidates(
        db_connection,
        caller=seed.member,
        chunk_ids=bm25.scanned_ids,
    )
    rechecked_ids = {item.chunk_id for item in rechecked}
    assert seed.restricted_chunk_id not in rechecked_ids
    _assert_no_seed_leaks(seed, tuple(item.chunk_id for item in rechecked))
    result = assemble_hybrid(
        dense_variants=(),
        bm25_variants=(bm25.candidates,),
        term_variants=(),
        scanned_bm25=bm25.scanned_ids,
        principal_scope_hash="contract",
        query_normalized=normalize_arabic_v1(shared),
        visibility_generation=1,
    )
    fused_ids = tuple(item.chunk_id for item in result.fused)
    _assert_no_seed_leaks(seed, fused_ids)
    assert seed.restricted_chunk_id not in set(fused_ids)
    assert len(result.scanned_bm25) <= BM25_SCAN_ID_CAP
    if (
        bm25.fallback_reason is RetrievalFallbackReason.NONE
        and seed.restricted_chunk_id in bm25.scanned_ids
    ):
        assert seed.restricted_chunk_id not in set(fused_ids)
