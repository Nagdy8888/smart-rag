"""Emit bounded synthetic traces for hosted LangSmith online evaluators.

This path invokes the admitted production graph sequentially. It never
creates a dataset, experiment, or ``Client.evaluate`` job. Holdout stays
sealed. The local ``--llm-judge`` path is not used here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.evaluation.agent_eval import (
    AgentEvalError,
    AgentEvalOutput,
    AgentEvalSelection,
    failed_target_output,
    parse_target_output,
)
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.langsmith_agent_runner import (
    ReservationLifecycle,
    assert_agent_eval_execution_bounds,
)
from smart_rag_core.evaluation.online import (
    AGENT_ONLINE_EVAL_SCHEMA_VERSION,
    APPLICATION_LANGSMITH_PROJECT,
    ONLINE_EVAL_MAX_CASES,
    ONLINE_EVAL_MAX_USD,
    ONLINE_EVAL_PROJECT,
    ONLINE_EVAL_SAMPLING_RATE,
    ONLINE_EVAL_SPEND_WINDOW,
    QUERY_AGENT_ONLINE_EVAL_RUN,
    assert_online_eval_permitted,
)
from smart_rag_core.evaluation.online_envelope import (
    OnlineEvalEnvelope,
    build_online_envelope,
    sample_online_envelope,
)
from smart_rag_core.evaluation.online_suite import (
    load_online_eval_selection,
    load_online_suite_manifest,
    online_suite_hash,
)
from smart_rag_core.evaluation.schema import EvaluationCase
from smart_rag_core.settings import SharedSettings


class OnlineEvalPlan(BaseModel):
    """Secret-free plan or result for one online-evaluation invocation.

    Attributes:
        mode: Always ``online``. Distinguishes this path from ``Client.evaluate``.
        project: Dedicated tracing project.
        application_project: Normal application project that stays untouched.
        root_run_name: Exact evaluated run name.
        trace_schema_version: Envelope schema.
        suite_hash: SHA-256 of suite identity and ordered ids.
        manifest_hash: Selected-set content hash from development cases.
        case_ids: Ordered selected identifiers.
        query_classes: Ordered unique query classes.
        languages: Ordered unique languages.
        expected_routes: Ordered unique labeled routes.
        holdout_opened: Always false.
        selected_case_count: Number of traces this invocation will emit.
        max_traces: Hard ceiling.
        sampling_rate: Online rule sampling rate.
        spend_limit_usd: Weekly evaluator spend cap.
        spend_window: Spend-cap window.
        backfill: Always false.
        concurrency: Always 1.
        repetitions: Always 1.
        local_judge: Always false. The hosted judge is the sole judge.
        dataset_created: Always false.
        experiment_created: Always false.
        envelope_valid: True when every selected case built a valid envelope.
        application_project_untouched: Always true for this tool.
        dry_run: True when no LangSmith, database, agent, or provider work ran.
        writes: True when traces were emitted.
        run_ids: Application run ids keyed by case id.
        trace_names: Root run names actually used.
        failed_case_ids: Cases whose target did not complete.
        bm25_degraded: True when ParadeDB fallback was permitted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["online"] = "online"
    project: Literal["smart-rag-agent-eval-online"] = ONLINE_EVAL_PROJECT
    application_project: Literal["smart-rag"] = APPLICATION_LANGSMITH_PROJECT
    root_run_name: Literal["query.agent.eval.online.v1"] = QUERY_AGENT_ONLINE_EVAL_RUN
    trace_schema_version: Literal["agent-online-eval-v1"] = (
        AGENT_ONLINE_EVAL_SCHEMA_VERSION
    )
    suite_hash: str
    manifest_hash: str
    case_ids: tuple[str, ...]
    query_classes: tuple[str, ...]
    languages: tuple[str, ...]
    expected_routes: tuple[str, ...]
    holdout_opened: Literal[False] = False
    selected_case_count: int = Field(ge=0, le=ONLINE_EVAL_MAX_CASES)
    max_traces: int = ONLINE_EVAL_MAX_CASES
    sampling_rate: float = ONLINE_EVAL_SAMPLING_RATE
    spend_limit_usd: str = format(ONLINE_EVAL_MAX_USD, "f")
    spend_window: Literal["weekly"] = ONLINE_EVAL_SPEND_WINDOW
    backfill: Literal[False] = False
    concurrency: Literal[1] = 1
    repetitions: Literal[1] = 1
    local_judge: Literal[False] = False
    dataset_created: Literal[False] = False
    experiment_created: Literal[False] = False
    envelope_valid: bool
    application_project_untouched: Literal[True] = True
    dry_run: bool
    writes: bool
    run_ids: dict[str, str] = Field(default_factory=dict)
    trace_names: tuple[str, ...] = ()
    failed_case_ids: tuple[str, ...] = ()
    bm25_degraded: bool = False


