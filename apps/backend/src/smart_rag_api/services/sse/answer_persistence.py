"""Post-terminal summary and assistant-message persistence."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

import psycopg
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.settings.postgres_connect import connect_postgres

if TYPE_CHECKING:
    from smart_rag_api.services.query_sse_mapping import QuerySseMapper

LOGGER = logging.getLogger(__name__)


class _CompactMemoryStore(Protocol):
    """Memory-store methods used after a successful terminal."""

    def put_compact(
        self,
        namespace: tuple[str, str, str],
        key: str,
        payload: dict[str, object],
    ) -> object:
        """Write one compacted store item.

        Args:
            namespace: Store namespace tuple.
            key: Item key.
            payload: Compact JSON mapping.

        Returns:
            Store write result.
        """

        ...


class AnswerPersistenceMixin:
    """Mixin: budgeted summary and assistant-message writes after a terminal."""

    _store: _CompactMemoryStore | None

    def _commit_successful_terminal(
        self,
        context: AuthorizedRuntimeContext,
        mapper: QuerySseMapper,
        settings: object,
        *,
        remaining_model_calls: int,
        terminal_status: str,
    ) -> None:
        """Write summary and assistant text after a non-error terminal.

        The caller must already have yielded ``completed`` or ``partial``.
        Persist failures stay off the SSE log so they cannot overwrite that
        terminal with ``error``.

        Side Effects:
            May consume ``usage_kind=summary`` and insert one assistant
            ``app.messages`` row. Logs ``error_type`` only when a write
            fails.

        Args:
            context: Authorized run context.
            mapper: Mapper that emitted the verified terminal.
            settings: Backend settings loaded once for this execute().
            remaining_model_calls: Remaining counted calls after the graph.
            terminal_status: Last node status.
        """

        try:
            self._maybe_summarize(
                context,
                settings,
                remaining_model_calls=remaining_model_calls,
                terminal_status=terminal_status,
            )
        except Exception as exc:
            LOGGER.info(
                "query summary skipped",
                extra={
                    "event": "query.sse.summary_failed",
                    "error_type": type(exc).__name__,
                    "run_id": str(context.run_id),
                },
            )
        try:
            self._persist_assistant_answer(context, mapper, settings)
        except Exception as exc:
            LOGGER.info(
                "assistant message persist skipped",
                extra={
                    "event": "query.sse.assistant_persist_failed",
                    "error_type": type(exc).__name__,
                    "run_id": str(context.run_id),
                },
            )

    def _maybe_summarize(
        self,
        context: AuthorizedRuntimeContext,
        settings: object,
        *,
        remaining_model_calls: int,
        terminal_status: str,
    ) -> None:
        """Write a budgeted compact summary when the envelope can afford it.

        Args:
            context: Authorized run context.
            settings: Backend settings loaded once for this execute().
            remaining_model_calls: Remaining counted calls after the graph.
            terminal_status: Last node status. Summaries are skipped on
                admission/routing rejection.
        """

        if terminal_status in {"admission_rejected", "routing_rejected"}:
            return
        if self._store is None:
            return
        from smart_rag_core.memory.summary import maybe_generate_conversation_summary
        from smart_rag_core.query_routing.preparation import caller_from_runtime

        db_url = getattr(settings, "supabase_db_url", None)
        postgres_url = db_url.get_secret_value() if db_url is not None else None
        if postgres_url is None:
            return
        store = self._store

        def _put(
            namespace: tuple[str, str, str],
            key: str,
            payload: dict[str, object],
        ) -> None:
            """Write one compacted store item.

            Args:
                namespace: Store namespace tuple.
                key: Item key.
                payload: JSON-compatible value.
            """

            store.put_compact(namespace, key, payload)

        with connect_postgres(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            maybe_generate_conversation_summary(
                connection,
                caller=caller_from_runtime(context),
                run_id=context.run_id,
                reservation_id=context.reservation_id,
                expected_version=context.optimistic_version,
                remaining_model_calls=remaining_model_calls,
                remaining_usd=context.remaining_usd,
                conversation_id=context.conversation_id,
                user_id=str(context.user_id),
                memory_records=(),
                store_put=_put,
            )
            connection.commit()

    def _persist_assistant_answer(
        self,
        context: AuthorizedRuntimeContext,
        mapper: QuerySseMapper,
        settings: object,
    ) -> None:
        """Persist verified assistant prose when a DSN and text exist.

        Args:
            context: Authorized run context.
            mapper: Mapper that emitted the verified terminal.
            settings: Backend settings loaded once for this execute().
        """

        answer_text = mapper.verified_text
        if not answer_text:
            return
        from smart_rag_core.query_admission.messages import append_query_message
        from smart_rag_core.query_routing.preparation import caller_from_runtime

        db_url = getattr(settings, "supabase_db_url", None)
        postgres_url = db_url.get_secret_value() if db_url is not None else None
        if postgres_url is None:
            return
        try:
            with connect_postgres(postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                append_query_message(
                    connection,
                    caller=caller_from_runtime(context),
                    conversation_id=context.conversation_id,
                    run_id=context.run_id,
                    role="assistant",
                    content=answer_text,
                )
                connection.commit()
        except (QueryAdmissionError, psycopg.Error):
            LOGGER.info(
                "assistant message persist skipped",
                extra={
                    "event": "query.sse.assistant_persist_failed",
                    "run_id": str(context.run_id),
                },
            )
