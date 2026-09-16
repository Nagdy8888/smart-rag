"""Contract tests for run-scoped Web evidence RPCs (P06-39)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.conversations import delete_conversation
from smart_rag_core.memory.reaper import search_conversation_lingering_ids
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import list_run_citations
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.web_research.models import WebCitation
from smart_rag_core.web_research.policy import excerpt_sha256
from smart_rag_core.web_research.store import (
    begin_web_research_operation,
    insert_web_citation,
    insert_web_source,
    mark_web_research_operation_sent,
)

from tests.contract.integration_support import require_supabase_db_url, try_connect
from tests.support.query_postgres import (
    admit,
    authorization_version,
    caller_context,
    insert_conversation,
    insert_user_profile,
)


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield a rollback Postgres connection or skip when local Supabase is down."""

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def _hash(seed: str) -> str:
    """Return a 64-character request hash.

    Args:
        seed: Stable test seed. Never a query.

    Returns:
        SHA-256 hex digest.
    """

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _admit_run(
    connection: psycopg.Connection, *, user_id: UUID, role: str
) -> tuple[CallerContext, UUID, UUID]:
    """Insert a profile, conversation, and admitted run as ``app_api``.

    Args:
        connection: Open test connection.
        user_id: Auth user id.
        role: Profile role.

    Returns:
        Caller context, run id, and conversation id.
    """

    connection.execute("RESET ROLE")
    with connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=user_id, role=role)
        conversation_id = insert_conversation(cursor, user_id=user_id)
        version = authorization_version(cursor)
    caller = caller_context(user_id=user_id, role=role, authorization_version=version)
    result, _key = admit(
        connection,
        caller=caller,
        conversation_id=conversation_id,
        message=f"web-evidence {user_id}",
    )
    connection.execute("SET ROLE app_api")
    return caller, result.context.run_id, conversation_id


def test_web_source_insert_list_omits_excerpt(
    db_connection: psycopg.Connection,
) -> None:
    """Owned insert lists URL metadata and never returns excerpt or span."""

    caller, run_id, _conversation_id = _admit_run(
        db_connection, user_id=uuid4(), role="member"
    )
    excerpt = "Public excerpt about water."
    source = insert_web_source(
        db_connection,
        caller=caller,
        run_id=run_id,
        source_index=0,
        url="https://example.com/water",
        title="Water",
        excerpt=excerpt,
    )
    insert_web_citation(
        db_connection,
        caller=caller,
        run_id=run_id,
        citation_index=0,
        source=source,
        citation=WebCitation(web_source_id=source.web_source_id, span="Public excerpt"),
    )
    records = list_run_citations(db_connection, caller=caller, run_id=run_id)
    assert len(records) == 1
    assert records[0].source_kind == "web"
    assert records[0].web_source_id == UUID(source.web_source_id)
    assert records[0].provenance.get("url") == "https://example.com/water"
    assert records[0].provenance.get("title") == "Water"
    dumped = str(records[0].provenance)
    assert "excerpt" not in dumped
    assert "Public excerpt" not in dumped
    assert "span" not in records[0].provenance
    assert "html" not in dumped
    assert "query" not in dumped


def test_operation_replay_and_conflict(db_connection: psycopg.Connection) -> None:
    """Same key+hash replays; different hash conflicts; sent is ambiguous."""

    caller, run_id, _conversation_id = _admit_run(
        db_connection, user_id=uuid4(), role="member"
    )
    first = begin_web_research_operation(
        db_connection,
        caller=caller,
        run_id=run_id,
        operation_key="search-round-1",
        kind="search",
        request_hash=_hash("q1"),
    )
    replay = begin_web_research_operation(
        db_connection,
        caller=caller,
        run_id=run_id,
        operation_key="search-round-1",
        kind="search",
        request_hash=_hash("q1"),
    )
    assert replay.replayed is True
    assert replay.operation_id == first.operation_id
    with pytest.raises(QueryAdmissionError, match="conflict"):
        begin_web_research_operation(
            db_connection,
            caller=caller,
            run_id=run_id,
            operation_key="search-round-1",
            kind="search",
            request_hash=_hash("q2"),
        )
    mark_web_research_operation_sent(
        db_connection,
        caller=caller,
        operation_id=UUID(first.operation_id),
    )
    with pytest.raises(QueryAdmissionError, match="ambiguous"):
        begin_web_research_operation(
            db_connection,
            caller=caller,
            run_id=run_id,
            operation_key="search-round-1",
            kind="search",
            request_hash=_hash("q1"),
        )


