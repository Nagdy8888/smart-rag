"""Verified citation persistence for Ask Sources."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.query_admission.service import list_run_citations
from smart_rag_core.query_answer.citations import (
    ensure_fusion_source_citations,
    maybe_persist_verified_citations,
    persist_answer_citations,
)
from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload
from smart_rag_core.query_fusion.models import PassageOrigin, ScoredPassage

from tests.contract.integration_support import require_supabase_db_url, try_connect
from tests.support.answer_verifier import verifier_fusion, verifier_passage
from tests.support.query_postgres import (
    admit,
    authorization_version,
    caller_context,
    insert_conversation,
    insert_user_profile,
)


def test_maybe_persist_skips_without_connection() -> None:
    """Studio and unbound graphs do not require durable citation rows."""

    fusion = verifier_fusion(verifier_passage(1, text="Refund period is 30 days."))
    answer = AnswerPayload(
        answer_text="Refund period is 30 days.",
        citations=(AnswerCitation(chunk_id=fusion.evidence[0].chunk_id),),
        status="complete",
    )
    assert (
        maybe_persist_verified_citations(
            None,
            caller=None,
            run_id=uuid4(),
            fusion=fusion,
            answer=answer,
        )
        == ()
    )


def test_maybe_persist_delegates_once_when_bound() -> None:
    """Verify node path inserts through the shared helper exactly once."""

    fusion = verifier_fusion(verifier_passage(1, text="Refund period is 30 days."))
    answer = AnswerPayload(
        answer_text="Refund period is 30 days.",
        citations=(AnswerCitation(chunk_id=fusion.evidence[0].chunk_id),),
        status="complete",
    )
    run_id = uuid4()
    caller = MagicMock()
    connection = MagicMock()
    inserted = (uuid4(),)

    with (
        patch(
            "smart_rag_core.query_answer.citations.list_run_citations",
            side_effect=[(), (MagicMock(),)],
        ) as list_existing,
        patch(
            "smart_rag_core.query_answer.citations.persist_answer_citations",
            return_value=inserted,
        ) as persist,
    ):
        first = maybe_persist_verified_citations(
            connection,
            caller=caller,
            run_id=run_id,
            fusion=fusion,
            answer=answer,
        )
        second = maybe_persist_verified_citations(
            connection,
            caller=caller,
            run_id=run_id,
            fusion=fusion,
            answer=answer,
        )

    assert first == inserted
    assert second == ()
    persist.assert_called_once()
    assert list_existing.call_count == 2


def test_ensure_fusion_source_citations_backfills_model_gap() -> None:
    """Live answers without structured citations still cite retrieved passages."""

    fusion = verifier_fusion(verifier_passage(1, text="Refund period is 30 days."))
    answer = AnswerPayload(
        answer_text="The refund period is 30 days.",
        status="complete",
    )
    enriched = ensure_fusion_source_citations(answer, fusion=fusion, tables=())
    assert enriched.citations[0].chunk_id == fusion.evidence[0].chunk_id


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


def test_persist_answer_citations_lists_for_owned_run(
    db_connection: psycopg.Connection,
) -> None:
    """Persisted rows are returned by ``GET /runs/{id}/citations`` RPC."""

    owner_id = uuid4()
    member_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    chunk_id = uuid4()

    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        cursor.execute(
            """
            INSERT INTO app.documents (
              id, title, visibility, created_by
            )
            VALUES (%s, 'Citation persist fixture', 'company_visible', %s)
            """,
            (document_id, owner_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, created_by
            )
            VALUES (%s, %s, 1, %s)
            """,
            (version_id, document_id, owner_id),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s
            WHERE id = %s
            """,
            (version_id, document_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text,
              page_number, section_path
            )
            VALUES (%s, %s, %s, 0, 'Refund period is 30 days.', 12, ARRAY['Refunds'])
            """,
            (chunk_id, document_id, version_id),
        )
        authz = authorization_version(cursor)

    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(
        db_connection,
        caller=member,
        conversation_id=conversation_id,
    )
    fusion = verifier_fusion(
        ScoredPassage(
            chunk_id=str(chunk_id),
            document_id=str(document_id),
            version_id=str(version_id),
            citation_text="Refund period is 30 days.",
            hybrid_rank=1,
            combined_score=1.0,
            origin=PassageOrigin.HYBRID,
            graph_discovered_only=False,
            page_number=12,
            section_path=("Refunds",),
        )
    )
    answer = AnswerPayload(
        answer_text="Refund period is 30 days.",
        citations=(
            AnswerCitation(chunk_id=str(chunk_id), span="Refund period is 30 days."),
        ),
        status="complete",
    )
    db_connection.execute("SET ROLE app_api")
    inserted = persist_answer_citations(
        db_connection,
        caller=member,
        run_id=admitted.context.run_id,
        fusion=fusion,
        answer=answer,
    )
    assert inserted
    records = list_run_citations(
        db_connection,
        caller=member,
        run_id=admitted.context.run_id,
    )
    assert len(records) == len(inserted)
    assert records[0].citation_index == 0
    assert records[0].chunk_id == UUID(str(chunk_id))
    assert records[0].provenance.get("page_number") == 12
    assert records[0].provenance.get("document_title") == "Citation persist fixture"
    assert "Refund period" not in str(records[0].provenance)
