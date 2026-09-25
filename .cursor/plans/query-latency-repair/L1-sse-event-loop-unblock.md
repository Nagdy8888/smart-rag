# L1 - Stop the SSE code from blocking the event loop

Read `00-rules-and-commands.md` first (especially **How to apply an edit**).

## Goal (why)

The API process runs one asyncio event loop. While any code on that loop
does a blocking database call (about 90 ms per network round trip to
Supabase), nothing else in the process can run: not the LangGraph graph,
not other users' streams, not heartbeats. Measured 2026-09-24:

- The SSE attach loop (`SseStreamService.iter_frames`) calls
  `self._store.list_after(...)` **directly on the loop** every 50 ms. Each
  call is a full database transaction (about 254 ms), so the loop is
  blocked about 80% of the time.
- Also on the loop: `assert_readable` (twice per attach), `_start_once`
  (schema append and `mark_running`), `_has_terminal` in the executor, the
  run connection's `connection.commit()` after every LangGraph chunk, the
  post-terminal summary/assistant persist, and opening the run connection
  (`open_run_app_api_connection`, about 0.6 s).

This packet moves every one of those calls to a worker thread with
`await asyncio.to_thread(...)` (still awaited, so the order of work does
not change) and makes the attach loop wake up as soon as this process
writes an event, instead of polling every 50 ms.

What does **not** change: the order of events, "persist before sending",
exactly one terminal event, heartbeat rules, reservation settlement, the
event store SQL. The event store itself is changed in L2, not here.

## Files this packet edits

| # | File |
| - | ---- |
| 1 | `apps/backend/src/smart_rag_api/services/sse/constants.py` |
| 2 | `apps/backend/src/smart_rag_api/services/sse/registry.py` |
| 3 | `apps/backend/src/smart_rag_api/services/sse/event_append.py` |
| 4 | `apps/backend/src/smart_rag_api/services/sse/replay_cancel.py` |
| 5 | `apps/backend/src/smart_rag_api/services/sse/run_orchestration.py` |
| 6 | `apps/backend/src/smart_rag_api/services/sse/service.py` |
| 7 | `apps/backend/src/smart_rag_api/services/sse/langgraph_stream_consume.py` |
| 8 | `apps/backend/src/smart_rag_api/services/sse/langgraph_execute.py` |
| 9 | `apps/backend/src/smart_rag_api/services/sse/langgraph_runtime.py` |
| 10 | `tests/unit/test_query_sse_lifecycle.py` (new tests only) |
| 11 | `docs/api/SSE.md`, `docs/evaluation/QUERY_LATENCY_REPAIR_EVIDENCE.md` |
| 12 | `tests/unit/test_query_graph_runtime.py` (one source-text assertion) |
| 13 | `apps/backend/src/smart_rag_api/services/sse/run_summary.py` (new) |
| 14 | `apps/backend/src/smart_rag_api/services/query_graph_runtime.py` |
| 15 | `tests/contract/test_stream_architecture_budgets.py` (one list entry) |
| 16 | `tests/unit/test_sse_run_summary.py` (new) |

Do not edit any other file. Before starting, run
`git status --short` and check none of these files already has changes.

## Edit 1 - `constants.py`

File: `apps/backend/src/smart_rag_api/services/sse/constants.py`

Find (exactly once):

```python
POLL_SECONDS = 0.05
"""Attach-loop poll interval in seconds while waiting for persisted events."""
```

Replace with:

```python
POLL_SECONDS = 0.05
"""Attach-loop poll interval in seconds when no live handle can wake it."""

ATTACH_IDLE_POLL_SECONDS = 0.5
"""Longest attach-loop wait for a run this process is executing.

Every append made by this process wakes the attach loop at once, so this
only bounds a missed wake-up."""
```

## Edit 2 - `registry.py` (`LiveQueryRun`)

File: `apps/backend/src/smart_rag_api/services/sse/registry.py`

Find (exactly once):

```python
class LiveQueryRun:
    """In-process handle for one run's executor and heartbeat."""

    def __init__(self) -> None:
        """Create an idle handle."""

        self.cancel_event = asyncio.Event()
        self.started = False
        self.terminal = False
        self.executor_task: asyncio.Task[None] | None = None
        self.heartbeat_task: asyncio.Task[None] | None = None
```

Replace with:

```python
class LiveQueryRun:
    """In-process handle for one run's executor, heartbeat, and wake-ups.

    ``append_generation`` counts events this process has persisted for the
    run. An attach loop reads it before a replay, then waits for it to
    change, so a new event is streamed without polling.
    """

    def __init__(self) -> None:
        """Create an idle handle."""

        self.cancel_event = asyncio.Event()
        self.started = False
        self.terminal = False
        self.executor_task: asyncio.Task[None] | None = None
        self.heartbeat_task: asyncio.Task[None] | None = None
        self.append_generation = 0
        self._append_event = asyncio.Event()

    def notify_appended(self) -> None:
        """Wake every attach loop that waits on this run.

        Must be called on the event-loop thread because ``asyncio.Event`` is
        not thread-safe. Code running in a worker thread must return to the
        loop first (``await asyncio.to_thread(...)`` does that).

        Side Effects:
            Increments ``append_generation`` and releases current waiters.
        """

        self.append_generation += 1
        released = self._append_event
        self._append_event = asyncio.Event()
        released.set()

    async def wait_appended(self, seen: int, timeout: float) -> int:
        """Wait until ``append_generation`` differs from ``seen``.

        Args:
            seen: Generation the caller read before its last replay.
            timeout: Longest wait in seconds.

        Returns:
            The current generation. Equal to ``seen`` after a timeout.
        """

        if self.append_generation != seen:
            return self.append_generation
        waiter = self._append_event
        try:
            await asyncio.wait_for(waiter.wait(), timeout=timeout)
        except TimeoutError:
            pass
        return self.append_generation
```

## Edit 3 - `event_append.py`

File: `apps/backend/src/smart_rag_api/services/sse/event_append.py`

3a. Find (exactly once):

