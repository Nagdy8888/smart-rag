"""Drift-safe LangSmith dataset sync and bounded ``Client.evaluate`` execution.

This module never imports backend or agent packages. Callers inject the
admitted-graph target. Holdout stays sealed. Dataset identity is the selected
development subset.
"""

from __future__ import annotations

import contextlib
import subprocess
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID

from smart_rag_core.evaluation.agent_eval import (
    AGENT_EVAL_SCHEMA_VERSION,
    AgentEvalError,
    AgentEvalOutput,
    AgentEvalReference,
    AgentEvalSelection,
    AgentEvalSummary,
    AgentJudgeResult,
    case_to_example_metadata,
    case_to_input,
    case_to_reference,
    decimal_sum,
    deterministic_evaluators,
    failed_target_output,
    hard_failure_reasons,
    judge_evaluator,
    median_latency_ms,
    output_from_graph_state,
    parse_target_output,
    sanitize_experiment_prefix,
    score_all,
    select_development_cases,
)
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.online import (
    ONLINE_EVAL_MAX_USD,
    ONLINE_EVAL_MOCK_DEFAULT,
    assert_online_eval_permitted,
)
from smart_rag_core.evaluation.schema import (
    DATASET_SCHEMA_VERSION,
    DEFAULT_RETRIEVAL_PROFILE_ID,
    LABEL_REVISION,
    DatasetSplit,
    EvaluationCase,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
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


def dataset_identity_metadata(selection: AgentEvalSelection) -> dict[str, object]:
    """Return LangSmith dataset metadata that must match on every rerun.

    Args:
        selection: Validated development selection.

    Returns:
        Identity metadata. Extra evaluator bindings are omitted on purpose.
    """

    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "label_revision": LABEL_REVISION,
        "split": DatasetSplit.DEVELOPMENT.value,
        "manifest_hash": selection.manifest_hash,
        "agent_eval_schema_version": AGENT_EVAL_SCHEMA_VERSION,
        "redaction_class": "synthetic",
        "holdout_opened": False,
    }


