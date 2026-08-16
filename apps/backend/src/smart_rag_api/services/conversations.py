"""Conversation HTTP service. Routers never open repositories."""

from __future__ import annotations

from uuid import UUID

import psycopg
from smart_rag_core.conversations import (
    ConversationRecord,
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
)
from smart_rag_core.security.identity import CallerContext


class ConversationService:
    """Factory-injected conversation operations."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Server-side Postgres URL.
        """

        self._postgres_url = postgres_url

    def create(self, caller: CallerContext, *, title: str | None) -> ConversationRecord:
        """Create a creator-owned conversation.

        Args:
            caller: Authenticated caller.
            title: Optional untrusted title.

        Returns:
            Created record.

        Raises:
            QueryAdmissionError: Authorization or insert failure.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            record = create_conversation(connection, caller=caller, title=title)
            connection.commit()
        return record

    def list(self, caller: CallerContext) -> tuple[ConversationRecord, ...]:
        """List conversations visible to the caller.

        Args:
            caller: Authenticated caller.

        Returns:
            Conversation records.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            return list_conversations(connection, caller=caller)

    def get(
        self, caller: CallerContext, *, conversation_id: UUID
    ) -> ConversationRecord:
        """Load one conversation.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation id.

        Returns:
            Conversation record.

        Raises:
            QueryAdmissionError: ``not_found`` when missing, deleted, or foreign
                for members/viewers.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            return get_conversation(
                connection, caller=caller, conversation_id=conversation_id
            )

    def delete(self, caller: CallerContext, *, conversation_id: UUID) -> None:
        """Tombstone and purge one owned conversation.

        Args:
            caller: Authenticated caller. Creator or owner/admin.
            conversation_id: Conversation id.

        Raises:
            QueryAdmissionError: ``not_found`` when missing, deleted, or
                foreign for members/viewers.

        Side Effects:
            One Postgres transaction: tombstone, cascade, content-free audit,
            LangSmith deletion request.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            delete_conversation(
                connection, caller=caller, conversation_id=conversation_id
            )
            connection.commit()
