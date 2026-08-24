"""Durable conversation message append/load for admitted query runs."""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext

_REASON_PREFIX = "query_message:"


def _raise_message_error(exc: BaseException) -> None:
    """Map a Postgres error to ``QueryAdmissionError``.

    Args:
        exc: Driver or database error.

    Raises:
        QueryAdmissionError: Always.
    """

    message = str(exc)
    reason = "database_rejected"
    if _REASON_PREFIX in message:
        start = message.find(_REASON_PREFIX) + len(_REASON_PREFIX)
        tail = message[start:].split()[0].strip("\"'")
        reason = tail.split("\n")[0]
    raise QueryAdmissionError(reason) from exc


def append_query_message(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
    run_id: UUID,
    role: str,
    content: str,
) -> UUID:
    """Persist one conversation message bound to an owned query run.

    Idempotent per ``(run_id, role)`` for ``user`` and ``assistant``.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        conversation_id: Conversation the caller must own.
        run_id: Admitted run.
        role: ``user`` or ``assistant``.
        content: Message body. Never logged by callers.

    Returns:
        Message id, existing or newly inserted.

    Raises:
        QueryAdmissionError: Authorization, ownership, or validation failure.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT message_id
                FROM app.append_query_message(
                  %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    conversation_id,
                    run_id,
                    role,
                    content,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_message_error(exc)
    if row is None:
        raise QueryAdmissionError("message_persist_failed")
    return UUID(str(row["message_id"]))


def load_query_run_user_message(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
) -> str | None:
    """Load the durable user message for an owned run.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Run id.

    Returns:
        User message text, or None when no row exists.

    Raises:
        QueryAdmissionError: Authorization or lookup failure other than miss.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT content
                FROM app.load_query_run_user_message(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_message_error(exc)
    if row is None:
        return None
    content = row.get("content")
    return str(content) if content is not None else None
