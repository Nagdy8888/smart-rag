"""Thin FastAPI helper to list creator-only conversation transcripts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, NoReturn
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import (
    RunCitationRecord,
    list_conversation_citations,
)
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.security.untrusted import isolate_untrusted_text

from smart_rag_api.services.query_runs import escape_run_citation

_REASON_PREFIX = "query_memory:"
_REASON_MAP = {
    "authorization_rejected": "authorization_rejected",
    "conversation_not_found": "not_found",
    "conversation_deleted": "conversation_deleted",
    "conversation_forbidden": "not_found",
}
TranscriptRole = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class ConversationMessageRecord:
    """One authorized transcript row.

    Attributes:
        message_id: Message primary key.
        role: ``user`` or ``assistant``.
        content: HTML-escaped untrusted text.
        created_at: Persist timestamp.
        run_id: Owning query run, when the message was admitted.
        citations: Escaped citations for assistant runs. Empty for user rows.
    """

    message_id: UUID
    role: TranscriptRole
    content: str
    created_at: datetime
    run_id: UUID | None = None
    citations: tuple[RunCitationRecord, ...] = field(default_factory=tuple)


def _raise_transcript(exc: BaseException) -> NoReturn:
    """Map a Postgres error to a typed transcript failure.

    Args:
        exc: Driver or database error.

    Raises:
        QueryAdmissionError: Always, with a stable HTTP-mapped reason.
    """

    message = str(exc)
    reason = "database_rejected"
    if _REASON_PREFIX in message:
        start = message.find(_REASON_PREFIX) + len(_REASON_PREFIX)
        tail = message[start:].split()[0].strip("\"'")
        raw = tail.split("\n")[0]
        reason = _REASON_MAP.get(raw, "not_found")
    raise QueryAdmissionError(reason) from exc


def list_conversation_messages(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
    limit: int = 50,
    before_id: UUID | None = None,
) -> tuple[ConversationMessageRecord, ...]:
    """Load a newest-first page of creator-owned user/assistant messages.

    Args:
        connection: Open connection. Caller must ``SET ROLE app_api``.
        caller: JWKS-verified, profile-reloaded identity.
        conversation_id: Conversation the caller must own.
        limit: Page size, default 50, maximum 100.
        before_id: Optional keyset cursor. Returns rows older than this id.

    Returns:
        Newest-first transcript records. Empty when the thread has no
        user/assistant messages.

    Raises:
        QueryAdmissionError: Authorization, deleted, foreign, or missing
            conversation. Foreign and deleted conversations use ``not_found``
            after HTTP mapping.

    Side Effects:
        Executes ``app.list_conversation_messages_v2`` and one bounded
        ``app.list_conversation_citations_v1`` batch. No model calls and no SSE.
    """

    bounded = min(max(limit, 1), 100)
    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT message_id, role, content, created_at, run_id
                FROM app.list_conversation_messages_v2(
                  %s::uuid, %s::text, %s::bigint, %s::uuid, %s::integer, %s::uuid
                )
                """,
                (
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    str(conversation_id),
                    bounded,
                    str(before_id) if before_id is not None else None,
                ),
            )
            rows = cursor.fetchall()
    except psycopg.Error as exc:
        _raise_transcript(exc)

    records: list[ConversationMessageRecord] = []
    for row in rows:
        created = row["created_at"]
        if not isinstance(created, datetime):
            raise QueryAdmissionError("database_rejected")
        role = str(row["role"])
        if role not in {"user", "assistant"}:
            continue
        records.append(
            ConversationMessageRecord(
                message_id=UUID(str(row["message_id"])),
                role=role,  # type: ignore[arg-type]
                content=isolate_untrusted_text(str(row["content"] or "")),
                created_at=created,
                run_id=_optional_uuid(row.get("run_id")),
            )
        )
    return _attach_conversation_citations(
        connection,
        caller=caller,
        conversation_id=conversation_id,
        records=tuple(records),
    )


def _optional_uuid(value: object) -> UUID | None:
    """Parse a nullable UUID column.

    Args:
        value: Driver value.

    Returns:
        UUID or ``None``.
    """

    if value is None:
        return None
    return UUID(str(value))


def _attach_conversation_citations(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
    records: tuple[ConversationMessageRecord, ...],
) -> tuple[ConversationMessageRecord, ...]:
    """Batch-load citations for assistant messages on one transcript page.

    Args:
        connection: Open ``app_api`` connection.
        caller: Conversation owner.
        conversation_id: Owned conversation.
        records: Newest-first transcript rows.

    Returns:
        Records with escaped citations attached to assistant rows.

    Raises:
        QueryAdmissionError: Batch-cap or authorization failure.
    """

    run_ids = tuple(
        dict.fromkeys(item.run_id for item in records if item.run_id is not None)
    )
    by_run: dict[UUID, list[RunCitationRecord]] = {}
    for offset in range(0, len(run_ids), 50):
        batch = run_ids[offset : offset + 50]
        pairs = list_conversation_citations(
            connection,
            caller=caller,
            conversation_id=conversation_id,
            run_ids=batch,
        )
        for run_id, citation in pairs:
            by_run.setdefault(run_id, []).append(escape_run_citation(citation))
    attached: list[ConversationMessageRecord] = []
    for item in records:
        citations: tuple[RunCitationRecord, ...] = ()
        if item.role == "assistant" and item.run_id is not None:
            citations = tuple(by_run.get(item.run_id, ()))
        attached.append(
            ConversationMessageRecord(
                message_id=item.message_id,
                role=item.role,
                content=item.content,
                created_at=item.created_at,
                run_id=item.run_id,
                citations=citations,
            )
        )
    return tuple(attached)


class ConversationTranscriptService:
    """Factory-injected transcript reads."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Server-side Postgres URL.
        """

        self._postgres_url = postgres_url

    def list(
        self,
        caller: CallerContext,
        *,
        conversation_id: UUID,
        limit: int = 50,
        before_id: UUID | None = None,
    ) -> tuple[ConversationMessageRecord, ...]:
        """List one page of creator-owned transcript messages.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation the caller must own.
            limit: Page size, default 50, maximum 100.
            before_id: Optional keyset cursor.

        Returns:
            Newest-first records.

        Raises:
            QueryAdmissionError: Authorization or missing conversation.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            return list_conversation_messages(
                connection,
                caller=caller,
                conversation_id=conversation_id,
                limit=limit,
                before_id=before_id,
            )
