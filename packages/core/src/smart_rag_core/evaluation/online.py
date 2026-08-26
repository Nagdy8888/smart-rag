"""Bounded online evaluation. Mock-mode default; no unlimited OpenAI.

Dedicated workspace evaluators attach only to
``smart-rag-agent-eval-online``. The normal ``smart-rag`` project stays
untouched. Holdout stays sealed.
"""

from __future__ import annotations

from decimal import Decimal

from smart_rag_core.evaluation.holdout import HoldoutAccess

ONLINE_EVAL_MOCK_DEFAULT = True
ONLINE_EVAL_MAX_CASES = 20
ONLINE_EVAL_MAX_USD = Decimal("2.00")
ONLINE_EVAL_PROJECT = "smart-rag-agent-eval-online"
APPLICATION_LANGSMITH_PROJECT = "smart-rag"
ONLINE_CODE_EVALUATOR_NAME = "smart-rag-agent-online-hard-metrics-v1"
ONLINE_LLM_EVALUATOR_NAME = "smart-rag-agent-online-judge-v1"
ONLINE_JUDGE_PROMPT_HANDLE = "smart-rag-eval-judge-v1"
ONLINE_JUDGE_PROMPT_TAG = "agent-online-eval-v1"
QUERY_AGENT_ONLINE_EVAL_RUN = "query.agent.eval.online.v1"
AGENT_ONLINE_EVAL_SCHEMA_VERSION = "agent-online-eval-v1"
ONLINE_EVAL_SAMPLING_RATE = 1.0
ONLINE_EVAL_SPEND_WINDOW = "weekly"
ONLINE_EVAL_ROOT_FILTER = 'eq(name, "query.agent.eval.online.v1")'
ONLINE_CODE_RULE_NAME = "smart-rag-agent-online-hard-metrics-v1-rule"
ONLINE_LLM_RULE_NAME = "smart-rag-agent-online-judge-v1-rule"
ONLINE_SUITE_SCHEMA_VERSION = "online-agent-eval-suite-v1"
ONLINE_SUITE_RELATIVE_PATH = (
    "tests/fixtures/evaluation/phase6/online_agent_eval_v1.json"
)


class OnlineEvalError(ValueError):
    """Raised when an online eval would be unbounded, holdout-touching, or over ceiling."""


def assert_online_eval_permitted(
    *,
    mock_mode: bool = ONLINE_EVAL_MOCK_DEFAULT,
    case_count: int,
    max_usd: Decimal,
    holdout_access: HoldoutAccess | None = None,
    unlimited_openai: bool = False,
) -> None:
    """Fail closed before any online evaluator job starts.

    Args:
        mock_mode: Default true. Live OpenAI still cannot exceed the ceiling.
        case_count: Bounded sample size.
        max_usd: Job cost ceiling in USD.
        holdout_access: Must remain denied. ``None`` uses ``HoldoutAccess.denied()``.
        unlimited_openai: Forbidden. Any true value fails closed.

    Raises:
        OnlineEvalError: Holdout enabled, unbounded OpenAI, sample too large,
            or cost above ``ONLINE_EVAL_MAX_USD``.

    Side Effects:
        None. Does not call providers.
    """

    access = holdout_access if holdout_access is not None else HoldoutAccess.denied()
    if access.allowed:
        raise OnlineEvalError("holdout_forbidden")
    if unlimited_openai:
        raise OnlineEvalError("unbounded_openai_forbidden")
    if case_count < 1 or case_count > ONLINE_EVAL_MAX_CASES:
        raise OnlineEvalError("sample_exceeds_ceiling")
    if max_usd > ONLINE_EVAL_MAX_USD or max_usd < 0:
        raise OnlineEvalError("cost_exceeds_ceiling")
    if not mock_mode and max_usd > ONLINE_EVAL_MAX_USD:
        raise OnlineEvalError("cost_exceeds_ceiling")
