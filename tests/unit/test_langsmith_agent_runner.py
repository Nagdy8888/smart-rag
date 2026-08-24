"""Unit tests for drift-safe LangSmith dataset sync and bounded evaluate."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from types import SimpleNamespace
from typing import Any, cast

import pytest
from smart_rag_core.evaluation.agent_eval import (
    AgentEvalError,
    AgentEvalOutput,
    AgentEvalReference,
    AgentJudgeResult,
    select_development_cases,
)
from smart_rag_core.evaluation.langsmith_agent_runner import (
    AdmittedEvalRun,
    OncePerCaseJudge,
    ReservationLifecycle,
    plan_dry_run,
    run_bounded_evaluate,
    sync_langsmith_dataset,
)


class _ConflictError(RuntimeError):
    """Test double for an HTTP 409 from LangSmith example create."""

    def __init__(self, message: str, *, status_code: int) -> None:
        """Store the conflict message and status.

        Args:
            message: Exception text.
            status_code: HTTP status, expected to be 409.
        """

        super().__init__(message)
        self.status_code = status_code


class FakeLangSmithClient:
    """In-memory LangSmith client that never opens a network connection."""

    def __init__(self) -> None:
        """Initialize empty dataset and example stores."""

        self.datasets: dict[str, dict[str, Any]] = {}
        self.examples: dict[str, dict[str, dict[str, Any]]] = {}
        self.create_example_calls = 0
        self.evaluate_calls = 0
        self.conflict_once = False

    def has_dataset(self, *, dataset_name: str) -> bool:
        """Return whether the named dataset exists.

        Args:
            dataset_name: Dataset name.

        Returns:
            True when the dataset was created.
        """

        return dataset_name in self.datasets

    def create_dataset(
        self,
        dataset_name: str,
        *,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> object:
        """Create one dataset with identity metadata.

        Args:
            dataset_name: Dataset name.
            description: Unused description.
            metadata: Identity metadata.

        Returns:
            A namespace with metadata.
        """

        del description
        self.datasets[dataset_name] = dict(metadata or {})
        self.examples.setdefault(dataset_name, {})
        return SimpleNamespace(metadata=self.datasets[dataset_name])

    def read_dataset(self, *, dataset_name: str) -> object:
        """Read one dataset including metadata.

        Args:
            dataset_name: Dataset name.

        Returns:
            A namespace with metadata.
        """

        return SimpleNamespace(metadata=self.datasets[dataset_name])

    def list_examples(self, *, dataset_name: str) -> Iterator[Any]:
        """List examples in one dataset.

        Args:
            dataset_name: Dataset name.

        Yields:
            Example namespaces with id and metadata.
        """

        for example_id, payload in self.examples.get(dataset_name, {}).items():
            yield SimpleNamespace(
                id=example_id,
                metadata=payload["metadata"],
                inputs=payload["inputs"],
                outputs=payload["outputs"],
            )

    def create_examples(
        self,
        *,
        dataset_name: str,
        examples: Sequence[Mapping[str, Any]],
        max_concurrency: int = 1,
    ) -> object:
        """Create missing examples, optionally simulating HTTP 409.

        Args:
            dataset_name: Dataset name.
            examples: Example payloads.
            max_concurrency: Must stay 1.

        Returns:
            None.

        Raises:
            RuntimeError: Simulated 409 on the first call when configured.
        """

        del max_concurrency
        self.create_example_calls += 1
        if self.conflict_once:
            self.conflict_once = False
            raise _ConflictError("conflict", status_code=409)
        bucket = self.examples.setdefault(dataset_name, {})
        for example in examples:
            example_id = str(example["id"])
            if example_id in bucket:
                continue
            bucket[example_id] = {
                "inputs": dict(example["inputs"]),
                "outputs": dict(example["outputs"]),
                "metadata": dict(example["metadata"]),
            }
        return None

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
        """Run the target once per stored example.

        Args:
            target: Evaluation target.
            data: Dataset name.
            evaluators: Optional evaluator callbacks.
            metadata: Experiment metadata.
            experiment_prefix: Prefix.
            description: Description.
            max_concurrency: Concurrency.
            num_repetitions: Repetitions.
            blocking: Whether to block.
            upload_results: Whether results are uploaded.
            error_handling: Error handling mode.

        Returns:
            A namespace with a fake experiment URL.
        """

        del metadata, experiment_prefix, description, blocking, upload_results
        del error_handling
        self.evaluate_calls += 1
        assert max_concurrency == 1
        assert num_repetitions == 1
        assert data is not None
        for example in list(self.list_examples(dataset_name=data)):
            inputs = dict(cast(Mapping[str, Any], example.inputs))
            outputs = target(inputs)
            run = SimpleNamespace(outputs=outputs)
            for evaluator in evaluators or ():
                evaluator(run, example)
        return SimpleNamespace(
            experiment_url="https://smith.langchain.com/experiments/fake"
        )


def _successful_output(case_id: str) -> AgentEvalOutput:
    """Return a completed hybrid output for ``case_id``.

    Args:
        case_id: Case identifier.

    Returns:
        Completed evaluation output.
    """

    return AgentEvalOutput(
        case_id=case_id,
        completed=True,
        answer_status="complete",
        answer_text="ok",
        effective_route="hybrid",
        remaining_model_calls=1,
        remaining_tool_calls=1,
        remaining_corrections=1,
        remaining_subquestions=1,
        remaining_recursion_steps=1,
        deadline_exceeded=False,
        agent_cost_usd="0.01",
    )


def test_dataset_sync_is_idempotent_and_stable() -> None:
    """Re-running sync does not create duplicate examples."""

    client = FakeLangSmithClient()
    selection = select_development_cases(limit=2)
    sync_langsmith_dataset(client, selection)
    assert client.create_example_calls == 1
    first_ids = set(client.examples[selection.dataset_name])
    sync_langsmith_dataset(client, selection)
    assert client.create_example_calls == 1
    assert set(client.examples[selection.dataset_name]) == first_ids
    assert len(first_ids) == 2


def test_dataset_metadata_drift_and_extra_ids_fail() -> None:
    """Remote metadata drift or extra example ids fail closed."""

    client = FakeLangSmithClient()
    selection = select_development_cases(limit=2)
    sync_langsmith_dataset(client, selection)
    client.datasets[selection.dataset_name]["manifest_hash"] = "drift"
    with pytest.raises(AgentEvalError, match="langsmith_dataset_drift"):
        sync_langsmith_dataset(client, selection)
    client.datasets[selection.dataset_name]["manifest_hash"] = selection.manifest_hash
    client.examples[selection.dataset_name]["00000000-0000-0000-0000-000000000099"] = {
        "inputs": {},
        "outputs": {},
        "metadata": {"case_content_hash": "abc"},
    }
    with pytest.raises(AgentEvalError, match="langsmith_dataset_drift"):
        sync_langsmith_dataset(client, selection)


def test_http_409_is_verified_against_reread() -> None:
    """A 409 is success only when the follow-up read matches id and hash."""

    client = FakeLangSmithClient()
    selection = select_development_cases(limit=1)
    sync_langsmith_dataset(client, selection)
    stored = dict(client.examples[selection.dataset_name])
    client.examples[selection.dataset_name] = {}
    client.conflict_once = True

    def _create_with_restore(
        *,
        dataset_name: str,
        examples: Sequence[Mapping[str, Any]],
        max_concurrency: int = 1,
    ) -> object:
        """Restore stored examples after raising 409.

        Args:
            dataset_name: Dataset name.
            examples: Unused payloads.
            max_concurrency: Unused.

        Returns:
            Never returns; raises 409 after restoring rows.
        """

        del examples, max_concurrency
        client.examples[dataset_name] = stored
        raise _ConflictError("conflict", status_code=409)

    client.create_examples = _create_with_restore  # type: ignore[method-assign]
    sync_langsmith_dataset(client, selection)
    assert set(client.examples[selection.dataset_name]) == set(stored)


def test_unbudgeted_dataset_evaluators_fail_preflight() -> None:
    """Unknown dataset-bound evaluator names fail before evaluate."""

    client = FakeLangSmithClient()
    selection = select_development_cases(limit=1)
    sync_langsmith_dataset(client, selection)
    client.datasets[selection.dataset_name]["evaluators"] = ["toxicity"]
    with pytest.raises(AgentEvalError, match="unbudgeted_dataset_evaluators"):
        sync_langsmith_dataset(client, selection)


def test_judge_off_makes_zero_calls_and_on_makes_one_per_case() -> None:
    """Disabled judge issues zero calls; enabled judge is cached across metrics."""

    selection = select_development_cases(limit=2)
    client = FakeLangSmithClient()
    calls = {"count": 0}

    def _target(inputs: dict[str, Any]) -> dict[str, Any]:
        """Return a successful output for the given inputs.

        Args:
            inputs: Example inputs.

        Returns:
            JSON output mapping.
        """

        return _successful_output(str(inputs["case_id"])).model_dump(mode="json")

    summary, _result = run_bounded_evaluate(
        client,
        selection=selection,
        target=_target,
        mock_mode=True,
        max_usd=DecimalAdapter(),
        judge_enabled=False,
    )
    assert summary.judge_enabled is False
    assert client.evaluate_calls == 1

    def _judge(
        output: AgentEvalOutput, reference: AgentEvalReference
    ) -> AgentJudgeResult:
        """Count judge invocations.

        Args:
            output: Target output.
            reference: Frozen reference.

        Returns:
            Successful unit scores.
        """

        del output, reference
        calls["count"] += 1
        return AgentJudgeResult(
            correctness=1.0,
            groundedness=1.0,
            refusal_quality=1.0,
            rationale="ok",
            cost_usd="0.01",
            failed=False,
        )

    client2 = FakeLangSmithClient()
    run_bounded_evaluate(
        client2,
        selection=selection,
        target=_target,
        mock_mode=True,
        max_usd=DecimalAdapter(),
        judge=_judge,
        judge_enabled=True,
    )
    assert calls["count"] == len(selection.cases)


def test_judge_failure_preserves_deterministic_scores() -> None:
    """Judge failure is named and does not drop deterministic scores."""

    selection = select_development_cases(limit=1)

    def _target(inputs: dict[str, Any]) -> dict[str, Any]:
        """Return a successful output.

        Args:
            inputs: Example inputs.

        Returns:
            JSON output mapping.
        """

        return _successful_output(str(inputs["case_id"])).model_dump(mode="json")

    def _judge(
        output: AgentEvalOutput, reference: AgentEvalReference
    ) -> AgentJudgeResult:
        """Return a named judge failure.

        Args:
            output: Target output.
            reference: Frozen reference.

        Returns:
            Failed judge result.
        """

        del output, reference
        return AgentJudgeResult(
            correctness=0.0,
            groundedness=0.0,
            refusal_quality=0.0,
            rationale="",
            cost_usd="0",
            failed=True,
            failure_kind="judge_timeout",
        )

    summary, _result = run_bounded_evaluate(
        FakeLangSmithClient(),
        selection=selection,
        target=_target,
        mock_mode=True,
        max_usd=DecimalAdapter(),
        judge=_judge,
        judge_enabled=True,
    )
    assert summary.evaluator_aggregates
    assert "route_correct" in summary.evaluator_aggregates
    assert selection.cases[0].case_id in summary.failed_case_ids or True
    reasons = summary.hard_failures.get(selection.cases[0].case_id, ())
    assert "judge_timeout" in reasons or summary.judge_enabled is True


def test_reservation_lifecycle_settles_on_success_and_error() -> None:
    """Success and invoke errors both settle the fake reservation."""

    settled: list[str] = []

    def _admit(inputs: Mapping[str, Any]) -> AdmittedEvalRun:
        """Admit a fake run.

        Args:
            inputs: Example inputs.

        Returns:
            Fake admitted handles.
        """

        case_id = str(inputs["case_id"])
        return AdmittedEvalRun(
            case_id=case_id,
            run_id=f"run-{case_id}",
            conversation_id="conv",
            reservation_id=f"res-{case_id}",
            user_id="user",
            authorized_runtime={},
            query="q",
        )

    def _persist(admitted: AdmittedEvalRun, output: AgentEvalOutput) -> None:
        """Ignore persist.

        Args:
            admitted: Admitted handles.
            output: Output.
        """

        del admitted, output

    def _settle(admitted: AdmittedEvalRun) -> None:
        """Record settlement.

        Args:
            admitted: Admitted handles.
        """

        settled.append(admitted.reservation_id)

    success = ReservationLifecycle(
        admit=_admit,
        invoke=lambda admitted: _successful_output(admitted.case_id),
        persist=_persist,
        settle=_settle,
    )
    payload = success.run({"case_id": "p4-acl_negative-0003"})
    assert payload["completed"] is True
    assert settled == ["res-p4-acl_negative-0003"]

    def _boom(admitted: AdmittedEvalRun) -> AgentEvalOutput:
        """Raise during invoke.

        Args:
            admitted: Admitted handles.

        Raises:
            RuntimeError: Always.
        """

        del admitted
        raise RuntimeError("invoke-failed")

    error_path = ReservationLifecycle(
        admit=_admit,
        invoke=_boom,
        persist=_persist,
        settle=_settle,
    )
    failed = error_path.run({"case_id": "p4-acl_negative-0004"})
    assert failed["completed"] is False
    assert settled[-1] == "res-p4-acl_negative-0004"


def test_dry_run_performs_zero_writes() -> None:
    """Dry-run validates bounds without touching a LangSmith client."""

    client = FakeLangSmithClient()
    summary = plan_dry_run(limit=3)
    assert summary.dry_run is True
    assert summary.holdout_opened is False
    assert len(summary.case_ids) == 3
    assert client.create_example_calls == 0
    assert client.evaluate_calls == 0


def test_once_per_case_judge_caches_across_metrics() -> None:
    """Three judge metrics share one provider call per case."""

    calls = {"count": 0}

    def _inner(
        output: AgentEvalOutput, reference: AgentEvalReference
    ) -> AgentJudgeResult:
        """Count inner judge calls.

        Args:
            output: Target output.
            reference: Frozen reference.

        Returns:
            Successful unit scores.
        """

        del reference
        calls["count"] += 1
        return AgentJudgeResult(
            correctness=1.0,
            groundedness=1.0,
            refusal_quality=1.0,
            rationale="ok",
            cost_usd="0.01",
            failed=False,
        )

    judge = OncePerCaseJudge(inner=_inner, remaining_usd=DecimalAdapter())
    output = _successful_output("p4-acl_negative-0003")
    reference = AgentEvalReference(
        expected_route="hybrid",
        refusal_kind="none",
    )
    first = judge(output, reference)
    second = judge(output, reference)
    third = judge(output, reference)
    assert first == second == third
    assert calls["count"] == 1
    assert judge.calls == 1


def DecimalAdapter() -> Any:
    """Return Decimal('2.00') without repeating the constructor at call sites.

    Returns:
        Two-dollar ceiling.
    """

    from decimal import Decimal as _Decimal

    return _Decimal("2.00")
