"""Shared SSE executor doubles and authorized-runtime builders."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from smart_rag_agents.query.graph import compile_query_graph as _compile_query_graph
from smart_rag_api.services.sse_stream import (
    LangGraphQueryRunExecutor,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import CallerContext, UserRole


def _caller() -> CallerContext:
    """Return a member caller with a stable UUID.

    Returns:
        Caller snapshot.
    """

    return CallerContext(
        user_id="00000000-0000-4000-8000-000000000011",
        role=UserRole.MEMBER,
        authorization_version=1,
    )


def _runtime(*, run_id: UUID | None = None) -> AuthorizedRuntimeContext:
    """Build a future-deadline authorized runtime.

    Args:
        run_id: Optional run id.

    Returns:
        Frozen runtime.
    """

    now = datetime.now(tz=UTC)
    return AuthorizedRuntimeContext(
        user_id=UUID("00000000-0000-4000-8000-000000000011"),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=run_id or uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=Phase6RouteFamily.COMPOSITE,
        deadline_at=now + timedelta(seconds=60),
        recursion_limit=8,
        correction_ceiling=1,
        subquestion_ceiling=0,
        model_call_ceiling=8,
        tool_ceiling=3,
        discovery_ceiling=0,
        manifest_ceiling=2,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("0.50"),
        remaining_usd=Decimal("0.50"),
        remaining_prompt_tokens=8000,
        remaining_completion_tokens=2000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="c" * 64,
        status="pending",
    )


class _FakeCompiled:
    """Compiled-graph stand-in that yields node-keyed updates."""

    def __init__(self, chunks: tuple[dict[str, object], ...]) -> None:
        """Store envelopes.

        Args:
            chunks: Node-keyed update mappings.
        """

        self._chunks = chunks

    async def astream(self, *args: object, **kwargs: object) -> Any:
        """Yield stored updates.

        Args:
            *args: Ignored graph input.
            **kwargs: Ignored stream options.

        Yields:
            Node-keyed envelopes.
        """

        del args, kwargs
        for chunk in self._chunks:
            yield chunk


class _RecordingAsyncStream:
    """Typed async stream that records consume and aclose counts."""

    def __init__(self, chunks: tuple[object, ...]) -> None:
        """Store ordered chunks.

        Args:
            chunks: Values yielded by ``__anext__``.
        """

        self._chunks = chunks
        self._index = 0
        self.consumed = 0
        self.aclose_count = 0

    def __aiter__(self) -> _RecordingAsyncStream:
        """Return this iterator.

        Returns:
            This stream.
        """

        return self

    async def __anext__(self) -> object:
        """Yield the next stored chunk.

        Returns:
            The next chunk.

        Raises:
            StopAsyncIteration: When every chunk has been consumed.
        """

        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        item = self._chunks[self._index]
        self._index += 1
        self.consumed += 1
        return item

    async def aclose(self) -> None:
        """Record one explicit close of an unfinished stream."""

        self.aclose_count += 1


class _RecordingCompiled:
    """Compiled-graph stand-in that returns a recording stream."""

    def __init__(self, stream: _RecordingAsyncStream) -> None:
        """Bind one stream.

        Args:
            stream: Iterator returned by ``astream``.
        """

        self._stream = stream

    def astream(self, *args: object, **kwargs: object) -> _RecordingAsyncStream:
        """Return the recording stream without wrapping it.

        Args:
            *args: Ignored graph input.
            **kwargs: Ignored stream options.

        Returns:
            The bound recording stream.
        """

        del args, kwargs
        return self._stream


def _verified_chunk(text: str) -> dict[str, object]:
    """Build a verify-node update that becomes a completed terminal.

    Args:
        text: Verified answer text.

    Returns:
        Node-keyed update mapping.
    """

    return {
        "verify_answer": {
            "status": "verified",
            "answer": AnswerPayload(answer_text=text, status="complete").model_dump(
                mode="json"
            ),
        }
    }


def _empty_verified_chunk() -> dict[str, object]:
    """Build a verify-node update that becomes an error terminal.

    Returns:
        Node-keyed update mapping.
    """

    return {
        "verify_answer": {
            "status": "verified",
            "answer": AnswerPayload(answer_text="  ", status="complete").model_dump(
                mode="json"
            ),
        }
    }


def _trailing_chunk() -> dict[str, object]:
    """Build a harmless trailing graph update.

    Returns:
        Node-keyed update mapping.
    """

    return {"persist": {"status": "answered"}}


def _patch_recording_executor(
    monkeypatch: Any,
    executor: LangGraphQueryRunExecutor,
    compiled: _RecordingCompiled,
) -> tuple[list[str], list[str]]:
    """Patch process bindings so execute uses a recording compiled graph.

    Args:
        monkeypatch: Pytest monkeypatch.
        executor: Production executor under test.
        compiled: Graph stand-in.

    Returns:
        Commit-call log and successful-settlement log.
    """

    commits: list[str] = []
    settlements: list[str] = []

    def _settings() -> SimpleNamespace:
        """Return fixture backend settings.

        Returns:
            Settings stand-in with tracing disabled.
        """

        return SimpleNamespace(
            langsmith_tracing=False,
            mock_model_mode=True,
            subprocessor_matrix_verified=True,
            allows_unsigned_local_live_providers=lambda: True,
            supabase_db_url=None,
        )

    def _permit_export(**kwargs: object) -> None:
        """Skip the LangSmith export gate.

        Args:
            **kwargs: Unused gate arguments.
        """

        del kwargs

    def _compile(*args: object, **kwargs: object) -> _RecordingCompiled:
        """Return the recording compiled graph.

        Args:
            *args: Ignored graph deps.
            **kwargs: Ignored compile options.

        Returns:
            Bound recording compiled graph.
        """

        del args, kwargs
        return compiled

    def _pending(**kwargs: object) -> dict[str, str]:
        """Return a compact pending state.

        Args:
            **kwargs: Ignored pending fields.

        Returns:
            Pending status mapping.
        """

        del kwargs
        return {"status": "pending"}

    def _open_connection(dsn: object) -> SimpleNamespace:
        """Return a connection that records commit and close.

        Args:
            dsn: Unused DSN.

        Returns:
            Connection stand-in.
        """

        del dsn
        return SimpleNamespace(
            commit=lambda: commits.append("commit"),
            close=lambda: commits.append("close"),
        )

    def _deps(**kwargs: object) -> object:
        """Return a dummy graph-deps object.

        Args:
            **kwargs: Unused builder arguments.

        Returns:
            Opaque deps stand-in.
        """

        del kwargs
        return object()

    def _bindings(settings: object) -> SimpleNamespace:
        """Return process bindings with a dummy DSN.

        Args:
            settings: Unused settings.

        Returns:
            Bindings stand-in.
        """

        del settings
        return SimpleNamespace(supabase_dsn="postgresql://x")

    def _store(settings: object) -> tuple[None, None]:
        """Return no memory-store binding.

        Args:
            settings: Unused settings.

        Returns:
            ``(None, None)`` store pair.
        """

        del settings
        return (None, None)

    def _summarize(*args: object, **kwargs: object) -> None:
        """Skip summary writes.

        Args:
            *args: Unused summarize arguments.
            **kwargs: Unused summarize options.
        """

        del args, kwargs

    def _persist(*args: object, **kwargs: object) -> None:
        """Record one successful assistant persist.

        Args:
            *args: Unused persist arguments.
            **kwargs: Unused persist options.
        """

        del args, kwargs
        settlements.append("persist")

    monkeypatch.setattr(
        "smart_rag_core.settings.load_backend_settings",
        _settings,
    )
    monkeypatch.setattr(
        "smart_rag_core.observability.governance_gate.assert_langsmith_export_permitted",
        _permit_export,
    )
    graph_mod = sys.modules[_compile_query_graph.__module__]
    monkeypatch.setattr(graph_mod, "compile_query_graph", _compile)
    monkeypatch.setattr(graph_mod, "pending_query_state", _pending)
    monkeypatch.setattr(
        "smart_rag_api.services.query_graph_runtime.open_run_app_api_connection",
        _open_connection,
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_graph_runtime.build_query_graph_deps",
        _deps,
    )
    monkeypatch.setattr(executor, "_process_bindings", _bindings)
    monkeypatch.setattr(executor, "_bind_memory_store", _store)
    monkeypatch.setattr(executor, "_maybe_summarize", _summarize)
    monkeypatch.setattr(executor, "_persist_assistant_answer", _persist)
    return commits, settlements
