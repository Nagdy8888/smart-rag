"""Publish private company-Ask dual-metric evals as LangSmith experiments.

Local gold and full answers stay under gitignored ``.private-eval/``. Live
upload is allowed only when the caller opts in and ``APP_ENV`` is ``local``.
This path creates a versioned LangSmith dataset plus an experiment with
dual-metric feedback; it does not open the sealed Phase 4 holdout and is not
a Combined +10pp quality claim.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from uuid import UUID

from smart_rag_core.evaluation.company_ask_diagnosis import (
    DiagnosisSignals,
    RunUsageTotals,
    bool_feedback_score,
    build_diagnosis_signals,
    failure_bucket_score,
)
from smart_rag_core.evaluation.company_ask_regression import (
    AskRegressionConfigError,
    CompanyAskQuestion,
    CompanyAskResult,
    load_private_gold,
    run_scored_questions,
    write_redacted_summary,
)
from smart_rag_core.evaluation.dual_metric import (
    DualMetricScore,
    RequiredFact,
    RetrievalStageAttribution,
    SourceResolutionStage,
    score_company_answer,
)
from smart_rag_core.evaluation.hashes import canonical_dumps, sha256_text
from smart_rag_core.evaluation.langsmith_agent_runner.dataset import (
    experiment_git_metadata,
)

COMPANY_ASK_LANGSMITH_SCHEMA = "company-ask-langsmith-v1"
DEFAULT_COMPANY_ASK_LANGSMITH_PROJECT = "smart-rag-company-ask-eval"
_EXAMPLE_NAMESPACE = UUID("6f3c2c1a-9a0e-4d7b-8f1c-2b5a9d0e4c71")


class CompanyAskLangSmithError(ValueError):
    """Raised when company-Ask LangSmith publish bounds fail closed."""


class CompanyAskLangSmithClient(Protocol):
    """Subset of LangSmith ``Client`` used by the company-Ask publisher."""

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
        """Create one dataset with identity metadata."""

        ...

    def read_dataset(self, *, dataset_name: str) -> object:
        """Read one dataset including metadata."""

        ...

    def list_examples(self, *, dataset_name: str) -> Any:
        """List examples in one dataset."""

        ...

    def create_examples(
        self,
        *,
        dataset_name: str,
        examples: Sequence[Mapping[str, Any]],
        max_concurrency: int = 1,
    ) -> object:
        """Create missing examples."""

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
        """Run one experiment that uploads results to LangSmith."""

        ...


@dataclass(frozen=True, slots=True)
class CompanyAskLangSmithPlan:
    """Dry-run plan for a company-Ask LangSmith publish.

    Attributes:
        dataset_name: Versioned dataset name including gold hash prefix.
        project_name: LangSmith project the caller should open.
        case_count: Number of gold questions selected.
        gold_content_hash: SHA-256 of the canonical gold payload.
        schema_version: Publisher schema identity.
        dry_run: Always ``True`` for plans.
        upload_private_content: Whether the live path would upload prompts,
            answers, and gold phrases.
    """

    dataset_name: str
    project_name: str
    case_count: int
    gold_content_hash: str
    schema_version: str
    dry_run: Literal[True] = True
    upload_private_content: bool = True


@dataclass(frozen=True, slots=True)
class CompanyAskLangSmithSummary:
    """Local summary after a LangSmith company-Ask experiment.

    Attributes:
        dataset_name: Dataset used for the experiment.
        project_name: LangSmith project name.
        case_count: Number of scored questions.
        gold_content_hash: Gold identity hash.
        experiment_url: LangSmith experiment URL when available.
        strict_pass: Count of strict phrase passes.
        grounded_fact_pass: Count of grounded-fact passes.
        deadline_failures: Count of deadline outcomes.
        total_cost_usd: Sum of recorded Ask ``llm_usage.cost_usd`` values.
        total_tokens: Sum of recorded Ask token totals.
        dry_run: Whether this was a plan-only summary.
    """

    dataset_name: str
    project_name: str
    case_count: int
    gold_content_hash: str
    experiment_url: str | None
    strict_pass: int
    grounded_fact_pass: int
    deadline_failures: int
    dry_run: bool
    total_cost_usd: float = 0.0
    total_tokens: int = 0


def assert_local_private_upload_permitted(
    *,
    app_env: str,
    upload_private_content: bool,
) -> None:
    """Fail closed unless local env and explicit private-content opt-in.

    Args:
        app_env: Deployment environment (``APP_ENV``).
        upload_private_content: Caller opt-in to upload prompts/answers/gold.

    Raises:
        CompanyAskLangSmithError: Staging/production, missing opt-in, or
            non-local environments.
    """

    if not upload_private_content:
        raise CompanyAskLangSmithError("upload_private_content_required")
    if app_env.strip().casefold() != "local":
        raise CompanyAskLangSmithError("private_langsmith_upload_local_only")


def gold_content_hash(questions: Sequence[CompanyAskQuestion]) -> str:
    """Hash private gold identity without writing phrases to Git.

    Args:
        questions: Loaded private gold questions.

    Returns:
        SHA-256 hex digest of the canonical gold payload.
    """

    payload = [
        {
            "id": item.question_id,
            "prompt": item.prompt,
            "page": item.page,
            "kind": item.kind,
            "facts": [
                {
                    "id": fact.fact_id,
                    "canonical": list(fact.canonical_phrases),
                    "aliases": list(fact.approved_aliases),
                }
                for fact in item.facts
            ],
        }
        for item in questions
    ]
    return sha256_text(canonical_dumps(payload))


def dataset_name_for_gold(questions: Sequence[CompanyAskQuestion]) -> str:
    """Return a stable LangSmith dataset name for one gold snapshot.

    Args:
        questions: Loaded private gold questions.

    Returns:
        Dataset name ``smart-rag-company-ask-<12 hex chars>``.
    """

    return f"smart-rag-company-ask-{gold_content_hash(questions)[:12]}"


def example_id_for_question(
    question_id: str,
    *,
    gold_content_hash: str,
) -> str:
    """Return a stable UUID string for one gold question id.

    Args:
        question_id: Private gold question identifier.
        gold_content_hash: Gold snapshot hash so example ids stay unique across
            LangSmith datasets in one workspace.

    Returns:
        UUID5 string derived from the publisher namespace, gold hash, and id.
    """

    return str(uuid.uuid5(_EXAMPLE_NAMESPACE, f"{gold_content_hash}:{question_id}"))


def plan_company_ask_langsmith_publish(
    *,
    questions: Sequence[CompanyAskQuestion],
    project_name: str = DEFAULT_COMPANY_ASK_LANGSMITH_PROJECT,
    upload_private_content: bool = True,
) -> CompanyAskLangSmithPlan:
    """Build a dry-run plan without contacting LangSmith.

    Args:
        questions: Loaded private gold.
        project_name: Destination LangSmith project.
        upload_private_content: Whether live upload would include private text.

    Returns:
        Machine-readable plan.
    """

    digest = gold_content_hash(questions)
    return CompanyAskLangSmithPlan(
        dataset_name=f"smart-rag-company-ask-{digest[:12]}",
        project_name=project_name,
        case_count=len(questions),
        gold_content_hash=digest,
        schema_version=COMPANY_ASK_LANGSMITH_SCHEMA,
        upload_private_content=upload_private_content,
    )


def dual_metric_evaluators() -> tuple[Callable[..., dict[str, Any]], ...]:
    """Return LangSmith evaluators for company-Ask dual-metric and diagnosis.

    Returns:
        Ordered evaluator callbacks compatible with ``Client.evaluate``.
        Includes retrieval/citation diagnosis keys used to improve RAG.
    """

    return (
        _dual_evaluator("strict_pass", _score_strict_pass),
        _dual_evaluator("grounded_fact_pass", _score_grounded_fact_pass),
        _dual_evaluator("fact_coverage", _score_fact_coverage),
        _dual_evaluator("no_deadline_failure", _score_no_deadline),
        _diagnosis_bool_evaluator("gold_page_cited"),
        _diagnosis_bool_evaluator("gold_in_fused"),
        _failure_bucket_evaluator(),
        _usage_number_evaluator("estimated_cost_usd"),
        _usage_number_evaluator("total_tokens"),
    )


def sync_company_ask_dataset(
    client: CompanyAskLangSmithClient,
    questions: Sequence[CompanyAskQuestion],
) -> str:
    """Create or verify the versioned company-Ask dataset.

    Args:
        client: LangSmith client subset.
        questions: Private gold questions.

    Returns:
        Dataset name.

    Raises:
        CompanyAskLangSmithError: Metadata drift or example hash mismatch.
    """

    digest = gold_content_hash(questions)
    name = f"smart-rag-company-ask-{digest[:12]}"
    metadata: dict[str, object] = {
        "schema_version": COMPANY_ASK_LANGSMITH_SCHEMA,
        "gold_content_hash": digest,
        "redaction_class": "private_local",
        "holdout_opened": False,
        "case_count": len(questions),
    }
    if not client.has_dataset(dataset_name=name):
        client.create_dataset(
            name,
            description=(
                "Private local company-Ask dual-metric gold. Not a holdout "
                "or Combined +10pp claim."
            ),
            metadata=dict(metadata),
        )
    existing = client.read_dataset(dataset_name=name)
    remote_meta = _object_mapping(getattr(existing, "metadata", None))
    for key, expected in metadata.items():
        if remote_meta.get(key) != expected:
            raise CompanyAskLangSmithError("langsmith_dataset_drift")
    desired = {
        example_id_for_question(item.question_id, gold_content_hash=digest): _case_hash(
            item
        )
        for item in questions
    }
    remote_by_id = _index_remote_examples(client.list_examples(dataset_name=name))
    extra = set(remote_by_id) - set(desired)
    if extra:
        raise CompanyAskLangSmithError("langsmith_dataset_drift")
    for example_id, case_hash in desired.items():
        remote = remote_by_id.get(example_id)
        if remote is not None and remote != case_hash:
            raise CompanyAskLangSmithError("langsmith_dataset_drift")
    missing = [item for item in desired if item not in remote_by_id]
    if not missing:
        return name
    examples = [
        _example_payload(item, gold_content_hash=digest)
        for item in questions
        if example_id_for_question(item.question_id, gold_content_hash=digest)
        in missing
    ]
    try:
        client.create_examples(dataset_name=name, examples=examples, max_concurrency=1)
    except Exception as exc:
        if not _is_conflict(exc):
            raise
        reread = _index_remote_examples(client.list_examples(dataset_name=name))
        for example_id, case_hash in desired.items():
            if reread.get(example_id) != case_hash:
                raise CompanyAskLangSmithError("langsmith_dataset_drift") from exc
        return name
    verified = _index_remote_examples(client.list_examples(dataset_name=name))
    for example_id, case_hash in desired.items():
        if verified.get(example_id) != case_hash:
            raise CompanyAskLangSmithError("langsmith_dataset_drift")
    return name


def publish_company_ask_experiment(
    client: CompanyAskLangSmithClient,
    *,
    questions: Sequence[CompanyAskQuestion],
    answer_rows: Mapping[str, Mapping[str, Any]],
    app_env: str,
    project_name: str = DEFAULT_COMPANY_ASK_LANGSMITH_PROJECT,
    upload_private_content: bool = True,
    experiment_prefix: str | None = None,
    summary_out: Path | None = None,
    diagnosis: Mapping[str, DiagnosisSignals] | None = None,
    usage: Mapping[str, RunUsageTotals] | None = None,
) -> CompanyAskLangSmithSummary:
    """Sync gold, run a LangSmith experiment, and return the local summary.

    The target replays already-collected full answers (from
    ``run_company_ask.py``). Dual-metric and diagnosis evaluators score each
    run against the uploaded gold reference. Prompts, answers, and gold
    phrases are uploaded only under the local private-content gate.

    Args:
        client: LangSmith client subset.
        questions: Private gold questions.
        answer_rows: Per-question answer objects with ``answer_text`` and
            optional stage/status fields.
        app_env: Deployment environment; must be ``local``.
        project_name: LangSmith project name for operator navigation.
        upload_private_content: Explicit opt-in to upload private text.
        experiment_prefix: Optional sanitized experiment prefix suffix.
        summary_out: Optional local redacted summary path.
        diagnosis: Optional per-question gold-page / failure-bucket signals.
            When omitted, signals are derived from fields already present on
            answer rows (``cited_pages``, ``fused_pages``, etc.).
        usage: Optional per-question ``app.llm_usage`` totals. Attached as
            LangSmith ``usage_metadata`` so Cost/Usage columns populate.

    Returns:
        Local summary including ``experiment_url`` when the SDK provides one.

    Raises:
        CompanyAskLangSmithError: Gate, drift, or missing answers.
        AskRegressionConfigError: Gold/answer parse failures.
    """

    assert_local_private_upload_permitted(
        app_env=app_env,
        upload_private_content=upload_private_content,
    )
    if not questions:
        raise CompanyAskLangSmithError("empty_gold")
    answers, stages, statuses, reasons = parse_company_ask_answer_rows(
        answer_rows, questions
    )
    results = run_scored_questions(
        questions,
        answers=answers,
        stages=stages,
        answer_status=statuses,
        terminal_reason=reasons,
    )
    dataset_name = sync_company_ask_dataset(client, questions)
    diagnosis_by_id = _resolve_diagnosis(
        questions,
        results=results,
        answer_rows=answer_rows,
        diagnosis=diagnosis,
    )
    usage_by_id = dict(usage or {})
    target_outputs = _target_outputs_by_question(
        questions,
        answer_rows=answer_rows,
        answers=answers,
        stages=stages,
        statuses=statuses,
        reasons=reasons,
        diagnosis=diagnosis_by_id,
        usage=usage_by_id,
    )

    try:
        from langsmith import traceable as _langsmith_traceable
    except ImportError:
        _langsmith_traceable = None

    def _target_body(inputs: dict[str, Any]) -> dict[str, Any]:
        """Return the precomputed Ask output for one dataset example.

        Args:
            inputs: LangSmith example inputs containing ``question_id``.

        Returns:
            JSON-compatible answer, stage, diagnosis, and usage fields.

        Raises:
            CompanyAskLangSmithError: Unknown question id.
        """

        question_id = str(inputs.get("question_id") or "").strip()
        try:
            payload = dict(target_outputs[question_id])
        except KeyError as exc:
            raise CompanyAskLangSmithError(
                f"missing_target_output:{question_id}"
            ) from exc
        _attach_usage_to_current_run(payload)
        return payload

    if _langsmith_traceable is not None:
        # LLM run_type makes LangSmith Cost/Usage columns render for the
        # experiment rows; usage_metadata is attached from app.llm_usage.
        _target = _langsmith_traceable(
            name="company-ask-eval",
            run_type="llm",
            metadata={"ls_provider": "openai", "ls_model_name": "gpt-4o-mini"},
        )(_target_body)
    else:
        _target = _target_body

    prefix = "company-ask-dual"
    if experiment_prefix:
        cleaned = _sanitize_prefix(experiment_prefix)
        prefix = f"{prefix}-{cleaned}"
    git_meta = experiment_git_metadata()
    digest = gold_content_hash(questions)
    result = client.evaluate(
        _target,
        data=dataset_name,
        evaluators=list(dual_metric_evaluators()),
        metadata={
            **git_meta,
            "dataset_name": dataset_name,
            "gold_content_hash": digest,
            "schema_version": COMPANY_ASK_LANGSMITH_SCHEMA,
            "project_name": project_name,
            "case_count": len(questions),
            "holdout_opened": False,
            "scoring": "dual_metric_plus_diagnosis",
            "upload_private_content": True,
            "feedback_keys": [
                "strict_pass",
                "grounded_fact_pass",
                "fact_coverage",
                "no_deadline_failure",
                "gold_page_cited",
                "gold_in_fused",
                "failure_bucket",
                "estimated_cost_usd",
                "total_tokens",
            ],
        },
        experiment_prefix=prefix,
        description=(
            "Private local company-Ask dual-metric + diagnosis experiment. "
            "Not a holdout or Combined +10pp claim."
        ),
        max_concurrency=1,
        num_repetitions=1,
        blocking=True,
        upload_results=True,
        error_handling="log",
    )
    if summary_out is not None:
        write_redacted_summary(results, summary_out)
    aggregates = _aggregate_results(results)
    usage_totals = _aggregate_usage(usage_by_id)
    return CompanyAskLangSmithSummary(
        dataset_name=dataset_name,
        project_name=project_name,
        case_count=len(questions),
        gold_content_hash=digest,
        experiment_url=_experiment_url(result),
        strict_pass=aggregates["strict_pass"],
        grounded_fact_pass=aggregates["grounded_fact_pass"],
        deadline_failures=aggregates["deadline_failures"],
        dry_run=False,
        total_cost_usd=usage_totals["total_cost_usd"],
        total_tokens=usage_totals["total_tokens"],
    )


def load_gold_and_answers(
    *,
    gold_path: Path,
    answers_path: Path,
    stage_export_path: Path | None = None,
) -> tuple[tuple[CompanyAskQuestion, ...], dict[str, dict[str, Any]]]:
    """Load private gold and answer rows for LangSmith publish.

    Args:
        gold_path: JSON array under ``.private-eval/``.
        answers_path: JSON object from ``run_company_ask.py --answers-out``.
        stage_export_path: Optional stage-export overlay.

    Returns:
        Questions and mutable answer-row mapping.

    Raises:
        AskRegressionConfigError: Path or payload validation fails.
        OSError: File read failure.
        json.JSONDecodeError: Invalid JSON.
    """

    questions = load_private_gold(gold_path)
    payload_obj: object = json.loads(answers_path.read_text(encoding="utf-8"))
    if stage_export_path is not None:
        export_obj: object = json.loads(stage_export_path.read_text(encoding="utf-8"))
        payload_obj = overlay_stage_export(payload_obj, export_obj)
    if not isinstance(payload_obj, dict):
        raise AskRegressionConfigError("answers JSON must be an object")
    rows: dict[str, dict[str, Any]] = {}
    for key, raw in cast(dict[object, object], payload_obj).items():
        question_id = str(key)
        if isinstance(raw, str):
            rows[question_id] = {"answer_text": raw}
            continue
        if not isinstance(raw, dict):
            raise AskRegressionConfigError("answer row must be a string or object")
        rows[question_id] = {
            str(field): value
            for field, value in cast(dict[object, object], raw).items()
        }
    return questions, rows


def parse_company_ask_answer_rows(
    answer_rows: Mapping[str, Mapping[str, Any]],
    questions: Sequence[CompanyAskQuestion],
) -> tuple[
    dict[str, str],
    dict[str, RetrievalStageAttribution],
    dict[str, str],
    dict[str, str],
]:
    """Parse answer rows into scorer inputs.

    Args:
        answer_rows: Per-question answer objects.
        questions: Gold questions; every id must have an answer row.

    Returns:
        Answers, stages, statuses, and terminal reasons.

    Raises:
        AskRegressionConfigError: Missing answer for a gold question.
    """

    answers: dict[str, str] = {}
    stages: dict[str, RetrievalStageAttribution] = {}
    statuses: dict[str, str] = {}
    reasons: dict[str, str] = {}
    for question in questions:
        try:
            row = answer_rows[question.question_id]
        except KeyError as exc:
            raise AskRegressionConfigError(
                f"missing full answer for {question.question_id}"
            ) from exc
        answers[question.question_id] = str(row.get("answer_text") or "")
        if row.get("status"):
            statuses[question.question_id] = str(row["status"])
        if row.get("reason"):
            reasons[question.question_id] = str(row["reason"])
        stages[question.question_id] = _stage_from_mapping(row.get("stages", {}))
    return answers, stages, statuses, reasons


def overlay_stage_export(payload: object, export: object) -> object:
    """Copy measured stage fields from a private export onto answer rows.

    Args:
        payload: Answers JSON object.
        export: Stage-export JSON object.

    Returns:
        The same payload, mutated when both values are objects.
    """

    if not isinstance(payload, dict) or not isinstance(export, dict):
        return cast(object, payload)
    typed_export = cast(dict[str, object], export)
    runs = typed_export.get("runs")
    if not isinstance(runs, Mapping):
        return cast(object, payload)
    runs_map = cast(Mapping[str, object], runs)
    typed = cast(dict[object, object], payload)
    for key, raw in typed.items():
        if not isinstance(raw, dict):
            continue
        exported = runs_map.get(str(key))
        if not isinstance(exported, Mapping):
            continue
        exported_map = cast(Mapping[str, object], exported)
        row = cast(dict[str, object], raw)
        stages = row.get("stages")
        merged: dict[str, object] = (
            dict(cast(Mapping[str, object], stages))
            if isinstance(stages, Mapping)
            else {}
        )
        for field, value in exported_map.items():
            if field == "run_id":
                continue
            merged[str(field)] = value
        row["stages"] = merged
    return cast(object, payload)


def _dual_evaluator(
    key: str,
    score_fn: Callable[[DualMetricScore], float],
) -> Callable[..., dict[str, Any]]:
    """Build one LangSmith dual-metric evaluator.

    Args:
        key: Feedback key.
        score_fn: Maps a dual-metric score to a float feedback value.

    Returns:
        Evaluator callback.
    """

    def _run(run: Any, example: Any) -> dict[str, Any]:
        """Score one experiment run against its gold reference.

        Args:
            run: LangSmith run with ``outputs``.
            example: LangSmith example with reference ``outputs``.

        Returns:
            Feedback dict with ``key``, ``score``, and ``comment``.
        """

        outputs = _run_outputs(run)
        reference = _example_outputs(example)
        score = _score_from_run_and_reference(outputs, reference)
        return {
            "key": key,
            "score": score_fn(score),
            "comment": f"outcome={score.outcome.value}",
        }

    _run.__name__ = f"eval_{key}"
    _run.__qualname__ = f"eval_{key}"
    return _run


def _score_strict_pass(score: DualMetricScore) -> float:
    """Return 1.0 when the strict phrase bar passes.

    Args:
        score: Dual-metric score.

    Returns:
        ``1.0`` or ``0.0``.
    """

    return 1.0 if score.strict_pass else 0.0


def _score_grounded_fact_pass(score: DualMetricScore) -> float:
    """Return 1.0 when grounded fact coverage is complete.

    Args:
        score: Dual-metric score.

    Returns:
        ``1.0`` or ``0.0``.
    """

    return 1.0 if score.grounded_fact_pass else 0.0


def _score_fact_coverage(score: DualMetricScore) -> float:
    """Return fact-coverage fraction.

    Args:
        score: Dual-metric score.

    Returns:
        Coverage in ``[0.0, 1.0]``.
    """

    return float(score.fact_coverage)


def _score_no_deadline(score: DualMetricScore) -> float:
    """Return 1.0 when the answer did not fail on deadline.

    Args:
        score: Dual-metric score.

    Returns:
        ``1.0`` or ``0.0``.
    """

    return 0.0 if score.deadline_failure else 1.0


def _diagnosis_bool_evaluator(key: str) -> Callable[..., dict[str, Any]]:
    """Build a LangSmith evaluator for one boolean diagnosis flag.

    Args:
        key: ``gold_page_cited`` or ``gold_in_fused``.

    Returns:
        Evaluator callback. Unknown measurements emit ``score=None``.
    """

    field = "gold_page_cited" if key == "gold_page_cited" else "gold_page_in_fused"

    def _run(run: Any, example: Any) -> dict[str, Any]:
        """Score one diagnosis boolean from target outputs.

        Args:
            run: LangSmith run with ``outputs``.
            example: Unused reference example.

        Returns:
            Feedback dict with optional score and a short comment.
        """

        del example
        outputs = _run_outputs(run)
        diagnosis = _object_mapping(outputs.get("diagnosis"))
        raw = diagnosis.get(field)
        measured = raw if isinstance(raw, bool) else None
        score = bool_feedback_score(measured)
        comment = "unknown" if measured is None else ("yes" if measured else "no")
        result: dict[str, Any] = {"key": key, "comment": comment}
        if score is not None:
            result["score"] = score
        return result

    _run.__name__ = f"eval_{key}"
    _run.__qualname__ = f"eval_{key}"
    return _run


def _failure_bucket_evaluator() -> Callable[..., dict[str, Any]]:
    """Build the LangSmith evaluator for the RAG failure bucket.

    Returns:
        Evaluator callback. ``score`` is 1.0 for ``pass``, else 0.0.
        ``comment`` and ``value`` carry the bucket name for filtering.
    """

    def _run(run: Any, example: Any) -> dict[str, Any]:
        """Score the failure bucket from target diagnosis outputs.

        Args:
            run: LangSmith run with ``outputs``.
            example: Unused reference example.

        Returns:
            Feedback dict with pass/fail score and bucket label.
        """

        del example
        outputs = _run_outputs(run)
        diagnosis = _object_mapping(outputs.get("diagnosis"))
        bucket = str(diagnosis.get("failure_bucket") or "unknown")
        return {
            "key": "failure_bucket",
            "score": failure_bucket_score(bucket),
            "value": bucket,
            "comment": f"bucket={bucket}",
        }

    _run.__name__ = "eval_failure_bucket"
    _run.__qualname__ = "eval_failure_bucket"
    return _run


def _usage_number_evaluator(key: str) -> Callable[..., dict[str, Any]]:
    """Build a LangSmith evaluator for cost or token totals.

    Args:
        key: ``estimated_cost_usd`` or ``total_tokens``.

    Returns:
        Evaluator callback. Missing usage emits comment ``unknown``.
    """

    def _run(run: Any, example: Any) -> dict[str, Any]:
        """Score one numeric usage field from target outputs.

        Args:
            run: LangSmith run with ``outputs``.
            example: Unused reference example.

        Returns:
            Feedback dict with the numeric score when measured.
        """

        del example
        outputs = _run_outputs(run)
        usage = _object_mapping(outputs.get("usage"))
        raw = usage.get(key)
        result: dict[str, Any] = {"key": key, "comment": "unknown"}
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return result
        result["score"] = float(raw)
        result["comment"] = str(raw)
        return result

    _run.__name__ = f"eval_{key}"
    _run.__qualname__ = f"eval_{key}"
    return _run


def _attach_usage_to_current_run(payload: Mapping[str, Any]) -> None:
    """Attach LangSmith-recognized usage/cost metadata to the active run.

    Args:
        payload: Target outputs that may include ``usage.usage_metadata``.

    Side Effects:
        Updates the current LangSmith run tree when tracing is active and
        usage metadata is present. No-op otherwise.
    """

    usage = _object_mapping(payload.get("usage"))
    metadata = usage.get("usage_metadata")
    if not isinstance(metadata, Mapping):
        return
    try:
        from langsmith import get_current_run_tree
    except ImportError:
        return
    run = get_current_run_tree()
    if run is None:
        return
    model = str(usage.get("model_id") or "gpt-4o-mini")
    run.metadata["ls_provider"] = "openai"
    run.metadata["ls_model_name"] = model
    typed_usage = {
        str(key): value
        for key, value in cast(Mapping[object, object], metadata).items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    if not typed_usage:
        return
    run.set(usage_metadata=typed_usage)


def _aggregate_usage(usage: Mapping[str, RunUsageTotals]) -> dict[str, float | int]:
    """Sum cost and tokens across the published questions.

    Args:
        usage: Per-question usage totals.

    Returns:
        Aggregate ``total_cost_usd`` and ``total_tokens``.
    """

    total_cost = 0.0
    total_tokens = 0
    for item in usage.values():
        total_cost += float(item.total_cost_usd)
        total_tokens += int(item.total_tokens)
    return {"total_cost_usd": total_cost, "total_tokens": total_tokens}


def _resolve_diagnosis(
    questions: Sequence[CompanyAskQuestion],
    *,
    results: Sequence[CompanyAskResult],
    answer_rows: Mapping[str, Mapping[str, Any]],
    diagnosis: Mapping[str, DiagnosisSignals] | None,
) -> dict[str, DiagnosisSignals]:
    """Merge caller-provided diagnosis with row-local page signals.

    Args:
        questions: Gold questions.
        results: Dual-metric scored results.
        answer_rows: Answer rows that may already carry page lists.
        diagnosis: Optional externally enriched signals (checkpoint/DB).

    Returns:
        Per-question diagnosis mapping.
    """

    by_result = {item.question_id: item for item in results}
    resolved: dict[str, DiagnosisSignals] = {}
    provided = diagnosis or {}
    for question in questions:
        result = by_result[question.question_id]
        if question.question_id in provided:
            resolved[question.question_id] = provided[question.question_id]
            continue
        row = answer_rows[question.question_id]
        resolved[question.question_id] = build_diagnosis_signals(
            outcome=result.score.outcome.value,
            grounded=result.score.grounded_fact_pass,
            gold_page=question.page,
            cited_pages=row.get("cited_pages"),
            fused_pages=row.get("fused_pages"),
            rerank_pool_pages=row.get("rerank_pool_pages"),
            selected_pages=row.get("selected_pages"),
            citation_failures=_string_tuple(row.get("citation_failures")),
            kind=question.kind,
        )
    return resolved


def _string_tuple(value: object) -> tuple[str, ...]:
    """Coerce a JSON list of strings.

    Args:
        value: Potential sequence.

    Returns:
        String tuple.
    """

    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        str(item) for item in cast(Sequence[object], value) if str(item).strip()
    )


def _score_from_run_and_reference(
    outputs: Mapping[str, Any],
    reference: Mapping[str, Any],
) -> DualMetricScore:
    """Rebuild dual-metric scoring from experiment I/O.

    Args:
        outputs: Target outputs including answer text and stages.
        reference: Example reference including facts.

    Returns:
        Dual-metric score.
    """

    facts = tuple(
        _fact_from_reference(item) for item in _as_list(reference.get("facts"))
    )
    stages = _stage_from_mapping(outputs.get("stages", {}))
    return score_company_answer(
        answer_text=str(outputs.get("answer_text") or ""),
        facts=facts,
        stages=stages,
        answer_status=(
            str(outputs["status"]) if outputs.get("status") is not None else None
        ),
        terminal_reason=(
            str(outputs["reason"]) if outputs.get("reason") is not None else None
        ),
    )


def _fact_from_reference(raw: object) -> RequiredFact:
    """Parse one reference fact object.

    Args:
        raw: JSON object from example outputs.

    Returns:
        Required fact.

    Raises:
        CompanyAskLangSmithError: Malformed fact.
    """

    if not isinstance(raw, Mapping):
        raise CompanyAskLangSmithError("reference_fact_invalid")
    mapping = cast(Mapping[str, object], raw)
    canonical = mapping.get("canonical", [])
    aliases = mapping.get("aliases", [])
    if not isinstance(canonical, list) or not canonical:
        raise CompanyAskLangSmithError("reference_fact_invalid")
    if not isinstance(aliases, list):
        raise CompanyAskLangSmithError("reference_fact_invalid")
    return RequiredFact(
        fact_id=str(mapping.get("id") or "fact"),
        canonical_phrases=tuple(str(item) for item in cast(list[object], canonical)),
        approved_aliases=tuple(str(item) for item in cast(list[object], aliases)),
    )


def _example_payload(
    question: CompanyAskQuestion,
    *,
    gold_content_hash: str,
) -> dict[str, Any]:
    """Build one LangSmith create_examples payload.

    Args:
        question: Private gold question.
        gold_content_hash: Gold snapshot hash for stable unique example ids.

    Returns:
        Example mapping with stable id, inputs, reference outputs, metadata.
    """

    case_hash = _case_hash(question)
    return {
        "id": example_id_for_question(
            question.question_id, gold_content_hash=gold_content_hash
        ),
        "inputs": {
            "question_id": question.question_id,
            "prompt": question.prompt,
            "page": question.page,
            "kind": question.kind,
        },
        "outputs": {
            "facts": [
                {
                    "id": fact.fact_id,
                    "canonical": list(fact.canonical_phrases),
                    "aliases": list(fact.approved_aliases),
                }
                for fact in question.facts
            ],
            "page": question.page,
            "kind": question.kind,
        },
        "metadata": {
            "question_id": question.question_id,
            "case_content_hash": case_hash,
            "schema_version": COMPANY_ASK_LANGSMITH_SCHEMA,
            "page": question.page,
            "kind": question.kind,
        },
    }


def _case_hash(question: CompanyAskQuestion) -> str:
    """Hash one gold question for drift detection.

    Args:
        question: Private gold question.

    Returns:
        SHA-256 hex digest.
    """

    return sha256_text(
        canonical_dumps(
            {
                "id": question.question_id,
                "prompt": question.prompt,
                "page": question.page,
                "kind": question.kind,
                "facts": [
                    {
                        "id": fact.fact_id,
                        "canonical": list(fact.canonical_phrases),
                        "aliases": list(fact.approved_aliases),
                    }
                    for fact in question.facts
                ],
            }
        )
    )


def _target_outputs_by_question(
    questions: Sequence[CompanyAskQuestion],
    *,
    answer_rows: Mapping[str, Mapping[str, Any]],
    answers: Mapping[str, str],
    stages: Mapping[str, RetrievalStageAttribution],
    statuses: Mapping[str, str],
    reasons: Mapping[str, str],
    diagnosis: Mapping[str, DiagnosisSignals],
    usage: Mapping[str, RunUsageTotals],
) -> dict[str, dict[str, Any]]:
    """Build evaluate-target outputs keyed by question id.

    Args:
        questions: Gold questions.
        answer_rows: Original answer rows (for run/conversation ids).
        answers: Full answer text.
        stages: Stage attribution.
        statuses: Optional answer statuses.
        reasons: Optional terminal reasons.
        diagnosis: Per-question diagnosis signals.
        usage: Per-question ``llm_usage`` totals.

    Returns:
        Target output mapping per question.
    """

    outputs: dict[str, dict[str, Any]] = {}
    for question in questions:
        row = answer_rows[question.question_id]
        stage = stages.get(question.question_id, RetrievalStageAttribution())
        signal = diagnosis[question.question_id]
        usage_totals = usage.get(question.question_id)
        payload: dict[str, Any] = {
            "question_id": question.question_id,
            "answer_text": answers[question.question_id],
            "status": statuses.get(question.question_id),
            "reason": reasons.get(question.question_id),
            "run_id": row.get("run_id"),
            "conversation_id": row.get("conversation_id"),
            "terminal": row.get("terminal"),
            "diagnosis": {
                "gold_page": signal.gold_page,
                "gold_page_cited": signal.gold_page_cited,
                "gold_page_in_fused": signal.gold_page_in_fused,
                "gold_page_in_rerank_pool": signal.gold_page_in_rerank_pool,
                "gold_page_in_selected": signal.gold_page_in_selected,
                "citation_failures": list(signal.citation_failures),
                "failure_bucket": signal.failure_bucket,
                "kind": signal.kind,
            },
            "stages": {
                "source_resolution": stage.source_resolution.value,
                "dense_hit": stage.dense_hit,
                "bm25_hit": stage.bm25_hit,
                "term_hit": stage.term_hit,
                "fused_rank": stage.fused_rank,
                "rerank_rank": stage.rerank_rank,
                "rerank_fallback": stage.rerank_fallback,
                "post_mmr_rank": stage.post_mmr_rank,
                "coverage_term": stage.coverage_term,
                "coverage_subquestion": stage.coverage_subquestion,
                "coverage_evidence_ratio": stage.coverage_evidence_ratio,
                "coverage_support_confidence": stage.coverage_support_confidence,
                "coverage_score": stage.coverage_score,
                "correction_outcome": stage.correction_outcome,
                "fused_count": stage.fused_count,
                "verifier_status": stage.verifier_status,
                "retrieval_empty": stage.retrieval_empty,
            },
        }
        if usage_totals is not None:
            usage_json = usage_totals.as_json()
            payload["usage"] = usage_json
            payload["usage_metadata"] = usage_json["usage_metadata"]
            payload["estimated_cost_usd"] = usage_json["estimated_cost_usd"]
        outputs[question.question_id] = payload
    return outputs


def _stage_from_mapping(raw: object) -> RetrievalStageAttribution:
    """Parse optional stage attribution from JSON.

    Args:
        raw: Mapping or empty.

    Returns:
        Frozen stage attribution.
    """

    if not isinstance(raw, Mapping):
        return RetrievalStageAttribution()
    mapping = {
        str(key): value for key, value in cast(Mapping[object, object], raw).items()
    }
    try:
        source_resolution = SourceResolutionStage(
            str(mapping.get("source_resolution") or "")
        )
    except ValueError:
        source_resolution = SourceResolutionStage.UNSCOPED
    fused_ids = mapping.get("fused_ids")
    fused_count = (
        len(cast(list[object], fused_ids))
        if isinstance(fused_ids, list)
        else _as_int(mapping.get("fused_count"), default=0)
    )
    return RetrievalStageAttribution(
        source_resolution=source_resolution,
        dense_hit=_optional_bool(mapping.get("dense_hit")),
        bm25_hit=_optional_bool(mapping.get("bm25_hit")),
        term_hit=_optional_bool(mapping.get("term_hit")),
        fused_rank=_optional_int(mapping.get("fused_rank")),
        rerank_rank=_optional_int(mapping.get("rerank_rank")),
        rerank_fallback=(
            str(mapping["rerank_fallback"])
            if mapping.get("rerank_fallback") is not None
            else None
        ),
        post_mmr_rank=_optional_int(mapping.get("post_mmr_rank")),
        coverage_term=_optional_float(mapping.get("coverage_term")),
        coverage_subquestion=_optional_float(mapping.get("coverage_subquestion")),
        coverage_evidence_ratio=_optional_float(mapping.get("coverage_evidence_ratio")),
        coverage_support_confidence=_optional_float(
            mapping.get("coverage_support_confidence")
        ),
        coverage_score=_optional_float(mapping.get("coverage_score")),
        correction_outcome=str(mapping.get("correction_outcome") or "none"),
        fused_count=fused_count if fused_count is not None else 0,
        verifier_status=(
            str(mapping["verifier_status"])
            if mapping.get("verifier_status") is not None
            else None
        ),
        retrieval_empty=bool(mapping.get("retrieval_empty") or False),
    )


def _aggregate_results(results: Sequence[CompanyAskResult]) -> dict[str, int]:
    """Aggregate dual-metric counts for the local summary.

    Args:
        results: Scored company-Ask results.

    Returns:
        Count mapping for strict, grounded, and deadline outcomes.
    """

    return {
        "strict_pass": sum(1 for item in results if item.score.strict_pass),
        "grounded_fact_pass": sum(
            1 for item in results if item.score.grounded_fact_pass
        ),
        "deadline_failures": sum(1 for item in results if item.score.deadline_failure),
    }


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


def _index_remote_examples(examples: Any) -> dict[str, str]:
    """Index remote examples by id to case-content hash.

    Args:
        examples: LangSmith examples iterable.

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
    """Coerce metadata to a string-keyed dict.

    Args:
        value: Mapping or None.

    Returns:
        Dict copy.
    """

    if isinstance(value, Mapping):
        typed = cast(Mapping[object, object], value)
        return {str(key): item for key, item in typed.items()}
    return {}