```python
from smart_rag_core.sse.store import PersistedRunEvent, RunEventStore, sqlstate_of

LOGGER = logging.getLogger(__name__)
```

Replace with:

```python
from smart_rag_core.sse.store import PersistedRunEvent, RunEventStore, sqlstate_of

from smart_rag_api.services.sse.registry import QueryRunRegistry

LOGGER = logging.getLogger(__name__)
```

3b. Find (exactly once):

```python
    """Mixin: persist one catalog event and log sanitized append failures."""

    _store: RunEventStore
```

Replace with:

```python
    """Mixin: persist one catalog event and log sanitized append failures."""

    _store: RunEventStore
    _registry: QueryRunRegistry
```

3c. Find (exactly once):

```python
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
```

Replace with:

```python
        """Persist one event off the asyncio loop, then wake attach loops.

        Heartbeat and executor orchestration must use this helper so a
        synchronous run-row lock wait cannot freeze ``astream`` or SSE
        attach. Callers still await each append before the next event so
        sequence order and exactly-one terminal stay unchanged. After the
        write returns, attach loops waiting on this run are woken, also when
        the append was replaced by a sanitized ``error`` or skipped.

        Args:
            caller: Owner.
            run_id: Run id.
            event_type: Allow-listed type.
            payload: Candidate payload.

        Returns:
            Persisted row, or None when append is rejected after sanitizing.
        """

        persisted = await asyncio.to_thread(
            self._append, caller, run_id, event_type, payload
        )
        live = self._registry.get(run_id)
        if live is not None:
            live.notify_appended()
        return persisted
```

## Edit 4 - `replay_cancel.py` (`_replay`)

File: `apps/backend/src/smart_rag_api/services/sse/replay_cancel.py`

Find (exactly once):

```python
        """Yield framed events after ``after``.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive cursor.

        Yields:
            Frame text, new cursor, and whether the event is terminal.
        """

        for event in self._store.list_after(caller, run_id=run_id, after=after):
```

Replace with:

```python
        """Yield framed events after ``after``.

        The store read runs on a worker thread so a slow database round trip
        cannot block the event loop.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive cursor.

        Yields:
            Frame text, new cursor, and whether the event is terminal.
        """

        events = await asyncio.to_thread(
            self._store.list_after, caller, run_id=run_id, after=after
        )
        for event in events:
```

Do not change `_has_terminal`; it stays synchronous because `_append`
calls it inside a worker thread.

## Edit 5 - `run_orchestration.py`

File: `apps/backend/src/smart_rag_api/services/sse/run_orchestration.py`

5a. Replace the whole `_start_once` method.

Find (exactly once):

```python
    def _start_once(
        self,
        caller: CallerContext,
        record: QueryRunRecord,
        live: LiveQueryRun,
        context: AuthorizedRuntimeContext | None,
    ) -> None:
        """Start the executor at most once in this process.

        Durable heartbeats are owned only by ``_run_heartbeat``.

        Args:
            caller: Owner.
            record: Current run row.
            live: Process handle.
            context: Fresh admit context when the POST is still in-flight.
        """

        if live.started:
            return
        live.started = True
        self._ensure_schema(caller, record.run_id)
        try:
            self._store.mark_running(caller, run_id=record.run_id)
        except QueryAdmissionError:
            LOGGER.info(
                "query run not marked running",
                extra={
                    "event": "sse.mark_running_skipped",
                    "run_id": str(record.run_id),
                },
            )
        message = self._registry.take_input(record.run_id)
        runtime = context or self._registry.take_context(record.run_id)
        if (not message or runtime is None) and self._postgres_url:
            loaded = self._load_durable_start(caller, record.run_id)
            if loaded is not None:
                loaded_message, loaded_runtime = loaded
                if not message:
                    message = loaded_message
                if runtime is None:
                    runtime = loaded_runtime
        live.executor_task = asyncio.create_task(
            self._run_executor(caller, record, live, message, runtime)
        )
        live.heartbeat_task = asyncio.create_task(
            self._run_heartbeat(caller, record.run_id, live)
        )
```

Replace with:

```python
    async def _start_once(
        self,
        caller: CallerContext,
        record: QueryRunRecord,
        live: LiveQueryRun,
        context: AuthorizedRuntimeContext | None,
    ) -> None:
        """Start the executor at most once in this process.

        ``live.started`` is set before the first ``await`` so two attaches
        racing on the same run cannot both start it. Store and durable-input
        calls run on worker threads. When a cancel arrives during those
        calls, the executor is not started (the cancel request already
        persisted ``cancelled``). Durable heartbeats are owned only by
        ``_run_heartbeat``.

        Args:
            caller: Owner.
            record: Current run row.
            live: Process handle.
            context: Fresh admit context when the POST is still in-flight.
        """

        if live.started:
            return
        live.started = True
        await asyncio.to_thread(self._ensure_schema, caller, record.run_id)
        live.notify_appended()
        try:
            await asyncio.to_thread(
                self._store.mark_running, caller, run_id=record.run_id
            )
        except QueryAdmissionError:
            LOGGER.info(
                "query run not marked running",
                extra={
                    "event": "sse.mark_running_skipped",
                    "run_id": str(record.run_id),
                },
            )
        message = self._registry.take_input(record.run_id)
        runtime = context or self._registry.take_context(record.run_id)
        if (not message or runtime is None) and self._postgres_url:
            loaded = await asyncio.to_thread(
                self._load_durable_start, caller, record.run_id
            )
            if loaded is not None:
                loaded_message, loaded_runtime = loaded
                if not message:
                    message = loaded_message
                if runtime is None:
                    runtime = loaded_runtime
        if live.cancel_event.is_set():
            live.terminal = True
            live.notify_appended()
            return
        live.executor_task = asyncio.create_task(
            self._run_executor(caller, record, live, message, runtime)
        )
        live.heartbeat_task = asyncio.create_task(
            self._run_heartbeat(caller, record.run_id, live)
        )
```

5b. In `_run_executor`. Find (exactly once):

