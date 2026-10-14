"""P06-46 PDF paragraph citation persistence, ACL recheck, and history batching."""

from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_api.services.conversation_transcript import list_conversation_messages
from smart_rag_api.services.query_runs import escape_run_citation
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.messages import append_query_message
from smart_rag_core.query_admission.service import (
    list_conversation_citations,
    list_run_citations,
)
from smart_rag_core.query_answer.citations import persist_answer_citations
from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload
from smart_rag_core.query_fusion.models import PassageOrigin, ScoredPassage
from smart_rag_core.security.identity import CallerContext

from tests.contract.integration_support import require_supabase_db_url, try_connect
from tests.support.answer_verifier import verifier_fusion
from tests.support.query_postgres import (
    admit,
    authorization_version,
    caller_context,
    insert_conversation,
    insert_user_profile,
)

SPAN = "The policy on page twenty five is binding."
TITLE = "Citation page fixture"


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


def _pdf_locators(
    *,
    page_index: int,
    page_label: str,
    extra: dict[str, object] | None = None,
) -> str:
    """Return jsonb locators for one PDF page, optionally a second locator.

    Args:
        page_index: Zero-based PDF file page.
        page_label: Printed label that must not drive ``pdf_page_number``.
        extra: Optional second locator mapping.

    Returns:
        JSON text for ``document_chunks.provenance``.
    """

    locators: list[dict[str, object]] = [
        {
            "format": "pdf",
            "page_index": page_index,
            "page_label": page_label,
        }
    ]
    if extra is not None:
        locators.append(extra)
    return json.dumps({"locators": locators})


def _insert_chunk(
    cursor: psycopg.Cursor,
    *,
    chunk_id: UUID,
    document_id: UUID,
    version_id: UUID,
    raw_text: str,
    page_number: int,
    provenance: str,
    parent_chunk_id: UUID | None = None,
    chunk_index: int = 0,
) -> None:
    """Insert one canonical chunk row.

    Args:
        cursor: Open postgres-role cursor.
        chunk_id: Chunk primary key.
        document_id: Owning document.
        version_id: Owning version.
        raw_text: Canonical text that must contain the citation span.
        page_number: Stored page that may disagree with locators.
        provenance: Locator jsonb text.
        parent_chunk_id: Parent chunk when this row is a leaf child.
        chunk_index: Order within the version.
    """

    cursor.execute(
        """
        INSERT INTO app.document_chunks (
          id, document_id, version_id, chunk_index, raw_text,
          page_number, provenance, parent_chunk_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        """,
        (
            chunk_id,
            document_id,
            version_id,
            chunk_index,
            raw_text,
            page_number,
            provenance,
            parent_chunk_id,
        ),
    )


