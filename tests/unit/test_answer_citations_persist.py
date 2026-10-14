"""Verified citation persistence for Ask Sources."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_agents.query.state import QueryGraphState
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import list_run_citations
from smart_rag_core.query_answer.citations import (
    CitationPersistResult,
    SkippedCitation,
    drop_skipped_citations,
    leading_sentence,
    maybe_persist_verified_citations,
    persist_answer_citations,
    repair_leaf_citations,
    shorten_contained_skipped_spans,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
)
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
        == CitationPersistResult()
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
            "smart_rag_core.query_answer.citations_persist.list_run_citations",
            side_effect=[(), (MagicMock(),)],
        ) as list_existing,
        patch(
            "smart_rag_core.query_answer.citations_persist.persist_answer_citations",
            return_value=CitationPersistResult(ids=inserted),
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

    assert first.ids == inserted
    assert second == CitationPersistResult()
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
            "smart_rag_core.query_answer.citations_persist.list_run_citations",
            return_value=(),
        ),
        patch(
            "smart_rag_core.query_answer.citations_persist.persist_answer_citations",
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


def _verify_persisted(
    monkeypatch: pytest.MonkeyPatch,
    spans: tuple[str, ...],
    *,
    skipped_span: str | None,
) -> QueryGraphState:
    """Run verify with a recorded citation-persist result.

    Args:
        monkeypatch: Pytest patcher.
        spans: Passage spans on the checked answer.
        skipped_span: Span the persist result reports as leaf-unresolved.

    Returns:
        Verify node state.
    """

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.nodes.verify import verify_answer_node
    from smart_rag_agents.query.state import pending_query_state
    from smart_rag_core.query_answer.models import AnswerParagraph, AtomicLink
    from smart_rag_core.security.identity import UserRole

    fusion = verifier_fusion(verifier_passage(1, text="Refund period is 30 days."))
    chunk_id = str(fusion.evidence[0].chunk_id)
    runtime = MagicMock()
    runtime.user_id = uuid4()
    runtime.role = UserRole.MEMBER
    runtime.authorization_version = 1
    runtime.session_id = None
    runtime.run_id = uuid4()

    def _runtime_from_state(_state: object) -> MagicMock:
        """Return the mocked runtime regardless of graph state."""

        return runtime

    def _keep_answer(answer: AnswerPayload, **_kwargs: object) -> AnswerPayload:
        """Skip paragraph rebuild so the test citations reach the drop step.

        Args:
            answer: Checked answer.
            _kwargs: Fusion and table arguments ignored by this stub.

        Returns:
            The same payload.
        """

        return answer

    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.runtime_from_state",
        _runtime_from_state,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.render_verified_company_answer",
        _keep_answer,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.summarize_run_usage",
        MagicMock(side_effect=QueryAdmissionError("database_rejected")),
    )
    skipped = ()
    if skipped_span is not None:
        skipped = (
            SkippedCitation(
                chunk_id=chunk_id,
                paragraph_index=0,
                span=skipped_span,
                reason="leaf_ambiguous",
            ),
        )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.maybe_persist_verified_citations",
        MagicMock(
            return_value=CitationPersistResult(
                ids=() if skipped_span is not None and len(spans) == 1 else (uuid4(),),
                skipped=skipped,
            )
        ),
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
        citations=tuple(
            AnswerCitation(chunk_id=chunk_id, span=span, paragraph_index=0)
            for span in spans
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
    verified = verify_answer_node(state, QueryGraphDeps(connection=MagicMock()))
    return verified


def test_verify_partial_when_some_citations_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One skipped leaf leaves a partial answer backed by the rest."""

    verified = _verify_persisted(
        monkeypatch,
        ("Refund period", "30 days"),
        skipped_span="30 days",
    )
    assert verified["status"] == "verified_partial"
    assert verified["detail"] == "citation_leaf_unresolved"
    verification = verified["verification"]
    assert isinstance(verification, dict)
    assert verification["skipped_citation_count"] == 1
    answer = verified["answer"]
    released = AnswerPayload.model_validate(answer)
    assert [item.span for item in released.citations] == ["Refund period"]


