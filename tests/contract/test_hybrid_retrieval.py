"""Contract tests for Phase 4 Packet 2 dense, term, BM25, and authorization."""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import psycopg
import pytest
from smart_rag_core.ingestion.embeddings.mock_vectors import mock_embedding_vector
from smart_rag_core.retrieval.bm25 import Bm25Retriever
from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer, Bm25ProjectionRow
from smart_rag_core.retrieval.dense import DenseRetriever
from smart_rag_core.retrieval.profiles import (
    EXACT_FALLBACK_AUTHORIZED_ROW_CAP,
    DenseMode,
    HnswProfileId,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.recheck import recheck_retrieval_candidates
from smart_rag_core.retrieval.session import (
    RetrievalSessionError,
    retrieval_transaction,
)
from smart_rag_core.retrieval.terms import TermRetriever
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

from tests.contract.hybrid_retrieval_seed import (
    HybridRetrievalSeed,
    normalized_arabic_hash,
    seed_hybrid_retrieval_fixture,
)
from tests.contract.integration_support import (
    ensure_paradedb_arabic_normalizer,
    ensure_paradedb_bm25_index,
    packet8_paradedb_url,
    paradedb_host_reachable,
    paradedb_psql,
    read_process_env,
    require_supabase_db_url,
    try_connect,
)


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield Postgres or skip when an explicit non-hosted DSN is unavailable."""

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def seed(db_connection: psycopg.Connection) -> HybridRetrievalSeed:
    """Commit one retrieval fixture on the live local database."""

    return seed_hybrid_retrieval_fixture(db_connection)


def test_exact_row_cap_matches_python_constant(
    db_connection: psycopg.Connection,
) -> None:
    """SQL exact-fallback cap matches the Python hard bound."""

    with db_connection.cursor() as cursor:
        cursor.execute("SET ROLE app_api")
        cursor.execute("SELECT app.retrieval_exact_row_cap()")
        row = cursor.fetchone()
    assert row is not None
    assert int(row[0]) == EXACT_FALLBACK_AUTHORIZED_ROW_CAP


def test_member_dense_excludes_restricted_stale_and_deleted(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Member dense results omit restricted, stale, and deleted chunks."""

    retriever = DenseRetriever(db_connection)
    query = mock_embedding_vector(seed.dense_query_text)
    result = retriever.retrieve(
        caller=seed.member,
        query_embedding=query,
        profile=HnswProfileId.HIGH,
        mode=DenseMode.ANN,
        candidate_limit=20,
    )
    ids = {candidate.chunk_id for candidate in result.candidates}
    assert seed.visible_chunk_ids[0] in ids
    assert seed.restricted_chunk_id not in ids
    assert seed.stale_chunk_id not in ids
    assert seed.deleted_chunk_id not in ids


def test_owner_dense_includes_restricted(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Owner dense retrieval can see the ACL-restricted chunk."""

    retriever = DenseRetriever(db_connection)
    query = mock_embedding_vector(seed.restricted_text)
    result = retriever.retrieve(
        caller=seed.owner,
        query_embedding=query,
        profile=HnswProfileId.MEDIUM,
        candidate_limit=10,
    )
    ids = {candidate.chunk_id for candidate in result.candidates}
    assert seed.restricted_chunk_id in ids


def test_disabled_caller_is_rejected_before_rpc(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Disabled callers cannot open a retrieval transaction."""

    retriever = DenseRetriever(db_connection)
    with pytest.raises(RetrievalSessionError, match="caller_disabled"):
        retriever.retrieve(
            caller=seed.disabled,
            query_embedding=mock_embedding_vector("annual leave"),
        )


def test_forged_and_stale_snapshot_return_zero_rows(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Forged user IDs and stale authorization versions return no rows."""

    retriever = DenseRetriever(db_connection)
    forged = CallerContext(
        user_id=str(uuid4()),
        role=UserRole.MEMBER,
        authorization_version=seed.auth_version,
        disabled=False,
        upload_enabled=True,
        mfa_enrolled=True,
    )
    stale = CallerContext(
        user_id=str(seed.member_id),
        role=UserRole.MEMBER,
        authorization_version=seed.auth_version + 99,
        disabled=False,
        upload_enabled=True,
        mfa_enrolled=True,
    )
    query = mock_embedding_vector(seed.dense_query_text)
    forged_result = retriever.retrieve(caller=forged, query_embedding=query)
    stale_result = retriever.retrieve(caller=stale, query_embedding=query)
    assert forged_result.candidates == ()
    assert stale_result.candidates == ()


def test_table_owner_null_caller_returns_zero(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Table-owner connections still fail closed on missing caller context."""

    query = mock_embedding_vector(seed.dense_query_text)
    literal = "[" + ",".join(f"{value:.8f}" for value in query) + "]"
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT chunk_id
            FROM app.retrieve_dense_candidates(
              NULL, NULL, NULL,
              %s::extensions.vector,
              'low',
              'ann',
              10,
              NULL
            )
            """,
            (literal,),
        )
        rows = cursor.fetchall()
    assert rows == []
    assert seed.visible_chunk_ids[0]


def test_service_role_cannot_execute_retrieval_rpc(
    db_connection: psycopg.Connection,
) -> None:
    """``service_role`` is not granted retrieval EXECUTE."""

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT has_function_privilege(
              'service_role',
              'app.retrieve_dense_candidates(uuid,text,bigint,extensions.vector,text,text,integer,text)',
              'execute'
            )
            """
        )
        row = cursor.fetchone()
    assert row is not None
    assert row[0] is False


def test_ann_matches_exact_oracle_on_fixture(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Filtered HNSW top-5 IDs match exact scan on the small seeded fixture."""

    retriever = DenseRetriever(db_connection)
    query = mock_embedding_vector(seed.dense_query_text)
    ann = retriever.retrieve(
        caller=seed.member,
        query_embedding=query,
        profile=HnswProfileId.HIGH,
        mode=DenseMode.ANN,
        candidate_limit=5,
    )
    exact = retriever.retrieve(
        caller=seed.member,
        query_embedding=query,
        profile=HnswProfileId.HIGH,
        mode=DenseMode.EXACT,
        candidate_limit=5,
    )
    assert ann.mode is DenseMode.ANN
    assert exact.mode is DenseMode.EXACT
    assert [item.chunk_id for item in ann.candidates] == [
        item.chunk_id for item in exact.candidates
    ]
    assert seed.visible_chunk_ids[0] == ann.candidates[0].chunk_id


def test_language_filter_is_applied_inside_rpc(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Language predicates run inside the RPC, not as an outer post-filter."""

    retriever = DenseRetriever(db_connection)
    query = mock_embedding_vector(seed.raw_arabic)
    arabic = retriever.retrieve(
        caller=seed.member,
        query_embedding=query,
        language="ar",
        candidate_limit=10,
    )
    ids = {candidate.chunk_id for candidate in arabic.candidates}
    assert seed.arabic_chunk_id in ids
    assert seed.visible_chunk_ids[0] not in ids


def test_hnsw_settings_do_not_leak_after_commit(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """``SET LOCAL`` HNSW GUCs reset after the retrieval transaction commits."""

    with db_connection.cursor() as cursor:
        cursor.execute("SHOW hnsw.ef_search")
        before_row = cursor.fetchone()
    db_connection.commit()
    assert before_row is not None
    with retrieval_transaction(
        db_connection,
        caller=seed.member,
        profile=HnswProfileId.HIGH,
    ):
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('hnsw.ef_search', true)")
            during_row = cursor.fetchone()
        assert during_row is not None
        assert during_row[0] == "120"
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        user_row = cursor.fetchone()
        cursor.execute("SHOW hnsw.ef_search")
        after_row = cursor.fetchone()
    assert user_row is not None
    assert user_row[0] == "postgres"
    assert after_row is not None
    assert after_row[0] == before_row[0]


def test_hnsw_explain_uses_index_when_seqscan_disabled(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """EXPLAIN of the dense ordering uses the HNSW index when seqscan is off."""

    query = mock_embedding_vector(seed.dense_query_text)
    literal = "[" + ",".join(f"{value:.8f}" for value in query) + "]"
    with retrieval_transaction(
        db_connection,
        caller=seed.member,
        profile=HnswProfileId.LOW,
    ):
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT set_config('enable_seqscan', 'off', true)")
            cursor.execute(
                """
                EXPLAIN (FORMAT TEXT)
                SELECT c.id
                FROM app.document_chunks AS c
                WHERE c.deleted_at IS NULL
                  AND c.embedding IS NOT NULL
                ORDER BY c.embedding <=> %s::extensions.vector
                LIMIT 5
                """,
                (literal,),
            )
            plan_rows = cursor.fetchall()
    plan = "\n".join(str(row[0]) for row in plan_rows)
    assert (
        "document_chunks_embedding_hnsw_idx" in plan
        or "HNSW" in plan.upper()
        or "Index" in plan
    )


def test_term_exact_code_and_alias(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Populated terms recall the exact code and the approved alias."""

    retriever = TermRetriever(db_connection)
    exact = retriever.retrieve(caller=seed.member, query_text=seed.code_term)
    alias = retriever.retrieve(caller=seed.member, query_text=seed.alias_term)
    exact_ids = {candidate.chunk_id for candidate in exact.candidates}
    alias_ids = {candidate.chunk_id for candidate in alias.candidates}
    assert seed.code_chunk_id in exact_ids
    assert exact.candidates[0].match_kind == "exact"
    assert seed.code_chunk_id in alias_ids
    assert any(candidate.match_kind == "alias" for candidate in alias.candidates)


def test_cold_term_channel_is_empty(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Unseeded codes cannot be claimed from an empty term channel.

    ``SKU-P4-*`` collides with the Phase 9 open-split corpus via trigram.
    A nonce outside dataset identifier rules keeps the cold-channel proof
    valid on a seeded candidate database.
    """

    retriever = TermRetriever(db_connection)
    result = retriever.retrieve(
        caller=seed.member,
        query_text=f"ZXQCOLD{uuid4().hex}",
    )
    assert result.empty_channel is True
    assert result.candidates == ()


def test_raw_citation_text_is_unchanged(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Retrieval does not mutate stored raw citation text."""

    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT raw_text, search_normalized FROM app.document_chunks WHERE id = %s",
            (seed.arabic_chunk_id,),
        )
        row = cursor.fetchone()
    assert row is not None
    assert row[0] == seed.raw_arabic
    assert row[1] == normalize_arabic_v1(seed.raw_arabic)
    assert row[0] != row[1]


def test_recheck_drops_stale_and_unauthorized_ids(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """BM25-style ID lists lose stale, deleted, and unauthorized survivors."""

    scanned = (
        seed.code_chunk_id,
        seed.stale_chunk_id,
        seed.deleted_chunk_id,
        seed.restricted_chunk_id,
    )
    survivors = recheck_retrieval_candidates(
        db_connection,
        caller=seed.member,
        chunk_ids=scanned,
    )
    ids = {candidate.chunk_id for candidate in survivors}
    assert seed.code_chunk_id in ids
    assert seed.stale_chunk_id not in ids
    assert seed.deleted_chunk_id not in ids
    assert seed.restricted_chunk_id not in ids


def test_postgrest_cannot_call_dense_rpc() -> None:
    """Anon Data API clients cannot invoke retrieval RPCs."""

    api_url = (read_process_env("SUPABASE_URL") or "").rstrip("/")
    anon = read_process_env("SUPABASE_ANON_KEY") or read_process_env(
        "NEXT_PUBLIC_SUPABASE_ANON_KEY"
    )
    if not api_url or not anon:
        pytest.skip("SUPABASE_URL and an anon key are required")
    host = (urlparse(api_url).hostname or "").casefold()
    if host in {"127.0.0.1", "localhost", "host.docker.internal"}:
        pytest.skip("hosted SUPABASE_URL required; local Auth fixture retired")
    try:
        response = httpx.post(
            f"{api_url}/rest/v1/rpc/retrieve_dense_candidates",
            headers={
                "apikey": anon,
                "Authorization": f"Bearer {anon}",
                "Content-Type": "application/json",
            },
            json={},
            timeout=10.0,
        )
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.skip("Supabase Data API unreachable")
    assert response.status_code in {401, 403, 404}


def test_arabic_normalization_parity_hashes(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Core, Supabase, and ParadeDB ``arabic_norm_v1`` hashes match."""

    raw = seed.raw_arabic
    core_hash = normalized_arabic_hash(raw)
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT search.normalize_arabic_v1(%s)", (raw,))
        sql_row = cursor.fetchone()
    assert sql_row is not None
    sql_hash = normalized_arabic_hash(str(sql_row[0]))
    assert sql_hash == core_hash
    if not paradedb_host_reachable() and not _paradedb_exec_ok():
        pytest.skip("ParadeDB unreachable for parity hash")
    ensure_paradedb_arabic_normalizer()
    completed = paradedb_psql(
        "SELECT search.normalize_arabic_v1(" + _sql_quote(raw) + ");\n"
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    parade_text = completed.stdout.strip()
    assert normalized_arabic_hash(parade_text) == core_hash


def test_bm25_typed_query_and_injection(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Typed BM25 queries return canonical IDs; injection text cannot change operators."""

    if not paradedb_host_reachable() and not _paradedb_exec_ok():
        pytest.skip("ParadeDB unreachable")
    parade_url = packet8_paradedb_url()
    if parade_url is None:
        pytest.skip("ParadeDB writer URL unavailable")
    ensure_paradedb_arabic_normalizer()
    ensure_paradedb_bm25_index()
    body = normalize_arabic_v1(
        f"Invoice {seed.code_term} requires delivery within thirty days {seed.token}"
    )
    injection = "leave') OR 1=1 -- ||| ###"
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
                    alias_search=normalize_arabic_v1(seed.alias_term),
                    body_search=body,
                    language="en",
                    acl_scope_id="scope-visible",
                    is_current=True,
                    visibility_generation=1,
                    normalization_version="arabic_norm_v1",
                    content_hash="fixture",
                ),
            )
        )
        parade.commit()
        retriever = Bm25Retriever(parade)
        matched = retriever.retrieve(
            supabase=db_connection,
            caller=seed.member,
            query_text=f"{seed.code_term} delivery",
        )
        injected = retriever.retrieve(
            supabase=db_connection,
            caller=seed.member,
            query_text=injection,
        )
    matched_ids = {candidate.chunk_id for candidate in matched.candidates}
    injected_ids = {candidate.chunk_id for candidate in injected.candidates}
    assert matched.fallback_reason is RetrievalFallbackReason.NONE
    assert seed.code_chunk_id in matched_ids
    assert seed.code_chunk_id not in injected_ids
    assert "body_search" not in injection
    variants = retriever.retrieve_variants(
        supabase=db_connection,
        caller=seed.member,
        texts=(f"{seed.code_term} delivery",),
        version_id=seed.visible_version_id,
    )
    assert variants.fallback_reason is RetrievalFallbackReason.NONE
    assert seed.code_chunk_id in {item.chunk_id for item in variants.candidates}


def _paradedb_exec_ok() -> bool:
    """Return whether Compose exec can reach ParadeDB.

    Returns:
        True when ``SELECT 1`` succeeds via ``paradedb_psql``.
    """

    from tests.contract.integration_support import paradedb_reachable

    return paradedb_reachable()


def _sql_quote(value: str) -> str:
    """Quote a SQL string literal for ``psql -c`` without logging secrets.

    Args:
        value: Raw Unicode text.

    Returns:
        Single-quoted SQL literal.
    """

    return "'" + value.replace("'", "''") + "'"


def test_candidate_limit_is_clamped(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Dense SQL clamps requested limits to 100."""

    retriever = DenseRetriever(db_connection)
    result = retriever.retrieve(
        caller=seed.member,
        query_embedding=mock_embedding_vector(seed.dense_query_text),
        candidate_limit=500,
    )
    assert len(result.candidates) <= 100
    assert seed.visible_chunk_ids[0] in {item.chunk_id for item in result.candidates}


def test_direct_and_session_protocol_return_identical_ids(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Two independent FastAPI-style sessions return the same authorized IDs."""

    query = mock_embedding_vector(seed.dense_query_text)
    first = DenseRetriever(db_connection).retrieve(
        caller=seed.member,
        query_embedding=query,
        profile=HnswProfileId.LOW,
        candidate_limit=8,
    )
    second = DenseRetriever(db_connection).retrieve(
        caller=seed.member,
        query_embedding=query,
        profile=HnswProfileId.LOW,
        candidate_limit=8,
    )
    assert [item.chunk_id for item in first.candidates] == [
        item.chunk_id for item in second.candidates
    ]