def plan_online_dry_run(
    *,
    limit: int | None = None,
    case_ids: Sequence[str] = (),
    query_classes: Sequence[str] = (),
    holdout_access: HoldoutAccess | None = None,
    mock_mode: bool = True,
    max_usd: Decimal = ONLINE_EVAL_MAX_USD,
) -> OnlineEvalPlan:
    """Validate the frozen suite and envelope with zero external writes.

    Args:
        limit: Optional prefix of the frozen suite.
        case_ids: Optional suite subset.
        query_classes: Optional class filter.
        holdout_access: Must remain denied.
        mock_mode: Whether mock adapters are required.
        max_usd: Job USD ceiling. Must stay at or below USD 2.

    Returns:
        Secret-free plan. No LangSmith, database, agent, or provider work.

    Raises:
        AgentEvalError: Suite, envelope, holdout, or bound checks fail.
    """

    access = holdout_access if holdout_access is not None else HoldoutAccess.denied()
    if access.allowed:
        raise AgentEvalError("holdout_forbidden")
    selection = load_online_eval_selection(
        limit=limit,
        case_ids=case_ids,
        query_classes=query_classes,
        holdout_access=HoldoutAccess.denied(),
    )
    assert_agent_eval_execution_bounds(
        max_concurrency=1,
        num_repetitions=1,
        max_usd=max_usd,
        unlimited_openai=False,
        mock_mode=mock_mode,
        case_count=len(selection.cases),
        holdout_access=HoldoutAccess.denied(),
    )
    envelopes = [sample_online_envelope(case) for case in selection.cases]
    return _plan_from_selection(
        selection,
        envelopes=envelopes,
        dry_run=True,
        writes=False,
    )


def run_online_eval_batch(
    lifecycle: ReservationLifecycle,
    selection: AgentEvalSelection,
    *,
    settings: SharedSettings,
    emit_root: Callable[..., Mapping[str, object]] | None = None,
    bm25_degraded: bool = False,
) -> OnlineEvalPlan:
    """Invoke the admitted graph once per suite case and emit online roots.

    Args:
        lifecycle: Admit/invoke/persist/settle closures.
        selection: Frozen-suite selection.
        settings: Process settings. Must already permit tracing.
        emit_root: Optional emitter used by tests. Defaults to the dedicated
            LangSmith parent helper.
        bm25_degraded: Recorded when ParadeDB fallback was permitted.

    Returns:
        Result summary. Dataset and experiment flags stay false.

    Raises:
        AgentEvalError: Holdout or bound checks fail.

    Side Effects:
        Runs the production graph and exports one dedicated root per case.
        Does not call ``Client.evaluate`` or create a dataset.
    """

    assert_online_eval_permitted(
        mock_mode=settings.mock_model_mode,
        case_count=len(selection.cases),
        max_usd=ONLINE_EVAL_MAX_USD,
        holdout_access=HoldoutAccess.denied(),
        unlimited_openai=False,
    )
    emitter = emit_root
    if emitter is None:
        from smart_rag_core.observability.query_run_trace import emit_online_eval_root

        emitter = emit_online_eval_root
    cases_by_id = {case.case_id: case for case in selection.cases}
    run_ids: dict[str, str] = {}
    failed: list[str] = []
    envelopes: list[OnlineEvalEnvelope] = []
    for case in selection.cases:
        output = _run_one_case(
            lifecycle,
            case,
            settings=settings,
            emit_root=emitter,
        )
        if output.run_id:
            run_ids[case.case_id] = output.run_id
        if not output.completed:
            failed.append(case.case_id)
        envelopes.append(build_online_envelope(cases_by_id[case.case_id], output))
    return _plan_from_selection(
        selection,
        envelopes=envelopes,
        dry_run=False,
        writes=True,
        run_ids=run_ids,
        failed_case_ids=tuple(failed),
        bm25_degraded=bm25_degraded,
        trace_names=tuple(QUERY_AGENT_ONLINE_EVAL_RUN for _ in selection.cases),
    )


