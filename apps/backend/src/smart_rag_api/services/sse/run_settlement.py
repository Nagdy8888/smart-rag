"""Schema, durable start, worker-unavailable, and reservation settlement."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

import psycopg
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import (
    load_query_run_runtime,
    true_up_query_reservation,
)
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.store import PersistedRunEvent, RunEventStore

from smart_rag_api.services.sse.constants import NON_STARTABLE_STATUSES

LOGGER = logging.getLogger(__name__)


class RunSettlementMixin:
    """Mixin: first schema event, durable resume input, and reservation true-up."""

    _store: RunEventStore
    _postgres_url: str | None
    _settled_run_ids: set[UUID]
    _sse_schema_version: str

    if TYPE_CHECKING:

        def _append(
            self,
            caller: CallerContext,
            run_id: UUID,
            event_type: str,
            payload: dict[str, object],
        ) -> PersistedRunEvent | None:
            """Persist one catalog event. Provided by EventAppendMixin."""

            ...

        def _has_terminal(self, caller: CallerContext, run_id: UUID) -> bool:
            """Return whether a terminal event exists. Provided by ReplayCancelMixin."""

            ...

    def _ensure_schema(self, caller: CallerContext, run_id: UUID) -> None:
        """Persist ``schema`` as sequence 1 when the log is empty.

        Args:
            caller: Owner.
            run_id: Run id.
        """

        existing = self._store.list_after(caller, run_id=run_id, after=0)
        if existing:
            return
        self._append(
            caller,
            run_id,
            "schema",
            {"sse_schema_version": self._sse_schema_version},
        )

    def _load_durable_start(
        self, caller: CallerContext, run_id: UUID
    ) -> tuple[str, AuthorizedRuntimeContext] | None:
        """Rebuild user text and runtime from durable records.

        Args:
            caller: Owner.
            run_id: Admitted run.

        Returns:
            Persisted message and runtime, or None when the DSN is unset
            or durable input cannot be loaded. Missing input must remain
            ``worker_unavailable`` for process-local tests.
        """

        if not self._postgres_url:
            return None
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                runtime, message = load_query_run_runtime(
                    connection, caller=caller, run_id=run_id
                )
        except (QueryAdmissionError, psycopg.Error):
            return None
        if not message:
            return None
        return message, runtime

    def _settle_reservation(self, caller: CallerContext, run_id: UUID) -> None:
        """True-up the run reservation once on a terminal event.

        Args:
            caller: Owner.
            run_id: Run whose reservation should settle.

        Side Effects:
            Calls ``true_up_query_reservation`` at most once per run in
            this process. No-ops without a DSN or reservation id.
        """

        if not self._postgres_url or run_id in self._settled_run_ids:
            return
        try:
            record = self._store.get_authorized_run(caller, run_id=run_id)
        except QueryAdmissionError:
            return
        reservation_id = record.reservation_id
        if reservation_id is None:
            self._settled_run_ids.add(run_id)
            return
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                true_up_query_reservation(
                    connection, caller=caller, reservation_id=reservation_id
                )
                connection.commit()
            self._settled_run_ids.add(run_id)
        except (QueryAdmissionError, psycopg.Error):
            LOGGER.info(
                "reservation true-up skipped",
                extra={
                    "event": "sse.reservation_true_up_failed",
                    "run_id": str(run_id),
                },
            )

    def _emit_worker_unavailable(self, caller: CallerContext, run_id: UUID) -> None:
        """Persist schema then a sanitized terminal when this process cannot run.

        Allowed only for true orphans: ``pending`` with no startable input on
        this process. Never persist ``worker_unavailable`` while status is
        ``running`` (another replica may still complete the run).

        Args:
            caller: Owner.
            run_id: Run id.
        """

        try:
            record = self._store.get_authorized_run(caller, run_id=run_id)
        except QueryAdmissionError:
            return
        if record.status in NON_STARTABLE_STATUSES:
            return
        self._ensure_schema(caller, run_id)
        if not self._has_terminal(caller, run_id):
            self._append(caller, run_id, "error", {"code": "worker_unavailable"})
