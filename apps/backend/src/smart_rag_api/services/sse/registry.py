"""Process-local live-run handles and pending graph inputs."""

from __future__ import annotations

import asyncio
from uuid import UUID

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext


class LiveQueryRun:
    """In-process handle for one run's executor and heartbeat."""

    def __init__(self) -> None:
        """Create an idle handle."""

        self.cancel_event = asyncio.Event()
        self.started = False
        self.terminal = False
        self.executor_task: asyncio.Task[None] | None = None
        self.heartbeat_task: asyncio.Task[None] | None = None


class QueryRunRegistry:
    """Process-local live runs and pending graph inputs keyed by ``run_id``."""

    def __init__(self) -> None:
        """Create an empty registry."""

        self._live: dict[UUID, LiveQueryRun] = {}
        self._inputs: dict[UUID, str] = {}
        self._contexts: dict[UUID, AuthorizedRuntimeContext] = {}

    def remember_input(
        self,
        run_id: UUID,
        message: str,
        context: AuthorizedRuntimeContext | None = None,
    ) -> None:
        """Store the user message and admit context for a later first attach.

        Args:
            run_id: Admitted run.
            message: Untrusted user text.
            context: Authorized runtime used to start the graph once.
        """

        self._inputs[run_id] = message
        if context is not None:
            self._contexts[run_id] = context

    def take_input(self, run_id: UUID) -> str:
        """Return the remembered message or empty string.

        Args:
            run_id: Run id.

        Returns:
            Stored message. Empty when this process never saw the POST body.
        """

        return self._inputs.get(run_id, "")

    def take_context(self, run_id: UUID) -> AuthorizedRuntimeContext | None:
        """Return the remembered admit context when this process saw the POST.

        Args:
            run_id: Run id.

        Returns:
            Stored context, or None after a process restart.
        """

        return self._contexts.get(run_id)

    def has_input(self, run_id: UUID) -> bool:
        """Return whether this process still has the POST body.

        Args:
            run_id: Run id.

        Returns:
            True when ``remember_input`` ran in this process.
        """

        return run_id in self._inputs

    def get(self, run_id: UUID) -> LiveQueryRun | None:
        """Return the live handle when this process owns the executor.

        Args:
            run_id: Run id.

        Returns:
            Live handle or None.
        """

        return self._live.get(run_id)

    def get_or_create(self, run_id: UUID) -> LiveQueryRun:
        """Return the existing handle or create an idle one.

        Args:
            run_id: Run id.

        Returns:
            Live handle.
        """

        handle = self._live.get(run_id)
        if handle is None:
            handle = LiveQueryRun()
            self._live[run_id] = handle
        return handle

    def drop(self, run_id: UUID) -> None:
        """Forget a finished live handle. Inputs stay for no-op reconnects.

        Args:
            run_id: Run id.
        """

        self._live.pop(run_id, None)

    def request_cancel(self, run_id: UUID) -> None:
        """Signal the live executor to stop. No-op when this process has none.

        Args:
            run_id: Run id.
        """

        handle = self._live.get(run_id)
        if handle is not None:
            handle.cancel_event.set()
