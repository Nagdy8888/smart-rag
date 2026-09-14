"""Local/test lifespan supervisor for durable exam leases (P06-31)."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import FastAPI
from smart_rag_agents.query.runtime.adapters_hybrid import (
    ProcessHybridRetriever,
    RunScopedHybrid,
)
from smart_rag_core.evaluation.private_pdf.exam_repository import (
    ExamRepository,
    ExamRepositoryError,
)
from smart_rag_core.evaluation.private_pdf.exam_runner import ExamRunner
from smart_rag_core.evaluation.private_pdf.quiz_repository import QuizCaseRepository
from smart_rag_core.query_admission.retrieve_budget import QueryRetrieveBudget
from smart_rag_core.retrieval.cache_store import RetrievalCacheMode
from smart_rag_core.retrieval.hybrid_run.types import HybridRunResult
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.settings import BackendSettings, Environment

LOGGER = logging.getLogger(__name__)


class EvalExamSupervisor:
    """One global exam loop. SQL claim is durable authority, not this task.

    Attributes:
        runner: Injected exam runner.
    """

    def __init__(self, runner: ExamRunner, *, idle_seconds: float = 2.0) -> None:
        """Bind the runner and idle interval.

        Args:
            runner: Durable exam runner.
            idle_seconds: Sleep when the queue is empty or no examiner is bound.
        """

        self._runner = runner
        self._idle_seconds = idle_seconds
        self._examiner: CallerContext | None = None

    def bind_examiner(self, caller: CallerContext) -> None:
        """Remember the owner/admin used for claim RPCs.

        Args:
            caller: Server-derived examiner. Packet 32 binds this on start/poll.
        """

        self._examiner = caller

    async def run_forever(self) -> None:
        """Claim and run exams until the lifespan cancels this task.

        Side Effects:
            Calls ``run_once`` on a worker thread. Logs error types only.
        """

        while True:
            try:
                caller = self._examiner
                if caller is not None:
                    await asyncio.to_thread(self._runner.run_once, caller)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.warning(
                    "eval_exam_supervisor_error",
                    extra={
                        "event": "eval_exam.supervisor_error",
                        "error_type": type(exc).__name__,
                    },
                )
            await asyncio.sleep(self._idle_seconds)


def _retrieve_from_app_state(
    application: FastAPI,
    *,
    query: str,
    caller: CallerContext,
    profile: object,
    query_budget: QueryRetrieveBudget,
    cache_mode: RetrievalCacheMode,
    deadline_seconds: float | None = None,
) -> HybridRunResult:
    """Forward exam retrieve through a per-run Hybrid facade.

    Args:
        application: FastAPI app with optional process Hybrid on state.
        query: Case question only.
        caller: Server-derived examiner.
        profile: Typed preparation profile.
        query_budget: Per-run ledger. Never written onto the process adapter.
        cache_mode: Must be ``cold_bypass``.
        deadline_seconds: Remaining retrieval slice.

    Returns:
        Production ``HybridRunResult``.

    Raises:
        ExamRepositoryError: Process Hybrid is not bound yet.
    """

    hybrid = getattr(application.state, "eval_exam_hybrid", None)
    if not isinstance(hybrid, ProcessHybridRetriever):
        raise ExamRepositoryError("hybrid_unbound")
    scoped = RunScopedHybrid(hybrid)
    scoped.query_budget = query_budget
    result = scoped.retrieve(
        query=query,
        caller=caller,
        profile=profile,
        deadline_seconds=deadline_seconds,
        cache_mode=cache_mode,
    )
    if not isinstance(result, HybridRunResult):
        raise ExamRepositoryError("hybrid_result_invalid")
    return result


def bind_eval_exam_supervisor(
    application: FastAPI,
    settings: BackendSettings,
) -> asyncio.Task[None] | None:
    """Start the exam supervisor when the local/test workspace flag is on.

    Args:
        application: FastAPI app entering lifespan.
        settings: Validated backend settings.

    Returns:
        Background task, or None when the supervisor must not start.

    Side Effects:
        Sets ``application.state.eval_exam_supervisor``.
    """

    application.state.eval_exam_supervisor = None
    if not settings.pdf_eval_workspace_enabled:
        return None
    if settings.app_env not in {Environment.LOCAL, Environment.TEST}:
        return None
    if settings.supabase_db_url is None:
        return None
    postgres_url = settings.supabase_db_url.get_secret_value()
    lease_owner = f"exam-{uuid4().hex}"

    def retrieve(
        *,
        query: str,
        caller: CallerContext,
        profile: object,
        query_budget: QueryRetrieveBudget,
        cache_mode: RetrievalCacheMode,
        deadline_seconds: float | None = None,
    ) -> HybridRunResult:
        """Forward one exam retrieve through app-state Hybrid.

        Args:
            query: Case question only.
            caller: Server-derived examiner.
            profile: Typed preparation profile.
            query_budget: Per-run ledger.
            cache_mode: Must be ``cold_bypass``.
            deadline_seconds: Remaining retrieval slice.

        Returns:
            Production ``HybridRunResult``.
        """

        return _retrieve_from_app_state(
            application,
            query=query,
            caller=caller,
            profile=profile,
            query_budget=query_budget,
            cache_mode=cache_mode,
            deadline_seconds=deadline_seconds,
        )

    runner = ExamRunner(
        exams=ExamRepository(postgres_url),
        quizzes=QuizCaseRepository(postgres_url),
        retrieve=retrieve,
        postgres_url=postgres_url,
        lease_owner=lease_owner,
        process_hybrid=getattr(application.state, "eval_exam_hybrid", None),
    )
    supervisor = EvalExamSupervisor(runner)
    application.state.eval_exam_supervisor = supervisor
    return asyncio.create_task(supervisor.run_forever(), name="eval-exam-supervisor")


def attach_exam_hybrid(application: FastAPI) -> None:
    """Reuse the process Hybrid adapter when Ask has already opened it.

    Args:
        application: FastAPI app.

    Side Effects:
        Sets ``application.state.eval_exam_hybrid`` when a process Hybrid
        is already cached on the query executor. Does not construct a second
        ranking implementation on the HTTP path.
    """

    existing = getattr(application.state, "eval_exam_hybrid", None)
    if isinstance(existing, ProcessHybridRetriever):
        return
    executor = getattr(application.state, "query_run_executor", None)
    factory = getattr(executor, "_factory", None)
    bindings = getattr(factory, "_bindings", None)
    hybrid = getattr(bindings, "hybrid_retriever", None)
    if isinstance(hybrid, ProcessHybridRetriever):
        application.state.eval_exam_hybrid = hybrid
        runner = getattr(
            getattr(application.state, "eval_exam_supervisor", None),
            "_runner",
            None,
        )
        if runner is not None:
            runner._process_hybrid = hybrid


def bind_exam_http_runtime(application: FastAPI, caller: CallerContext) -> None:
    """Bind the examiner and reuse process Hybrid for the supervisor.

    Args:
        application: FastAPI app.
        caller: Server-derived owner/admin.
    """

    attach_exam_hybrid(application)
    supervisor = getattr(application.state, "eval_exam_supervisor", None)
    bind = getattr(supervisor, "bind_examiner", None)
    if callable(bind):
        bind(caller)
