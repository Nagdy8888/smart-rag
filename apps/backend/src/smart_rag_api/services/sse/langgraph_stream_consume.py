"""Map LangGraph ``updates`` chunks into catalog SSE drafts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext

from smart_rag_api.services.sse.chunks import token_counts_from_update
from smart_rag_api.services.sse.stream_dispatch import dispatch_stream_part

if TYPE_CHECKING:
    from smart_rag_api.services.query_sse_mapping import QuerySseMapper


class StreamCancelEvent(Protocol):
    """Cooperative cancel flag observed while draining ``astream``."""

    def is_set(self) -> bool:
        """Return whether the owner cancelled the live run.

        Returns:
            True when consume must stop without a successful terminal.
        """

        ...


class StreamCommitConnection(Protocol):
    """Open ``app_api`` connection that can commit after each chunk."""

    def commit(self) -> object:
        """Commit the current transaction.

        Returns:
            Driver commit result. Ignored by the consume loop.
        """

        ...


class StreamTerminationSink(Protocol):
    """Callable that records the executor termination summary."""

    def __call__(
        self,
        *,
        reason: str,
        terminal_event_type: str | None = None,
        stream_exhausted: bool | None = None,
    ) -> None:
        """Store a sanitized stream-termination summary.

        Args:
            reason: ``completed``, ``partial``, ``cancelled``, or ``error``.
            terminal_event_type: First SSE terminal type, if any.
            stream_exhausted: Override for natural ``astream`` exhaustion.
        """

        ...


class StreamSuccessfulTerminalCommit(Protocol):
    """Callable that persists summary/assistant rows after completed/partial."""

    def __call__(
        self,
        context: AuthorizedRuntimeContext,
        mapper: QuerySseMapper,
        settings: object,
        *,
        remaining_model_calls: int,
        terminal_status: str,
    ) -> None:
        """Write post-terminal persistence for a successful run.

        Args:
            context: Authorized run context.
            mapper: Mapper that emitted the verified terminal.
            settings: Backend settings loaded once for this execute().
            remaining_model_calls: Remaining counted calls after the graph.
            terminal_status: Last node status.
        """

        ...


@dataclass
class MappedStreamResult:
    """Counters collected while draining one compiled ``astream``.

    Attributes:
        stream_exhausted: True when the iterator completed naturally.
        last_remaining_calls: Latest remaining model-call budget.
        last_status: Latest node status string.
        last_prompt_tokens: Latest prompt token total.
        last_completion_tokens: Latest completion token total.
        successful_terminal_committed: True after a completed/partial persist.
    """

    stream_exhausted: bool
    last_remaining_calls: int
    last_status: str
    last_prompt_tokens: int | None
    last_completion_tokens: int | None
    successful_terminal_committed: bool


def _update_counters(
    typed_update: dict[str, object],
    *,
    last_remaining_calls: int,
    last_status: str,
    last_prompt_tokens: int | None,
    last_completion_tokens: int | None,
) -> tuple[int, str, int | None, int | None]:
    """Refresh remaining-call, status, and token counters from one node.

    Args:
        typed_update: One node return mapping.
        last_remaining_calls: Current remaining-call budget.
        last_status: Current status string.
        last_prompt_tokens: Current prompt total.
        last_completion_tokens: Current completion total.

    Returns:
        Updated counter tuple.
    """

    remaining = typed_update.get("remaining_model_calls")
    if isinstance(remaining, int):
        last_remaining_calls = remaining
    raw_status = typed_update.get("status")
    if isinstance(raw_status, str) and raw_status:
        last_status = raw_status[:64]
    prompt_tokens, completion_tokens = token_counts_from_update(typed_update)
    if prompt_tokens is not None:
        last_prompt_tokens = prompt_tokens
    if completion_tokens is not None:
        last_completion_tokens = completion_tokens
    return (
        last_remaining_calls,
        last_status,
        last_prompt_tokens,
        last_completion_tokens,
    )


async def iter_mapped_langgraph_updates(
    *,
    stream_iter: AsyncIterator[object],
    mapper: QuerySseMapper,
    context: AuthorizedRuntimeContext,
    settings: object,
    cancel_event: StreamCancelEvent,
    connection: StreamCommitConnection,
    commit_successful_terminal: StreamSuccessfulTerminalCommit,
    set_termination: StreamTerminationSink,
    last_remaining_calls: int,
    last_status: str,
) -> AsyncIterator[tuple[str, dict[str, object]] | MappedStreamResult]:
    """Yield mapped drafts, then one ``MappedStreamResult``.

    Args:
        stream_iter: Compiled ``astream`` iterator.
        mapper: Per-run mapper that owns first-terminal-wins.
        context: Authorized run context.
        settings: Loaded backend settings.
        cancel_event: Cooperative cancel handle with ``is_set``.
        connection: Open ``app_api`` connection with ``commit``.
        commit_successful_terminal: Persist helper after completed/partial.
        set_termination: Termination-summary writer.
        last_remaining_calls: Initial remaining-call budget.
        last_status: Initial status string.

    Yields:
        Catalog ``(event_type, payload)`` drafts, then the consume result.

    Side Effects:
        Commits the run-scoped ``app_api`` connection before mapping each
        stream part and once more after natural exhaustion so the final
        graph node (``verify_answer``) can persist citations and counted
        usage before the executor closes the connection.
    """

    from smart_rag_api.services.query_sse_mapping import assert_catalog_event

    stream_exhausted = False
    successful_terminal_committed = False
    terminal_yielded = False
    last_prompt_tokens: int | None = None
    last_completion_tokens: int | None = None
    async for raw_chunk in stream_iter:
        connection.commit()
        if cancel_event.is_set():
            set_termination(
                reason="cancelled",
                terminal_event_type="cancelled",
                stream_exhausted=False,
            )
            break
        dispatched = dispatch_stream_part(raw_chunk, mapper)
        for typed_update in dispatched.node_updates:
            (
                last_remaining_calls,
                last_status,
                last_prompt_tokens,
                last_completion_tokens,
            ) = _update_counters(
                typed_update,
                last_remaining_calls=last_remaining_calls,
                last_status=last_status,
                last_prompt_tokens=last_prompt_tokens,
                last_completion_tokens=last_completion_tokens,
            )
        for event_type, payload in dispatched.drafts:
            assert_catalog_event(event_type, payload)
            if event_type == "usage":
                event_prompt, event_completion = token_counts_from_update(payload)
                if event_prompt is not None:
                    last_prompt_tokens = event_prompt
                if event_completion is not None:
                    last_completion_tokens = event_completion
            yield (event_type, payload)
            if event_type in {"completed", "partial", "error", "cancelled"}:
                if not terminal_yielded:
                    terminal_yielded = True
                    reason = (
                        "error"
                        if event_type == "error"
                        else ("cancelled" if event_type == "cancelled" else event_type)
                    )
                    set_termination(reason=reason, terminal_event_type=event_type)
                if (
                    event_type in {"completed", "partial"}
                    and not successful_terminal_committed
                ):
                    successful_terminal_committed = True
                    commit_successful_terminal(
                        context,
                        mapper,
                        settings,
                        remaining_model_calls=last_remaining_calls,
                        terminal_status=last_status,
                    )
    else:
        stream_exhausted = True
    if stream_exhausted and not cancel_event.is_set():
        for event_type, payload in mapper.finish():
            assert_catalog_event(event_type, payload)
            yield (event_type, payload)
            if event_type in {"completed", "partial", "error", "cancelled"}:
                set_termination(
                    reason=("error" if event_type == "error" else event_type),
                    terminal_event_type=event_type,
                    stream_exhausted=True,
                )
            if (
                event_type in {"completed", "partial"}
                and not successful_terminal_committed
            ):
                successful_terminal_committed = True
                commit_successful_terminal(
                    context,
                    mapper,
                    settings,
                    remaining_model_calls=last_remaining_calls,
                    terminal_status=last_status,
                )
    if stream_exhausted and not cancel_event.is_set():
        connection.commit()
    yield MappedStreamResult(
        stream_exhausted=stream_exhausted,
        last_remaining_calls=last_remaining_calls,
        last_status=last_status,
        last_prompt_tokens=last_prompt_tokens,
        last_completion_tokens=last_completion_tokens,
        successful_terminal_committed=successful_terminal_committed,
    )