```python
        runtime = context or self._registry.take_context(record.run_id)
        if (runtime is None or not message) and self._postgres_url:
            loaded = self._load_durable_start(caller, record.run_id)
            if loaded is not None:
                loaded_message, loaded_runtime = loaded
                if not message:
                    message = loaded_message
                if runtime is None:
                    runtime = loaded_runtime
        if runtime is None:
            self._emit_worker_unavailable(caller, record.run_id)
            live.terminal = True
            self._cancel_tasks(live)
            return
```

Replace with:

```python
        runtime = context or self._registry.take_context(record.run_id)
        if (runtime is None or not message) and self._postgres_url:
            loaded = await asyncio.to_thread(
                self._load_durable_start, caller, record.run_id
            )
            if loaded is not None:
                loaded_message, loaded_runtime = loaded
                if not message:
                    message = loaded_message
                if runtime is None:
                    runtime = loaded_runtime
        if runtime is None:
            await asyncio.to_thread(
                self._emit_worker_unavailable, caller, record.run_id
            )
            live.terminal = True
            live.notify_appended()
            self._cancel_tasks(live)
            return
```

5c. There are three `_has_terminal` checks in `_run_executor`. Change
each one with the three edits 5c-1, 5c-2, and 5c-3 below. After them,
`self._has_terminal(caller, record.run_id)` must not appear anywhere in
the file.

5c-1 (end of `_consume`). Find (exactly once):

```python
                            completion_tokens = event_completion
                if not self._has_terminal(caller, record.run_id):
```

Replace with:

```python
                            completion_tokens = event_completion
                if not await asyncio.to_thread(
                    self._has_terminal, caller, record.run_id
                ):
```

5c-2 (`except asyncio.CancelledError:`). Find (exactly once):

```python
        except asyncio.CancelledError:
            if not self._has_terminal(caller, record.run_id):
```

Replace with:

```python
        except asyncio.CancelledError:
            if not await asyncio.to_thread(self._has_terminal, caller, record.run_id):
```

5c-3 (`except Exception as exc:`). Find (exactly once):

```python
            )
            if not self._has_terminal(caller, record.run_id):
```

Replace with:

```python
            )
            if not await asyncio.to_thread(self._has_terminal, caller, record.run_id):
```

5d. The end of `_run_executor`. Find (exactly once):

```python
        finally:
            live.terminal = True
            heartbeat = live.heartbeat_task
```

Replace with:

```python
        finally:
            live.terminal = True
            live.notify_appended()
            heartbeat = live.heartbeat_task
```

5e. In the `_run_executor` docstring. Find (exactly once):

```python
        Each catalog append is awaited on a worker thread so a run-row
        lock wait cannot freeze this event loop. Sequence order is the
        executor yield order.
```

Replace with:

```python
        Each catalog append, terminal lookup, and durable-input load is
        awaited on a worker thread so a database wait cannot freeze this
        event loop. Sequence order is the executor yield order. Attach
        loops are woken when the executor ends.
```

5f and 5g keep `run_orchestration.py` at 300 lines or fewer
(`tests/contract/test_stream_architecture_budgets.py`): the termination
summary block moves, unchanged in behavior, into `run_summary.py`
(Edit 13).

5f. The imports. Find (exactly once):

```python
from typing import TYPE_CHECKING, cast
```

Replace with:

```python
from typing import TYPE_CHECKING
```

5g. Find (exactly once):

```python
from smart_rag_api.services.sse.chunks import (
    coerce_stream_token_count,
    token_counts_from_update,
)
from smart_rag_api.services.sse.executors import QueryRunExecutor
from smart_rag_api.services.sse.registry import LiveQueryRun, QueryRunRegistry
from smart_rag_api.services.sse.run_heartbeat import RunHeartbeatMixin
```

Replace with:

```python
from smart_rag_api.services.sse.chunks import token_counts_from_update
from smart_rag_api.services.sse.executors import QueryRunExecutor
from smart_rag_api.services.sse.registry import LiveQueryRun, QueryRunRegistry
from smart_rag_api.services.sse.run_heartbeat import RunHeartbeatMixin
from smart_rag_api.services.sse.run_summary import build_termination_payload
```

5h. The end of `_consume`. Find (exactly once):

```python
                summary = getattr(self._executor, "termination_summary", None)
                payload: dict[str, object]
                if isinstance(summary, dict):
                    typed_summary = cast(dict[object, object], summary)
                    payload = {str(key): value for key, value in typed_summary.items()}
                else:
                    payload = {
                        "termination_reason": (
                            "cancelled" if live.cancel_event.is_set() else "unknown"
                        ),
                        "terminal_event_type": None,
                        "stream_exhausted": False,
                    }
                if assistant_parts:
                    payload["assistant_message"] = "".join(assistant_parts)
                if prompt_tokens is None:
                    prompt_tokens = coerce_stream_token_count(
                        payload.get("input_tokens")
                    )
                if prompt_tokens is None:
                    prompt_tokens = coerce_stream_token_count(
                        payload.get("prompt_tokens")
                    )
                if completion_tokens is None:
                    completion_tokens = coerce_stream_token_count(
                        payload.get("output_tokens")
                    )
                if completion_tokens is None:
                    completion_tokens = coerce_stream_token_count(
                        payload.get("completion_tokens")
                    )
                if prompt_tokens is not None:
                    payload["input_tokens"] = prompt_tokens
                if completion_tokens is not None:
                    payload["output_tokens"] = completion_tokens
                input_count = coerce_stream_token_count(payload.get("input_tokens"))
                output_count = coerce_stream_token_count(payload.get("output_tokens"))
                if input_count is not None or output_count is not None:
                    from smart_rag_core.observability.langsmith_tracing import (
                        estimate_traced_chat_cost_usd,
                    )

                    input_total = 0 if input_count is None else input_count
                    output_total = 0 if output_count is None else output_count
                    payload["input_tokens"] = input_total
                    payload["output_tokens"] = output_total
                    payload["total_tokens"] = input_total + output_total
                    payload["estimated_cost_usd"] = float(
                        estimate_traced_chat_cost_usd(
                            input_tokens=input_total,
                            output_tokens=output_total,
                        )
                    )
                return payload
```

Replace with:

