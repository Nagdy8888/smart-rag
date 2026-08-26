"""Query-run executor protocol used by the SSE attach service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext


class QueryRunExecutor(Protocol):
    """Produces application SSE drafts. Heartbeat and schema are service-owned."""

    def execute(
        self,
        *,
        context: AuthorizedRuntimeContext,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Yield ``(event_type, payload)`` until complete, cancelled, or failed.

        Args:
            context: Authorized runtime from admission.
            message: Untrusted user text for graph input.
            cancel_event: Set when POST ``/runs/{id}/cancel`` fires.

        Returns:
            Async iterator of allow-listed event type and extra=forbid payload.
        """

        raise NotImplementedError
