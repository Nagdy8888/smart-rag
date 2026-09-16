"""Verified citation persistence for Ask Sources."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import list_run_citations
from smart_rag_core.query_answer.citations import (
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


def test_maybe_persist_reraises_bound_failure() -> None:
    """A bound persist failure is not hidden as an empty success list."""

    fusion = verifier_fusion(verifier_passage(1, text="Refund period is 30 days."))
    answer = AnswerPayload(
        answer_text="Refund period is 30 days.",
        citations=(AnswerCitation(chunk_id=fusion.evidence[0].chunk_id),),
        status="complete",
    )
    with (
        patch(
            "smart_rag_core.query_answer.citations.list_run_citations",
            return_value=(),
        ),
        patch(
            "smart_rag_core.query_answer.citations.persist_answer_citations",
            side_effect=QueryAdmissionError("span_not_contained"),
        ),
    ):
        with pytest.raises(QueryAdmissionError, match="span_not_contained"):
            maybe_persist_verified_citations(
                MagicMock(),
                caller=MagicMock(),
                run_id=uuid4(),
                fusion=fusion,
                answer=answer,
            )


def test_verify_bound_persist_failure_is_not_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bound citation persist failure cannot terminate as verified."""

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.nodes.verify import verify_answer_node
    from smart_rag_agents.query.state import pending_query_state
    from smart_rag_core.query_answer.models import AnswerParagraph, AtomicLink
    from smart_rag_core.security.identity import UserRole

    fusion = verifier_fusion(verifier_passage(1, text="Refund period is 30 days."))
    chunk_id = fusion.evidence[0].chunk_id
    runtime = MagicMock()
    runtime.user_id = uuid4()
    runtime.role = UserRole.MEMBER
    runtime.authorization_version = 1
    runtime.session_id = None
    runtime.run_id = uuid4()

    def _runtime_from_state(_state: object) -> MagicMock:
        """Return the mocked runtime regardless of graph state."""

        return runtime

    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.runtime_from_state",
        _runtime_from_state,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.summarize_run_usage",
        MagicMock(side_effect=QueryAdmissionError("database_rejected")),
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.maybe_persist_verified_citations",
        MagicMock(side_effect=QueryAdmissionError("span_not_contained")),
    )
    state = pending_query_state(user_query="What is the refund period?")
    state["status"] = "answered"
    state["remaining_model_calls"] = 8
    state["fusion"] = fusion.model_dump(mode="json")
    state["answer"] = AnswerPayload(
        answer_text="Refund period is 30 days.",
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="Refund period is 30 days.",
                link_ids=("l1",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span="Refund period is 30 days.",
                paragraph_index=0,
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="Refund period is 30 days.",
                chunk_ids=(chunk_id,),
            ),
        ),
        status="complete",
    ).model_dump(mode="json")
    verified = verify_answer_node(
        state,
        QueryGraphDeps(connection=MagicMock()),
    )
    assert verified["status"] != "verified"
    assert verified["detail"] == "citation_persist_failed"


def test_live_persist_does_not_backfill_fusion_citations() -> None:
    """Citation persist never reconstructs rows from every fusion passage."""

    from smart_rag_core.query_answer import citations as citations_mod

    source = Path(citations_mod.__file__).read_text(encoding="utf-8")
    assert "ensure_fusion_source_citations" not in source
    fusion = verifier_fusion(verifier_passage(1, text="Refund period is 30 days."))
    answer = AnswerPayload(
        answer_text="The refund period is 30 days.",
        status="complete",
    )
    assert answer.citations == ()
    persisted = maybe_persist_verified_citations(
        None,
        caller=None,
        run_id=None,
        fusion=fusion,
        answer=answer,
    )
    assert persisted == ()


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
              page_number, section_path, provenance
            )
            VALUES (
              %s, %s, %s, 0, 'Refund period is 30 days.', 12, ARRAY['Refunds'],
              '{"locators": [{"format": "pdf", "page_index": 11, "page_label": "xii"}]}'::jsonb
            )
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
            AnswerCitation(
                chunk_id=str(chunk_id),
                span="Refund period is 30 days.",
                paragraph_index=0,
            ),
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
    assert records[0].provenance.get("page_label") == "xii"
    assert records[0].provenance.get("document_title") == "Citation persist fixture"
    assert records[0].paragraph_index == 0
    assert records[0].document_title == "Citation persist fixture"
    assert records[0].pdf_page_number == 12
    assert records[0].evidence_excerpt == "Refund period is 30 days."
    assert "Refund period" not in str(records[0].provenance)