def test_verify_insufficient_when_every_citation_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero persisted citations stay insufficient evidence."""

    verified = _verify_persisted(
        monkeypatch,
        ("30 days",),
        skipped_span="30 days",
    )
    assert verified["status"] == "insufficient_evidence"
    assert verified["detail"] == "citation_leaf_unresolved"


def test_repair_leaf_citations_uses_claim_local_unique_span() -> None:
    """A short ambiguous span retargets onto the unique claim-holding passage."""

    from smart_rag_core.query_answer.models import AnswerParagraph, AtomicLink
    from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

    parent = verifier_passage(
        1,
        text=(
            "> 0.25 signals major drift.\n\n"
            "prioritize retraining if PSI > 0.25 persists over 48 hours."
        ),
        rank=1,
    )
    leaf = verifier_passage(
        2,
        text="prioritize retraining if PSI > 0.25 persists over 48 hours.",
        rank=2,
    )
    fusion = verifier_fusion(parent, leaf)
    parent_id = str(fusion.evidence[0].chunk_id)
    leaf_id = str(fusion.evidence[1].chunk_id)
    claim = "prioritize retraining if PSI > 0.25 persists over 48 hours."
    answer = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=parent_id,
                span="> 0.25",
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim=claim,
                chunk_ids=(parent_id,),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    skipped = (
        SkippedCitation(
            chunk_id=parent_id,
            paragraph_index=0,
            span="> 0.25",
            reason="leaf_ambiguous",
        ),
    )
    repaired = repair_leaf_citations(answer, fusion, skipped)
    assert repaired.citations[0].chunk_id == leaf_id
    repaired_span = repaired.citations[0].span
    assert repaired_span is not None
    assert "PSI > 0.25" in repaired_span
    assert "48 hours" in repaired_span


def test_verify_partial_after_leaf_citation_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero-persist leaf skips recover when claim-local repair then persists."""

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.nodes.verify import verify_answer_node
    from smart_rag_agents.query.state import pending_query_state
    from smart_rag_core.query_answer.models import AnswerParagraph, AtomicLink
    from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
    from smart_rag_core.security.identity import UserRole

    parent = verifier_passage(
        1,
        text=(
            "SHA-256 and SHA-1 appear in several layers.\n\n"
            "Computing a SHA-256 hash of incoming data upon receipt is "
            "recommended for maintaining data integrity in MAESTRO layer 2, "
            "Data operations."
        ),
        rank=1,
    )
    leaf = verifier_passage(
        2,
        text=(
            "Computing a SHA-256 hash of incoming data upon receipt is "
            "recommended for maintaining data integrity in MAESTRO layer 2, "
            "Data operations."
        ),
        rank=2,
    )
    fusion = verifier_fusion(parent, leaf)
    parent_id = str(fusion.evidence[0].chunk_id)
    leaf_id = str(fusion.evidence[1].chunk_id)
    assert leaf_id != parent_id
    claim = (
        "Computing a SHA-256 hash of incoming data upon receipt is "
        "recommended for maintaining data integrity in MAESTRO layer 2, "
        "Data operations."
    )
    runtime = MagicMock()
    runtime.user_id = uuid4()
    runtime.role = UserRole.MEMBER
    runtime.authorization_version = 1
    runtime.session_id = None
    runtime.run_id = uuid4()
    calls: list[AnswerPayload] = []

    def _persist(
        _connection: object,
        *,
        caller: object,
        run_id: object,
        fusion: object,
        answer: AnswerPayload,
    ) -> CitationPersistResult:
        """Skip every citation on the first call; accept a repaired claim span.

        Args:
            _connection: Unused mock connection.
            caller: Unused caller.
            run_id: Unused run id.
            fusion: Unused fusion.
            answer: Answer being persisted.

        Returns:
            Persist result for this attempt.
        """

        del caller, run_id, fusion
        calls.append(answer)
        if len(calls) == 1:
            skipped = tuple(
                SkippedCitation(
                    chunk_id=str(item.chunk_id or ""),
                    paragraph_index=item.paragraph_index,
                    span=(item.span or "").strip(),
                    reason="leaf_ambiguous",
                )
                for item in answer.citations
            )
            return CitationPersistResult(ids=(), skipped=skipped)
        assert answer.citations
        assert any(
            "SHA-256" in (item.span or "") and len(item.span or "") >= 12
            for item in answer.citations
        )
        return CitationPersistResult(ids=(uuid4(),), skipped=())

    def _runtime(_state: object) -> MagicMock:
        """Return the fake runtime for any graph state.

        Args:
            _state: Unused graph state.

        Returns:
            The test runtime.
        """

        return runtime

    def _render(answer: object, **_kwargs: object) -> object:
        """Return the answer unchanged.

        Args:
            answer: Verified answer payload.
            **_kwargs: Unused render options.

        Returns:
            The same answer object.
        """

        return answer

    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.runtime_from_state",
        _runtime,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.render_verified_company_answer",
        _render,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.summarize_run_usage",
        MagicMock(side_effect=QueryAdmissionError("database_rejected")),
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.verify.maybe_persist_verified_citations",
        _persist,
    )
    state = pending_query_state(
        user_query="What hashing example does MAESTRO recommend?"
    )
    state["status"] = "answered"
    state["remaining_model_calls"] = 8
    state["fusion"] = fusion.model_dump(mode="json")
    state["answer"] = AnswerPayload(
        answer_text=claim,
        paragraphs=(AnswerParagraph(paragraph_index=0, text=claim, link_ids=("l1",)),),
        citations=(
            AnswerCitation(
                chunk_id=parent_id,
                span="SHA-256",
                paragraph_index=0,
                atomic_link_id="l1",
            ),
        ),
        atomic_links=(AtomicLink(link_id="l1", claim=claim, chunk_ids=(parent_id,)),),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    ).model_dump(mode="json")
    verified = verify_answer_node(state, QueryGraphDeps(connection=MagicMock()))
    assert verified["status"] == "verified_partial"
    assert verified["detail"] == "citation_leaf_unresolved"
    assert len(calls) == 2


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
    assert persisted == CitationPersistResult()


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
    assert inserted.ids
    records = list_run_citations(
        db_connection,
        caller=member,
        run_id=admitted.context.run_id,
    )
    assert len(records) == len(inserted.ids)
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