def _run_outputs(run: Any) -> dict[str, Any]:
    """Extract outputs from a LangSmith run object.

    Args:
        run: Run with ``outputs`` attribute or mapping.

    Returns:
        String-keyed outputs dict.
    """

    outputs = getattr(run, "outputs", None)
    if outputs is None and isinstance(run, Mapping):
        outputs = cast(Mapping[object, object], run).get("outputs")
    return _object_mapping(outputs)


def _example_outputs(example: Any) -> dict[str, Any]:
    """Extract reference outputs from a LangSmith example.

    Args:
        example: Example with ``outputs`` attribute or mapping.

    Returns:
        String-keyed outputs dict.
    """

    outputs = getattr(example, "outputs", None)
    if outputs is None and isinstance(example, Mapping):
        outputs = cast(Mapping[object, object], example).get("outputs")
    return _object_mapping(outputs)


def _experiment_url(result: object) -> str | None:
    """Extract a LangSmith experiment URL when present.

    Args:
        result: SDK evaluate result.

    Returns:
        URL string or ``None``.
    """

    for attr in ("experiment_url", "url"):
        value = getattr(result, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    if isinstance(result, Mapping):
        mapped = cast(Mapping[object, object], result)
        value = mapped.get("experiment_url") or mapped.get("url")
        if isinstance(value, str) and value.strip():
            return value
    return None


def _sanitize_prefix(raw: str) -> str:
    """Sanitize an optional experiment prefix suffix.

    Args:
        raw: Caller-provided suffix.

    Returns:
        Lowercase ``[a-z0-9-]`` text bounded to 32 characters.

    Raises:
        CompanyAskLangSmithError: Empty or invalid after sanitization.
    """

    cleaned = "".join(
        char if char.isalnum() or char == "-" else "-" for char in raw.strip().lower()
    ).strip("-")
    cleaned = cleaned[:32].strip("-")
    if not cleaned:
        raise CompanyAskLangSmithError("experiment_prefix_invalid")
    return cleaned


def _as_list(value: object) -> list[object]:
    """Coerce a value to a list.

    Args:
        value: Potential list.

    Returns:
        List copy, or empty list.
    """

    if isinstance(value, list):
        return list(cast(list[object], value))
    return []


def _optional_bool(value: object) -> bool | None:
    """Parse an optional bool.

    Args:
        value: Raw JSON value.

    Returns:
        Bool, or ``None`` when absent.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return None


def _optional_int(value: object) -> int | None:
    """Parse an optional int.

    Args:
        value: Raw JSON value.

    Returns:
        Int, or ``None``.
    """

    if value is None or value == "":
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_int(value: object, *, default: int | None = None) -> int | None:
    """Parse an int with a default.

    Args:
        value: Raw JSON value.
        default: Fallback.

    Returns:
        Int or default.
    """

    parsed = _optional_int(value)
    return default if parsed is None else parsed


def _optional_float(value: object) -> float | None:
    """Parse an optional float.

    Args:
        value: Raw JSON value.

    Returns:
        Float, or ``None``.
    """

    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
