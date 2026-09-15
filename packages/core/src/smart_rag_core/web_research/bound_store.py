"""Bound Postgres adapter for P06-39 Web RPCs."""

from __future__ import annotations

from uuid import UUID

import psycopg

from smart_rag_core.security.identity import CallerContext
from smart_rag_core.web_research.models import WebOperationState, WebSourceRecord
from smart_rag_core.web_research.store import (
    begin_web_research_operation,
    complete_web_research_operation,
    insert_web_source,
    mark_web_research_operation_sent,
)


class BoundWebStore:
    """``WebOperationStore`` bound to one run and caller.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Query run.
    """

    def __init__(
        self,
        connection: psycopg.Connection,
        *,
        caller: CallerContext,
        run_id: UUID,
    ) -> None:
        """Bind persistence to one creator-owned run.

        Args:
            connection: Open ``app_api`` connection.
            caller: Server-derived owner.
            run_id: Query run.
        """

        self._connection = connection
        self._caller = caller
        self._run_id = run_id

    def begin(
        self,
        *,
        operation_key: str,
        kind: str,
        request_hash: str,
    ) -> WebOperationState:
        """Begin or replay one operation.

        Args:
            operation_key: Stable per-run key.
            kind: ``search``, ``contents``, or ``fetch``.
            request_hash: SHA-256 of the request body.

        Returns:
            Durable operation state.
        """

        return begin_web_research_operation(
            self._connection,
            caller=self._caller,
            run_id=self._run_id,
            operation_key=operation_key,
            kind=kind,
            request_hash=request_hash,
        )

    def mark_sent(self, *, operation_id: str) -> WebOperationState:
        """Mark planned as sent.

        Args:
            operation_id: Operation primary key.

        Returns:
            Updated state.
        """

        return mark_web_research_operation_sent(
            self._connection,
            caller=self._caller,
            operation_id=UUID(operation_id),
        )

    def complete(
        self,
        *,
        operation_id: str,
        ok: bool,
        failure_reason: str | None = None,
    ) -> WebOperationState:
        """Complete a sent operation.

        Args:
            operation_id: Operation primary key.
            ok: True for success.
            failure_reason: Safe reason when ``ok`` is false.

        Returns:
            Terminal state.
        """

        return complete_web_research_operation(
            self._connection,
            caller=self._caller,
            operation_id=UUID(operation_id),
            ok=ok,
            failure_reason=failure_reason,
        )

    def insert_source(
        self,
        *,
        source_index: int,
        url: str,
        title: str,
        excerpt: str,
        published_date: str | None = None,
    ) -> WebSourceRecord:
        """Persist one bounded source.

        Args:
            source_index: 0-5.
            url: Provider URL.
            title: Optional title.
            excerpt: 1-8000 characters.
            published_date: Optional date string.

        Returns:
            Persisted source.
        """

        return insert_web_source(
            self._connection,
            caller=self._caller,
            run_id=self._run_id,
            source_index=source_index,
            url=url,
            title=title,
            excerpt=excerpt,
            published_date=published_date,
        )
