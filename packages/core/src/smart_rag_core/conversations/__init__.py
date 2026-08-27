"""Creator-owned conversation RPCs used by thin FastAPI services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.security.untrusted import isolate_untrusted_text

_REASON_PREFIX = "conversation:"


@dataclass(frozen=True, slots=True)
class ConversationTitleSource:
    """First-turn excerpts used to generate a session title.

    Attributes:
        current_title: Raw stored title, or None.
        user_excerpt: Oldest user message, truncated to 2000 characters.
        assistant_excerpt: Oldest assistant message, truncated to 2000
            characters. Empty when the first answer is not persisted yet.
    """

    current_title: str | None
    user_excerpt: str
    assistant_excerpt: str


@dataclass(frozen=True, slots=True)
class ConversationRecord:
    """Authorized conversation row.

    Attributes:
        conversation_id: Primary key.
        creator_user_id: Owner of the thread.
        title: Escaped title for JSON responses.
        created_at: Creation timestamp when the RPC returns it.
        deleted: True when the row is soft-deleted (never returned by list).
    """

    conversation_id: UUID
    creator_user_id: UUID
    title: str | None
    created_at: datetime | None = None
    deleted: bool = False


def _raise_conversation(exc: BaseException) -> NoReturn:
    """Map a Postgres error to a typed conversation failure.

    Args:
        exc: Driver or database error.

    Raises:
        QueryAdmissionError: Always, with a stable reason when prefixed.
    """

    message = str(exc)
    reason = "database_rejected"
    if _REASON_PREFIX in message:
        start = message.find(_REASON_PREFIX) + len(_REASON_PREFIX)
        tail = message[start:].split()[0].strip("\"'")
        reason = tail.split("\n")[0]
    raise QueryAdmissionError(reason) from exc


def _conversation_record(row: object) -> ConversationRecord:
    """Map one RPC dict row to a conversation record.

    Args:
        row: ``dict_row`` mapping.

    Returns:
        Conversation with an escaped title.

    Raises:
        QueryAdmissionError: When the row is not a mapping.
    """

    if not isinstance(row, dict):
        raise QueryAdmissionError("conversation_create_failed")
    mapped = cast(dict[str, object], row)
    raw_title = mapped.get("title")
    created = mapped.get("created_at")
    created_at = created if isinstance(created, datetime) else None
    return ConversationRecord(
        conversation_id=UUID(str(mapped["id"])),
        creator_user_id=UUID(str(mapped["creator_user_id"])),
        title=isolate_untrusted_text(str(raw_title)) if raw_title is not None else None,
        created_at=created_at,
    )


def create_conversation(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    title: str | None,
) -> ConversationRecord:
    """Insert one creator-owned conversation.

    Args:
        connection: Open connection. Caller must ``SET ROLE app_api``.
        caller: Server-derived identity.
        title: Optional untrusted title. Stored raw; returned escaped.

    Returns:
        Created conversation.

    Raises:
        QueryAdmissionError: Authorization or insert failure.

    Side Effects:
        Inserts ``app.conversations``.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.create_conversation(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    title,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_conversation(exc)
    if row is None:
        raise QueryAdmissionError("conversation_create_failed")
    return _conversation_record(row)


def list_conversations(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    limit: int = 50,
    cursor_created_at: datetime | None = None,
    cursor_id: UUID | None = None,
) -> tuple[ConversationRecord, ...]:
    """List non-deleted conversations the caller may see.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived identity.
        limit: Page size, default 50, max 200.
        cursor_created_at: Optional keyset timestamp.
        cursor_id: Optional keyset id. Must be paired with ``cursor_created_at``.

    Returns:
        Creator-owned rows, plus owner/admin audit visibility, newest first.

    Raises:
        QueryAdmissionError: Authorization or cursor failure.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, creator_user_id, title, created_at
                FROM app.list_user_conversations_page(%s, %s, %s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    limit,
                    cursor_created_at,
                    cursor_id,
                ),
            )
            rows = cursor.fetchall()
    except psycopg.Error as exc:
        _raise_conversation(exc)
    return tuple(_conversation_record(row) for row in rows)


def delete_conversation(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
) -> None:
    """Tombstone and purge one conversation in a single Postgres transaction.

    Args:
        connection: Open ``app_api`` connection. Caller must commit.
        caller: Server-derived identity. Creator or owner/admin.
        conversation_id: Conversation primary key.

    Raises:
        QueryAdmissionError: ``not_found`` for missing, foreign (non-privileged),
            or unauthorized callers.

    Side Effects:
        Sets ``conversations.deleted_at``, deletes messages/runs/events/
        citations/feedback/checkpoints/store rows, appends a content-free
        audit event, and inserts a durable LangSmith deletion request.
        Idempotent when already tombstoned.
    """

    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT app.delete_conversation(%s, %s, %s, %s)
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        conversation_id,
                    ),
                )
    except psycopg.Error as exc:
        _raise_conversation(exc)


def get_conversation(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
) -> ConversationRecord:
    """Load one non-deleted conversation the caller may read.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived identity.
        conversation_id: Conversation primary key.

    Returns:
        Conversation record with escaped title.

    Raises:
        QueryAdmissionError: ``not_found`` or authorization failure.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.get_conversation(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    conversation_id,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_conversation(exc)
    if row is None:
        raise QueryAdmissionError("not_found")
    return _conversation_record(row)


def get_conversation_title_source(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
) -> ConversationTitleSource:
    """Load creator-only title excerpts for one conversation.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived identity. Must be the creator.
        conversation_id: Conversation primary key.

    Returns:
        Current title plus first user and assistant excerpts.

    Raises:
        QueryAdmissionError: ``not_found`` for missing, deleted, or foreign
            conversations.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.get_conversation_title_source(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    conversation_id,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_conversation(exc)
    if row is None:
        raise QueryAdmissionError("not_found")
    mapped = cast(dict[str, object], row)
    raw_title = mapped.get("current_title")
    user_excerpt = mapped.get("user_excerpt")
    assistant_excerpt = mapped.get("assistant_excerpt")
    return ConversationTitleSource(
        current_title=str(raw_title) if raw_title is not None else None,
        user_excerpt=str(user_excerpt) if user_excerpt is not None else "",
        assistant_excerpt=(
            str(assistant_excerpt) if assistant_excerpt is not None else ""
        ),
    )


def update_conversation_title(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
    title: str,
) -> ConversationRecord:
    """Replace the creator-owned conversation title.

    Args:
        connection: Open ``app_api`` connection. Caller must commit.
        caller: Server-derived identity. Must be the creator.
        conversation_id: Conversation primary key.
        title: Untrusted title. Stored raw; returned escaped.

    Returns:
        Updated conversation.

    Raises:
        QueryAdmissionError: ``not_found`` for missing, deleted, or foreign
            conversations.

    Side Effects:
        Updates ``app.conversations.title``.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.update_conversation_title(%s, %s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    conversation_id,
                    title,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_conversation(exc)
    if row is None:
        raise QueryAdmissionError("not_found")
    return _conversation_record(row)
