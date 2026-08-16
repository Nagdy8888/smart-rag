"""Thin FastAPI helper to load creator-only query memory. No SSE router."""

from __future__ import annotations

from uuid import UUID

import psycopg
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.memory import load_authorized_memory
from smart_rag_core.query_routing.models import MemoryRecord
from smart_rag_core.security.identity import CallerContext


def load_query_memory_for_caller(
    postgres_url: str,
    *,
    caller: CallerContext,
    conversation_id: UUID,
) -> tuple[MemoryRecord, ...]:
    """Load last-N authorized messages with ``SET ROLE app_api``.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller: JWKS-verified, profile-reloaded identity.
        conversation_id: Conversation the caller must own.

    Returns:
        Untrusted delimited memory records.

    Raises:
        QueryRoutingError: Authorization, deleted, or foreign conversation.

    Side Effects:
        Executes ``app.load_query_memory``. No model calls and no SSE.
    """

    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            records = load_authorized_memory(
                connection,
                caller=caller,
                conversation_id=conversation_id,
            )
            connection.commit()
    except QueryRoutingError:
        raise
    except psycopg.Error as exc:
        raise QueryRoutingError("database_rejected") from exc
    return records