class _FakeCursor:
    """Cursor that fails chosen ``insert_run_citation_v2`` attempts."""

    def __init__(self, failures: dict[int, str]) -> None:
        """Record which 1-based insert attempts should raise.

        Args:
            failures: Attempt number to ``query_citation`` reason.
        """

        self.statements: list[str] = []
        self.params: list[object] = []
        self._failures = failures
        self._attempts = 0
        self._pending: tuple[object, ...] | None = None

    def __enter__(self) -> _FakeCursor:
        """Enter the cursor context.

        Returns:
            This cursor.
        """

        return self

    def __exit__(self, *exc: object) -> bool:
        """Leave the cursor context without swallowing errors.

        Args:
            exc: Exception triple from the context manager protocol.

        Returns:
            False so errors propagate.
        """

        return False

    def execute(self, sql: str, params: object = None) -> None:
        """Record the statement and fail configured insert attempts.

        Args:
            sql: SQL text.
            params: Bound parameters, if any.

        Raises:
            psycopg.errors.RaiseException: Configured leaf or ACL reason.
        """

        text = " ".join(sql.split())
        self.statements.append(text)
        self.params.append(params)
        if "insert_run_citation_v2" in text:
            self._attempts += 1
            reason = self._failures.get(self._attempts)
            if reason:
                raise psycopg.errors.RaiseException(f"query_citation:{reason}")
            self._pending = (uuid4(),)

    def fetchone(self) -> tuple[object, ...] | None:
        """Return the row queued by the last successful insert.

        Returns:
            One-column row, or None.
        """

        row, self._pending = self._pending, None
        return row


def _connection_with(cursor: _FakeCursor) -> MagicMock:
    """Return a connection whose ``cursor()`` yields ``cursor``.

    Args:
        cursor: Fake cursor.

    Returns:
        Connection mock.
    """

    connection = MagicMock()
    connection.cursor.return_value = cursor
    return connection


_TWO_SENTENCES = "Refund period is 30 days from purchase. Shipping is refunded too."


def test_persist_retries_with_leading_sentence_then_succeeds() -> None:
    """A straddling span is retried once with its first sentence."""

    fusion = verifier_fusion(verifier_passage(1, text=_TWO_SENTENCES))
    chunk_id = fusion.evidence[0].chunk_id
    answer = AnswerPayload(
        answer_text="Refunds take 30 days.",
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span=_TWO_SENTENCES,
                paragraph_index=0,
            ),
        ),
        status="complete",
    )
    cursor = _FakeCursor(failures={1: "span_not_contained"})
    result = persist_answer_citations(
        _connection_with(cursor),
        caller=MagicMock(user_id=uuid4()),
        run_id=uuid4(),
        fusion=fusion,
        answer=answer,
    )
    assert len(result.ids) == 1
    assert result.skipped == ()
    inserts = [
        params
        for statement, params in zip(cursor.statements, cursor.params, strict=True)
        if "insert_run_citation_v2" in statement
    ]
    assert len(inserts) == 2
    second = inserts[1]
    assert isinstance(second, tuple)
    assert second[6] == leading_sentence(_TWO_SENTENCES)
    assert "SAVEPOINT citation_leaf" in cursor.statements
    assert "ROLLBACK TO SAVEPOINT citation_leaf" in cursor.statements


