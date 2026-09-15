"""app_api repository for run-scoped Web evidence RPCs."""

from __future__ import annotations

from typing import Literal, NoReturn
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.web_research.models import (
    WebCitation,
    WebOperationState,
    WebSourceRecord,
)
from smart_rag_core.web_research.policy import (
    assert_span_contained,
    excerpt_sha256,
    normalize_web_url,
)

_REASON_PREFIXES = ("web_evidence:", "web_operation:", "query_admission:")
_OPERATION_STATUSES = frozenset(
    {"planned", "sent", "succeeded", "failed", "ambiguous"}
)


def _raise_web_error(exc: BaseException) -> NoReturn:
    """Map a Postgres error to ``QueryAdmissionError``.

    Args:
        exc: Driver or database error.

    Raises:
        QueryAdmissionError: Always.
    """

    message = str(exc)
    reason = "database_rejected"
    for prefix in _REASON_PREFIXES:
        if prefix in message:
            start = message.find(prefix) + len(prefix)
            tail = message[start:].split()[0].strip("\"'")
            reason = f"{prefix}{tail.split(chr(10))[0]}"
            break
    raise QueryAdmissionError(reason) from exc


def _require_row(row: dict[str, object] | None) -> dict[str, object]:
    """Return a fetched RPC row or fail closed.

    Args:
        row: Cursor row.

    Returns:
        The row mapping.

    Raises:
        QueryAdmissionError: If the RPC returned no row.
    """

    if row is None:
        raise QueryAdmissionError("web_evidence:not_found")
    return row


def _cell(row: dict[str, object], key: str) -> object:
    """Return one RPC column.

    Args:
        row: Fetched row.
        key: Column name.

    Returns:
        Column value.
    """

    return row[key]


def _operation_status(value: object) -> Literal[
    "planned", "sent", "succeeded", "failed", "ambiguous"
]:
    """Parse a durable operation status.

    Args:
        value: RPC status text.

    Returns:
        Allowed status literal.

    Raises:
        QueryAdmissionError: If the status is unknown.
    """

    text = str(value)
    if text not in _OPERATION_STATUSES:
        raise QueryAdmissionError("web_operation:conflict")
    if text == "planned":
        return "planned"
    if text == "sent":
        return "sent"
    if text == "succeeded":
        return "succeeded"
    if text == "failed":
        return "failed"
    return "ambiguous"


def begin_web_research_operation(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    operation_key: str,
    kind: str,
    request_hash: str,
) -> WebOperationState:
    """Begin or replay one idempotent Web operation.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Query run.
        operation_key: Stable key unique per run.
        kind: ``search``, ``contents``, or ``fetch``.
        request_hash: SHA-256 of the request body.

    Returns:
        Operation id and status.

    Raises:
        QueryAdmissionError: Ownership, conflict, or ambiguous sent state.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT operation_id, status, replayed
                FROM app.begin_web_research_operation(
                  %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                    operation_key,
                    kind,
                    request_hash,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_web_error(exc)
    fetched = _require_row(row)
    return WebOperationState(
        operation_id=str(_cell(fetched, "operation_id")),
        status=_operation_status(_cell(fetched, "status")),
        replayed=bool(_cell(fetched, "replayed")),
    )


def mark_web_research_operation_sent(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    operation_id: UUID,
) -> WebOperationState:
    """Mark a planned operation sent. Ambiguous sent rows fail closed.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        operation_id: Operation primary key.

    Returns:
        Updated status and attempt count.

    Raises:
        QueryAdmissionError: Ambiguous or missing operation.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT operation_id, status, attempts
                FROM app.mark_web_research_operation_sent(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    operation_id,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_web_error(exc)
    fetched = _require_row(row)
    attempts_raw = _cell(fetched, "attempts")
    return WebOperationState(
        operation_id=str(_cell(fetched, "operation_id")),
        status=_operation_status(_cell(fetched, "status")),
        attempts=int(str(attempts_raw)),
    )


def complete_web_research_operation(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    operation_id: UUID,
    ok: bool,
    provider_request_id: str | None = None,
    failure_reason: str | None = None,
) -> WebOperationState:
    """Complete a sent operation as succeeded or failed.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        operation_id: Operation primary key.
        ok: True for success.
        provider_request_id: Optional Exa request id.
        failure_reason: Safe machine-readable reason when ``ok`` is false.

    Returns:
        Terminal status.

    Raises:
        QueryAdmissionError: Missing or non-sent operation.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT operation_id, status
                FROM app.complete_web_research_operation(
                  %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    operation_id,
                    ok,
                    provider_request_id,
                    failure_reason,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_web_error(exc)
    fetched = _require_row(row)
    return WebOperationState(
        operation_id=str(_cell(fetched, "operation_id")),
        status=_operation_status(_cell(fetched, "status")),
    )


def insert_web_source(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    source_index: int,
    url: str,
    title: str,
    excerpt: str,
    published_date: str | None = None,
) -> WebSourceRecord:
    """Persist one bounded Web source after URL policy and hash check.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Query run.
        source_index: 0-5.
        url: Provider URL, normalized before insert.
        title: Optional title.
        excerpt: 1-8000 characters.
        published_date: Optional provider date string.

    Returns:
        Persisted source including content hash.

    Raises:
        QueryAdmissionError: Cap, URL, hash, or ownership failure.
        ValueError: If the URL fails crawl policy before the RPC.
    """

    normalized = normalize_web_url(url)
    digest = excerpt_sha256(excerpt)
    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT web_source_id
                FROM app.insert_web_source(
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                    source_index,
                    normalized,
                    title,
                    excerpt,
                    digest,
                    published_date,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_web_error(exc)
    fetched = _require_row(row)
    return WebSourceRecord(
        web_source_id=str(_cell(fetched, "web_source_id")),
        source_index=source_index,
        url=normalized,
        title=title[:512],
        excerpt=excerpt,
        content_hash=digest,
        published_date=published_date,
    )


def insert_web_citation(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    citation_index: int,
    source: WebSourceRecord,
    citation: WebCitation,
) -> UUID:
    """Persist one verified Web citation after span containment.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Query run.
        citation_index: 0-11.
        source: Persisted source for this run.
        citation: Span bound to ``source.web_source_id``.

    Returns:
        Inserted citation UUID.

    Raises:
        ValueError: If the span is not a substring of the excerpt.
        QueryAdmissionError: Cap, ownership, or cross-run source.
    """

    if citation.web_source_id != source.web_source_id:
        raise ValueError("web_evidence:not_found")
    assert_span_contained(excerpt=source.excerpt, citation=citation)
    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT web_citation_id
                FROM app.insert_web_citation(
                  %s, %s, %s, %s, %s, %s::uuid, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                    citation_index,
                    source.web_source_id,
                    citation.span,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_web_error(exc)
    fetched = _require_row(row)
    return UUID(str(_cell(fetched, "web_citation_id")))
