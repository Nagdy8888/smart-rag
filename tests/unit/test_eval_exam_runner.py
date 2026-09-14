"""Production-corpus Hybrid exam runner tests (P06-31)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
from smart_rag_core.evaluation.private_pdf.exam_fingerprint import (
    ExamCandidateFingerprint,
    capture_exam_candidate_fingerprint,
)
from smart_rag_core.evaluation.private_pdf.exam_repository import (
    ClaimedExam,
    ExamFinalizeResult,
    ExamPersistResult,
    ExamRunStatus,
    exam_error_code,
)
from smart_rag_core.evaluation.private_pdf.exam_runner import ExamRunner
from smart_rag_core.evaluation.private_pdf.quiz_repository import (
    QuizCaseDetail,
    QuizGoldLocator,
    QuizRepositoryError,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryBudgetError
from smart_rag_core.query_admission.repository.admit import QueryAdmissionResult
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.models import QueryPreparation
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.retrieval.cache_store import RetrievalCacheMode
from smart_rag_core.retrieval.coverage import (
    CoverageDecision,
    CoverageSignal,
    HybridCoverage,
)
from smart_rag_core.retrieval.hybrid_run.types import (
    EvidenceLocator,
    EvidenceUnit,
    HybridRunResult,
)
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import CallerContext, UserRole

_CANARY_ANSWER = "CANARY_EXPECTED_ANSWER_SECRET"


class _Conn:
    """Idle connection stand-in for admit/true-up."""

    def __enter__(self) -> _Conn:
        """Return this connection.

        Returns:
            Self.
        """

        return self

    def __exit__(self, *args: object) -> bool:
        """Skip exception suppression.

        Args:
            *args: Context-manager exception triple.

        Returns:
            False.
        """

        return False

    def execute(self, *args: object, **kwargs: object) -> None:
        """Ignore SQL.

        Args:
            *args: Unused.
            **kwargs: Unused.
        """

        del args, kwargs


def _caller() -> CallerContext:
    """Return an owner examiner.

    Returns:
        Owner caller.
    """

    return CallerContext(
        user_id=str(uuid4()),
        role=UserRole.OWNER,
        authorization_version=1,
    )


def _runtime(*, remaining_usd: Decimal = Decimal("2.80")) -> AuthorizedRuntimeContext:
    """Return a Hybrid admission envelope.

    Args:
        remaining_usd: Remaining reservation.

    Returns:
        Frozen runtime context.
    """

    now = datetime.now(UTC)
    return AuthorizedRuntimeContext(
        user_id=uuid4(),
        role=UserRole.OWNER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=Phase6RouteFamily.HYBRID,
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
        deadline_at=now + timedelta(seconds=25),
        recursion_limit=24,
        correction_ceiling=1,
        subquestion_ceiling=3,
        model_call_ceiling=7,
        tool_ceiling=4,
        discovery_ceiling=1,
        manifest_ceiling=3,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("2.80"),
        remaining_usd=remaining_usd,
        remaining_prompt_tokens=72000,
        remaining_completion_tokens=18000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="a" * 64,
        status="pending",
    )


def _gold(chunk_id: UUID, *, stale: bool = False) -> QuizGoldLocator:
    """Build one gold locator.

    Args:
        chunk_id: Gold chunk.
        stale: Stale flag.

    Returns:
        Locator.
    """

    return QuizGoldLocator(
        ordinal=1,
        chunk_id=chunk_id,
        document_id=uuid4(),
        version_id=uuid4(),
        page_number=3,
        page_label="3",
        section_path=("Leave",),
        stale=stale,
    )


def _detail(
    case_id: UUID,
    gold_id: UUID,
    *,
    stale: bool = False,
    question: str = "What is our refund period?",
) -> QuizCaseDetail:
    """Build an approved quiz case.

    Args:
        case_id: Case id.
        gold_id: Gold chunk.
        stale: Gold staleness.
        question: Question text.

    Returns:
        Case detail.
    """

    return QuizCaseDetail(
        case_id=case_id,
        split="development",
        query_class="factual_definition",
        review_status="approved",
        generated_only=False,
        source_family_id="leave",
        question=question,
        expected_answer=_CANARY_ANSWER,
        atomic_facts=("refund is 14 days",),
        required_terms=("refund",),
        expected_scope="company",
        source_run_id=None,
        document_id=uuid4(),
        version_id=uuid4(),
        gold=(_gold(gold_id, stale=stale),),
        gold_stale=stale,
        reviewer_user_id=uuid4(),
        row_version=1,
    )


def _hybrid(ranked_ids: tuple[UUID, ...], gold_id: UUID) -> HybridRunResult:
    """Build a frozen Hybrid result.

    Args:
        ranked_ids: Production ranked IDs.
        gold_id: Gold chunk used for a locator.

    Returns:
        Hybrid result.
    """

    evidence = tuple(
        EvidenceUnit(
            chunk_id=chunk_id,
            document_id=uuid4(),
            version_id=uuid4(),
            citation_text="canonical refund policy",
            locator=EvidenceLocator(page_number=3, section_path=("Leave",)),
        )
        for chunk_id in ranked_ids[:12]
    ) or (
        EvidenceUnit(
            chunk_id=gold_id,
            document_id=uuid4(),
            version_id=uuid4(),
            citation_text="canonical refund policy",
            locator=EvidenceLocator(page_number=3, section_path=("Leave",)),
        ),
    )
    return HybridRunResult(
        ranked_ids=ranked_ids,
        evidence=evidence,
        coverage=HybridCoverage(
            signal=CoverageSignal.NONE,
            decision=CoverageDecision.ANSWER,
        ),
        fallback_reason=RetrievalFallbackReason.NONE,
        deadline_exhausted=False,
        first_evidence_ms=12.0,
        embedding_call_count=1,
        rerank_call_count=1,
        selected_ids=ranked_ids,
    )


class _FakeExams:
    """In-memory exam RPC fake."""

    def __init__(self, claimed: ClaimedExam | None) -> None:
        """Bind the claim payload.

        Args:
            claimed: Claimed exam or None.
        """

        self.claimed = claimed
        self.status = "running"
        self.persisted: list[tuple[UUID, bool, int]] = []
        self.finalized: list[tuple[bool, str | None]] = []
        self.heartbeats = 0
        self._seen: set[UUID] = set()
        self._gets = 0
        self.cancel_after_retrieve = False

    def claim(
        self, caller: CallerContext, *, lease_owner: str, lease_seconds: int
    ) -> ClaimedExam | None:
        """Return the queued exam.

        Args:
            caller: Examiner.
            lease_owner: Lease token.
            lease_seconds: Lease length.

        Returns:
            Claimed exam.
        """

        del caller, lease_owner, lease_seconds
        return self.claimed

    def heartbeat(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
        lease_owner: str,
        lease_seconds: int,
    ) -> datetime:
        """Count heartbeats.

        Args:
            caller: Examiner.
            exam_run_id: Exam id.
            lease_owner: Lease token.
            lease_seconds: Lease length.

        Returns:
            Now.
        """

        del caller, exam_run_id, lease_owner, lease_seconds
        self.heartbeats += 1
        return datetime.now(UTC)

    def reclaim(self, caller: CallerContext, **kwargs: object) -> bool:
        """Unused reclaim.

        Args:
            caller: Examiner.
            **kwargs: Unused.

        Returns:
            True.
        """

        del caller, kwargs
        return True

    def persist_case_result(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
        case_id: UUID,
        hit: bool,
        gold_count: int,
        ranked_hit_count: int,
        latency_ms: int | None,
    ) -> ExamPersistResult:
        """Record one count-only result.

        Args:
            caller: Examiner.
            exam_run_id: Exam id.
            case_id: Case id.
            hit: Recall hit.
            gold_count: Gold count.
            ranked_hit_count: Gold IDs in top 10.
            latency_ms: Latency.

        Returns:
            Persist outcome.
        """

        del caller, gold_count, ranked_hit_count, latency_ms
        inserted = case_id not in self._seen
        self._seen.add(case_id)
        self.persisted.append((case_id, hit, 1 if inserted else 0))
        return ExamPersistResult(
            exam_run_id=exam_run_id,
            case_id=case_id,
            inserted=inserted,
            completed_case_count=len(self._seen),
        )

    def finalize(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
        gates_pass: bool,
        error_code: str | None,
    ) -> ExamFinalizeResult:
        """Record finalize.

        Args:
            caller: Examiner.
            exam_run_id: Exam id.
            gates_pass: Overlay gates.
            error_code: Failure code.

        Returns:
            Terminal exam outcome.
        """

        del caller
        self.finalized.append((gates_pass, error_code))
        status = "failed" if error_code else "succeeded"
        self.status = status
        return ExamFinalizeResult(
            exam_run_id=exam_run_id,
            status=status,
            report_present=error_code is None,
        )

    def cancel(self, caller: CallerContext, *, exam_run_id: UUID) -> str:
        """Mark cancelled.

        Args:
            caller: Examiner.
            exam_run_id: Exam id.

        Returns:
            Status.
        """

        del caller, exam_run_id
        self.status = "cancelled"
        return self.status

    def get(self, caller: CallerContext, *, exam_run_id: UUID) -> ExamRunStatus | None:
        """Return poll status.

        Args:
            caller: Examiner.
            exam_run_id: Exam id.

        Returns:
            Status row.
        """

        assert self.claimed is not None
        del caller
        self._gets += 1
        if self.cancel_after_retrieve and self._gets >= 2:
            self.status = "cancelled"
        return ExamRunStatus(
            exam_run_id=exam_run_id,
            split=self.claimed.split,
            status=self.status,
            dataset_hash=self.claimed.dataset_hash,
            candidate_fingerprint=self.claimed.candidate_fingerprint,
            case_count=self.claimed.case_count,
            completed_case_count=len(self._seen),
            holdout_opened=False,
            conversation_id=self.claimed.conversation_id,
        )


class _FakeQuizzes:
    """Quiz get fake."""

    def __init__(self, details: dict[UUID, QuizCaseDetail]) -> None:
        """Bind case details.

        Args:
            details: Case map.
        """

        self.details = details
        self.calls: list[UUID] = []
        self.error: str | None = None

    def get(self, caller: CallerContext, *, case_id: UUID) -> QuizCaseDetail:
        """Return one case.

        Args:
            caller: Examiner.
            case_id: Case id.

        Returns:
            Detail.

        Raises:
            QuizRepositoryError: Missing or unauthorized.
        """

        del caller
        self.calls.append(case_id)
        if self.error is not None:
            raise QuizRepositoryError(self.error)
        if case_id not in self.details:
            raise QuizRepositoryError("not_found")
        return self.details[case_id]


def _claimed(
    case_ids: tuple[UUID, ...],
    *,
    split: str = "development",
    completed: int = 0,
    fingerprint: str = "f" * 64,
) -> ClaimedExam:
    """Build a claimed exam.

    Args:
        case_ids: Snapshot ids.
        split: Split.
        completed: Already persisted count.
        fingerprint: Candidate fingerprint.

    Returns:
        Claimed exam.
    """

    return ClaimedExam(
        exam_run_id=uuid4(),
        conversation_id=uuid4(),
        split=split,
        dataset_hash="d" * 64,
        candidate_fingerprint=fingerprint,
        case_ids=case_ids,
        case_count=len(case_ids),
        completed_case_count=completed,
    )


def _admit_factory(
    *,
    remaining_usd: Decimal = Decimal("2.80"),
    reconnect: bool = False,
) -> Callable[..., QueryAdmissionResult]:
    """Build an admit stub with a frozen reservation.

    Args:
        remaining_usd: Remaining reservation dollars.
        reconnect: Whether this admit is a crash reconnect.

    Returns:
        Admit callable.
    """

    def admit(connection: object, **kwargs: object) -> QueryAdmissionResult:
        """Return one Hybrid admission.

        Args:
            connection: Unused.
            **kwargs: Unused admission fields.

        Returns:
            Admission result.
        """

        del connection, kwargs
        return QueryAdmissionResult(
            context=_runtime(remaining_usd=remaining_usd),
            reconnect=reconnect,
        )

    return admit


def _prepare_ok(
    query: str,
    *,
    runtime: AuthorizedRuntimeContext,
    **kwargs: object,
) -> QueryPreparation:
    """Prepare with question text and empty memory.

    Args:
        query: Case question.
        runtime: Admitted runtime.
        **kwargs: Unused preparation fields.

    Returns:
        Production preparation.
    """

    del kwargs
    return prepare_query(query, runtime=runtime, memory=())


def _noop_true_up(connection: object, **kwargs: object) -> None:
    """Skip settlement side effects in unit tests.

    Args:
        connection: Unused.
        **kwargs: Unused.
    """

    del connection, kwargs


def _count_true_up(counter: dict[str, int]) -> Callable[..., None]:
    """Build a true-up stub that increments a counter.

    Args:
        counter: Mutable ``value`` map.

    Returns:
        True-up callable.
    """

    def true_up(connection: object, **kwargs: object) -> None:
        """Count one settlement.

        Args:
            connection: Unused.
            **kwargs: Unused.
        """

        del connection, kwargs
        counter["value"] += 1

    return true_up


def _hybrid_retrieve(
    ranked: tuple[UUID, ...],
    gold_id: UUID,
) -> Callable[..., HybridRunResult]:
    """Return a retrieve stub with frozen ranked IDs.

    Args:
        ranked: Ranked IDs.
        gold_id: Gold chunk for locators.

    Returns:
        Retrieve callable.
    """

    def retrieve(**kwargs: object) -> HybridRunResult:
        """Return the frozen Hybrid result.

        Args:
            **kwargs: Unused retrieve fields.

        Returns:
            Frozen Hybrid result.
        """

        del kwargs
        return _hybrid(ranked, gold_id)

    return retrieve


def test_exam_error_code_is_content_free() -> None:
    """Mapped codes never return SQL or question text."""

    missing = psycopg.errors.UndefinedFunction("function missing")
    holdout = psycopg.errors.RaiseException("eval_exam:holdout_rejected")
    assert exam_error_code(missing) == "exam_schema_missing"
    assert exam_error_code(holdout) == "holdout_rejected"
    assert exam_error_code(RuntimeError("SELECT question FROM")) == "request_rejected"


def test_capture_exam_candidate_fingerprint_is_complete() -> None:
    """Production pins produce a 64-character complete digest."""

    captured = capture_exam_candidate_fingerprint()
    assert captured.complete is True
    assert captured.missing == ()
    assert len(captured.digest) == 64


def test_ranked_id_parity_and_cold_bypass_without_version_pin() -> None:
    """Exam scores the production Hybrid ranked_ids without cloning ranking."""

    gold_id = uuid4()
    filler = tuple(uuid4() for _ in range(9))
    ranked = (gold_id, *filler)
    case_id = uuid4()
    claimed = _claimed((case_id,))
    exams = _FakeExams(claimed)
    quizzes = _FakeQuizzes({case_id: _detail(case_id, gold_id)})
    process = SimpleNamespace(query_budget=None)
    retrieve_calls: list[dict[str, object]] = []
    prepare_queries: list[str] = []
    true_ups: list[UUID] = []

    def retrieve(**kwargs: object) -> HybridRunResult:
        """Record retrieve kwargs.

        Args:
            **kwargs: Retrieve arguments.

        Returns:
            Frozen Hybrid result.
        """

        retrieve_calls.append(kwargs)
        return _hybrid(ranked, gold_id)

    def admit(connection: object, **kwargs: object) -> QueryAdmissionResult:
        """Admit one Hybrid run.

        Args:
            connection: Unused.
            **kwargs: Admit arguments.

        Returns:
            Admission result.
        """

        del connection, kwargs
        return QueryAdmissionResult(context=_runtime(), reconnect=False)

    def prepare(
        query: str,
        *,
        runtime: AuthorizedRuntimeContext,
        **kwargs: object,
    ) -> QueryPreparation:
        """Prepare with question text only.

        Args:
            query: Case question.
            runtime: Admitted runtime.
            **kwargs: Unused preparation fields.

        Returns:
            Production preparation.
        """

        prepare_queries.append(query)
        return _prepare_ok(query, runtime=runtime, **kwargs)

    def true_up(connection: object, *, caller: object, reservation_id: UUID) -> None:
        """Record settlement.

        Args:
            connection: Unused.
            caller: Examiner.
            reservation_id: Reservation.
        """

        del connection, caller
        true_ups.append(reservation_id)

    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=retrieve,
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        process_hybrid=process,
        admit=admit,
        prepare=prepare,
        true_up=true_up,
        connect=_Conn,
    )
    runner.run_once(_caller())
    assert retrieve_calls
    kwargs = retrieve_calls[0]
    assert kwargs["cache_mode"] is RetrievalCacheMode.COLD_BYPASS
    assert "restrict_version_id" not in kwargs
    assert kwargs["query"] == "What is our refund period?"
    assert _CANARY_ANSWER not in str(kwargs)
    assert str(gold_id) not in str(kwargs)
    assert prepare_queries == ["What is our refund period?"]
    assert _CANARY_ANSWER not in prepare_queries[0]
    assert exams.persisted == [(case_id, True, 1)]
    assert exams.finalized
    assert exams.finalized[0][1] is None
    assert true_ups
    assert process.query_budget is None


def test_crash_after_result_write_does_not_retrieve_again() -> None:
    """Completed snapshot cases are not retrieved a second time."""

    gold_id = uuid4()
    done_id = uuid4()
    next_id = uuid4()
    claimed = _claimed((done_id, next_id), completed=1)
    exams = _FakeExams(claimed)
    quizzes = _FakeQuizzes(
        {
            done_id: _detail(done_id, gold_id, question="done question"),
            next_id: _detail(next_id, gold_id, question="next question"),
        }
    )
    retrieve_queries: list[str] = []

    def retrieve(**kwargs: object) -> HybridRunResult:
        """Retrieve remaining cases only.

        Args:
            **kwargs: Retrieve arguments.

        Returns:
            Frozen Hybrid result.
        """

        retrieve_queries.append(str(kwargs["query"]))
        return _hybrid((gold_id,), gold_id)

    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=retrieve,
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        admit=_admit_factory(reconnect=True),
        prepare=_prepare_ok,
        true_up=_noop_true_up,
        connect=_Conn,
    )
    runner.run_claimed(_caller(), claimed)
    assert retrieve_queries == ["next question"]
    assert done_id not in quizzes.calls


def test_budget_exhaustion_before_retrieve_has_no_official_report() -> None:
    """Zero remaining USD fails closed without retrieve."""

    gold_id = uuid4()
    case_id = uuid4()
    claimed = _claimed((case_id,))
    exams = _FakeExams(claimed)
    quizzes = _FakeQuizzes({case_id: _detail(case_id, gold_id)})
    retrieved = {"value": 0}

    def retrieve(**kwargs: object) -> HybridRunResult:
        """Must not run.

        Args:
            **kwargs: Unused.

        Returns:
            Unused result.
        """

        del kwargs
        retrieved["value"] += 1
        return _hybrid((gold_id,), gold_id)

    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=retrieve,
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        admit=_admit_factory(remaining_usd=Decimal("0")),
        prepare=_prepare_ok,
        true_up=_noop_true_up,
        connect=_Conn,
    )
    runner.run_once(_caller())
    assert retrieved["value"] == 0
    assert exams.persisted == []
    assert exams.finalized == [(False, "budget_exhausted")]


def test_budget_exhaustion_during_retrieve_settles_reservation() -> None:
    """Retrieve budget errors true-up and skip the official report."""

    gold_id = uuid4()
    case_id = uuid4()
    claimed = _claimed((case_id,))
    exams = _FakeExams(claimed)
    quizzes = _FakeQuizzes({case_id: _detail(case_id, gold_id)})
    true_ups = {"value": 0}

    def retrieve(**kwargs: object) -> HybridRunResult:
        """Fail closed after the provider path starts.

        Args:
            **kwargs: Unused.

        Raises:
            QueryBudgetError: Remaining USD cannot cover rerank.
        """

        del kwargs
        raise QueryBudgetError("model_call_exhausted")

    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=retrieve,
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        admit=_admit_factory(),
        prepare=_prepare_ok,
        true_up=_count_true_up(true_ups),
        connect=_Conn,
    )
    runner.run_once(_caller())
    assert true_ups["value"] == 1
    assert exams.finalized == [(False, "model_call_exhausted")]


def test_bm25_outage_forces_gates_pass_false() -> None:
    """Named BM25 degradation cannot publish overlay gates as pass."""

    gold_id = uuid4()
    case_id = uuid4()
    claimed = _claimed((case_id,))
    exams = _FakeExams(claimed)
    quizzes = _FakeQuizzes({case_id: _detail(case_id, gold_id)})

    def retrieve(**kwargs: object) -> HybridRunResult:
        """Return a BM25 outage result.

        Args:
            **kwargs: Unused.

        Returns:
            Degraded Hybrid result.
        """

        del kwargs
        result = _hybrid((gold_id,), gold_id)
        return HybridRunResult(
            ranked_ids=result.ranked_ids,
            evidence=result.evidence,
            coverage=result.coverage,
            fallback_reason=RetrievalFallbackReason.BM25_UNAVAILABLE,
            deadline_exhausted=result.deadline_exhausted,
            first_evidence_ms=result.first_evidence_ms,
            embedding_call_count=1,
            rerank_call_count=0,
            selected_ids=result.selected_ids,
        )

    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=retrieve,
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        admit=_admit_factory(),
        prepare=_prepare_ok,
        true_up=_noop_true_up,
        connect=_Conn,
    )
    runner.run_once(_caller())
    assert exams.finalized
    assert exams.finalized[0] == (False, None)


def test_cancellation_settles_reservation_without_official_report() -> None:
    """Cancelled exams settle the active reservation and skip finalize success."""

    gold_id = uuid4()
    case_id = uuid4()
    claimed = _claimed((case_id,))
    exams = _FakeExams(claimed)
    exams.cancel_after_retrieve = True
    quizzes = _FakeQuizzes({case_id: _detail(case_id, gold_id)})
    true_ups = {"value": 0}

    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=_hybrid_retrieve((gold_id,), gold_id),
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        admit=_admit_factory(),
        prepare=_prepare_ok,
        true_up=_count_true_up(true_ups),
        connect=_Conn,
    )
    runner.run_once(_caller())
    assert exams.persisted == []
    assert exams.finalized == []
    assert true_ups["value"] == 1


def test_stale_gold_and_revoked_caller_fail_closed() -> None:
    """ACL/current-version flip and missing cases never publish a report."""

    gold_id = uuid4()
    stale_id = uuid4()
    claimed = _claimed((stale_id,))
    exams = _FakeExams(claimed)
    quizzes = _FakeQuizzes({stale_id: _detail(stale_id, gold_id, stale=True)})
    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=_hybrid_retrieve((gold_id,), gold_id),
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        admit=_admit_factory(),
        prepare=_prepare_ok,
        true_up=_noop_true_up,
        connect=_Conn,
    )
    runner.run_once(_caller())
    assert exams.finalized == [(False, "gold_stale")]

    missing_id = uuid4()
    claimed2 = _claimed((missing_id,))
    exams2 = _FakeExams(claimed2)
    runner2 = ExamRunner(
        exams=exams2,
        quizzes=_FakeQuizzes({}),
        retrieve=_hybrid_retrieve((gold_id,), gold_id),
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        admit=_admit_factory(),
        prepare=_prepare_ok,
        true_up=_noop_true_up,
        connect=_Conn,
    )
    runner2.run_once(_caller())
    assert exams2.finalized == [(False, "not_found")]


def test_incomplete_fingerprint_blocks_qualification() -> None:
    """Qualification fails closed when the candidate fingerprint is incomplete."""

    gold_id = uuid4()
    case_id = uuid4()
    claimed = _claimed((case_id,), split="qualification", fingerprint="")
    exams = _FakeExams(claimed)
    quizzes = _FakeQuizzes({case_id: _detail(case_id, gold_id)})
    retrieved = {"value": 0}

    def retrieve(**kwargs: object) -> HybridRunResult:
        """Must not run for incomplete qualification fingerprints.

        Args:
            **kwargs: Unused.

        Returns:
            Unused result.
        """

        del kwargs
        retrieved["value"] += 1
        return _hybrid((gold_id,), gold_id)

    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=retrieve,
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        fingerprint=lambda: ExamCandidateFingerprint(
            digest="", complete=False, missing=("frozen_profile",)
        ),
        admit=_admit_factory(),
        prepare=_prepare_ok,
        true_up=_noop_true_up,
        connect=_Conn,
    )
    runner.run_once(_caller())
    assert retrieved["value"] == 0
    assert exams.finalized == [(False, "incomplete_fingerprint")]


def test_lease_reclaim_does_not_double_increment() -> None:
    """Duplicate persist of a completed case does not increment progress."""

    gold_id = uuid4()
    case_id = uuid4()
    claimed = _claimed((case_id,))
    exams = _FakeExams(claimed)
    quizzes = _FakeQuizzes({case_id: _detail(case_id, gold_id)})
    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=_hybrid_retrieve((gold_id,), gold_id),
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        admit=_admit_factory(reconnect=True),
        prepare=_prepare_ok,
        true_up=_noop_true_up,
        connect=_Conn,
    )
    caller = _caller()
    runner.run_claimed(caller, claimed)
    second = ClaimedExam(
        exam_run_id=claimed.exam_run_id,
        conversation_id=claimed.conversation_id,
        split=claimed.split,
        dataset_hash=claimed.dataset_hash,
        candidate_fingerprint=claimed.candidate_fingerprint,
        case_ids=claimed.case_ids,
        case_count=claimed.case_count,
        completed_case_count=1,
    )
    runner.run_claimed(caller, second)
    assert exams.persisted == [(case_id, True, 1)]


def test_revoked_caller_fail_closed() -> None:
    """Caller authorization failures during gold lookup never publish a report."""

    gold_id = uuid4()
    case_id = uuid4()
    claimed = _claimed((case_id,))
    exams = _FakeExams(claimed)
    quizzes = _FakeQuizzes({case_id: _detail(case_id, gold_id)})
    quizzes.error = "forbidden"
    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=_hybrid_retrieve((gold_id,), gold_id),
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        admit=_admit_factory(),
        prepare=_prepare_ok,
        true_up=_noop_true_up,
        connect=_Conn,
    )
    runner.run_once(_caller())
    assert exams.finalized == [(False, "forbidden")]
    assert exams.persisted == []


def test_exam_does_not_write_process_hybrid_budget() -> None:
    """Ask and exam share a process adapter only; exam never assigns its budget."""

    gold_id = uuid4()
    case_id = uuid4()
    claimed = _claimed((case_id,))
    exams = _FakeExams(claimed)
    quizzes = _FakeQuizzes({case_id: _detail(case_id, gold_id)})
    process = SimpleNamespace(query_budget=None)
    seen_budget: list[object] = []

    def retrieve(
        *,
        query: str,
        caller: CallerContext,
        profile: object,
        query_budget: object,
        cache_mode: RetrievalCacheMode,
        deadline_seconds: float | None = None,
    ) -> HybridRunResult:
        """Record the run ledger without touching the process adapter.

        Args:
            query: Case question.
            caller: Examiner.
            profile: Typed profile.
            query_budget: Per-run ledger.
            cache_mode: Cache mode.
            deadline_seconds: Remaining slice.

        Returns:
            Frozen Hybrid result.
        """

        del query, caller, profile, cache_mode, deadline_seconds
        seen_budget.append(query_budget)
        return _hybrid((gold_id,), gold_id)

    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=retrieve,
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        process_hybrid=process,
        admit=_admit_factory(),
        prepare=_prepare_ok,
        true_up=_noop_true_up,
        connect=_Conn,
    )
    runner.run_once(_caller())
    assert process.query_budget is None
    assert seen_budget
    assert seen_budget[0] is not None


def test_process_hybrid_budget_mutation_fails_closed() -> None:
    """A mutated process adapter budget cannot publish an official report."""

    gold_id = uuid4()
    case_id = uuid4()
    claimed = _claimed((case_id,))
    exams = _FakeExams(claimed)
    quizzes = _FakeQuizzes({case_id: _detail(case_id, gold_id)})
    process = SimpleNamespace(query_budget=None)

    def retrieve(
        *,
        query: str,
        caller: CallerContext,
        profile: object,
        query_budget: object,
        cache_mode: RetrievalCacheMode,
        deadline_seconds: float | None = None,
    ) -> HybridRunResult:
        """Simulate a concurrent Ask write onto the process adapter.

        Args:
            query: Case question.
            caller: Examiner.
            profile: Typed profile.
            query_budget: Per-run ledger.
            cache_mode: Cache mode.
            deadline_seconds: Remaining slice.

        Returns:
            Frozen Hybrid result.
        """

        del query, caller, profile, query_budget, cache_mode, deadline_seconds
        process.query_budget = object()
        return _hybrid((gold_id,), gold_id)

    runner = ExamRunner(
        exams=exams,
        quizzes=quizzes,
        retrieve=retrieve,
        postgres_url="postgresql://app_api@127.0.0.1/app",
        lease_owner="exam-test-owner",
        process_hybrid=process,
        admit=_admit_factory(),
        prepare=_prepare_ok,
        true_up=_noop_true_up,
        connect=_Conn,
    )
    runner.run_once(_caller())
    assert exams.finalized == [(False, "process_budget_mutated")]
