"""Unit tests for additive term needles and fail-closed term outage."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from smart_rag_core.retrieval.hybrid_run.channels import (
    collect_term_lists,
    unpack_term,
)
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.retrieval.term_needles import (
    expand_term_texts,
    extract_term_needles,
)
from smart_rag_core.retrieval.terms import TermRetriever
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


def _caller() -> CallerContext:
    """Return a member caller.

    Returns:
        Frozen identity.
    """

    return CallerContext(
        user_id=str(uuid4()),
        role=UserRole.MEMBER,
        authorization_version=1,
    )


def _candidate() -> RetrievalCandidate:
    """Return one fused candidate.

    Returns:
        Frozen candidate.
    """

    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )


def test_extract_term_needles_keeps_codes_and_arabic_tokens() -> None:
    """The term channel receives extracted tokens, not only the sentence."""

    query = "ما هو INV-1001 في سياسة OpenAPI؟"
    needles = extract_term_needles(query)
    assert "inv-1001" in needles
    assert normalize_arabic_v1("سياسة") in needles
    assert "openapi" in needles
    assert query not in needles


def test_extract_term_needles_ignores_aliases_absent_from_query() -> None:
    """Unauthorized glossary strings cannot be injected as extra needles."""

    needles = extract_term_needles(
        "What is INV-1001?",
        extra=("SecretHandbookAlias",),
    )
    assert "SecretHandbookAlias" not in needles
    assert "secrethandbookalias" not in needles
    assert "inv-1001" in needles


def test_sql_metacharacters_remain_data() -> None:
    """Extracted needles keep quote and comment characters as literal text."""

    payload = "'; DROP TABLE app.document_search_terms; --"
    needles = extract_term_needles(f'Find "{payload}" for INV-1001')
    joined = " ".join(needles)
    assert "drop table" in joined
    assert "document_search_terms" in joined.replace("-", " ") or (
        "document_search_terms" in joined
    )
    assert all("\x00" not in item for item in needles)
    assert all(";" not in item for item in needles)


def test_expand_term_texts_appends_needles() -> None:
    """Ranking variants keep the sentence and add bounded needles."""

    expanded = expand_term_texts(("What is INV-1001?", "INV status"))
    assert expanded[0] == "What is INV-1001?"
    assert "inv-1001" in expanded


def test_collect_term_lists_queries_extracted_tokens() -> None:
    """collect_term_lists retrieves needles in addition to the sentence."""

    seen: list[str] = []
    hit = _candidate()

    def _retrieve(*, caller: object, query_text: str) -> tuple[RetrievalCandidate, ...]:
        """Record one term retrieve.

        Args:
            caller: Unused identity.
            query_text: Ranking or needle text.

        Returns:
            One candidate for the code needle, else empty.
        """

        del caller
        seen.append(query_text)
        if query_text == "inv-1001":
            return (hit,)
        return ()

    lists = collect_term_lists(_retrieve, caller=_caller(), texts=("What is INV-1001?",))
    assert "What is INV-1001?" in seen
    assert "inv-1001" in seen
    assert any(hit.chunk_id == item.chunk_id for variant in lists for item in variant)


def test_term_retriever_binds_extra_terms_and_rechecks(monkeypatch) -> None:
    """Live retrieve passes extra needles as a bound array, then rechecks."""

    captured: dict[str, object] = {}
    allowed = _candidate()
    denied = _candidate()

    class _Cursor:
        """Capture the RPC execute payload."""

        def __enter__(self) -> _Cursor:
            """Return the cursor.

            Returns:
                Self.
            """

            return self

        def __exit__(self, *_args: object) -> bool:
            """Do not suppress errors.

            Returns:
                False.
            """

            return False

        def execute(self, query: object, params: object = None) -> None:
            """Store the bound parameters.

            Args:
                query: SQL text.
                params: Bound RPC arguments.
            """

            captured["query"] = str(query)
            captured["params"] = params

        def fetchall(self) -> list[tuple[object, ...]]:
            """Return one authorized and one stale row.

            Returns:
                Fake RPC rows.
            """

            return [
                (allowed.chunk_id, allowed.document_id, allowed.version_id, "exact", 1.0),
                (denied.chunk_id, denied.document_id, denied.version_id, "exact", 1.0),
            ]

    class _Connection:
        """Minimal cursor factory."""

        def cursor(self) -> _Cursor:
            """Open one fake cursor.

            Returns:
                Capture cursor.
            """

            return _Cursor()

    @contextmanager
    def _txn(*_args: object, **_kwargs: object):
        """Skip SET LOCAL for the unit test.

        Yields:
            None.
        """

        yield

    monkeypatch.setattr(
        "smart_rag_core.retrieval.terms.retrieval_transaction",
        _txn,
    )
    monkeypatch.setattr(
        "smart_rag_core.retrieval.terms.recheck_retrieval_candidates",
        lambda *_args, **_kwargs: (allowed,),
    )
    result = TermRetriever(_Connection()).retrieve(  # type: ignore[arg-type]
        caller=_caller(),
        query_text="What is INV-1001?",
    )
    params = captured["params"]
    assert isinstance(params, tuple)
    assert "inv-1001" in params[-1]
    assert "%s::text[]" in str(captured["query"])
    assert [item.chunk_id for item in result.candidates] == [allowed.chunk_id]
    assert denied.chunk_id not in {item.chunk_id for item in result.candidates}


def test_term_outage_is_named(monkeypatch) -> None:
    """Database failures record term_unavailable without fake success."""

    class _Connection:
        """Raise on cursor use."""

        def cursor(self) -> object:
            """Open a cursor that fails.

            Raises:
                psycopg.Error: Simulated outage.
            """

            raise psycopg.OperationalError("term_outage")

    @contextmanager
    def _txn(*_args: object, **_kwargs: object):
        """Skip SET LOCAL.

        Yields:
            None.
        """

        yield

    monkeypatch.setattr(
        "smart_rag_core.retrieval.terms.retrieval_transaction",
        _txn,
    )
    result = TermRetriever(_Connection()).retrieve(  # type: ignore[arg-type]
        caller=_caller(),
        query_text="What is INV-1001?",
    )
    assert result.fallback_reason is RetrievalFallbackReason.TERM_UNAVAILABLE
    assert result.candidates == ()
    lists, reason = unpack_term(result)
    assert lists == ((),)
    assert reason is RetrievalFallbackReason.TERM_UNAVAILABLE
    assert unpack_term(SimpleNamespace())[1] is RetrievalFallbackReason.TERM_UNAVAILABLE
