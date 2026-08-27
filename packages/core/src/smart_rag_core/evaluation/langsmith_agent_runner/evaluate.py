"""Bounded evaluate execution and local dry-run planning."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

from smart_rag_core.evaluation.agent_eval import (
    AGENT_EVAL_SCHEMA_VERSION,
    AgentEvalError,
    AgentEvalOutput,
    AgentEvalReference,
    AgentEvalSelection,
    AgentEvalSummary,
    AgentJudgeResult,
    case_to_reference,
    decimal_sum,
    deterministic_evaluators,
    hard_failure_reasons,
    judge_evaluator,
    median_latency_ms,
    parse_target_output,
    sanitize_experiment_prefix,
    score_all,
    select_development_cases,
)
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.langsmith_agent_runner.dataset import (
    experiment_git_metadata,
    sync_langsmith_dataset,
)
from smart_rag_core.evaluation.langsmith_agent_runner.types import (
    OncePerCaseJudge,
)
from smart_rag_core.evaluation.online import (
    ONLINE_EVAL_MAX_USD,
    ONLINE_EVAL_MOCK_DEFAULT,
    assert_online_eval_permitted,
)
from smart_rag_core.evaluation.schema import (
    DATASET_SCHEMA_VERSION,
    DEFAULT_RETRIEVAL_PROFILE_ID,
    LABEL_REVISION,
)


def assert_agent_eval_execution_bounds(
    *,
    max_concurrency: int,
    num_repetitions: int,
    max_usd: Decimal,
    unlimited_openai: bool,
    mock_mode: bool,
    case_count: int,
    holdout_access: HoldoutAccess | None = None,
) -> None:
    """Fail closed when concurrency, repetitions, or online bounds are violated.

    Args:
        max_concurrency: Must be 1.
        num_repetitions: Must be 1.
        max_usd: Job cost ceiling.
        unlimited_openai: Forbidden.
        mock_mode: Whether mock adapters are required.
        case_count: Selected case count.
        holdout_access: Must remain denied.

    Raises:
        AgentEvalError: Concurrency, repetition, or holdout checks fail.
        OnlineEvalError: Online sample, USD, or unbounded OpenAI fail.
    """

    if max_concurrency != 1:
        raise AgentEvalError("concurrency_exceeds_ceiling")
    if num_repetitions != 1:
        raise AgentEvalError("repetitions_exceed_ceiling")
    access = holdout_access if holdout_access is not None else HoldoutAccess.denied()
    if access.allowed:
        raise AgentEvalError("holdout_forbidden")
    assert_online_eval_permitted(
        mock_mode=mock_mode,
        case_count=case_count,
        max_usd=max_usd,
        holdout_access=HoldoutAccess.denied(),
        unlimited_openai=unlimited_openai,
    )


def run_bounded_evaluate(
    client: Any,
    *,
    selection: AgentEvalSelection,
    target: Callable[[dict[str, Any]], dict[str, Any]],
    mock_mode: bool,
    max_usd: Decimal,
    judge: Callable[[AgentEvalOutput, AgentEvalReference], AgentJudgeResult]
    | None = None,
    judge_enabled: bool = False,
    experiment_prefix: str | None = None,
    bm25_degraded: bool = False,
    graph_degraded: bool = False,
    remaining_judge_usd: Decimal | None = None,
    extra_metadata: Mapping[str, object] | None = None,
) -> tuple[AgentEvalSummary, object]:
    """Synchronize the dataset and run ``Client.evaluate`` under hard bounds.

    Args:
        client: LangSmith client subset.
        selection: Validated development selection.
        target: Admitted-graph target returning ``AgentEvalOutput`` JSON.
        mock_mode: Whether mock adapters are required.
        max_usd: Job USD ceiling.
        judge: Optional one-call-per-case judge.
        judge_enabled: Whether judge evaluators are attached.
        experiment_prefix: Optional sanitized suffix.
        bm25_degraded: Whether BM25 fallback was explicitly allowed.
        graph_degraded: Whether graph retrieve is unbound.
        remaining_judge_usd: Remaining USD allocated to judge calls.
        extra_metadata: Optional model/prompt version fields merged into
            experiment metadata. Must not contain source text or secrets.

    Returns:
        Local summary and the SDK experiment result object.

    Raises:
        AgentEvalError: Bounds, drift, or unbudgeted evaluators fail.
        OnlineEvalError: Online ceilings fail.
    """

    access = HoldoutAccess.denied()
    assert_agent_eval_execution_bounds(
        max_concurrency=1,
        num_repetitions=1,
        max_usd=max_usd,
        unlimited_openai=False,
        mock_mode=mock_mode,
        case_count=len(selection.cases),
        holdout_access=access,
    )
    sync_langsmith_dataset(client, selection)
    prefix = "smart-rag-agent-eval"
    suffix = sanitize_experiment_prefix(experiment_prefix)
    if suffix:
        prefix = f"{prefix}-{suffix}"
    wrapped_judge: OncePerCaseJudge | None = None
    evaluators = list(deterministic_evaluators())
    if judge_enabled:
        if judge is None:
            raise AgentEvalError("judge_required")
        wrapped_judge = OncePerCaseJudge(
            inner=judge,
            remaining_usd=remaining_judge_usd
            if remaining_judge_usd is not None
            else max_usd,
        )
        for metric in ("correctness", "groundedness", "refusal_quality"):
            evaluators.append(judge_evaluator(wrapped_judge, metric=metric))
    collected: list[AgentEvalOutput] = []

    def _recorded_target(inputs: dict[str, Any]) -> dict[str, Any]:
        """Invoke the caller target and retain the typed output.

        Args:
            inputs: LangSmith example inputs.

        Returns:
            JSON-compatible output mapping.
        """

        raw = target(inputs)
        parsed = parse_target_output(raw)
        collected.append(parsed)
        return parsed.model_dump(mode="json")

    git_meta = experiment_git_metadata()
    experiment_metadata: dict[str, object] = {
        **git_meta,
        "dataset_name": selection.dataset_name,
        "manifest_hash": selection.manifest_hash,
        "schema_version": DATASET_SCHEMA_VERSION,
        "label_revision": LABEL_REVISION,
        "selected_case_ids": [case.case_id for case in selection.cases],
        "query_classes": list(_ordered_classes(selection)),
        "retrieval_profile_id": DEFAULT_RETRIEVAL_PROFILE_ID,
        "mock_mode": mock_mode,
        "judge_enabled": judge_enabled,
        "max_cases": len(selection.cases),
        "max_concurrency": 1,
        "num_repetitions": 1,
        "max_usd": format(max_usd, "f"),
        "bm25_degraded": bm25_degraded,
        "graph_degraded": graph_degraded,
        "holdout_opened": False,
        "agent_eval_schema_version": AGENT_EVAL_SCHEMA_VERSION,
    }
    if extra_metadata:
        experiment_metadata.update(dict(extra_metadata))
    result = client.evaluate(
        _recorded_target,
        data=selection.dataset_name,
        evaluators=evaluators,
        metadata=experiment_metadata,
        experiment_prefix=prefix,
        description=(
            "Bounded synthetic development agent evaluation. Not a quality claim."
        ),
        max_concurrency=1,
        num_repetitions=1,
        blocking=True,
        upload_results=True,
        error_handling="log",
    )
    if len(collected) != len(selection.cases):
        raise AgentEvalError("experiment_result_count_mismatch")
    summary = build_local_summary(
        selection,
        collected,
        experiment_url=_experiment_url(result),
        mock_mode=mock_mode,
        judge_enabled=judge_enabled,
        dry_run=False,
        bm25_degraded=bm25_degraded,
        graph_degraded=graph_degraded,
        judge_results=wrapped_judge.results if wrapped_judge is not None else {},
    )
    return summary, result


def plan_dry_run(
    *,
    limit: int,
    case_ids: Sequence[str] = (),
    query_classes: Sequence[str] = (),
    holdout_access: HoldoutAccess | None = None,
    mock_mode: bool = ONLINE_EVAL_MOCK_DEFAULT,
    max_usd: Decimal = ONLINE_EVAL_MAX_USD,
    judge_enabled: bool = False,
    experiment_prefix: str | None = None,
    unlimited_openai: bool = False,
    max_concurrency: int = 1,
    num_repetitions: int = 1,
) -> AgentEvalSummary:
    """Validate selection and bounds without LangSmith, DB, or provider work.

    Args:
        limit: Maximum cases.
        case_ids: Optional development ids.
        query_classes: Optional class filters.
        holdout_access: Must remain denied.
        mock_mode: Whether mock adapters are required.
        max_usd: Job USD ceiling.
        judge_enabled: Recorded in the plan only.
        experiment_prefix: Optional sanitized suffix.
        unlimited_openai: Forbidden.
        max_concurrency: Must be 1.
        num_repetitions: Must be 1.

    Returns:
        Dry-run summary with dataset identity and selected ids.
    """

    access = holdout_access if holdout_access is not None else HoldoutAccess.denied()
    selection = select_development_cases(
        limit=limit,
        case_ids=case_ids,
        query_classes=query_classes,
        holdout_access=access,
    )
    assert_agent_eval_execution_bounds(
        max_concurrency=max_concurrency,
        num_repetitions=num_repetitions,
        max_usd=max_usd,
        unlimited_openai=unlimited_openai,
        mock_mode=mock_mode,
        case_count=len(selection.cases),
        holdout_access=access,
    )
    sanitize_experiment_prefix(experiment_prefix)
    return build_local_summary(
        selection,
        (),
        experiment_url=None,
        mock_mode=mock_mode,
        judge_enabled=judge_enabled,
        dry_run=True,
        bm25_degraded=False,
        graph_degraded=False,
        judge_results={},
    )


def build_local_summary(
    selection: AgentEvalSelection,
    outputs: Sequence[AgentEvalOutput],
    *,
    experiment_url: str | None,
    mock_mode: bool,
    judge_enabled: bool,
    dry_run: bool,
    bm25_degraded: bool,
    graph_degraded: bool,
    judge_results: Mapping[str, AgentJudgeResult],
) -> AgentEvalSummary:
    """Build the machine-readable local summary. No source text or secrets.

    Args:
        selection: Validated selection.
        outputs: Target outputs in selection order, empty for dry-run.
        experiment_url: LangSmith experiment URL when a live run occurred.
        mock_mode: Whether mock adapters were required.
        judge_enabled: Whether the judge was requested.
        dry_run: Whether no writes occurred.
        bm25_degraded: Whether BM25 fallback was used or allowed.
        graph_degraded: Whether graph retrieve was unbound.
        judge_results: Optional judge payloads keyed by case id.

    Returns:
        Frozen summary. ``acl_leak_free=0`` is a hard failure.
    """

    references = {case.case_id: case_to_reference(case) for case in selection.cases}
    aggregates: dict[str, list[float]] = {}
    failed: list[str] = []
    hard: dict[str, tuple[str, ...]] = {}
    run_ids: dict[str, str] = {}
    agent_costs: list[str] = []
    judge_costs: list[str] = []
    latencies: list[int] = []
    any_bm25 = bm25_degraded
    any_graph = graph_degraded
    for output in outputs:
        reference = references[output.case_id]
        scores = score_all(output, reference)
        for key, value in scores.items():
            aggregates.setdefault(key, []).append(value)
        reasons = list(hard_failure_reasons(output, scores))
        judge = judge_results.get(output.case_id)
        if judge is not None:
            if judge.failed:
                reasons.append(judge.failure_kind or "judge_failed")
            judge_costs.append(judge.cost_usd)
        if reasons:
            failed.append(output.case_id)
            hard[output.case_id] = tuple(reasons)
        elif any(
            value == 0.0
            for key, value in scores.items()
            if key != "answer_reference_overlap"
        ):
            failed.append(output.case_id)
        if output.run_id:
            run_ids[output.case_id] = output.run_id
        agent_costs.append(output.agent_cost_usd)
        if output.latency_ms is not None:
            latencies.append(output.latency_ms)
        if output.bm25_fallback:
            any_bm25 = True
        if output.graph_degraded:
            any_graph = True
    mean_scores = {
        key: (sum(values) / len(values) if values else 0.0)
        for key, values in aggregates.items()
    }
    return AgentEvalSummary(
        dataset_name=selection.dataset_name,
        manifest_hash=selection.manifest_hash,
        experiment_url=experiment_url,
        case_ids=tuple(case.case_id for case in selection.cases),
        query_classes=_ordered_classes(selection),
        evaluator_aggregates=mean_scores,
        failed_case_ids=tuple(dict.fromkeys(failed)),
        hard_failures=hard,
        run_ids=run_ids,
        agent_cost_usd=decimal_sum(agent_costs),
        judge_cost_usd=decimal_sum(judge_costs),
        latency_ms_p50=median_latency_ms(latencies),
        bm25_degraded=any_bm25,
        graph_degraded=any_graph,
        holdout_opened=False,
        dry_run=dry_run,
        mock_mode=mock_mode,
        judge_enabled=judge_enabled,
        selected_case_count=len(selection.cases),
    )


def _ordered_classes(selection: AgentEvalSelection) -> tuple[str, ...]:
    """Return unique query classes in selection order.

    Args:
        selection: Validated selection.

    Returns:
        Ordered class names.
    """

    if selection.query_class_filters:
        return selection.query_class_filters
    return tuple(dict.fromkeys(case.query_class.value for case in selection.cases))


def _experiment_url(result: object) -> str | None:
    """Extract a LangSmith experiment URL when present.

    Args:
        result: SDK evaluate result.

    Returns:
        URL string or None.
    """

    for attr in ("experiment_url", "url"):
        value = getattr(result, attr, None)
        if isinstance(value, str) and value.startswith("https://"):
            return value
    if isinstance(result, Mapping):
        mapped = cast(Mapping[object, object], result)
        value = mapped.get("experiment_url") or mapped.get("url")
        if isinstance(value, str) and value.startswith("https://"):
            return value
    return None
