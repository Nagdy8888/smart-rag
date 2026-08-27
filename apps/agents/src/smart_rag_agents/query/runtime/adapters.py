"""Process and run-scoped Hybrid, graph, and table adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

import psycopg
from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.gateways.embedding import EmbeddingGateway
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
from smart_rag_core.retrieval.bm25 import Bm25Retriever
from smart_rag_core.retrieval.context_loader import (
    ChunkContext,
    fetch_authorized_chunk_context,
)
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.tables.executor import TableSandboxError
from smart_rag_core.tables.refusals import TableQueryRefusal
from smart_rag_core.tables.resolver import PostgresTableResolver, TableResolveError
from smart_rag_core.tables.service import StructuredTableError, structured_table_query


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


class _DsnChannelMarker:
    """Truthy Hybrid channel flag. Per-channel jobs open their own DSN connections.

    Attributes:
        retrieve: Unused placeholder. ``HybridRetriever`` reconstructs dense
            and term adapters when ``supabase_dsn`` is set.
    """

    retrieve = None


class DsnBm25Retriever:
    """ParadeDB BM25 adapter that opens one connection per retrieve.

    Concurrent Hybrid channel threads must not share a ``psycopg`` connection.
    """

    def __init__(self, parade_dsn: str) -> None:
        """Store the unpublished ParadeDB URL.

        Args:
            parade_dsn: ``PARADEDB_URL`` secret value.
        """

        self._parade_dsn = parade_dsn

    def retrieve(
        self,
        *,
        supabase: psycopg.Connection,
        caller: CallerContext,
        query_text: str,
    ) -> object:
        """Scan BM25 IDs on a fresh ParadeDB connection.

        Args:
            supabase: Canonical connection used only for ACL recheck.
            caller: Server-derived caller.
            query_text: Raw query.

        Returns:
            ``Bm25RetrievalResult``. Hybrid catches connection failures and
            degrades to dense plus term.

        Side Effects:
            Opens and closes one ParadeDB connection.
        """

        with psycopg.connect(self._parade_dsn, connect_timeout=8) as parade:
            return Bm25Retriever(parade).retrieve(
                supabase=supabase,
                caller=caller,
                query_text=query_text,
            )


class ProcessHybridRetriever:
    """Hybrid retrieve that reuses the embedding gateway and opens per-call DB connections.

    ``HybridRetriever`` context loading captures the retrieve caller, so each
    ``retrieve`` builds an inner retriever. Dense/term/BM25-recheck threads
    still use ``supabase_dsn``.
    """

    def __init__(
        self,
        *,
        embedding_gateway: EmbeddingGateway,
        supabase_dsn: str,
        bm25: DsnBm25Retriever | None,
    ) -> None:
        """Bind the process embedding gateway and DSNs.

        Args:
            embedding_gateway: Shared ``EmbeddingGateway``.
            supabase_dsn: Full canonical Postgres URL including password.
            bm25: Optional per-retrieve ParadeDB adapter. ``None`` degrades
                BM25 (approved dense+term Hybrid).
        """

        self._embedding_gateway = embedding_gateway
        self._supabase_dsn = supabase_dsn
        self._bm25 = bm25
        self.query_budget: object | None = None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
        query_budget: object | None = None,
    ) -> object:
        """Run one Hybrid retrieve with per-channel connections.

        Args:
            query: Branch query text.
            caller: Server-derived caller.
            profile: Typed query profile when present.
            deadline_seconds: Remaining retrieval slice.
            query_budget: Optional per-run retrieve ledger. Copied onto the
                inner retriever so concurrent SSE runs do not share it.

        Returns:
            ``HybridRunResult`` with ranked IDs. BM25 snippets are never evidence.

        Side Effects:
            Embedding gateway call plus per-channel Postgres (and optional
            ParadeDB) connections.
        """

        typed_profile = profile if isinstance(profile, ExpectedProfile) else None
        inner = HybridRetriever(
            embedding_gateway=self._embedding_gateway,
            supabase=None,
            paradedb=None,
            supabase_dsn=self._supabase_dsn,
            dense=_DsnChannelMarker(),
            bm25=self._bm25,
            term=_DsnChannelMarker(),
            load_context=context_loader(self._supabase_dsn, caller),
        )
        budget = query_budget if query_budget is not None else self.query_budget
        inner.query_budget = budget  # type: ignore[assignment]
        return inner.retrieve(
            query=query,
            caller=caller,
            profile=typed_profile,
            deadline_seconds=deadline_seconds,
        )


@dataclass(slots=True)
class RunScopedHybrid:
    """Per-run Hybrid facade. ``query_budget`` must not live on the process adapter.

    Attributes:
        inner: Process DSN-based Hybrid.
        query_budget: Set by ``execute_branches`` for this compiled run only.
    """

    inner: ProcessHybridRetriever
    query_budget: object | None = None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
    ) -> object:
        """Forward retrieve with this run's budget.

        Args:
            query: Branch query text.
            caller: Server-derived caller.
            profile: Typed query profile when present.
            deadline_seconds: Remaining retrieval slice.

        Returns:
            ``HybridRunResult``.
        """

        return self.inner.retrieve(
            query=query,
            caller=caller,
            profile=profile,
            deadline_seconds=deadline_seconds,
            query_budget=self.query_budget,
        )


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


def context_loader(
    supabase_dsn: str, caller: CallerContext
) -> Callable[[tuple[UUID, ...]], tuple[ChunkContext, ...]]:
    """Build a context RPC loader that opens one connection per fetch.

    Args:
        supabase_dsn: Canonical Postgres URL.
        caller: Retrieve caller captured for ACL.

    Returns:
        ``ContextFn`` used by ``HybridRetriever``.
    """

    def load(chunk_ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Load authorized chunk context on a fresh idle login connection.

        ``fetch_authorized_chunk_context`` starts ``retrieval_transaction``,
        which requires an idle connection and applies ``SET LOCAL ROLE
        app_api``. Pre-setting the role would leave the connection
        in-transaction and fail closed on hosted pooler and local Postgres.

        Args:
            chunk_ids: Canonical IDs.

        Returns:
            Authorized rows. Unauthorized IDs are omitted.
        """

        with psycopg.connect(supabase_dsn) as connection:
            return fetch_authorized_chunk_context(
                connection,
                caller=caller,
                chunk_ids=chunk_ids,
            )

    return load


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
            with psycopg.connect(postgres_url) as connection:
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