```python
                return build_termination_payload(
                    getattr(self._executor, "termination_summary", None),
                    cancelled=live.cancel_event.is_set(),
                    assistant_parts=assistant_parts,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
```

## Edit 6 - `service.py`

File: `apps/backend/src/smart_rag_api/services/sse/service.py`

6a. Find (exactly once):

```python
from smart_rag_api.services.sse.constants import NON_STARTABLE_STATUSES, POLL_SECONDS
```

Replace with:

```python
from smart_rag_api.services.sse.constants import (
    ATTACH_IDLE_POLL_SECONDS,
    NON_STARTABLE_STATUSES,
    POLL_SECONDS,
)
```

6b. Replace the body of `iter_frames` (everything after its docstring).

Find (exactly once):

```python
        self.assert_readable(caller, run_id=run_id)
        cursor = after
        async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
            cursor = sequence
            yield frame
            if terminal:
                return

        record = self.assert_readable(caller, run_id=run_id)
        live = self._registry.get(run_id)
        if live is None and record.status in NON_STARTABLE_STATUSES:
            async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
                cursor = sequence
                yield frame
                if terminal:
                    return
            return

        if live is None and record.status == "pending":
            if context is None and not self._registry.has_input(run_id):
                loaded = self._load_durable_start(caller, run_id)
                if loaded is None:
                    self._emit_worker_unavailable(caller, run_id)
                    async for frame, sequence, terminal in self._replay(
                        caller, run_id, cursor
                    ):
                        cursor = sequence
                        yield frame
                        if terminal:
                            return
                    return
                message, runtime = loaded
                self._registry.remember_input(run_id, message, runtime)
                context = runtime
            live = self._registry.get_or_create(run_id)
            self._start_once(caller, record, live, context)

        if live is not None and not live.started and record.status == "pending":
            self._start_once(caller, record, live, context)

        while True:
            emitted = False
            async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
                cursor = sequence
                emitted = True
                yield frame
                if terminal:
                    self._registry.drop(run_id)
                    return
            handle = self._registry.get(run_id)
            if handle is None or handle.terminal:
                async for frame, sequence, terminal in self._replay(
                    caller, run_id, cursor
                ):
                    cursor = sequence
                    yield frame
                    if terminal:
                        self._registry.drop(run_id)
                        return
                if not emitted:
                    return
            await asyncio.sleep(POLL_SECONDS)
```

Replace with:

```python
        await asyncio.to_thread(self.assert_readable, caller, run_id=run_id)
        cursor = after
        async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
            cursor = sequence
            yield frame
            if terminal:
                return

        record = await asyncio.to_thread(self.assert_readable, caller, run_id=run_id)
        live = self._registry.get(run_id)
        if live is None and record.status in NON_STARTABLE_STATUSES:
            async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
                cursor = sequence
                yield frame
                if terminal:
                    return
            return

        if live is None and record.status == "pending":
            if context is None and not self._registry.has_input(run_id):
                loaded = await asyncio.to_thread(
                    self._load_durable_start, caller, run_id
                )
                if loaded is None:
                    await asyncio.to_thread(
                        self._emit_worker_unavailable, caller, run_id
                    )
                    async for frame, sequence, terminal in self._replay(
                        caller, run_id, cursor
                    ):
                        cursor = sequence
                        yield frame
                        if terminal:
                            return
                    return
                message, runtime = loaded
                self._registry.remember_input(run_id, message, runtime)
                context = runtime
            live = self._registry.get_or_create(run_id)
            await self._start_once(caller, record, live, context)

        if live is not None and not live.started and record.status == "pending":
            await self._start_once(caller, record, live, context)

        while True:
            handle = self._registry.get(run_id)
            seen = handle.append_generation if handle is not None else 0
            emitted = False
            async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
                cursor = sequence
                emitted = True
                yield frame
                if terminal:
                    self._registry.drop(run_id)
                    return
            handle = self._registry.get(run_id)
            if handle is None or handle.terminal:
                async for frame, sequence, terminal in self._replay(
                    caller, run_id, cursor
                ):
                    cursor = sequence
                    yield frame
                    if terminal:
                        self._registry.drop(run_id)
                        return
                if not emitted:
                    return
                await asyncio.sleep(POLL_SECONDS)
                continue
            await handle.wait_appended(seen, ATTACH_IDLE_POLL_SECONDS)
```

`seen` is read **before** the replay on purpose: an event written while
the replay runs changes the generation, so the next wait returns at once.

6c. In the `iter_frames` docstring.

Find (exactly once):

```python
            SSE frames. Persistence happens before each yield.
```

Replace with:

```python
            SSE frames. Persistence happens before each yield. Store reads
            run on worker threads; a live run wakes this loop on each append.
```

## Edit 7 - `langgraph_stream_consume.py`

File: `apps/backend/src/smart_rag_api/services/sse/langgraph_stream_consume.py`

7a. Find (exactly once):

```python
from collections.abc import AsyncIterator
from dataclasses import dataclass
```

Replace with:

```python
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
```

7b. In `iter_mapped_langgraph_updates`. Find (exactly once):

```python
    async for raw_chunk in stream_iter:
        connection.commit()
```

Replace with:

```python
    async for raw_chunk in stream_iter:
        await asyncio.to_thread(connection.commit)
```

7c. The file has two `commit_successful_terminal(` calls with different
indentation. Change both with 7c-1 and 7c-2.

7c-1. Find (exactly once):

```python
                    successful_terminal_committed = True
                    commit_successful_terminal(
                        context,
                        mapper,
                        settings,
                        remaining_model_calls=last_remaining_calls,
                        terminal_status=last_status,
                    )
```

Replace with:

```python
                    successful_terminal_committed = True
                    await asyncio.to_thread(
                        commit_successful_terminal,
                        context,
                        mapper,
                        settings,
                        remaining_model_calls=last_remaining_calls,
                        terminal_status=last_status,
                    )
```

7c-2. Find (exactly once):

```python
                successful_terminal_committed = True
                commit_successful_terminal(
                    context,
                    mapper,
                    settings,
                    remaining_model_calls=last_remaining_calls,
                    terminal_status=last_status,
                )
```