def experiment_git_metadata(*, repo_root: Path | None = None) -> dict[str, object]:
    """Capture git commit and dirty-tree state without printing secrets.

    Args:
        repo_root: Repository root. Defaults to this file's repo.

    Returns:
        ``git_commit`` hex and ``git_dirty`` boolean. Unknown git is dirty.
    """

    root = repo_root if repo_root is not None else REPO_ROOT
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        dirty_text = subprocess.check_output(
            ["git", "status", "--porcelain"],  # noqa: S607
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": "unknown", "git_dirty": True}
    return {"git_commit": commit, "git_dirty": bool(dirty_text.strip())}


def sync_langsmith_dataset(
    client: LangSmithEvalClient,
    selection: AgentEvalSelection,
) -> None:
    """Create or verify the versioned dataset. Extra remote IDs fail closed.

    Args:
        client: LangSmith client subset.
        selection: Validated development selection.

    Raises:
        AgentEvalError: Metadata drift, extra examples, hash mismatch,
            unbudgeted dataset evaluators, or unverified 409 conflict.
    """

    metadata = dataset_identity_metadata(selection)
    name = selection.dataset_name
    if not client.has_dataset(dataset_name=name):
        client.create_dataset(
            name,
            description=(
                "Synthetic development agent-eval cases. Holdout sealed. "
                "Not a quality claim."
            ),
            metadata=dict(metadata),
        )
    existing = client.read_dataset(dataset_name=name)
    remote_meta = _object_mapping(getattr(existing, "metadata", None))
    for key in _DATASET_METADATA_KEYS:
        if remote_meta.get(key) != metadata[key]:
            raise AgentEvalError("langsmith_dataset_drift")
    _assert_no_unbudgeted_evaluators(remote_meta)
    desired = {
        str(selection.example_ids[case.case_id]): selection.case_hashes[case.case_id]
        for case in selection.cases
    }
    remote_by_id = _index_remote_examples(client.list_examples(dataset_name=name))
    extra = set(remote_by_id) - set(desired)
    if extra:
        raise AgentEvalError("langsmith_dataset_drift")
    for example_id, case_hash in desired.items():
        remote = remote_by_id.get(example_id)
        if remote is None:
            continue
        if remote != case_hash:
            raise AgentEvalError("langsmith_dataset_drift")
    missing_ids = [item for item in desired if item not in remote_by_id]
    if not missing_ids:
        return
    examples = [
        _example_create_payload(selection, case)
        for case in selection.cases
        if str(selection.example_ids[case.case_id]) in missing_ids
    ]
    try:
        client.create_examples(dataset_name=name, examples=examples, max_concurrency=1)
    except Exception as exc:
        if not _is_conflict(exc):
            raise
        reread = _index_remote_examples(client.list_examples(dataset_name=name))
        for example_id, case_hash in desired.items():
            if reread.get(example_id) != case_hash:
                raise AgentEvalError("langsmith_dataset_drift") from exc
        return
    verified = _index_remote_examples(client.list_examples(dataset_name=name))
    for example_id, case_hash in desired.items():
        if verified.get(example_id) != case_hash:
            raise AgentEvalError("langsmith_dataset_drift")


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


def _example_create_payload(
    selection: AgentEvalSelection, case: EvaluationCase
) -> dict[str, Any]:
    """Build one LangSmith ``create_examples`` payload.

    Args:
        selection: Validated selection.
        case: Development case.

    Returns:
        Example mapping with stable id, inputs, reference outputs, metadata.
    """

    case_hash = selection.case_hashes[case.case_id]
    return {
        "id": str(selection.example_ids[case.case_id]),
        "inputs": case_to_input(case).model_dump(mode="json"),
        "outputs": case_to_reference(case).model_dump(mode="json"),
        "metadata": case_to_example_metadata(
            case, case_hash=case_hash, manifest_hash=selection.manifest_hash
        ),
    }


def _index_remote_examples(examples: Iterator[object]) -> dict[str, str]:
    """Index remote examples by id to case-content hash.

    Args:
        examples: LangSmith examples.

    Returns:
        Mapping of example id string to ``case_content_hash``.
    """

    indexed: dict[str, str] = {}
    for example in examples:
        example_id = _example_id(example)
        metadata = _object_mapping(getattr(example, "metadata", None))
        if not metadata and isinstance(example, Mapping):
            example_map = cast(Mapping[object, object], example)
            metadata = _object_mapping(example_map.get("metadata"))
            if not example_id:
                example_id = str(example_map.get("id") or "")
        hashed = str(metadata.get("case_content_hash") or "")
        if example_id:
            indexed[example_id] = hashed
    return indexed


def _example_id(example: object) -> str:
    """Return the example id as a string.

    Args:
        example: LangSmith example.

    Returns:
        UUID string, or empty.
    """

    raw: object = getattr(example, "id", None)
    if raw is None and isinstance(example, Mapping):
        raw = cast(Mapping[object, object], example).get("id")
    if raw is None:
        return ""
    if isinstance(raw, UUID):
        return str(raw)
    return str(raw)


def _object_mapping(value: object) -> dict[str, Any]:
    """Coerce dataset or example metadata to a string-keyed dict.

    Args:
        value: Mapping or None.

    Returns:
        Dict copy.
    """

    if isinstance(value, Mapping):
        typed = cast(Mapping[object, object], value)
        return {str(key): item for key, item in typed.items()}
    return {}


def _assert_no_unbudgeted_evaluators(metadata: Mapping[str, Any]) -> None:
    """Fail when the dataset binds unknown extra evaluators.

    Args:
        metadata: Dataset metadata.

    Raises:
        AgentEvalError: Unbudgeted evaluator names are present.
    """

    bound: list[str] = []
    for key in ("evaluators", "dataset_evaluators", "workspace_evaluators"):
        raw = metadata.get(key)
        if isinstance(raw, str) and raw:
            bound.append(raw)
        elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            bound.extend(str(item) for item in cast(Sequence[object], raw) if item)
    unknown = [item for item in bound if item not in ALLOWED_EVALUATOR_KEYS]
    if unknown:
        raise AgentEvalError("unbudgeted_dataset_evaluators")


def _is_conflict(exc: BaseException) -> bool:
    """Return whether an exception represents HTTP 409.

    Args:
        exc: Raised error.

    Returns:
        True when status 409 or a conflict message is present.
    """

    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    if status == 409:
        return True
    text = str(exc).lower()
    return "409" in text or "conflict" in text


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
