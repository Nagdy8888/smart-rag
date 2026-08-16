"""Bounded authorized conversation memory. Packet 7 owns summary store."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.query_routing.constants import MEMORY_MESSAGE_LIMIT
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.models import MemoryRecord
from smart_rag_core.query_routing.safety import delimit_memory_record
from smart_rag_core.security.identity import CallerContext

_REASON_PREFIX = "query_memory:"


def load_authorized_memory(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
    limit: int = MEMORY_MESSAGE_LIMIT,
) -> tuple[MemoryRecord, ...]:
    """Load the last N creator-owned messages as untrusted delimited records.

    No summary column or LangGraph store is read. Packet 7 owns summaries.
    Source documents are never joined.

    Args:
        connection: Open connection. Caller must ``SET ROLE app_api``.
        caller: Server-derived identity.
        conversation_id: Conversation the caller must own.
        limit: Message cap, default 12, maximum 12.

    Returns:
        Newest-first memory records. Empty when the thread has no messages.

    Raises:
        QueryRoutingError: Authorization, deleted conversation, or foreign
            conversation.

    Side Effects:
        Executes ``app.load_query_memory``. No model calls.
    """

    bounded = min(max(limit, 1), MEMORY_MESSAGE_LIMIT)
    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT message_id, role, content, created_at
                FROM app.load_query_memory(
                  %s::uuid, %s::text, %s::bigint, %s::uuid, %s::integer
                )
                """,
                (
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    str(conversation_id),
                    bounded,
                ),
            )
            rows = cursor.fetchall()
    except psycopg.Error as exc:
        message = str(exc)
        reason = "database_rejected"
        if _REASON_PREFIX in message:
            start = message.find(_REASON_PREFIX) + len(_REASON_PREFIX)
            tail = message[start:].split()[0].strip("\"'")
            reason = tail.split("\n")[0]
        raise QueryRoutingError(reason) from exc

    records: list[MemoryRecord] = []
    for row in rows:
        created = row["created_at"]
        created_text = (
            created.isoformat() if isinstance(created, datetime) else str(created)
        )
        records.append(
            delimit_memory_record(
                message_id=str(row["message_id"]),
                role=str(row["role"]),
                content=str(row["content"] or ""),
                created_at=created_text,
            )
        )
    return tuple(records)