Replace with:

```python
                successful_terminal_committed = True
                await asyncio.to_thread(
                    commit_successful_terminal,
                    context,
                    mapper,
                    settings,
                    remaining_model_calls=last_remaining_calls,
                    terminal_status=last_status,
                )
```

7d. Find (exactly once):

```python
    if stream_exhausted and not cancel_event.is_set():
        connection.commit()
```

Replace with:

```python
    if stream_exhausted and not cancel_event.is_set():
        await asyncio.to_thread(connection.commit)
```

7e. In the docstring. Find (exactly once):

```python
    Side Effects:
        Commits the run-scoped ``app_api`` connection before mapping each
        stream part and once more after natural exhaustion so the final
        graph node (``verify_answer``) can persist citations and counted
        usage before the executor closes the connection.
```

Replace with:

```python
    Side Effects:
        Commits the run-scoped ``app_api`` connection before mapping each
        stream part and once more after natural exhaustion so the final
        graph node (``verify_answer``) can persist citations and counted
        usage before the executor closes the connection. Commits and the
        post-terminal persist run on a worker thread and are awaited in
        order, so they never block the event loop.
```

## Edit 8 - `langgraph_execute.py`

File: `apps/backend/src/smart_rag_api/services/sse/langgraph_execute.py`

Find (exactly once):

```python
            if mapper is not None and mapper.verified_text:
                self._persist_assistant_answer(context, mapper, settings)
            raise
```

Replace with:

```python
            if mapper is not None and mapper.verified_text:
                await asyncio.to_thread(
                    self._persist_assistant_answer, context, mapper, settings
                )
            raise
```

## Edit 9 - `langgraph_runtime.py` (`open_langgraph_astream`)

File: `apps/backend/src/smart_rag_api/services/sse/langgraph_runtime.py`

This file must stay at 300 lines or fewer
(`tests/contract/test_stream_architecture_budgets.py`). It is exactly 300
lines before this packet, so Edit 9 keeps the line count unchanged: the
thread offload lives in `open_run_app_api_connection_async` (Edit 14).

9a. Find (exactly once):

```python
    from smart_rag_api.services.query_graph_runtime import (
        build_query_graph_deps,
        open_run_app_api_connection,
    )
    from smart_rag_api.services.sse.stream_dispatch import production_astream_options

    bindings = process_bindings(settings)
    connection = open_run_app_api_connection(bindings.supabase_dsn)
```

Replace with:

```python
    from smart_rag_api.services.query_graph_runtime import (
        build_query_graph_deps,
        open_run_app_api_connection_async,
    )
    from smart_rag_api.services.sse.stream_dispatch import production_astream_options

    bindings = process_bindings(settings)
    connection = await open_run_app_api_connection_async(bindings.supabase_dsn)
```

9b. In its docstring.

Find (exactly once):

```python
        ``app_api`` connection. The executor owns ``astream`` ``aclose``.
```

Replace with:

```python
        ``app_api`` connection on a worker thread; executor owns ``astream`` ``aclose``.
```

## Edit 10 - tests (`tests/unit/test_query_sse_lifecycle.py`)

File: `tests/unit/test_query_sse_lifecycle.py`

10a. The import block. Find (exactly once):

```python
import asyncio
import inspect
import logging
import threading
import time
from typing import Any
```

Replace with:

```python
import asyncio
import inspect
import logging
import threading
import time
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
```

10b. Append to the end of the file:

```python
def test_live_run_wait_appended_timeout_and_notify() -> None:
    """``wait_appended`` returns on timeout, on notify, and when already newer."""

    from smart_rag_api.services.sse.registry import LiveQueryRun

    async def _run() -> tuple[int, int, float, int]:
        """Wait with no notify, then with a notify, then with a stale seen.

        Returns:
            Generation after timeout, after notify, seconds waited for the
            notify, and generation for an already-newer ``seen``.
        """

        live = LiveQueryRun()
        timed_out = await live.wait_appended(0, 0.05)
        loop = asyncio.get_running_loop()
        loop.call_later(0.05, live.notify_appended)
        started = time.monotonic()
        notified = await live.wait_appended(0, 2.0)
        waited = time.monotonic() - started
        immediate = await live.wait_appended(0, 5.0)
        return timed_out, notified, waited, immediate

    timed_out, notified, waited, immediate = asyncio.run(_run())
    assert timed_out == 0
    assert notified == 1
    assert waited < 1.0
    assert immediate == 1


class _SlowListStore(MemoryRunEventStore):
    """Memory store whose replay read blocks the calling thread."""

    def __init__(self, hold_seconds: float) -> None:
        """Configure the blocking read.

        Args:
            hold_seconds: Sleep per ``list_after`` call.
        """

        super().__init__()
        self.hold_seconds = hold_seconds

    def list_after(self, caller: Any, *, run_id: Any, after: int) -> Any:
        """Block this thread, then read.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive cursor.

        Returns:
            Events from the memory store.
        """

        time.sleep(self.hold_seconds)
        return super().list_after(caller, run_id=run_id, after=after)


def test_replay_list_after_runs_off_event_loop() -> None:
    """A slow replay read cannot freeze the asyncio loop."""

    store = _SlowListStore(0.2)
    service = SseStreamService(
        store=store,
        registry=QueryRunRegistry(),
        executor=FixtureQueryRunExecutor(),
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _probe() -> int:
        """Tick every 10 ms while one replay read blocks its thread.

        Returns:
            Ticks counted during the replay.
        """

        ticks = 0

        async def _ticker() -> None:
            """Count loop turns until cancelled."""

            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        ticker = asyncio.create_task(_ticker())
        async for _item in typed_attr(service, "_replay")(caller, runtime.run_id, 0):
            pass
        ticker.cancel()
        return ticks

    assert asyncio.run(_probe()) >= 8


class _SpacedExecutor:
    """Executor that yields status events with a fixed gap, then completes."""

    def __init__(self, count: int, gap_seconds: float) -> None:
        """Configure the spaced stream.

        Args:
            count: Status events before ``completed``.
            gap_seconds: Sleep before each status event.
        """

        self.count = count
        self.gap_seconds = gap_seconds
        self.start_count = 0

    async def execute(
        self,
        *,
        context: Any,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Yield spaced status events, then ``completed``.

        Args:
            context: Unused authorized context.
            message: Unused user text.
            cancel_event: Unused cancel flag.

        Yields:
            Catalog drafts.
        """

        del context, message, cancel_event
        self.start_count += 1
        for index in range(self.count):
            await asyncio.sleep(self.gap_seconds)
            yield ("status", {"stage": f"stage_{index}", "status": "running"})
        yield ("completed", {})


def test_attach_wakes_on_append_not_idle_poll(monkeypatch: Any) -> None:
    """Frames for a live run arrive on append, not after the idle poll."""

    monkeypatch.setattr(
        "smart_rag_api.services.sse.service.ATTACH_IDLE_POLL_SECONDS", 5.0
    )
    service = SseStreamService(
        store=MemoryRunEventStore(),
        registry=QueryRunRegistry(),
        executor=_SpacedExecutor(count=4, gap_seconds=0.05),
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _drain() -> tuple[list[str], float]:
        """Attach once and read every frame through the terminal.

        Returns:
            ``event:`` lines and elapsed seconds.
        """

        started = time.monotonic()
        lines: list[str] = []
        async for frame in service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        ):
            lines.extend(
                line for line in frame.splitlines() if line.startswith("event:")
            )
        return lines, time.monotonic() - started

    lines, elapsed = asyncio.run(_drain())
    assert lines[-1] == "event: completed"
    assert lines.count("event: status") == 4
    assert elapsed < 1.5


def test_start_once_is_single_under_concurrent_attach() -> None:
    """Two attaches racing on one pending run start one executor."""

    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor(hold_seconds=0.1, emit_completed=True)
    service = SseStreamService(
        store=store,
        registry=QueryRunRegistry(),
        executor=executor,
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _attach() -> list[str]:
        """Read one attach to its terminal.

        Returns:
            Frames from this attach.
        """

        return [
            frame
            async for frame in service.iter_frames(
                caller, run_id=runtime.run_id, after=0, context=runtime
            )
        ]

    async def _both() -> list[list[str]]:
        """Run two attaches at once.

        Returns:
            Frames from each attach.
        """

        return list(await asyncio.gather(_attach(), _attach()))

    first, second = asyncio.run(_both())
    schema_rows = [
        item
        for item in store.list_after(caller, run_id=runtime.run_id, after=0)
        if item.event_type == "schema"
    ]
    assert executor.start_count == 1
    assert len(schema_rows) == 1
    assert any("event: completed" in frame for frame in first)
    assert any("event: completed" in frame for frame in second)


def test_stream_commits_and_terminal_persist_run_off_event_loop(
    monkeypatch: Any,
) -> None:
    """Run-connection open, commits, and post-terminal persist use threads."""

    stream = RecordingAsyncStream((verified_chunk("THREAD"), trailing_chunk()))
    executor = LangGraphQueryRunExecutor()
    patch_recording_executor(monkeypatch, executor, RecordingCompiled(stream))
    loop_threads: list[int] = []
    open_threads: list[int] = []
    commit_threads: list[int] = []
    persist_threads: list[int] = []

    def _open_connection(dsn: object) -> Any:
        """Return a connection whose commit records its thread.

        Args:
            dsn: Unused DSN.

        Returns:
            Connection stand-in.
        """

        del dsn
        open_threads.append(threading.get_ident())

        def _commit() -> None:
            """Record the committing thread."""

            commit_threads.append(threading.get_ident())

        def _close() -> None:
            """Accept close."""

        return SimpleNamespace(commit=_commit, close=_close)

    def _persist(*args: object, **kwargs: object) -> None:
        """Record the persisting thread.

        Args:
            *args: Unused persist arguments.
            **kwargs: Unused persist options.
        """

        del args, kwargs
        persist_threads.append(threading.get_ident())

    monkeypatch.setattr(
        "smart_rag_api.services.query_graph_runtime.open_run_app_api_connection",
        _open_connection,
    )
    monkeypatch.setattr(executor, "_persist_assistant_answer", _persist)

    async def _drain() -> None:
        """Consume the patched executor and record the loop thread."""

        loop_threads.append(threading.get_ident())
        async for _event in executor.execute(
            context=make_runtime(),
            message="hello",
            cancel_event=asyncio.Event(),
        ):
            pass

    asyncio.run(_drain())
    assert open_threads
    assert commit_threads
    assert persist_threads
    assert loop_threads[0] not in open_threads
    assert loop_threads[0] not in commit_threads
    assert loop_threads[0] not in persist_threads
```

If `test_stream_commits_and_terminal_persist_run_off_event_loop` fails
with `persist_threads` empty, open `tests/support/query_sse.py` and check
that `verified_chunk` still produces a `completed` terminal; do not change
the assertions.

## Edit 11 - docs

File: `docs/api/SSE.md`

11a. Section "Persist offload and run-row locks": add one paragraph at
the end of the section.

Find (exactly once):

```markdown
This is the c31e50dc stall class. Disabling LangSmith tracing is not the
fix. Authenticated live timing after this repair is still unverified.
```

Replace with:

```markdown
This is the c31e50dc stall class. Disabling LangSmith tracing is not the
fix. Authenticated live timing after this repair is still unverified.

Since latency packet L1 (2026-09), every event-store read and write, the
run-row lookups (`assert_readable`, `mark_running`, terminal checks), the
run connection's per-chunk `commit()`, the run connection open, and the
post-terminal summary and assistant persist run on worker threads through
`asyncio.to_thread`, awaited in the same order as before. The attach loop
no longer polls every 50 ms for a run this process executes: each append
calls `LiveQueryRun.notify_appended()`, and the attach loop waits with
`wait_appended(seen, ATTACH_IDLE_POLL_SECONDS)` (0.5 s upper bound). Runs
without a live handle in this process keep the 50 ms `POLL_SECONDS` loop
and still return when a round emits nothing. The terminal frame can reach
the browser before the assistant `app.messages` row is written; the chat
UI keeps the live answer until the refetched transcript matches it.
```

