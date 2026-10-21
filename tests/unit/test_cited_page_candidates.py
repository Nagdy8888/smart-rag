"""Cited-page term hits stay ahead of lexical term hits."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import psycopg
from psycopg.pq import TransactionStatus
from smart_rag_core.retrieval.pages import (
    PAGE_CANDIDATE_SQL,
    idle_page_connection,
    merge_cited_page_candidates,
    release_term_channel,
)
from smart_rag_core.retrieval.profiles import (
    TERM_CANDIDATE_CAP,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.types import RetrievalCandidate, TermRetrievalResult


def _candidate() -> RetrievalCandidate:
    """Build one authorized candidate with a fresh chunk id.

    Returns:
        Retrieval candidate scored like a cited-page hit.
    """

    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )


def test_cited_page_12_is_kept_when_lexical_term_is_empty() -> None:
    """A cited page chunk is the term list when lexical term returned nothing."""

    page_hit = _candidate()
    merged = merge_cited_page_candidates((), (page_hit,))
    assert [item.chunk_id for variant in merged for item in variant] == [
        page_hit.chunk_id
    ]


def test_term_failure_still_returns_the_cited_page_hit() -> None:
    """A failed term call keeps a synthetic cited-page chunk and the outage."""

    page_hit = _candidate()

    def _failing_term() -> None:
        """Raise the way a term RPC outage does.

        Raises:
            RuntimeError: Always.
        """

        raise RuntimeError("term_rpc_down")

    result = None
    try:
        _failing_term()
    except RuntimeError:
        result = release_term_channel((), (page_hit,), term_failed=True)
    assert isinstance(result, TermRetrievalResult)
    assert result.fallback_reason is RetrievalFallbackReason.TERM_UNAVAILABLE
    assert [item.chunk_id for item in result.candidates] == [page_hit.chunk_id]


def test_cited_page_hits_stay_inside_the_term_cap() -> None:
    """Page hits occupy the term cap before later lexical hits."""

    page_hits = tuple(_candidate() for _ in range(TERM_CANDIDATE_CAP))
    lexical = (_candidate(),)
    merged = merge_cited_page_candidates((lexical,), page_hits)
    kept = [item.chunk_id for variant in merged for item in variant]
    assert kept == [item.chunk_id for item in page_hits]
    assert lexical[0].chunk_id not in kept


def test_page_fetch_uses_a_new_connection_when_the_term_connection_is_busy() -> None:
    """A non-idle term connection does not host the page transaction."""

    busy = _Conn(TransactionStatus.INTRANS)
    opened = _Conn(TransactionStatus.IDLE)
    connection, close_when_done = idle_page_connection(
        cast(psycopg.Connection, busy),
        lambda: cast(psycopg.Connection, opened),
    )
    assert connection is opened
    assert close_when_done is True
    idle = _Conn(TransactionStatus.IDLE)
    same, close_idle = idle_page_connection(
        cast(psycopg.Connection, idle),
        lambda: cast(psycopg.Connection, opened),
    )
    assert same is idle
    assert close_idle is False


def test_cited_page_sql_keeps_acl_and_skips_the_representative_flag() -> None:
    """Explicit page cites authorize chunks search ranking would drop."""

    sql = PAGE_CANDIDATE_SQL.casefold()
    assert "is_search_representative" not in sql
    assert "caller_can_read_document" in sql
    assert "current_version_id" in sql


class _Conn:
    """Connection stand-in with only the transaction status the helper reads."""

    def __init__(self, status: TransactionStatus) -> None:
        """Store the status idle_page_connection inspects.

        Args:
            status: psycopg transaction status.
        """

        self.info = _Info(status)


class _Info:
    """Transaction-status holder matching ``connection.info``."""

    def __init__(self, status: TransactionStatus) -> None:
        """Store one transaction status.

        Args:
            status: psycopg transaction status.
        """

        self.transaction_status = status
