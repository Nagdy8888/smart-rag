"""Process and run-scoped Hybrid, graph, and table adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

import psycopg
from smart_rag_core.gateways.model import (
    ModelGatewayUnavailableError,
    QueryProfileModelRequest,
)
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_profile.versions import (
    PROFILE_PROMPT_SHA256,
    PROFILE_PROMPT_VERSION,
)
from smart_rag_core.query_routing.branches import (
    GraphRetrieveLike,
    TableExecuteLike,
)
from smart_rag_core.query_routing.models import (
    BranchSpec,
    MemoryRecord,
    PreparationModelPayload,
)
from smart_rag_core.query_routing.preparation import PrepModelCaller
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.settings.postgres_connect import connect_postgres
from smart_rag_core.tables.executor import TableSandboxError
from smart_rag_core.tables.refusals import TableQueryRefusal
from smart_rag_core.tables.resolver import PostgresTableResolver, TableResolveError
from smart_rag_core.tables.service import StructuredTableError, structured_table_query

from smart_rag_agents.query.runtime.adapters_hybrid import (
    DsnBm25Retriever,
    ProcessHybridRetriever,
    RunScopedHybrid,
    context_loader,
)

__all__ = [
    "DsnBm25Retriever",
    "ProcessHybridRetriever",
    "RunScopedGraph",
    "RunScopedHybrid",
    "bind_profile_model_caller",
    "bind_table_executor",
    "context_loader",
    "lightrag_budget_lock",
]


class _ProfileGatewayLike(Protocol):
    """Minimal async profile gateway used by the sync preparation thunk."""

    async def generate_query_profile(self, request: QueryProfileModelRequest) -> object:
        """Generate one structured profile payload.

        Args:
            request: Bounded profile request.

        Returns:
            Gateway response with a ``payload`` attribute.
        """


LIGHTRAG_BUDGET_LOCK: asyncio.Lock | None = None


def lightrag_budget_lock() -> asyncio.Lock:
    """Return the process lock that serializes Combined ``query_budget`` bind.

    Returns:
        Loop-safe lock created on first Combined retrieve.
    """

    global LIGHTRAG_BUDGET_LOCK
    if LIGHTRAG_BUDGET_LOCK is None:
        LIGHTRAG_BUDGET_LOCK = asyncio.Lock()  # pyright: ignore[reportConstantRedefinition]
    return LIGHTRAG_BUDGET_LOCK


class RunScopedGraph:
    """Per-run LightRAG facade so ``query_budget`` is not shared across SSE runs."""

    def __init__(self, adapter: GraphRetrieveLike) -> None:
        """Wrap one process graph adapter.

        Args:
            adapter: Lifespan LightRAG adapter.
        """

        self._adapter = adapter
        self.query_budget: object | None = None

    async def _forward(
        self,
        method_name: str,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Bind this run's ledger, then invoke one adapter retrieve.

        Args:
            method_name: ``retrieve_local``, ``retrieve_hybrid``, or
                ``retrieve_global_steering``.
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Structured leads. Never evidence.
        """

        method = getattr(self._adapter, method_name)
        async with lightrag_budget_lock():
            self._adapter.query_budget = self.query_budget  # type: ignore[assignment]
            return await method(
                query=query,
                hl_keywords=hl_keywords,
                ll_keywords=ll_keywords,
                bounds=bounds,
            )

    async def retrieve_local(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Forward local graph retrieve.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Structured leads. Never evidence.
        """

        return await self._forward(
            "retrieve_local",
            query=query,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            bounds=bounds,
        )

    async def retrieve_hybrid(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Forward graph-hybrid retrieve.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Structured leads.
        """

        return await self._forward(
            "retrieve_hybrid",
            query=query,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            bounds=bounds,
        )

    async def retrieve_global_steering(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Forward global steering retrieve.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Steering leads. Never evidence.
        """

        return await self._forward(
            "retrieve_global_steering",
            query=query,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            bounds=bounds,
        )


def bind_table_executor(postgres_url: str) -> TableExecuteLike:
    """Bind the existing structured-table engine with per-call ``app_api`` ACL.

    Args:
        postgres_url: Canonical Postgres URL.

    Returns:
        ``TableExecuteLike`` callable. Does not invent a second table engine.
    """

    def execute(spec: BranchSpec, caller: CallerContext) -> object:
        """Execute one table branch through ``structured_table_query``.

        Args:
            spec: Table branch spec with a declarative plan.
            caller: Server-derived caller.

        Returns:
            ``TableQueryResult``, or None when the plan is missing or ACL/sandbox
            refuses. Never a fabricated table success.
        """

        plan = spec.table_plan
        if plan is None:
            return None
        try:
            with connect_postgres(postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                resolver = PostgresTableResolver(connection, local_root=Path("."))
                return structured_table_query(plan, caller=caller, resolver=resolver)
        except (
            TableResolveError,
            StructuredTableError,
            TableQueryRefusal,
            TableSandboxError,
            psycopg.Error,
            OSError,
        ):
            return None

    return execute


class BoundProfileModelCaller:
    """Sync profile thunk that stashes provider tokens after each call.

    Attributes:
        last_prompt_tokens: Provider prompt tokens from the last call.
        last_completion_tokens: Provider completion tokens from the last
            call.
    """

    def __init__(
        self,
        *,
        gateway: object,
        prompt_text: str,
        model_id: str,
        cancel_check: Callable[[], bool] | None,
        remaining_deadline_seconds: float,
    ) -> None:
        """Bind gateway and prompt pins for one process-scoped caller.

        Args:
            gateway: ``ModelGateway`` with ``generate_query_profile``.
            prompt_text: Pinned profile prompt body.
            model_id: Allow-listed profile model id.
            cancel_check: Cooperative cancellation probe.
            remaining_deadline_seconds: Client timeout bound.
        """

        self._gateway = gateway
        self._prompt_text = prompt_text
        self._model_id = model_id
        self._cancel_check = cancel_check
        self._remaining_deadline_seconds = remaining_deadline_seconds
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0

    def __call__(
        self, query: str, memory: tuple[MemoryRecord, ...]
    ) -> PreparationModelPayload:
        """Invoke one counted profile call and validate the payload.

        Args:
            query: Original user text.
            memory: Bounded untrusted memory records.

        Returns:
            Schema-valid preparation payload.

        Raises:
            ValueError: Malformed or extra-field payload.
            ModelGatewayUnavailableError: Timeout, cancel, or provider
                failure.
        """

        from smart_rag_agents.query.gateway.sync_bridge import run_coro

        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        profile_gateway = cast(_ProfileGatewayLike, self._gateway)
        recent_memory = "\n".join(item.delimited for item in memory)[:4000]
        request = QueryProfileModelRequest(
            query=query[:2000] or "query",
            prompt_text=self._prompt_text,
            prompt_version=PROFILE_PROMPT_VERSION,
            prompt_sha256=PROFILE_PROMPT_SHA256,
            model_id=self._model_id,
            remaining_deadline_seconds=self._remaining_deadline_seconds,
            recent_memory=recent_memory,
        )
        try:
            response = run_coro(
                lambda: profile_gateway.generate_query_profile(request),
                cancel_check=self._cancel_check,
                timeout_seconds=self._remaining_deadline_seconds,
            )
        except AnswerError as exc:
            raise ModelGatewayUnavailableError(
                str(exc) or "profile_unavailable"
            ) from exc
        prompt = getattr(response, "input_tokens", 0)
        completion = getattr(response, "output_tokens", 0)
        self.last_prompt_tokens = (
            prompt if isinstance(prompt, int) and not isinstance(prompt, bool) else 0
        )
        self.last_completion_tokens = (
            completion
            if isinstance(completion, int) and not isinstance(completion, bool)
            else 0
        )
        raw: object = getattr(response, "payload", None)
        if not isinstance(raw, dict):
            raise ValueError("profile_malformed")
        typed: dict[str, object] = {
            str(key): value for key, value in cast(dict[object, object], raw).items()
        }
        if "scope_degradation_reason" in typed:
            raise ValueError("profile_malformed")
        try:
            return PreparationModelPayload.model_validate(typed)
        except Exception as exc:
            raise ValueError("profile_malformed") from exc


def bind_profile_model_caller(
    *,
    gateway: object,
    prompt_text: str,
    model_id: str,
    cancel_check: Callable[[], bool] | None,
    remaining_deadline_seconds: float = 25.0,
) -> PrepModelCaller:
    """Bind the sync preparation thunk to the async profile gateway.

    Args:
        gateway: ``ModelGateway`` with ``generate_query_profile``.
        prompt_text: Pinned profile prompt body.
        model_id: Allow-listed profile model id recorded on usage.
        cancel_check: Cooperative cancellation probe.
        remaining_deadline_seconds: Client timeout bound.

    Returns:
        Sync ``PrepModelCaller``. Malformed payloads raise ``ValueError``.
        Provider/timeout failures raise ``ModelGatewayUnavailableError``.
        Successful calls stash ``last_prompt_tokens`` and
        ``last_completion_tokens`` on the returned callable.
    """

    return BoundProfileModelCaller(
        gateway=gateway,
        prompt_text=prompt_text,
        model_id=model_id,
        cancel_check=cancel_check,
        remaining_deadline_seconds=remaining_deadline_seconds,
    )
