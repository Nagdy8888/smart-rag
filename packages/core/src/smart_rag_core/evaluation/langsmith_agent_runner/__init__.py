"""Compatibility facade for LangSmith agent-eval dataset sync and evaluate."""

from smart_rag_core.evaluation.langsmith_agent_runner.dataset import (
    dataset_identity_metadata,
    experiment_git_metadata,
    sync_langsmith_dataset,
)
from smart_rag_core.evaluation.langsmith_agent_runner.evaluate import (
    assert_agent_eval_execution_bounds,
    build_local_summary,
    plan_dry_run,
    run_bounded_evaluate,
)
from smart_rag_core.evaluation.langsmith_agent_runner.types import (
    ALLOWED_EVALUATOR_KEYS,
    AdmittedEvalRun,
    LangSmithEvalClient,
    OncePerCaseJudge,
    ReservationLifecycle,
)

__all__ = [
    "ALLOWED_EVALUATOR_KEYS",
    "AdmittedEvalRun",
    "LangSmithEvalClient",
    "OncePerCaseJudge",
    "ReservationLifecycle",
    "assert_agent_eval_execution_bounds",
    "build_local_summary",
    "dataset_identity_metadata",
    "experiment_git_metadata",
    "plan_dry_run",
    "run_bounded_evaluate",
    "sync_langsmith_dataset",
]