def test_caps_and_span_and_foreign_run(db_connection: psycopg.Connection) -> None:
    """Seventh source, thirteenth citation, and foreign-run source fail closed."""

    caller, run_id, _conversation_id = _admit_run(
        db_connection, user_id=uuid4(), role="member"
    )
    other, other_run_id, _other_conversation = _admit_run(
        db_connection, user_id=uuid4(), role="member"
    )
    sources = [
        insert_web_source(
            db_connection,
            caller=caller,
            run_id=run_id,
            source_index=index,
            url=f"https://example.com/p{index}",
            title="T",
            excerpt="abcdef",
        )
        for index in range(6)
    ]
    with pytest.raises(QueryAdmissionError, match="cap_exceeded"):
        insert_web_source(
            db_connection,
            caller=caller,
            run_id=run_id,
            source_index=0,
            url="https://example.com/p6",
            title="T",
            excerpt="abcdef",
        )
    with pytest.raises(ValueError, match="span_not_contained"):
        insert_web_citation(
            db_connection,
            caller=caller,
            run_id=run_id,
            citation_index=0,
            source=sources[0],
            citation=WebCitation(
                web_source_id=sources[0].web_source_id, span="missing"
            ),
        )
    with pytest.raises(QueryAdmissionError, match="not_found"):
        list_run_citations(db_connection, caller=other, run_id=run_id)
    other_source = insert_web_source(
        db_connection,
        caller=other,
        run_id=other_run_id,
        source_index=0,
        url="https://example.com/other",
        title="O",
        excerpt="other excerpt",
    )
    with pytest.raises(QueryAdmissionError, match="not_found"):
        insert_web_citation(
            db_connection,
            caller=caller,
            run_id=run_id,
            citation_index=0,
            source=other_source,
            citation=WebCitation(
                web_source_id=other_source.web_source_id, span="other"
            ),
        )


def test_thirteenth_citation_and_invalid_inputs(
    db_connection: psycopg.Connection,
) -> None:
    """Citation cap, bad URL, bad hash, and oversized excerpt fail closed."""

    caller, run_id, _conversation_id = _admit_run(
        db_connection, user_id=uuid4(), role="member"
    )
    source = insert_web_source(
        db_connection,
        caller=caller,
        run_id=run_id,
        source_index=0,
        url="https://example.com/cap",
        title="Cap",
        excerpt="same span " * 20,
    )
    for index in range(12):
        insert_web_citation(
            db_connection,
            caller=caller,
            run_id=run_id,
            citation_index=index,
            source=source,
            citation=WebCitation(web_source_id=source.web_source_id, span="same span"),
        )
    with pytest.raises(QueryAdmissionError, match="cap_exceeded"):
        insert_web_citation(
            db_connection,
            caller=caller,
            run_id=run_id,
            citation_index=0,
            source=source,
            citation=WebCitation(web_source_id=source.web_source_id, span="same span"),
        )
    with pytest.raises(ValueError, match="invalid_url"):
        insert_web_source(
            db_connection,
            caller=caller,
            run_id=run_id,
            source_index=1,
            url="https://127.0.0.1/private",
            title="Bad",
            excerpt="loopback",
        )
    with pytest.raises(QueryAdmissionError, match="invalid_excerpt"):
        insert_web_source(
            db_connection,
            caller=caller,
            run_id=run_id,
            source_index=1,
            url="https://example.com/oversize",
            title="Big",
            excerpt="x" * 8001,
        )


def test_rpc_rejects_mismatched_content_hash(
    db_connection: psycopg.Connection,
) -> None:
    """RPC hash check rejects a digest that is not SHA-256 of the excerpt."""

    caller, run_id, _conversation_id = _admit_run(
        db_connection, user_id=uuid4(), role="member"
    )
    db_connection.execute("RESET ROLE")
    db_connection.execute("SET ROLE app_api")
    with pytest.raises(psycopg.Error, match="invalid_hash"):
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM app.insert_web_source(
                  %s, %s, %s, %s, 1, 'https://example.com/hash', 'T',
                  'ok excerpt', %s, NULL
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                    "0" * 64,
                ),
            )
    assert excerpt_sha256("ok excerpt") != "0" * 64


def test_delete_conversation_purges_web_tables(
    db_connection: psycopg.Connection,
) -> None:
    """Conversation delete removes operations, sources, and citations."""

    caller, run_id, conversation_id = _admit_run(
        db_connection, user_id=uuid4(), role="member"
    )
    begin_web_research_operation(
        db_connection,
        caller=caller,
        run_id=run_id,
        operation_key="search-round-1",
        kind="search",
        request_hash=_hash("delete"),
    )
    source = insert_web_source(
        db_connection,
        caller=caller,
        run_id=run_id,
        source_index=0,
        url="https://example.com/delete",
        title="D",
        excerpt="to be purged",
    )
    insert_web_citation(
        db_connection,
        caller=caller,
        run_id=run_id,
        citation_index=0,
        source=source,
        citation=WebCitation(web_source_id=source.web_source_id, span="purged"),
    )
    delete_conversation(db_connection, caller=caller, conversation_id=conversation_id)
    db_connection.execute("RESET ROLE")
    lingering = search_conversation_lingering_ids(
        db_connection, conversation_id=conversation_id
    )
    assert lingering.get("app.web_research_operations") == 0
    assert lingering.get("app.web_sources") == 0
    assert lingering.get("app.web_citations") == 0


def test_app_api_cannot_insert_web_tables_directly(
    db_connection: psycopg.Connection,
) -> None:
    """``app_api`` has no table DML on Web evidence tables."""

    db_connection.execute("SET ROLE app_api")
    with pytest.raises(psycopg.Error):
        db_connection.execute(
            """
            INSERT INTO app.web_sources (
              run_id, source_index, url, title, excerpt, content_hash
            )
            VALUES (
              gen_random_uuid(), 0, 'https://example.com/x', '', 'x',
              repeat('a', 64)
            )
            """
        )
    db_connection.execute("RESET ROLE")