11b. `docs/evaluation/QUERY_LATENCY_REPAIR_EVIDENCE.md`: fill the L1 row
of the "Per-packet timing log" table after the live proof below.

## Edit 12 - source-text guard for the run connection

File: `tests/unit/test_query_graph_runtime.py`

This test reads `langgraph_runtime.py` as text to prove the run
connection is always opened (no `connection = None` fallback). Edit 9a
changes the call to `open_run_app_api_connection_async(...)`, so the
searched text changes with it. Change only this one line.

Find (exactly once):

```python
    assert "open_run_app_api_connection(bindings.supabase_dsn)" in runtime_source
```

Replace with:

```python
    assert "open_run_app_api_connection_async(bindings.supabase_dsn)" in runtime_source
```

## Edit 13 - new file `run_summary.py`

File: `apps/backend/src/smart_rag_api/services/sse/run_summary.py`

Full contents:

```python
"""Termination summary payload for one finished SSE executor stream."""

from __future__ import annotations

from typing import cast

from smart_rag_api.services.sse.chunks import coerce_stream_token_count


def build_termination_payload(
    summary: object,
    *,
    cancelled: bool,
    assistant_parts: list[str],
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> dict[str, object]:
    """Build the executor's termination payload with token and cost totals.

    Token counts seen on ``usage`` events win. Missing counts fall back to
    the executor summary (``input_tokens`` then ``prompt_tokens``, and
    ``output_tokens`` then ``completion_tokens``). When any count is known,
    both totals, ``total_tokens``, and an estimated USD cost are set.

    Args:
        summary: The executor's ``termination_summary``. Anything that is not
            a dict is replaced by a minimal summary.
        cancelled: Whether the run's cancel event is set.
        assistant_parts: Streamed ``token_delta`` texts in order.
        prompt_tokens: Last prompt-token count from ``usage`` events.
        completion_tokens: Last completion-token count from ``usage`` events.

    Returns:
        A new payload dict. ``summary`` is not modified.
    """

    payload: dict[str, object]
    if isinstance(summary, dict):
        typed_summary = cast(dict[object, object], summary)
        payload = {str(key): value for key, value in typed_summary.items()}
    else:
        payload = {
            "termination_reason": "cancelled" if cancelled else "unknown",
            "terminal_event_type": None,
            "stream_exhausted": False,
        }
    if assistant_parts:
        payload["assistant_message"] = "".join(assistant_parts)
    if prompt_tokens is None:
        prompt_tokens = coerce_stream_token_count(payload.get("input_tokens"))
    if prompt_tokens is None:
        prompt_tokens = coerce_stream_token_count(payload.get("prompt_tokens"))
    if completion_tokens is None:
        completion_tokens = coerce_stream_token_count(payload.get("output_tokens"))
    if completion_tokens is None:
        completion_tokens = coerce_stream_token_count(payload.get("completion_tokens"))
    if prompt_tokens is not None:
        payload["input_tokens"] = prompt_tokens
    if completion_tokens is not None:
        payload["output_tokens"] = completion_tokens
    input_count = coerce_stream_token_count(payload.get("input_tokens"))
    output_count = coerce_stream_token_count(payload.get("output_tokens"))
    if input_count is not None or output_count is not None:
        from smart_rag_core.observability.langsmith_tracing import (
            estimate_traced_chat_cost_usd,
        )

        input_total = 0 if input_count is None else input_count
        output_total = 0 if output_count is None else output_count
        payload["input_tokens"] = input_total
        payload["output_tokens"] = output_total
        payload["total_tokens"] = input_total + output_total
        payload["estimated_cost_usd"] = float(
            estimate_traced_chat_cost_usd(
                input_tokens=input_total,
                output_tokens=output_total,
            )
        )
    return payload
```

## Edit 14 - `query_graph_runtime.py` (async connection open)

File: `apps/backend/src/smart_rag_api/services/query_graph_runtime.py`

14a. Find (exactly once):

```python
from __future__ import annotations

from collections.abc import Callable
```

Replace with:

```python
from __future__ import annotations

import asyncio
from collections.abc import Callable
```

14b. Find (exactly once):

```python
    "open_run_app_api_connection",
]
```

Replace with:

```python
    "open_run_app_api_connection",
    "open_run_app_api_connection_async",
]
```

14c. Append to the end of the file:

```python
async def open_run_app_api_connection_async(supabase_dsn: str) -> psycopg.Connection:
    """Open the run's ``app_api`` connection on a worker thread.

    The connect (TLS plus pooler handshake, about 0.5 s) must not block the
    SSE event loop. ``open_run_app_api_connection`` is looked up in this
    module at call time, so tests that patch it here still apply.

    Args:
        supabase_dsn: Canonical Postgres URL.

    Returns:
        Autocommit-off connection with ``SET ROLE app_api``. Caller must
        close it.

    Raises:
        QueryGraphRuntimeError: If the connection cannot be opened.
    """

    return await asyncio.to_thread(open_run_app_api_connection, supabase_dsn)
```

## Edit 15 - stream line budget list

File: `tests/contract/test_stream_architecture_budgets.py`

Find (exactly once):

```python
    "apps/backend/src/smart_rag_api/services/sse/replay_cancel.py",
)
```

Replace with:

```python
    "apps/backend/src/smart_rag_api/services/sse/replay_cancel.py",
    "apps/backend/src/smart_rag_api/services/sse/run_summary.py",
)
```

## Edit 16 - new file `tests/unit/test_sse_run_summary.py`

File: `tests/unit/test_sse_run_summary.py`

Full contents:

