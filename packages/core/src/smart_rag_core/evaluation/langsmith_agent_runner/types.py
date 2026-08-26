"""LangSmith agent-eval client protocols and run handles."""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, cast

from smart_rag_core.evaluation.agent_eval import (
    AgentEvalOutput,
    AgentEvalReference,
    AgentJudgeResult,
    failed_target_output,
    output_from_graph_state,
    parse_target_output,
)

REPO_ROOT = Path(__file__).resolve().parents[6]

ALLOWED_EVALUATOR_KEYS = frozenset(
    {
        "route_correct",
        "refusal_correct",
        "citation_precision",
        "citation_recall",
        "acl_leak_free",
        "profile_fields_correct",
        "bounds_respected",
        "answer_reference_overlap",
        "target_completed",
        "judge_correctness",
        "judge_groundedness",
        "judge_refusal_quality",
    }
)

_DATASET_METADATA_KEYS = (
    "schema_version",
    "label_revision",
    "split",
    "manifest_hash",
    "agent_eval_schema_version",
    "redaction_class",
    "holdout_opened",
)


class LangSmithEvalClient(Protocol):
    """Subset of LangSmith ``Client`` used by this runner."""

    def has_dataset(self, *, dataset_name: str) -> bool:
        """Return whether the named dataset exists."""

        ...

    def create_dataset(
        self,
        dataset_name: str,
        *,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> object:
        """Create one dataset with exact identity metadata."""

        ...

    def read_dataset(self, *, dataset_name: str) -> object:
        """Read one dataset including metadata."""

        ...

    def list_examples(self, *, dataset_name: str) -> Iterator[object]:
        """List examples in one dataset."""

        ...

    def create_examples(
        self,
        *,
        dataset_name: str,
        examples: Sequence[Mapping[str, Any]],
        max_concurrency: int = 1,
    ) -> object:
        """Create missing examples. HTTP 409 is not success by itself."""

        ...

    def evaluate(
        self,
        target: Callable[[dict[str, Any]], dict[str, Any]],
        /,
        data: str | None = None,
        evaluators: Sequence[Callable[..., Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        experiment_prefix: str | None = None,
        description: str | None = None,
        max_concurrency: int | None = 0,
        num_repetitions: int = 1,
        blocking: bool = True,
        upload_results: bool = True,
        error_handling: str = "log",
    ) -> object:
        """Run one bounded experiment."""

        ...


@dataclass
class AdmittedEvalRun:
    """Admitted-run handles used by the reservation lifecycle.

    Attributes:
        case_id: Synthetic case identifier.
        run_id: Application run id.
        conversation_id: Conversation id.
        reservation_id: Budget reservation id.
        user_id: Authenticated subject id.
        authorized_runtime: JSON dump of authorized runtime context.
        query: Synthetic user query.
    """

    case_id: str
    run_id: str
    conversation_id: str
    reservation_id: str
    user_id: str
    authorized_runtime: dict[str, object]
    query: str


@dataclass
class ReservationLifecycle:
    """Admit, invoke, persist, and always true-up one evaluation case."""

    admit: Callable[[Mapping[str, Any]], AdmittedEvalRun]
    invoke: Callable[[AdmittedEvalRun], object]
    persist: Callable[[AdmittedEvalRun, AgentEvalOutput], None]
    settle: Callable[[AdmittedEvalRun], None]

    def run(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        """Execute one case and always settle the reservation.

        Args:
            inputs: LangSmith example inputs containing ``case_id``.

        Returns:
            JSON-compatible ``AgentEvalOutput``. Infrastructure failures still
            produce a scored failed row.
        """

        case_id = str(inputs.get("case_id") or "unknown")
        admitted: AdmittedEvalRun | None = None
        try:
            admitted = self.admit(inputs)
            raw = self.invoke(admitted)
            output = _coerce_output(case_id, admitted, raw)
            self.persist(admitted, output)
            return output.model_dump(mode="json")
        except Exception:
            failed = failed_target_output(case_id, failure_kind="target_invoke_failed")
            if admitted is not None:
                with contextlib.suppress(Exception):
                    self.persist(admitted, failed)
            return failed.model_dump(mode="json")
        finally:
            if admitted is not None:
                self.settle(admitted)


@dataclass
class OncePerCaseJudge:
    """Ensure at most one judge provider call per case."""

    inner: Callable[[AgentEvalOutput, AgentEvalReference], AgentJudgeResult]
    remaining_usd: Decimal
    calls: int = 0
    results: dict[str, AgentJudgeResult] = field(
        default_factory=lambda: dict[str, AgentJudgeResult]()
    )
    stopped: bool = False

    def __call__(
        self, output: AgentEvalOutput, reference: AgentEvalReference
    ) -> AgentJudgeResult:
        """Return a cached judge result, or invoke once when budget remains.

        Args:
            output: Target output.
            reference: Frozen reference.

        Returns:
            Typed judge result. Budget exhaustion is a named failure.
        """

        cached = self.results.get(output.case_id)
        if cached is not None:
            return cached
        if output.case_id not in self.results:
            try:
                agent_cost = Decimal(output.agent_cost_usd)
            except (ArithmeticError, ValueError):
                agent_cost = Decimal("0")
            if agent_cost > 0:
                self.remaining_usd = max(Decimal("0"), self.remaining_usd - agent_cost)
        if self.stopped or self.remaining_usd <= 0:
            self.stopped = True
            result = AgentJudgeResult(
                correctness=0.0,
                groundedness=0.0,
                refusal_quality=0.0,
                rationale="",
                cost_usd="0",
                failed=True,
                failure_kind="judge_budget_exhausted",
            )
            self.results[output.case_id] = result
            return result
        result = self.inner(output, reference)
        self.calls += 1
        cost = Decimal(result.cost_usd)
        if cost > self.remaining_usd:
            self.stopped = True
        self.remaining_usd = max(Decimal("0"), self.remaining_usd - cost)
        self.results[output.case_id] = result
        return result


def _coerce_output(
    case_id: str,
    admitted: AdmittedEvalRun,
    result: object,
) -> AgentEvalOutput:
    """Normalize an invoke result into ``AgentEvalOutput``.

    Args:
        case_id: Case identifier.
        admitted: Admitted run handles.
        result: Typed output, JSON mapping, or final graph state.

    Returns:
        Typed evaluation output.
    """

    if isinstance(result, AgentEvalOutput):
        return result
    if isinstance(result, Mapping) and "completed" in result:
        return parse_target_output(cast(Mapping[str, Any], result))
    if isinstance(result, Mapping):
        mapped = cast(Mapping[str, Any], result)
        fusion = mapped.get("fusion")
        bm25 = None
        graph_degraded = False
        if isinstance(fusion, Mapping):
            fusion_map = cast(Mapping[str, Any], fusion)
            reason = fusion_map.get("fallback_reason")
            if isinstance(reason, str) and reason:
                bm25 = reason
                if "graph" in reason:
                    graph_degraded = True
        return output_from_graph_state(
            case_id,
            mapped,
            run_id=admitted.run_id,
            conversation_id=admitted.conversation_id,
            bm25_fallback=bm25,
            graph_degraded=graph_degraded,
        )
    return failed_target_output(case_id, failure_kind="target_output_invalid")
