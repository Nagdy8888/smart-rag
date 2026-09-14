"""Restart-safe production-corpus Hybrid exam runner (P06-31)."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid5

import psycopg

from smart_rag_core.evaluation.private_pdf.exam_fingerprint import (
    capture_exam_candidate_fingerprint,
)
from smart_rag_core.evaluation.private_pdf.exam_repository import (
    ClaimedExam,
    ExamQueries,
    ExamRepositoryError,
)
from smart_rag_core.evaluation.private_pdf.metrics import (
    PrivatePdfRetrieveScore,
    aggregate_retrieve_gates,
    retrieve_gates_pass,
    score_retrieve_case,
)
from smart_rag_core.evaluation.private_pdf.quiz_repository import (
    QuizCaseDetail,
    QuizRepositoryError,
)
from smart_rag_core.evaluation.ranked_ids import recall_hit_at_k
from smart_rag_core.query_admission.exceptions import (
    QueryAdmissionError,
    QueryBudgetError,
)
from smart_rag_core.query_admission.repository.admit import (
    QueryAdmissionResult,
    admit_query_run,
)
from smart_rag_core.query_admission.repository.reservation import (
    true_up_query_reservation,
)
from smart_rag_core.query_admission.retrieve_budget import QueryRetrieveBudget
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.models import QueryPreparation
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.retrieval.cache_store import RetrievalCacheMode
from smart_rag_core.retrieval.coverage import CoverageDecision
from smart_rag_core.retrieval.hybrid_run.types import HybridRunResult
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import CallerContext

LOGGER = logging.getLogger(__name__)
_ADMIT_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


class ExamRetrieveFn(Protocol):
    """Production Hybrid retrieve used by exams. Must not clone ranking."""

    def __call__(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object,
        query_budget: QueryRetrieveBudget,
        cache_mode: RetrievalCacheMode,
        deadline_seconds: float | None = None,
    ) -> HybridRunResult:
        """Run one Hybrid retrieve.

        Args:
            query: Case question only.
            caller: Server-derived examiner.
            profile: Typed preparation profile.
            query_budget: Per-run ledger. Must not live on a process adapter.
            cache_mode: Must be ``cold_bypass`` for exams.
            deadline_seconds: Remaining retrieval slice.

        Returns:
            Production ``HybridRunResult``.
        """

        ...


class ExamCaseLookup(Protocol):
    """Quiz lookup used to revalidate gold. Tests may implement only ``get``."""

    def get(self, caller: CallerContext, *, case_id: UUID) -> QuizCaseDetail:
        """Return one case including gold locators.

        Args:
            caller: Server-derived examiner.
            case_id: Snapshot case id.

        Returns:
            Case detail.
        """

        ...


class ExamConnectFn(Protocol):
    """Open a connection used as a context manager for admit and true-up."""

    def __call__(self) -> AbstractContextManager[object]:
        """Return an open connection context.

        Returns:
            Context manager yielding a connection.
        """

        ...


def _payload_hash(exam_run_id: UUID, case_id: UUID) -> str:
    """Return a stable admit payload hash without question text.

    Args:
        exam_run_id: Durable exam id.
        case_id: Snapshot case id.

    Returns:
        SHA-256 hex.
    """

    canonical = f"{exam_run_id}:{case_id}".encode()
    return hashlib.sha256(canonical).hexdigest()


def _ranked_hit_count(ranked_ids: Sequence[UUID], gold_ids: Sequence[UUID]) -> int:
    """Count gold UUIDs present in the production Hybrid top 10.

    Args:
        ranked_ids: ``HybridRunResult.ranked_ids``.
        gold_ids: Required gold chunk ids.

    Returns:
        Count in ``[0, len(gold_ids)]``.
    """

    top = set(ranked_ids[:10])
    return sum(1 for gold_id in gold_ids if gold_id in top)


class ExamRunner:
    """Claims durable exams and scores them with production Hybrid retrieve.

    One process runs at most one case at a time. Durable authority is SQL
    claim/heartbeat/persist, not an in-memory lock. Ask must not share
    ``query_budget`` with this runner.

    Args:
        exams: Exam RPC repository.
        quizzes: Quiz RPC repository used to revalidate gold.
        retrieve: Production Hybrid retrieve callable.
        postgres_url: ``app_api`` DSN for admit/true-up. Never operator.
        lease_owner: Process lease token, at least eight characters.
        lease_seconds: Bounded 5-60 second lease.
        process_hybrid: Optional process-adapter whose ``query_budget``
            must remain unset. Tests pass the process Hybrid retriever.
        admit: Injected admit. Defaults to ``admit_query_run``.
        prepare: Injected preparation. Defaults to ``prepare_query``.
        true_up: Injected true-up. Defaults to ``true_up_query_reservation``.
        fingerprint: Fingerprint capture. Defaults to the production capture.
        connect: Optional connection factory for tests.
    """

    def __init__(
        self,
        *,
        exams: ExamQueries,
        quizzes: ExamCaseLookup,
        retrieve: ExamRetrieveFn,
        postgres_url: str,
        lease_owner: str,
        lease_seconds: int = 30,
        process_hybrid: object | None = None,
        admit: Callable[..., QueryAdmissionResult] = admit_query_run,
        prepare: Callable[..., QueryPreparation] = prepare_query,
        true_up: Callable[..., object] = true_up_query_reservation,
        fingerprint: Callable[[], object] = capture_exam_candidate_fingerprint,
        connect: ExamConnectFn | None = None,
    ) -> None:
        """Bind durable exam dependencies.

        Args:
            exams: Exam RPCs.
            quizzes: Quiz RPCs.
            retrieve: Production Hybrid retrieve.
            postgres_url: ``app_api`` DSN.
            lease_owner: Process lease token.
            lease_seconds: Lease length.
            process_hybrid: Process Hybrid adapter whose ``query_budget``
                must remain unset. Exams bind a per-run ledger instead.
            admit: Admit function.
            prepare: Preparation function.
            true_up: Reservation true-up.
            fingerprint: Fingerprint capture.
            connect: Optional connection factory.
        """

        self._exams = exams
        self._quizzes = quizzes
        self._retrieve = retrieve
        self._postgres_url = postgres_url
        self._lease_owner = lease_owner
        self._lease_seconds = lease_seconds
        self._process_hybrid = process_hybrid
        self._admit = admit
        self._prepare = prepare
        self._true_up = true_up
        self._fingerprint = fingerprint
        self._connect = connect

    def _open(self) -> AbstractContextManager[object]:
        """Open an ``app_api`` connection.

        Returns:
            Open connection context manager.
        """

        if self._connect is not None:
            return self._connect()
        connection = psycopg.connect(self._postgres_url)
        connection.execute("SET ROLE app_api")
        return connection

    def run_once(self, caller: CallerContext) -> ClaimedExam | None:
        """Claim at most one exam and run it to a terminal SQL state.

        Args:
            caller: Server-derived owner/admin examiner.

        Returns:
            The claimed exam, or None when the queue is empty.
        """

        claimed = self._exams.claim(
            caller,
            lease_owner=self._lease_owner,
            lease_seconds=self._lease_seconds,
        )
        if claimed is None:
            return None
        self.run_claimed(caller, claimed)
        return claimed

    def run_claimed(self, caller: CallerContext, claimed: ClaimedExam) -> None:
        """Score remaining cases on a claimed exam.

        Args:
            caller: Server-derived owner/admin examiner.
            claimed: Claimed lease payload.

        Side Effects:
            Heartbeats, admits Hybrid runs, persists count-only results,
            true-ups reservations, and finalizes or fails the exam.
        """

        LOGGER.info(
            "eval_exam_claimed",
            extra={
                "event": "eval_exam.claimed",
                "exam_run_id": str(claimed.exam_run_id),
                "case_count": claimed.case_count,
            },
        )
        captured = self._fingerprint()
        complete = bool(getattr(captured, "complete", False))
        if claimed.split == "qualification" and (
            not complete or not claimed.candidate_fingerprint
        ):
            self._fail(caller, claimed.exam_run_id, "incomplete_fingerprint")
            return
        scores: list[PrivatePdfRetrieveScore] = []
        skipped = claimed.completed_case_count
        remaining = claimed.case_ids[skipped:]
        bm25_degraded = False
        try:
            for case_id in remaining:
                status = self._exams.get(caller, exam_run_id=claimed.exam_run_id)
                if status is not None and status.status == "cancelled":
                    return
                self._exams.heartbeat(
                    caller,
                    exam_run_id=claimed.exam_run_id,
                    lease_owner=self._lease_owner,
                    lease_seconds=self._lease_seconds,
                )
                score, degraded = self._score_case(
                    caller,
                    claimed=claimed,
                    case_id=case_id,
                )
                if score is None:
                    return
                scores.append(score)
                bm25_degraded = bm25_degraded or degraded
        except (QueryAdmissionError, QueryBudgetError) as exc:
            self._fail(caller, claimed.exam_run_id, exc.reason)
            return
        except (ExamRepositoryError, QuizRepositoryError) as exc:
            self._fail(caller, claimed.exam_run_id, exc.code)
            return
        if (
            self._process_hybrid is not None
            and getattr(self._process_hybrid, "query_budget", None) is not None
        ):
            self._fail(caller, claimed.exam_run_id, "process_budget_mutated")
            return
        status = self._exams.get(caller, exam_run_id=claimed.exam_run_id)
        if status is not None and status.status in {"cancelled", "failed", "succeeded"}:
            return
        gates = False
        if skipped == 0 and scores:
            report = aggregate_retrieve_gates(tuple(scores))
            gates = retrieve_gates_pass(report) and not bm25_degraded
        if bm25_degraded:
            gates = False
        self._exams.finalize(
            caller,
            exam_run_id=claimed.exam_run_id,
            gates_pass=gates,
            error_code=None,
        )

    def _fail(self, caller: CallerContext, exam_run_id: UUID, code: str) -> None:
        """Finalize without an official report.

        Args:
            caller: Server-derived examiner.
            exam_run_id: Exam to fail.
            code: Content-free error code.
        """

        LOGGER.info(
            "eval_exam_failed",
            extra={
                "event": "eval_exam.failed",
                "exam_run_id": str(exam_run_id),
                "error_code": code[:64],
            },
        )
        try:
            self._exams.finalize(
                caller,
                exam_run_id=exam_run_id,
                gates_pass=False,
                error_code=code[:64],
            )
        except ExamRepositoryError:
            return

    def _score_case(
        self,
        caller: CallerContext,
        *,
        claimed: ClaimedExam,
        case_id: UUID,
    ) -> tuple[PrivatePdfRetrieveScore | None, bool]:
        """Admit, retrieve, score, persist, and true-up one case.

        Args:
            caller: Server-derived examiner.
            claimed: Claimed exam.
            case_id: Snapshot case id.

        Returns:
            Score and BM25-degraded flag. ``(None, False)`` when the exam
            was failed closed inside this call.

        Raises:
            QueryAdmissionError: Admission or budget failure.
            QuizRepositoryError: Gold revalidation failure.
        """

        detail = self._quizzes.get(caller, case_id=case_id)
        if detail.review_status != "approved" or detail.gold_stale:
            self._fail(caller, claimed.exam_run_id, "gold_stale")
            return None, False
        gold_ids = tuple(item.chunk_id for item in detail.gold)
        if not gold_ids or any(item.stale for item in detail.gold):
            self._fail(caller, claimed.exam_run_id, "gold_stale")
            return None, False
        reservation_id: UUID
        with self._open() as connection:
            admitted = self._admit(
                connection,
                caller=caller,
                conversation_id=claimed.conversation_id,
                idempotency_key=uuid5(
                    _ADMIT_NAMESPACE, f"{claimed.exam_run_id}:{case_id}"
                ),
                payload_hash=_payload_hash(claimed.exam_run_id, case_id),
                route_family=Phase6RouteFamily.HYBRID,
                requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
            )
            runtime = admitted.context
            reservation_id = runtime.reservation_id
            try:
                if runtime.remaining_usd <= Decimal("0"):
                    self._fail(caller, claimed.exam_run_id, "budget_exhausted")
                    return None, False
                preparation = self._prepare(
                    detail.question,
                    runtime=runtime,
                    memory=(),
                    requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
                    connection=connection,
                    caller=caller,
                )
                remaining_calls = runtime.model_call_ceiling - int(
                    preparation.model_calls
                )
                if remaining_calls < 1 or runtime.remaining_usd <= Decimal("0"):
                    self._fail(caller, claimed.exam_run_id, "budget_exhausted")
                    return None, False
                budget = QueryRetrieveBudget(
                    remaining_model_calls=remaining_calls,
                    remaining_usd=runtime.remaining_usd,
                    connection=connection,
                    caller=caller,
                    run_id=runtime.run_id,
                    reservation_id=reservation_id,
                    expected_version=runtime.optimistic_version,
                )
                try:
                    result = self._retrieve(
                        query=detail.question,
                        caller=caller,
                        profile=preparation.profile,
                        query_budget=budget,
                        cache_mode=RetrievalCacheMode.COLD_BYPASS,
                    )
                except (QueryBudgetError, QueryAdmissionError) as exc:
                    self._fail(caller, claimed.exam_run_id, exc.reason)
                    return None, False
                status = self._exams.get(caller, exam_run_id=claimed.exam_run_id)
                if status is not None and status.status == "cancelled":
                    return None, False
                refused = result.coverage.decision is CoverageDecision.REFUSE
                gold_pages = tuple(
                    item.page_number
                    for item in detail.gold
                    if item.page_number is not None
                )
                evidence_pages = tuple(
                    int(unit.locator.page_number)
                    for unit in result.evidence
                    if unit.locator.page_number is not None
                )
                score = score_retrieve_case(
                    case_id=str(case_id),
                    query_class=detail.query_class,
                    ranked_ids=result.ranked_ids,
                    gold_ids=gold_ids,
                    gold_pages=gold_pages,
                    evidence_pages=evidence_pages,
                    expected_refusal=False,
                    refused=refused,
                    acl_leak=False,
                    required_terms=detail.required_terms,
                    first_evidence_ms=result.first_evidence_ms,
                    rerank_call_count=result.rerank_call_count,
                    bm25_fallback=str(result.fallback_reason),
                    fused_ids=result.fused_ids,
                    rerank_fallback=str(result.rerank_fallback or "none"),
                    selected_ids=result.selected_ids,
                    dense_ids=result.dense_ids,
                    bm25_ids=result.bm25_ids,
                    term_ids=result.term_ids,
                )
                hit = recall_hit_at_k(result.ranked_ids, gold_ids, 10)
                latency = int(result.first_evidence_ms)
                persisted = self._exams.persist_case_result(
                    caller,
                    exam_run_id=claimed.exam_run_id,
                    case_id=case_id,
                    hit=hit,
                    gold_count=len(gold_ids),
                    ranked_hit_count=_ranked_hit_count(result.ranked_ids, gold_ids),
                    latency_ms=latency,
                )
                degraded = (
                    result.fallback_reason is RetrievalFallbackReason.BM25_UNAVAILABLE
                )
                if not persisted.inserted:
                    LOGGER.info(
                        "eval_exam_case_replayed",
                        extra={
                            "event": "eval_exam.case_replayed",
                            "exam_run_id": str(claimed.exam_run_id),
                            "case_id": str(case_id),
                        },
                    )
                return score, degraded
            finally:
                self._true_up(
                    connection,
                    caller=caller,
                    reservation_id=reservation_id,
                )
