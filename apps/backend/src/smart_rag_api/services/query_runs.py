"""Query-run HTTP service: admit, fetch, cancel, citations. No SSE bodies."""

from __future__ import annotations

from uuid import UUID

import psycopg
from pydantic import SecretStr
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.messages import append_query_message
from smart_rag_core.query_admission.service import (
    QueryRunRecord,
    RunCitationRecord,
    cancel_query_run,
    fail_query_run,
    get_query_run,
    list_run_citations,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.runtime.valkey import ValkeyClient
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.security.untrusted import isolate_untrusted_text

from smart_rag_api.services.query_admission import admit_query_run_for_caller

STREAM_PATH_TEMPLATE = "/runs/{run_id}/events"


class QueryRunService:
    """Factory-injected run operations."""

    def __init__(
        self,
        postgres_url: str,
        *,
        valkey_client: ValkeyClient | None = None,
    ) -> None:
        """Store DSN and optional limits client.

        Args:
            postgres_url: app_api URL.
            valkey_client: FastAPI-owned limits Valkey.
        """

        self._postgres_url = postgres_url
        self._valkey_client = valkey_client

    def submit_auto_message(
        self,
        caller: CallerContext,
        *,
        conversation_id: UUID,
        idempotency_key: UUID,
        message: str,
    ) -> tuple[AuthorizedRuntimeContext, str]:
        """Admit a Composite envelope for Auto chat. Does not start SSE.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation the caller must own.
            idempotency_key: Client UUID key.
            message: Untrusted user text (hashed for admission).

        Returns:
            Authorized context and the packet 6 stream path.

        Raises:
            QueryAdmissionError: Rate, ownership, budget, or idempotency.
        """

        result = admit_query_run_for_caller(
            self._postgres_url,
            caller=caller,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            message=message,
            route_family=Phase6RouteFamily.COMPOSITE,
            postgres_rate_limit_url=SecretStr(self._postgres_url),
            valkey_client=self._valkey_client,
        )
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                append_query_message(
                    connection,
                    caller=caller,
                    conversation_id=conversation_id,
                    run_id=result.context.run_id,
                    role="user",
                    content=message,
                )
                connection.commit()
        except (psycopg.Error, QueryAdmissionError) as exc:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                try:
                    fail_query_run(
                        connection,
                        caller=caller,
                        run_id=result.context.run_id,
                    )
                    connection.commit()
                except QueryAdmissionError:
                    connection.rollback()
            del exc
            raise QueryAdmissionError("message_persist_failed") from None
        stream_path = STREAM_PATH_TEMPLATE.format(run_id=result.context.run_id)
        return result.context, stream_path

    def get(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
        """Fetch one owned run.

        Args:
            caller: Authenticated caller.
            run_id: Run id.

        Returns:
            Run record.

        Raises:
            QueryAdmissionError: ``not_found`` for missing or foreign runs.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            return get_query_run(connection, caller=caller, run_id=run_id)

    def cancel(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
        """Cancel one owned run. Not SSE cancel transport.

        Args:
            caller: Authenticated caller.
            run_id: Run id.

        Returns:
            Updated run.

        Raises:
            QueryAdmissionError: Ownership or state failures.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            record = cancel_query_run(connection, caller=caller, run_id=run_id)
            connection.commit()
        return record

    def citations(
        self, caller: CallerContext, *, run_id: UUID
    ) -> tuple[RunCitationRecord, ...]:
        """Return citation IDs with escaped provenance strings.

        Args:
            caller: Authenticated caller.
            run_id: Run id.

        Returns:
            Citation records without passage text.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            records = list_run_citations(connection, caller=caller, run_id=run_id)
        escaped: list[RunCitationRecord] = []
        for item in records:
            provenance = {
                str(key): isolate_untrusted_text(value)
                if isinstance(value, str)
                else value
                for key, value in item.provenance.items()
            }
            escaped.append(
                RunCitationRecord(
                    citation_id=item.citation_id,
                    citation_index=item.citation_index,
                    chunk_id=item.chunk_id,
                    provenance=provenance,
                    source_unavailable=item.source_unavailable,
                )
            )
        return tuple(escaped)