def _seed_document(
    cursor: psycopg.Cursor,
    *,
    owner_id: UUID,
    title: str = TITLE,
) -> tuple[UUID, UUID]:
    """Insert a company-visible document and current version.

    Args:
        cursor: Open postgres-role cursor.
        owner_id: Document creator.
        title: Live document title.

    Returns:
        ``(document_id, version_id)``.
    """

    document_id = uuid4()
    version_id = uuid4()
    cursor.execute(
        """
        INSERT INTO app.documents (id, title, visibility, created_by)
        VALUES (%s, %s, 'company_visible', %s)
        """,
        (document_id, title, owner_id),
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
    return document_id, version_id


def _persist(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    chunk_id: UUID,
    document_id: UUID,
    version_id: UUID,
    span: str = SPAN,
    paragraph_index: int | None = 0,
    extra_citations: tuple[AnswerCitation, ...] = (),
) -> tuple[UUID, ...]:
    """Persist one passage citation through ``insert_run_citation_v2``.

    Args:
        connection: Open connection.
        caller: Server-derived caller.
        run_id: Admitted run.
        chunk_id: Source chunk, possibly a parent.
        document_id: Document UUID for fusion locators.
        version_id: Version UUID for fusion locators.
        span: Exact excerpt.
        paragraph_index: Owning paragraph.
        extra_citations: Additional citations written after the first.

    Returns:
        Inserted citation UUIDs.
    """

    fusion = verifier_fusion(
        ScoredPassage(
            chunk_id=str(chunk_id),
            document_id=str(document_id),
            version_id=str(version_id),
            citation_text=span,
            hybrid_rank=1,
            combined_score=1.0,
            origin=PassageOrigin.HYBRID,
            graph_discovered_only=False,
            page_number=12,
        )
    )
    citations = (
        AnswerCitation(
            chunk_id=str(chunk_id),
            span=span,
            paragraph_index=paragraph_index,
        ),
        *extra_citations,
    )
    answer = AnswerPayload(
        answer_text=span,
        citations=citations,
        status="complete",
    )
    connection.execute("SET ROLE app_api")
    try:
        result = persist_answer_citations(
            connection,
            caller=caller,
            run_id=run_id,
            fusion=fusion,
            answer=answer,
        )
        return result.ids
    finally:
        connection.execute("RESET ROLE")


def test_leaf_citation_uses_locator_viewer_page_25(
    db_connection: psycopg.Connection,
) -> None:
    """A leaf on locator page_index 24 is returned as PDF viewer page 25."""

    owner_id = uuid4()
    member_id = uuid4()
    chunk_id = uuid4()
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        document_id, version_id = _seed_document(cursor, owner_id=owner_id)
        _insert_chunk(
            cursor,
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=SPAN,
            page_number=12,
            provenance=_pdf_locators(page_index=24, page_label="12"),
        )
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    inserted = _persist(
        db_connection,
        caller=member,
        run_id=admitted.context.run_id,
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
    )
    assert inserted
    db_connection.execute("SET ROLE app_api")
    try:
        records = list_run_citations(
            db_connection, caller=member, run_id=admitted.context.run_id
        )
    finally:
        db_connection.execute("RESET ROLE")
    assert len(records) == 1
    assert records[0].chunk_id == chunk_id
    assert records[0].pdf_page_number == 25
    assert records[0].document_title == TITLE
    assert records[0].evidence_excerpt == SPAN
    assert records[0].paragraph_index == 0
    assert records[0].provenance.get("page_label") == "12"
    assert records[0].provenance.get("page_number") == 12
    assert SPAN not in str(records[0].provenance)


def test_parent_resolves_to_one_child_on_page_25(
    db_connection: psycopg.Connection,
) -> None:
    """Citing a parent stores the matching leaf child and its PDF page."""

    owner_id = uuid4()
    member_id = uuid4()
    parent_id = uuid4()
    child_id = uuid4()
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        document_id, version_id = _seed_document(cursor, owner_id=owner_id)
        _insert_chunk(
            cursor,
            chunk_id=parent_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=SPAN,
            page_number=12,
            provenance=_pdf_locators(page_index=0, page_label="i"),
        )
        _insert_chunk(
            cursor,
            chunk_id=child_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=SPAN,
            page_number=12,
            provenance=_pdf_locators(page_index=24, page_label="12"),
            parent_chunk_id=parent_id,
            chunk_index=1,
        )
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    _persist(
        db_connection,
        caller=member,
        run_id=admitted.context.run_id,
        chunk_id=parent_id,
        document_id=document_id,
        version_id=version_id,
    )
    db_connection.execute("SET ROLE app_api")
    try:
        records = list_run_citations(
            db_connection, caller=member, run_id=admitted.context.run_id
        )
    finally:
        db_connection.execute("RESET ROLE")
    assert records[0].chunk_id == child_id
    assert records[0].pdf_page_number == 25


def test_two_matching_children_are_rejected(
    db_connection: psycopg.Connection,
) -> None:
    """The same span in two children fails closed as ``leaf_ambiguous``."""

    owner_id = uuid4()
    member_id = uuid4()
    parent_id = uuid4()
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        document_id, version_id = _seed_document(cursor, owner_id=owner_id)
        _insert_chunk(
            cursor,
            chunk_id=parent_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=SPAN,
            page_number=1,
            provenance=_pdf_locators(page_index=0, page_label="1"),
        )
        for index in (1, 2):
            _insert_chunk(
                cursor,
                chunk_id=uuid4(),
                document_id=document_id,
                version_id=version_id,
                raw_text=SPAN,
                page_number=12,
                provenance=_pdf_locators(page_index=24, page_label="12"),
                parent_chunk_id=parent_id,
                chunk_index=index,
            )
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    with pytest.raises(QueryAdmissionError, match="leaf_ambiguous"):
        _persist(
            db_connection,
            caller=member,
            run_id=admitted.context.run_id,
            chunk_id=parent_id,
            document_id=document_id,
            version_id=version_id,
        )


@pytest.mark.parametrize("span", [None, "", "   ", "not in the leaf"])
def test_non_representative_cited_chunk_resolves_to_itself(
    db_connection: psycopg.Connection,
) -> None:
    """A span that sits only in a non-representative cited chunk persists."""

    owner_id = uuid4()
    member_id = uuid4()
    chunk_id = uuid4()
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        document_id, version_id = _seed_document(cursor, owner_id=owner_id)
        _insert_chunk(
            cursor,
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=SPAN,
            page_number=25,
            provenance=_pdf_locators(page_index=24, page_label="12"),
        )
        cursor.execute(
            """
            UPDATE app.document_chunks
            SET is_search_representative = false
            WHERE id = %s
            """,
            (chunk_id,),
        )
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    _persist(
        db_connection,
        caller=member,
        run_id=admitted.context.run_id,
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
    )
    db_connection.execute("SET ROLE app_api")
    try:
        records = list_run_citations(
            db_connection, caller=member, run_id=admitted.context.run_id
        )
    finally:
        db_connection.execute("RESET ROLE")
    assert records[0].chunk_id == chunk_id


def test_null_empty_or_non_contained_span_is_rejected(
    db_connection: psycopg.Connection,
    span: str | None,
) -> None:
    """Null, empty, and non-contained spans cannot persist."""

    owner_id = uuid4()
    member_id = uuid4()
    chunk_id = uuid4()
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        document_id, version_id = _seed_document(cursor, owner_id=owner_id)
        _insert_chunk(
            cursor,
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=SPAN,
            page_number=25,
            provenance=_pdf_locators(page_index=24, page_label="12"),
        )
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    expected = (
        "citation_span_required" if not (span or "").strip() else "span_not_contained"
    )
    with pytest.raises(QueryAdmissionError, match=expected):
        _persist(
            db_connection,
            caller=member,
            run_id=admitted.context.run_id,
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            span=span or "",
        )


def test_multi_page_locators_are_rejected(db_connection: psycopg.Connection) -> None:
    """A leaf with two distinct PDF page_index values fails persist."""

    owner_id = uuid4()
    member_id = uuid4()
    chunk_id = uuid4()
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        document_id, version_id = _seed_document(cursor, owner_id=owner_id)
        _insert_chunk(
            cursor,
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=SPAN,
            page_number=25,
            provenance=_pdf_locators(
                page_index=24,
                page_label="12",
                extra={"format": "pdf", "page_index": 25, "page_label": "13"},
            ),
        )
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    with pytest.raises(QueryAdmissionError, match="page_ambiguous"):
        _persist(
            db_connection,
            caller=member,
            run_id=admitted.context.run_id,
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
        )


def test_idempotent_replay_and_conflict_and_thirteenth_citation(
    db_connection: psycopg.Connection,
) -> None:
    """Exact replay returns one row; conflict and citation 13 fail."""

    owner_id = uuid4()
    member_id = uuid4()
    chunk_id = uuid4()
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        document_id, version_id = _seed_document(cursor, owner_id=owner_id)
        _insert_chunk(
            cursor,
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=SPAN,
            page_number=12,
            provenance=_pdf_locators(page_index=24, page_label="12"),
        )
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    first = _persist(
        db_connection,
        caller=member,
        run_id=admitted.context.run_id,
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
    )
    second = _persist(
        db_connection,
        caller=member,
        run_id=admitted.context.run_id,
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
    )
    assert first == second
    extras = tuple(
        AnswerCitation(
            chunk_id=str(chunk_id),
            span=SPAN,
            paragraph_index=0,
        )
        for _ in range(12)
    )
    db_connection.execute("SAVEPOINT cite_bounds")
    try:
        with pytest.raises(QueryAdmissionError, match="answer_bounds_exceeded"):
            _persist(
                db_connection,
                caller=member,
                run_id=admitted.context.run_id,
                chunk_id=chunk_id,
                document_id=document_id,
                version_id=version_id,
                extra_citations=extras,
            )
    finally:
        db_connection.execute("ROLLBACK TO SAVEPOINT cite_bounds")
        db_connection.execute("RELEASE SAVEPOINT cite_bounds")
    db_connection.execute("SET ROLE app_api")
    db_connection.execute("SAVEPOINT cite_conflict")
    try:
        with db_connection.cursor() as cursor:
            with pytest.raises(psycopg.Error, match="replay_conflict"):
                cursor.execute(
                    """
                    SELECT citation_id
                    FROM app.insert_run_citation_v2(
                      %s, %s, %s, %s, %s, %s::uuid, %s, %s, %s::jsonb
                    )
                    """,
                    (
                        member.user_id,
                        member.rpc_role(),
                        member.rpc_authorization_version(),
                        str(admitted.context.run_id),
                        0,
                        str(chunk_id),
                        "binding",
                        0,
                        "{}",
                    ),
                )
    finally:
        db_connection.execute("ROLLBACK TO SAVEPOINT cite_conflict")
        db_connection.execute("RELEASE SAVEPOINT cite_conflict")
        db_connection.execute("RESET ROLE")


def test_foreign_run_is_not_found(db_connection: psycopg.Connection) -> None:
    """Foreign runs are indistinguishable not-found on citation list."""

    owner_id = uuid4()
    member_id = uuid4()
    stranger_id = uuid4()
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        insert_user_profile(cursor, user_id=stranger_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    stranger = caller_context(stranger_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    db_connection.execute("SET ROLE app_api")
    try:
        with pytest.raises(QueryAdmissionError, match="not_found"):
            list_run_citations(
                db_connection, caller=stranger, run_id=admitted.context.run_id
            )
    finally:
        db_connection.execute("RESET ROLE")


def test_current_version_flip_strips_title_page_and_excerpt(
    db_connection: psycopg.Connection,
) -> None:
    """Stale current-version citations hide title, page, and excerpt."""

    owner_id = uuid4()
    member_id = uuid4()
    chunk_id = uuid4()
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        document_id, version_id = _seed_document(cursor, owner_id=owner_id)
        _insert_chunk(
            cursor,
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=SPAN,
            page_number=12,
            provenance=_pdf_locators(page_index=24, page_label="12"),
        )
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    _persist(
        db_connection,
        caller=member,
        run_id=admitted.context.run_id,
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
    )
    with db_connection.cursor() as cursor:
        next_version = uuid4()
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, created_by
            )
            VALUES (%s, %s, 2, %s)
            """,
            (next_version, document_id, owner_id),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s
            WHERE id = %s
            """,
            (next_version, document_id),
        )
    db_connection.execute("SET ROLE app_api")
    try:
        records = list_run_citations(
            db_connection, caller=member, run_id=admitted.context.run_id
        )
    finally:
        db_connection.execute("RESET ROLE")
    assert records[0].source_unavailable is True
    assert records[0].chunk_id is None
    assert records[0].document_title is None
    assert records[0].pdf_page_number is None
    assert records[0].evidence_excerpt is None
    assert TITLE not in str(records[0].provenance)


def test_hostile_excerpt_is_escaped(db_connection: psycopg.Connection) -> None:
    """HTTP sanitizer escapes a hostile excerpt and never returns raw HTML."""

    owner_id = uuid4()
    member_id = uuid4()
    chunk_id = uuid4()
    hostile = "<script>alert(1)</script>"
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        document_id, version_id = _seed_document(
            cursor, owner_id=owner_id, title="<b>Secret</b>"
        )
        _insert_chunk(
            cursor,
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=hostile,
            page_number=25,
            provenance=_pdf_locators(page_index=24, page_label="12"),
        )
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    _persist(
        db_connection,
        caller=member,
        run_id=admitted.context.run_id,
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
        span=hostile,
    )
    db_connection.execute("SET ROLE app_api")
    try:
        records = list_run_citations(
            db_connection, caller=member, run_id=admitted.context.run_id
        )
    finally:
        db_connection.execute("RESET ROLE")
    escaped = escape_run_citation(records[0])
    assert escaped.evidence_excerpt == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert escaped.document_title == "&lt;b&gt;Secret&lt;/b&gt;"
    assert "<script>" not in (escaped.evidence_excerpt or "")
    assert "<b>" not in (escaped.document_title or "")


def test_transcript_history_batches_assistant_citations(
    db_connection: psycopg.Connection,
) -> None:
    """One transcript page returns assistant-run citations without N+1 reads."""

    owner_id = uuid4()
    member_id = uuid4()
    stranger_id = uuid4()
    chunk_id = uuid4()
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        insert_user_profile(cursor, user_id=stranger_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        document_id, version_id = _seed_document(cursor, owner_id=owner_id)
        _insert_chunk(
            cursor,
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=SPAN,
            page_number=12,
            provenance=_pdf_locators(page_index=24, page_label="12"),
        )
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    stranger = caller_context(stranger_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    _persist(
        db_connection,
        caller=member,
        run_id=admitted.context.run_id,
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
    )
    db_connection.execute("SET ROLE app_api")
    try:
        append_query_message(
            db_connection,
            caller=member,
            conversation_id=conversation_id,
            run_id=admitted.context.run_id,
            role="user",
            content="What is the policy?",
        )
        append_query_message(
            db_connection,
            caller=member,
            conversation_id=conversation_id,
            run_id=admitted.context.run_id,
            role="assistant",
            content=SPAN,
        )
        messages = list_conversation_messages(
            db_connection,
            caller=member,
            conversation_id=conversation_id,
        )
        pairs = list_conversation_citations(
            db_connection,
            caller=member,
            conversation_id=conversation_id,
            run_ids=(admitted.context.run_id, uuid4()),
        )
        with pytest.raises(QueryAdmissionError, match="not_found"):
            list_conversation_messages(
                db_connection,
                caller=stranger,
                conversation_id=conversation_id,
            )
    finally:
        db_connection.execute("RESET ROLE")
    assistant = next(item for item in messages if item.role == "assistant")
    user = next(item for item in messages if item.role == "user")
    assert assistant.run_id == admitted.context.run_id
    assert assistant.citations[0].pdf_page_number == 25
    assert assistant.citations[0].evidence_excerpt == SPAN
    assert user.citations == ()
    assert len(pairs) == 1
    assert pairs[0][0] == admitted.context.run_id


def test_legacy_null_paragraph_gains_no_invented_excerpt(
    db_connection: psycopg.Connection,
) -> None:
    """Legacy rows without paragraph/span stay honest and invent no excerpt."""

    owner_id = uuid4()
    member_id = uuid4()
    chunk_id = uuid4()
    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        document_id, version_id = _seed_document(cursor, owner_id=owner_id)
        _insert_chunk(
            cursor,
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            raw_text=SPAN,
            page_number=12,
            provenance=_pdf_locators(page_index=24, page_label="12"),
        )
        authz = authorization_version(cursor)
    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(db_connection, caller=member, conversation_id=conversation_id)
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.citations (
              run_id, citation_index, chunk_id, snippet, provenance
            )
            VALUES (%s, 0, %s, '', '{}'::jsonb)
            """,
            (admitted.context.run_id, chunk_id),
        )
    db_connection.execute("SET ROLE app_api")
    try:
        records = list_run_citations(
            db_connection, caller=member, run_id=admitted.context.run_id
        )
    finally:
        db_connection.execute("RESET ROLE")
    assert records[0].paragraph_index is None
    assert records[0].evidence_excerpt is None
    assert records[0].pdf_page_number == 25
    assert records[0].source_unavailable is False