def _run_one_case(
    lifecycle: ReservationLifecycle,
    case: EvaluationCase,
    *,
    settings: SharedSettings,
    emit_root: Callable[..., Mapping[str, object]],
) -> AgentEvalOutput:
    """Run one suite case under the dedicated online parent.

    Args:
        lifecycle: Reservation lifecycle.
        case: Synthetic development case.
        settings: Process settings.
        emit_root: Parent-span emitter.

    Returns:
        Normalized graph output. Infrastructure failures stay named.
    """

    envelope = sample_online_envelope(case)
    captured: dict[str, AgentEvalOutput] = {}

    def produce_outputs() -> dict[str, object]:
        """Admit, invoke, persist, and settle, then return envelope outputs.

        Returns:
            JSON-compatible online outputs.
        """

        raw = lifecycle.run(
            {
                "case_id": case.case_id,
                "query": case.query,
                "language": case.language,
                "query_class": case.query_class.value,
            }
        )
        output = parse_target_output(raw)
        captured["output"] = output
        return build_online_envelope(case, output).outputs.model_dump(mode="json")

    try:
        emit_root(
            produce_outputs,
            settings=settings,
            inputs=envelope.inputs.model_dump(mode="json"),
        )
    except Exception:
        captured.setdefault(
            "output",
            failed_target_output(case.case_id, failure_kind="online_emit_failed"),
        )
    return captured.get(
        "output",
        failed_target_output(case.case_id, failure_kind="online_output_missing"),
    )


def _plan_from_selection(
    selection: AgentEvalSelection,
    *,
    envelopes: Sequence[OnlineEvalEnvelope],
    dry_run: bool,
    writes: bool,
    run_ids: dict[str, str] | None = None,
    failed_case_ids: tuple[str, ...] = (),
    bm25_degraded: bool = False,
    trace_names: tuple[str, ...] = (),
) -> OnlineEvalPlan:
    """Build the secret-free online plan from a validated selection.

    Args:
        selection: Frozen-suite selection.
        envelopes: Validated envelopes, one per case.
        dry_run: Whether any external work ran.
        writes: Whether traces were emitted.
        run_ids: Application run ids.
        failed_case_ids: Incomplete cases.
        bm25_degraded: ParadeDB fallback flag.
        trace_names: Emitted root names.

    Returns:
        Typed plan.
    """

    manifest = load_online_suite_manifest()
    return OnlineEvalPlan(
        suite_hash=online_suite_hash(manifest),
        manifest_hash=selection.manifest_hash,
        case_ids=tuple(case.case_id for case in selection.cases),
        query_classes=tuple(
            dict.fromkeys(case.query_class.value for case in selection.cases)
        ),
        languages=tuple(dict.fromkeys(case.language for case in selection.cases)),
        expected_routes=tuple(
            dict.fromkeys(case.expected_route.value for case in selection.cases)
        ),
        selected_case_count=len(selection.cases),
        envelope_valid=len(envelopes) == len(selection.cases),
        dry_run=dry_run,
        writes=writes,
        run_ids=run_ids or {},
        failed_case_ids=failed_case_ids,
        bm25_degraded=bm25_degraded,
        trace_names=trace_names,
    )