```python
"""Termination payload built after an SSE executor stream ends."""

from __future__ import annotations

from smart_rag_api.services.sse.run_summary import build_termination_payload


def test_non_dict_summary_becomes_minimal_payload() -> None:
    """A missing executor summary yields reason, terminal type, and no tokens."""

    payload = build_termination_payload(
        None,
        cancelled=True,
        assistant_parts=[],
        prompt_tokens=None,
        completion_tokens=None,
    )

    assert payload == {
        "termination_reason": "cancelled",
        "terminal_event_type": None,
        "stream_exhausted": False,
    }


def test_usage_counts_win_and_cost_is_estimated() -> None:
    """``usage`` counts override the summary and set totals and cost."""

    summary: dict[str, object] = {
        "termination_reason": "completed",
        "input_tokens": 1,
        "output_tokens": 2,
    }

    payload = build_termination_payload(
        summary,
        cancelled=False,
        assistant_parts=["Hello ", "world"],
        prompt_tokens=100,
        completion_tokens=40,
    )

    assert payload["assistant_message"] == "Hello world"
    assert payload["input_tokens"] == 100
    assert payload["output_tokens"] == 40
    assert payload["total_tokens"] == 140
    cost = payload["estimated_cost_usd"]
    assert isinstance(cost, float)
    assert cost >= 0.0
    assert summary["input_tokens"] == 1


def test_summary_counts_fill_missing_usage_counts() -> None:
    """Without ``usage`` counts, the summary's prompt/completion names count."""

    payload = build_termination_payload(
        {"prompt_tokens": 7, "completion_tokens": 3},
        cancelled=False,
        assistant_parts=[],
        prompt_tokens=None,
        completion_tokens=None,
    )

    assert payload["input_tokens"] == 7
    assert payload["output_tokens"] == 3
    assert payload["total_tokens"] == 10
```

## Commands (run all; each must exit 0)

```powershell
uv run python -m ruff format apps/backend/src/smart_rag_api/services/sse apps/backend/src/smart_rag_api/services/query_graph_runtime.py tests/unit/test_query_sse_lifecycle.py tests/unit/test_query_graph_runtime.py tests/unit/test_sse_run_summary.py tests/contract/test_stream_architecture_budgets.py
uv run python -m ruff check --select I --fix apps/backend/src/smart_rag_api/services/sse apps/backend/src/smart_rag_api/services/query_graph_runtime.py tests/unit/test_query_sse_lifecycle.py tests/unit/test_sse_run_summary.py
uv run python -m pytest tests/unit/test_query_graph_runtime.py tests/unit/test_query_sse_lifecycle.py tests/unit/test_query_sse_event_store.py tests/unit/test_sse_run_summary.py
uv run python -m pytest tests/contract/test_stream_architecture_budgets.py
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier format
uv run python scripts/check.py --tier docs
```

Expected (measured in a dry run on 2026-09-24 with L0 applied): the first
pytest line prints `43 passed`; the budget test prints `3 passed`; the
unit tier prints `1621 passed, 4 skipped`; types prints `0 errors`. A higher passed count is fine if the
repo gained tests; the word `failed` must not appear.

Proof that nothing blocking is left on the loop in these files:

```powershell
rg -n "self\._store\.(list_after|mark_running|get_authorized_run)\(|connection\.commit\(\)|open_run_app_api_connection\(" apps/backend/src/smart_rag_api/services/sse
```

Expected hits and why each is allowed (each runs only inside a worker
thread after this packet, or is an import):

| File | Hits | Function containing the hit |
| ---- | ---- | --------------------------- |
| `replay_cancel.py` | 1 | `_has_terminal` (called by `_append` and through `to_thread`) |
| `run_access.py` | 2 | `assert_readable`, `notify_cancel` (cancel route; unchanged) |
| `answer_persistence.py` | 2 | `_maybe_summarize`, `_persist_assistant_answer` |
| `run_settlement.py` | 4 | `_ensure_schema`, `_settle_reservation` (2), `_emit_worker_unavailable` |

Before L1 the same command prints 14 hits; after L1 it must print exactly
these 9. The hits that must be gone are in `replay_cancel.py` (`_replay`),
`run_orchestration.py`, `langgraph_stream_consume.py` (2), and
`langgraph_runtime.py`. If the count is not 9, or any other hit appears,
stop and report it. Paste the output in the report.

`notify_cancel` stays synchronous and does not call `notify_appended`
(it can run off the loop thread). After an explicit cancel, the attach
loop therefore sees `cancelled` within `ATTACH_IDLE_POLL_SECONDS` (0.5 s)
or sooner when the executor ends.

## Live proof

1. Before numbers: the `L0-b` report.
2. Rebuild the image and run the image probe (`00-rules-and-commands.md`).
   It must print `L0 present` and `L1 present`.
3. Timing run with tag `L1-after`, then
   `uv run python scripts/eval_latency_report.py compare .private-eval/runs/L0-b/latency.json .private-eval/runs/L1-after/latency.json`.
4. Expected: `wall_seconds` median and `pre_first_stage_s` median lower
   than `L0-b` by more than the noise band. `event_spacing_median_s` may
   drop only a little, because appends and replays still share one store
   session until L2. `deadline_exhausted` must not rise.
5. If `wall_seconds` median is **higher** than `L0-b` by more than the
   noise band, stop and report. Otherwise continue.

## Done when

- [ ] All 16 edits applied exactly; `git diff --stat` lists only the files
      in the table above.
- [ ] The `rg` proof shows no blocking store/commit call on the loop.
- [ ] The 5 new lifecycle tests and 3 run-summary tests pass; every other
      existing test passes, and the only changed existing assertion is the
      one in Edit 12.
- [ ] `tests/contract/test_stream_architecture_budgets.py` passes (every
      stream owner at 300 lines or fewer).
- [ ] Unit, lint, types, format, docs tiers pass.
- [ ] `L1-after` report exists, compare pasted, L1 evidence row filled.
- [ ] Committed and pushed; `gh pr checks --watch --fail-fast` exit 0.

## Commit

```text
perf(sse): keep store and run-connection calls off the event loop, wake attach on append (L1)
```

## Do not

- Do not stop awaiting appends in the executor (that is L3).
- Do not edit `packages/core/src/smart_rag_core/sse/store.py` (that is L2).
- Do not add a wait that holds the terminal frame until persistence ends.
- Do not remove `POLL_SECONDS`.
- Do not make `_has_terminal` or `_append` async.
