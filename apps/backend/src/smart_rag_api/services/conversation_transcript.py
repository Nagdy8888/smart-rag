"""Thin FastAPI helper to list creator-only conversation transcripts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, NoReturn
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.knowledge import KnowledgeResult
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import RunCitationRecord
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.security.untrusted import isolate_untrusted_text

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
        run_id: Owning query run when the message and run share ownership.
        citation_count: Persisted citation rows for that run, clamped 0..50.
        source_kind: ``company_document``, ``web``, or null when mixed/none.
        citations: Always empty on the list path. Excerpts use citation detail.
    """

    message_id: UUID
    role: TranscriptRole
    content: str
    created_at: datetime
    run_id: UUID | None = None
    run_status: str | None = None
    requested_search_scope: str | None = None
    answer_origin: str | None = None
    citation_count: int = 0
    source_kind: str | None = None
    knowledge_result: KnowledgeResult | None = None
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
        Executes ``app.list_conversation_messages_v3``. Citation excerpts
        are not loaded on this path.
    """

    bounded = min(max(limit, 1), 100)
    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT message_id, role, content, created_at, run_id,
                       citation_count, source_kind, presentation.requested_search_scope, presentation.answer_origin,
                       CASE WHEN run_id IS NOT NULL THEN
                         (SELECT r.status::text FROM app.get_query_run_v3(
                           %s,%s,%s,transcript.run_id) r)
                         ELSE NULL END AS run_status,
                       app.get_run_knowledge_result(%s, %s, %s, run_id) AS knowledge_result,
                       CASE WHEN role='assistant' AND run_id IS NOT NULL THEN
                         app.run_knowledge_history_unavailable(%s,%s,%s,run_id)
                         ELSE false END AS source_unavailable
                FROM app.list_conversation_messages_v3(
                  %s::uuid, %s::text, %s::bigint, %s::uuid, %s::integer, %s::uuid
                ) AS transcript
                LEFT JOIN LATERAL app.get_run_presentation_v1(
                  %s,%s,%s,transcript.run_id
                ) presentation ON transcript.run_id IS NOT NULL
                ORDER BY created_at DESC, message_id DESC
                """,
                (
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    str(conversation_id),
                    bounded,
                    str(before_id) if before_id is not None else None,
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
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
        kind = row.get("source_kind")
        source_kind = str(kind) if kind in {"company_document", "web"} else None
        count_raw = row.get("citation_count")
        citation_count = 0 if count_raw is None else max(0, min(int(count_raw), 50))
        records.append(
            ConversationMessageRecord(
                message_id=UUID(str(row["message_id"])),
                role=role,  # type: ignore[arg-type]
                content=isolate_untrusted_text(
                    "Source unavailable. This answer is hidden because its supporting evidence is no longer accessible."
                    if row.get("source_unavailable")
                    else str(row["content"] or "")
                ),
                created_at=created,
                run_id=_optional_uuid(row.get("run_id")),
                citation_count=citation_count,
                source_kind=source_kind,
                run_status=str(row["run_status"]) if row.get("run_status") else None,
                requested_search_scope=row.get("requested_search_scope"),
                answer_origin=row.get("answer_origin"),
                knowledge_result=KnowledgeResult.model_validate(row["knowledge_result"])
                if row.get("knowledge_result") and not row.get("source_unavailable")
                else None,
            )
        )
    return tuple(records)


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
