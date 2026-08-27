"""Sync/async SSE append, catalog validation, and append-failure logging."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING
from uuid import UUID

from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.catalog import TERMINAL_SSE_EVENT_TYPES
from smart_rag_core.sse.store import PersistedRunEvent, RunEventStore, sqlstate_of

LOGGER = logging.getLogger(__name__)


class EventAppendMixin:
    """Mixin: persist one catalog event and log sanitized append failures."""

    _store: RunEventStore

    if TYPE_CHECKING:

        def _has_terminal(self, caller: CallerContext, run_id: UUID) -> bool:
            """Return whether a terminal event exists. Provided by ReplayCancelMixin."""

            ...

        def _settle_reservation(self, caller: CallerContext, run_id: UUID) -> None:
            """True-up the reservation once. Provided by RunSettlementMixin."""

            ...

    def _log_append_failure(
        self,
        *,
        run_id: UUID,
        event_type: str,
        exc: BaseException,
        elapsed_seconds: float,
    ) -> None:
        """Log one sanitized append failure without secrets or payloads.

        Args:
            run_id: Run whose event failed to persist.
            event_type: Allow-listed type that was attempted.
            exc: Admission or driver error. Message text is not logged.
            elapsed_seconds: Wall time spent in the store call.

        Side Effects:
            Writes one structured info record. Never logs DSNs, JWTs,
            payload bodies, or exception messages.
        """

        reason = getattr(exc, "reason", None)
        if not isinstance(reason, str) or not reason:
            reason = type(exc).__name__
        LOGGER.info(
            "sse append failed",
            extra={
                "event": "sse.append_failed",
                "run_id": str(run_id),
                "sse_event_type": event_type,
                "reason": reason[:64],
                "sqlstate": sqlstate_of(exc),
                "elapsed_seconds": round(elapsed_seconds, 3),
            },
        )

    async def _append_async(
        self,
        caller: CallerContext,
        run_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> PersistedRunEvent | None:
        """Persist one event off the asyncio loop.

        Heartbeat and executor orchestration must use this helper so a
        synchronous run-row lock wait cannot freeze ``astream`` or SSE
        polling. Callers still await each append before the next event so
        sequence order and exactly-one terminal stay unchanged.

        Args:
            caller: Owner.
            run_id: Run id.
            event_type: Allow-listed type.
            payload: Candidate payload.

        Returns:
            Persisted row, or None when append is rejected after sanitizing.
        """

        return await asyncio.to_thread(
            self._append, caller, run_id, event_type, payload
        )

    def _append(
        self,
        caller: CallerContext,
        run_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> PersistedRunEvent | None:
        """Persist one event. Invalid drafts become a sanitized error.

        Args:
            caller: Owner.
            run_id: Run id.
            event_type: Allow-listed type.
            payload: Candidate payload.

        Returns:
            Persisted row, or None when append is rejected after sanitizing.
            Heartbeat lock or admission failures degrade to None. Status and
            terminal admission failures keep that same None return so the
            existing executor failure path can persist a sanitized error.
        """

        if event_type == "heartbeat" and self._has_terminal(caller, run_id):
            return None
        started = time.monotonic()
        try:
            persisted = self._store.append(
                caller,
                run_id=run_id,
                event_type=event_type,
                payload=payload,
            )
        except ValueError:
            LOGGER.info(
                "rejected sse payload",
                extra={"event": "sse.payload_rejected", "sse_event_type": event_type},
            )
            if event_type == "error":
                return None
            try:
                persisted = self._store.append(
                    caller,
                    run_id=run_id,
                    event_type="error",
                    payload={"code": "run_failed"},
                )
            except (QueryAdmissionError, ValueError) as exc:
                self._log_append_failure(
                    run_id=run_id,
                    event_type="error",
                    exc=exc,
                    elapsed_seconds=time.monotonic() - started,
                )
                return None
        except QueryAdmissionError as exc:
            self._log_append_failure(
                run_id=run_id,
                event_type=event_type,
                exc=exc,
                elapsed_seconds=time.monotonic() - started,
            )
            return None
        if persisted.event_type in TERMINAL_SSE_EVENT_TYPES:
            self._settle_reservation(caller, run_id)
        return persisted
