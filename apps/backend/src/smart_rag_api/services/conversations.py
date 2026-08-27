"""Conversation HTTP service. Routers never open repositories."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg
from smart_rag_agents.prompts import conversation_title_prompt_text
from smart_rag_core.conversations import (
    ConversationRecord,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversation_title_source,
    list_conversations,
    update_conversation_title,
)
from smart_rag_core.conversations.title import (
    compact_conversation_title,
    needs_llm_conversation_title,
    title_generation_excerpt,
)
from smart_rag_core.gateways.model import (
    ConversationTitleModelRequest,
    ModelGateway,
    ModelGatewayUnavailableError,
)
from smart_rag_core.gateways.openai_answer import OpenAIAnswerError
from smart_rag_core.query_answer.versions import (
    CONVERSATION_TITLE_MODEL_ID,
    CONVERSATION_TITLE_PROMPT_SHA256,
    CONVERSATION_TITLE_PROMPT_VERSION,
)
from smart_rag_core.security.identity import CallerContext

from smart_rag_api.services.keyset import parse_created_at_id_cursor


@dataclass(frozen=True, slots=True)
class ConversationTitleResult:
    """Title-refresh outcome including provider usage for this call.

    Attributes:
        record: Conversation after the title write or skip.
        prompt_tokens: Provider prompt tokens. 0 when the model was skipped
            or failed before a billed response.
        completion_tokens: Provider completion tokens. 0 when skipped or
            failed.
    """

    record: ConversationRecord
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _non_negative_tokens(value: int) -> int:
    """Clamp a provider usage field to a non-negative integer.

    Args:
        value: Provider-reported token count.

    Returns:
        ``value`` when ``>= 0``, otherwise ``0``.
    """

    return max(0, value)


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

    def list(
        self,
        caller: CallerContext,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[ConversationRecord, ...]:
        """List conversations visible to the caller.

        Args:
            caller: Authenticated caller.
            limit: Page size, default 50, max 200.
            cursor: Optional ``created_at,id`` keyset cursor.

        Returns:
            Conversation records, newest first.

        Raises:
            QueryAdmissionError: Authorization or cursor failure.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            cursor_created_at, cursor_id = parse_created_at_id_cursor(cursor)
            return list_conversations(
                connection,
                caller=caller,
                limit=max(1, min(limit, 200)),
                cursor_created_at=cursor_created_at,
                cursor_id=cursor_id,
            )

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

    async def generate_title(
        self,
        caller: CallerContext,
        *,
        conversation_id: UUID,
        gateway: ModelGateway,
    ) -> ConversationTitleResult:
        """Fill the session title from a bounded LLM summary when needed.

        Args:
            caller: Authenticated creator.
            conversation_id: Conversation id.
            gateway: Process model gateway.

        Returns:
            Conversation plus this call's provider tokens. Tokens are 0
            when the model was skipped or failed. On model failure the
            existing fallback title is kept.

        Raises:
            QueryAdmissionError: ``not_found`` when missing, deleted, or
                foreign.

        Side Effects:
            May call the model gateway once and update
            ``app.conversations.title``. Failure keeps the prior title.
            Title tokens are not reserved against the query-run envelope.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            source = get_conversation_title_source(
                connection, caller=caller, conversation_id=conversation_id
            )
            current = get_conversation(
                connection, caller=caller, conversation_id=conversation_id
            )
        excerpt = title_generation_excerpt(source.current_title, source.user_excerpt)
        if excerpt == "":
            return ConversationTitleResult(record=current)
        if not needs_llm_conversation_title(source.current_title, excerpt):
            return ConversationTitleResult(record=current)
        fallback = compact_conversation_title(excerpt)
        try:
            response = await gateway.generate_conversation_title(
                ConversationTitleModelRequest(
                    user_excerpt=excerpt[:2000],
                    assistant_excerpt=source.assistant_excerpt[:2000],
                    prompt_text=conversation_title_prompt_text(),
                    prompt_version=CONVERSATION_TITLE_PROMPT_VERSION,
                    prompt_sha256=CONVERSATION_TITLE_PROMPT_SHA256,
                    model_id=CONVERSATION_TITLE_MODEL_ID,
                    remaining_deadline_seconds=8.0,
                )
            )
            raw_title = response.payload.get("title")
            title = compact_conversation_title(
                str(raw_title) if isinstance(raw_title, str) else ""
            )
            if title == "Chat":
                title = fallback
        except (
            ModelGatewayUnavailableError,
            OpenAIAnswerError,
            ValueError,
            OSError,
        ):
            return ConversationTitleResult(record=current)
        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            record = update_conversation_title(
                connection,
                caller=caller,
                conversation_id=conversation_id,
                title=title,
            )
            connection.commit()
        return ConversationTitleResult(
            record=record,
            prompt_tokens=_non_negative_tokens(response.input_tokens),
            completion_tokens=_non_negative_tokens(response.output_tokens),
        )
