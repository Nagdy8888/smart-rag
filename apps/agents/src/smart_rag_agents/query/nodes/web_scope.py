"""Bounded Web research node: Exa, crawl-proxy fallback, persist, synthesize."""

from __future__ import annotations

import asyncio
import contextvars
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, cast

from langgraph.config import get_stream_writer
from smart_rag_core.gateways.crawl_proxy import CrawlProxyGateway
from smart_rag_core.gateways.exa_search import (
    ExaContentsResponse,
    ExaSearchGateway,
    ExaSearchResponse,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.preparation import caller_from_runtime
from smart_rag_core.web_research.bound_store import BoundWebStore
from smart_rag_core.web_research.exceptions import WebResearchError
from smart_rag_core.web_research.executor import run_web_research
from smart_rag_core.web_research.fetch import CrawlProxyCandidateFetch
from smart_rag_core.web_research.models import WebSourceRecord
from smart_rag_core.web_research.planner import propose_follow_ups

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.web_answer import synthesize_web_answer
from smart_rag_agents.query.nodes.shared import runtime_from_state, skip_closed_nodes
from smart_rag_agents.query.state import QueryGraphState

LOGGER = logging.getLogger(__name__)


def _await_exa(
    factory: Callable[[], object], *, cancel_check: Callable[[], bool] | None
) -> object:
    """Run one Exa coroutine without rewriting typed ``ExaSearchError``.

    Args:
        factory: Zero-arg callable returning an awaitable.
        cancel_check: Cooperative cancellation probe.

    Returns:
        Gateway result.

    Raises:
        BaseException: Original gateway errors, including ``ExaSearchError``.
        WebResearchError: Cancellation.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        produced = factory()
        if asyncio.iscoroutine(produced):
            return asyncio.run(produced)
        return produced
    if cancel_check is not None and cancel_check():
        raise WebResearchError("cancelled")
    box: dict[str, object] = {}
    errors: dict[str, BaseException] = {}
    copied = contextvars.copy_context()

    def _worker() -> None:
        """Complete the awaitable on a dedicated loop."""

        def _inner() -> None:
            """Run the factory on this copied context."""

            try:
                produced = factory()
                if asyncio.iscoroutine(produced):
                    box["value"] = asyncio.run(produced)
                else:
                    box["value"] = produced
            except BaseException as exc:
                errors["exc"] = exc

        copied.run(_inner)

    thread = threading.Thread(target=_worker, name="exa-gateway-loop", daemon=True)
    thread.start()
    deadline = time.monotonic() + 50.0
    while thread.is_alive():
        if cancel_check is not None and cancel_check():
            raise WebResearchError("cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WebResearchError("web_search_timeout")
        thread.join(timeout=min(0.05, remaining))
    if "exc" in errors:
        raise errors["exc"]
    return box.get("value")


class _SyncExaPort:
    """Sync facade over an injected async Exa gateway."""

    def __init__(
        self,
        gateway: ExaSearchGateway,
        *,
        cancel_check: Callable[[], bool] | None,
    ) -> None:
        """Bind the gateway.

        Args:
            gateway: Process-injected Exa client.
            cancel_check: Per-run cancellation probe.
        """

        self._gateway = gateway
        self._cancel = cancel_check

    def search(
        self,
        *,
        query: str,
        remaining_deadline_seconds: float,
        num_results: int,
    ) -> ExaSearchResponse:
        """Search through the injected gateway."""

        result = _await_exa(
            lambda: self._gateway.search(
                query=query,
                remaining_deadline_seconds=remaining_deadline_seconds,
                num_results=num_results,
            ),
            cancel_check=self._cancel,
        )
        return result  # type: ignore[return-value]

    def get_contents(
        self,
        *,
        urls: tuple[str, ...],
        allowed_urls: frozenset[str],
        remaining_deadline_seconds: float,
    ) -> ExaContentsResponse:
        """Fetch contents through the injected gateway."""

        result = _await_exa(
            lambda: self._gateway.get_contents(
                urls=urls,
                allowed_urls=allowed_urls,
                remaining_deadline_seconds=remaining_deadline_seconds,
            ),
            cancel_check=self._cancel,
        )
        return result  # type: ignore[return-value]

    def aclose(self) -> None:
        """Close the HTTP client without logging the key."""

        _await_exa(lambda: self._gateway.aclose(), cancel_check=None)


def _emit_progress(stage: str) -> None:
    """Emit a key-only ``node_start`` stage. Never includes query or bodies."""

    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer({"kind": "node_start", "stage": stage})


def _deadline_seconds(state: QueryGraphState) -> float:
    """Return remaining seconds from the admitted deadline."""

    raw = state.get("deadline_at")
    if not isinstance(raw, str) or not raw:
        return 40.0
    try:
        deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 40.0
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    return max(0.1, (deadline - datetime.now(UTC)).total_seconds())


def forbidden_web_memory_snippets(state: QueryGraphState) -> tuple[str, ...]:
    """Return prior conversation strings that must never reach Exa.

    Admission persists the current user turn before ``load_memory``. That
    record must not be treated as a company passage or ``sanitize_exa_query``
    refuses the Ask text and never calls Exa.

    Args:
        state: Planned Web-research state.

    Returns:
        Prior memory bodies of at least 24 characters, excluding the
        current ``user_query`` and rewrite.
    """

    current_query = str(state.get("user_query") or "").strip()
    rewrite = _exa_query(state)
    skip = {item for item in (current_query, rewrite) if len(item) >= 24}
    snippets: list[str] = []
    for record in state.get("memory_records") or []:
        content = record.get("content")
        if isinstance(content, str) and len(content.strip()) >= 24:
            stripped = content.strip()
            if stripped in skip:
                continue
            snippets.append(stripped)
    return tuple(snippets)


def _exa_query(state: QueryGraphState) -> str:
    """Return rewritten user text only. Never memory or company passages.

    Args:
        state: Planned Web-research state.

    Returns:
        Preparation rewrite when present, otherwise ``user_query``.
    """

    raw = state.get("preparation")
    if isinstance(raw, dict):
        rewrite = raw.get("rewrite")
        if isinstance(rewrite, str) and rewrite.strip():
            return rewrite.strip()
    return str(state.get("user_query") or "")


def _fail_closed(
    state: QueryGraphState,
    *,
    status: Literal["routing_rejected", "insufficient_evidence"],
    detail: str,
) -> QueryGraphState:
    """Return a typed Web fail-closed node update.

    Args:
        state: Current graph state.
        status: Terminal graph status.
        detail: Published ``web_*`` / ``web_search_*`` reason. Never a
            query, URL, or key.

    Returns:
        State with no answer draft.
    """

    LOGGER.info(
        "web research failed closed status=%s detail=%s",
        status[:64],
        detail[:64],
        extra={"event": "query.web_scope.failed"},
    )
    return cast(
        QueryGraphState,
        {**state, "status": status, "detail": detail, "answer": None},
    )


def web_scope_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Run bounded Web research or fail closed. Never retrieves company evidence.

    State inputs:
        Planned ``web_research`` retrieval plan and rewritten ``user_query``.
        Conversation memory is treated as forbidden snippet text.

    State outputs:
        Web-origin answer draft, persisted ``web_sources``, or a typed
        fail-closed status. Company citation lists stay empty.

    Persistence writes:
        Web operations and ``web_sources`` through P06-39 RPCs when a
        connection is bound. Citations wait for ``verify_answer``.

    External/model calls:
        Injected Exa search/contents, optional crawl-proxy fallback, one
        deterministic critique, and one ``web_answer_v1`` synthesis when a
        model gateway and prompt are bound (extractive mock otherwise).
        Never constructed inside this node.

    Budget/deadline behavior:
        At most two rounds, five external ops, 50s remaining deadline.

    Failure/fallback route:
        Typed ``web_search_*`` / ``web_runtime_unavailable`` /
        ``web_evidence_insufficient`` / ``web_content_unavailable``.
        Never Hybrid, general, or company retrieve. Does not emit
        ``token_delta``.

    Args:
        state: State after ``compile_plan``.
        deps: Injected Exa, crawl-proxy, flags, and ``app_api`` connection.

    Returns:
        Answered state for verification, or a fail-closed terminal.
    """

    if skip_closed_nodes(state):
        return state
    context = runtime_from_state(state)
    LOGGER.info(
        "web research node entered enabled=%s configured=%s gateway=%s conn=%s ctx=%s",
        int(bool(deps.web_search_enabled)),
        int(bool(deps.web_search_configured)),
        int(isinstance(deps.exa_search_gateway, ExaSearchGateway)),
        int(deps.connection is not None),
        int(context is not None),
        extra={"event": "query.web_scope.entered"},
    )
    if not deps.web_search_enabled:
        return _fail_closed(
            state, status="routing_rejected", detail="web_search_disabled"
        )
    gateway = deps.exa_search_gateway
    if not deps.web_search_configured or not isinstance(gateway, ExaSearchGateway):
        return _fail_closed(
            state, status="routing_rejected", detail="web_search_unconfigured"
        )
    if deps.connection is None or context is None:
        return _fail_closed(
            state, status="routing_rejected", detail="web_runtime_unavailable"
        )
    fetch = None
    if isinstance(deps.crawl_proxy_gateway, CrawlProxyGateway):
        fetch = CrawlProxyCandidateFetch(deps.crawl_proxy_gateway)
    port = _SyncExaPort(gateway, cancel_check=deps.cancel_check)
    store = BoundWebStore(
        deps.connection,
        caller=caller_from_runtime(context),
        run_id=context.run_id,
    )

    def _synthesize(query: str, sources: tuple[WebSourceRecord, ...]) -> AnswerPayload:
        """Build the Web draft via gateway or extractive fallback.

        Args:
            query: Sanitized user query.
            sources: Persisted Web sources.

        Returns:
            Grounded ``AnswerPayload``.
        """

        return synthesize_web_answer(
            deps, query=query, sources=sources, context=context
        )

    synthesize = None
    if deps.model_gateway is not None and deps.web_answer_prompt_text:
        synthesize = _synthesize
    try:
        result = run_web_research(
            user_query=_exa_query(state),
            search=port,
            store=store,
            fetch=fetch,
            remaining_deadline_seconds=lambda: _deadline_seconds(state),
            cancel_check=deps.cancel_check,
            progress=_emit_progress,
            forbidden_snippets=forbidden_web_memory_snippets(state),
            critique=propose_follow_ups,
            synthesize=synthesize,
        )
    except WebResearchError as exc:
        port.aclose()
        status: Literal["insufficient_evidence", "routing_rejected"] = (
            "insufficient_evidence"
        )
        if exc.reason.startswith("web_search_") or exc.reason in {
            "web_operation:ambiguous",
            "web_operation:conflict",
            "company_passage_forbidden",
            "cancelled",
        }:
            status = "routing_rejected"
        if exc.reason == "web_content_unavailable":
            status = "insufficient_evidence"
        return _fail_closed(state, status=status, detail=exc.reason)
    except QueryAdmissionError as exc:
        port.aclose()
        reason = str(getattr(exc, "reason", "") or "web_operation:conflict")[:64]
        return _fail_closed(state, status="routing_rejected", detail=reason)
    except Exception as exc:
        port.aclose()
        LOGGER.info(
            "web research unexpected failure",
            extra={
                "event": "query.web_scope.failed",
                "status": "routing_rejected",
                "detail": type(exc).__name__[:64],
            },
        )
        return _fail_closed(
            state, status="routing_rejected", detail="web_search_transport_failed"
        )
    port.aclose()
    answer = result.answer
    if answer.answer_origin is not KnowledgeScope.WEB:
        answer = answer.model_copy(update={"answer_origin": KnowledgeScope.WEB})
    return cast(
        QueryGraphState,
        {
            **state,
            "status": "answered",
            "detail": "web_research_draft",
            "answer": answer.model_dump(mode="json"),
            "web_sources": [item.model_dump(mode="json") for item in result.sources],
            "answer_call_count": 1,
            "fusion": None,
            "table_composition": None,
        },
    )