def test_persist_skips_leaf_unresolved_and_keeps_other_citations() -> None:
    """Two leaf failures skip one citation; the next citation still persists."""

    fusion = verifier_fusion(verifier_passage(1, text=_TWO_SENTENCES))
    chunk_id = fusion.evidence[0].chunk_id
    answer = AnswerPayload(
        answer_text="Refunds take 30 days.",
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span=_TWO_SENTENCES,
                paragraph_index=0,
            ),
            AnswerCitation(
                chunk_id=chunk_id,
                span="Shipping is refunded too.",
                paragraph_index=0,
            ),
        ),
        status="complete",
    )
    cursor = _FakeCursor(failures={1: "leaf_ambiguous", 2: "span_not_contained"})
    result = persist_answer_citations(
        _connection_with(cursor),
        caller=MagicMock(user_id=uuid4()),
        run_id=uuid4(),
        fusion=fusion,
        answer=answer,
    )
    assert len(result.ids) == 1
    assert len(result.skipped) == 1
    assert result.skipped[0].reason == "span_not_contained"
    assert result.skipped[0].chunk_id == str(chunk_id)
    assert cursor.statements.count("ROLLBACK TO SAVEPOINT citation_leaf") == 2


def test_persist_non_leaf_reason_still_fails_closed() -> None:
    """ACL and replay reasons raise as before."""

    fusion = verifier_fusion(verifier_passage(1, text=_TWO_SENTENCES))
    answer = AnswerPayload(
        answer_text="Refunds take 30 days.",
        citations=(
            AnswerCitation(
                chunk_id=fusion.evidence[0].chunk_id,
                span=_TWO_SENTENCES,
                paragraph_index=0,
            ),
        ),
        status="complete",
    )
    cursor = _FakeCursor(failures={1: "authorization_rejected"})
    with pytest.raises(QueryAdmissionError, match="authorization_rejected"):
        persist_answer_citations(
            _connection_with(cursor),
            caller=MagicMock(user_id=uuid4()),
            run_id=uuid4(),
            fusion=fusion,
            answer=answer,
        )


def test_leading_sentence_rules() -> None:
    """Retry spans are strictly shorter, long enough, and end at a sentence."""

    assert leading_sentence(_TWO_SENTENCES) == (
        "Refund period is 30 days from purchase."
    )
    assert leading_sentence("Short one. Two.") == ""
    assert leading_sentence("No terminal punctuation at all here") == ""
    assert leading_sentence("Only one sentence but a long one indeed.") == ""


def test_contained_opening_keeps_paragraph_and_shortens_span() -> None:
    """A leaf skip of a fused opening keeps the paragraph and shortens the span."""

    fusion = verifier_fusion(verifier_passage(1, text=_TWO_SENTENCES))
    chunk_id = fusion.evidence[0].chunk_id
    answer = AnswerPayload(
        answer_text=_TWO_SENTENCES,
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text=_TWO_SENTENCES,
                link_ids=("opening-1",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span=_TWO_SENTENCES,
                paragraph_index=0,
                atomic_link_id="opening-1",
            ),
        ),
        status="complete",
    )
    shortened = shorten_contained_skipped_spans(
        answer,
        fusion,
        (
            SkippedCitation(
                chunk_id=str(chunk_id),
                paragraph_index=0,
                span=_TWO_SENTENCES,
                reason="span_not_contained",
            ),
        ),
    )
    assert shortened.paragraphs[0].text == _TWO_SENTENCES
    assert shortened.answer_text == _TWO_SENTENCES
    assert shortened.citations[0].span == leading_sentence(_TWO_SENTENCES)
    dropped = drop_skipped_citations(
        shortened,
        (
            SkippedCitation(
                chunk_id=str(chunk_id),
                paragraph_index=0,
                span=shortened.citations[0].span,
                reason="span_not_contained",
            ),
        ),
    )
    assert dropped.paragraphs[0].text == _TWO_SENTENCES
    assert dropped.answer_text == _TWO_SENTENCES


def test_drop_skipped_citations_removes_only_matching_span() -> None:
    """Dropping is keyed on chunk, paragraph, and span."""

    chunk = uuid4()
    answer = AnswerPayload(
        answer_text="x",
        citations=(
            AnswerCitation(chunk_id=str(chunk), span="A sentence.", paragraph_index=0),
            AnswerCitation(chunk_id=str(chunk), span="Another one.", paragraph_index=0),
        ),
        status="complete",
    )
    dropped = drop_skipped_citations(
        answer,
        (
            SkippedCitation(
                chunk_id=str(chunk),
                paragraph_index=0,
                span="A sentence.",
                reason="leaf_ambiguous",
            ),
        ),
    )
    assert [citation.span for citation in dropped.citations] == ["Another one."]
