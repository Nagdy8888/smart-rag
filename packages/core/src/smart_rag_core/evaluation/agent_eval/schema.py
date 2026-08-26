"""Agent-eval Pydantic contracts and dataset identity constants."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from smart_rag_core.evaluation.online import (
    ONLINE_EVAL_MAX_CASES,
)
from smart_rag_core.evaluation.schema import (
    DatasetSplit,
    EvaluationCase,
)

AGENT_EVAL_SCHEMA_VERSION = "agent-eval-v1"

AGENT_EVAL_DATASET_PREFIX = "smart-rag-agent-eval"

REFUSAL_ROUTE_ALIASES = frozenset({"refusal", "scoped_refusal"})

MAX_EXPERIMENT_PREFIX_CHARS = 40

_EXPERIMENT_PREFIX_RE = re.compile(r"[^A-Za-z0-9_-]+")

EvaluatorResult = dict[str, Any]

LangSmithEvaluator = Callable[[Any, Any], EvaluatorResult]


class AgentEvalError(ValueError):
    """Raised when agent evaluation bounds, split, or dataset identity fail closed."""


class AgentEvalInput(BaseModel):
    """LangSmith example inputs for one synthetic development case.

    Attributes:
        case_id: Frozen case identifier.
        query: Synthetic query text. Allowed in dataset rows only.
        language: Query language code.
        query_class: Canonical query class.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=8, max_length=64)
    query: str = Field(min_length=1, max_length=2000)
    language: Literal["en", "ar", "mixed"]
    query_class: str = Field(min_length=1, max_length=64)


class AgentEvalReference(BaseModel):
    """LangSmith example reference outputs used by deterministic scorers.

    Attributes:
        acceptable_answers: Gold answer variants; empty when refusal is expected.
        expected_route: Labeled route.
        refusal_kind: Explicit refusal or limitation kind.
        visible_chunk_ids: Actor-visible passage identifiers.
        visible_table_ids: Actor-visible table identifiers.
        forbidden_evidence_ids: Invisible or forbidden evidence identifiers.
        expected_profile_fields: Stable profile fields required for scoring.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    acceptable_answers: tuple[str, ...] = ()
    expected_route: str = Field(min_length=1, max_length=64)
    refusal_kind: str = Field(min_length=1, max_length=64)
    visible_chunk_ids: tuple[str, ...] = ()
    visible_table_ids: tuple[str, ...] = ()
    forbidden_evidence_ids: tuple[str, ...] = ()
    expected_profile_fields: dict[str, object] = Field(default_factory=dict)


class AgentEvalSelectedEvidence(BaseModel):
    """One bounded synthetic evidence record for hosted online evaluation.

    Attributes:
        evidence_id: Fixture chunk or table identifier.
        excerpt: At most 600 characters of canonical synthetic citation text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=128)
    excerpt: str = Field(default="", max_length=600)


class AgentEvalOutput(BaseModel):
    """Normalized production-graph output for one evaluation case.

    Attributes:
        case_id: Case identifier copied from the example.
        run_id: Application run id, when admission succeeded.
        conversation_id: Synthetic conversation id, when created.
        completed: Whether the target produced a valid terminal output.
        failure_kind: Named infrastructure or scoring failure, if any.
        answer_text: Agent answer. Synthetic dataset rows may retain it.
        answer_status: ``complete``, ``partial``, ``refused``, or empty.
        requested_route: Envelope family reserved at admit.
        effective_route: Planner-selected family.
        corrected_route: Family after the one correction, if any.
        cited_chunk_ids: Passage ids cited in the answer.
        cited_table_ids: Table ids cited in the answer.
        selected_evidence_ids: Fusion/selected evidence ids.
        selected_evidence: Bounded id-plus-excerpt records for online traces.
        refusal_kind: Observed refusal or limitation token.
        profile_fields: Structured preparation fields used for scoring.
        remaining_model_calls: Remaining counted gateway calls, or None.
        remaining_tool_calls: Remaining tool executions, or None.
        remaining_corrections: Remaining correction slots, or None.
        remaining_subquestions: Remaining subquestion slots, or None.
        remaining_recursion_steps: Remaining graph supersteps, or None.
        deadline_exceeded: True when the run exhausted its deadline.
        latency_ms: End-to-end latency.
        agent_cost_usd: Recorded agent USD as a decimal string.
        judge_cost_usd: Recorded judge USD as a decimal string.
        bm25_fallback: Named BM25 fallback, if any.
        graph_degraded: True when graph retrieve was unbound or failed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1, max_length=64)
    run_id: str | None = None
    conversation_id: str | None = None
    completed: bool = False
    failure_kind: str | None = None
    answer_text: str = ""
    answer_status: str = ""
    requested_route: str | None = None
    effective_route: str | None = None
    corrected_route: str | None = None
    cited_chunk_ids: tuple[str, ...] = ()
    cited_table_ids: tuple[str, ...] = ()
    selected_evidence_ids: tuple[str, ...] = ()
    selected_evidence: tuple[AgentEvalSelectedEvidence, ...] = ()
    refusal_kind: str | None = None
    profile_fields: dict[str, object] = Field(default_factory=dict)
    remaining_model_calls: int | None = None
    remaining_tool_calls: int | None = None
    remaining_corrections: int | None = None
    remaining_subquestions: int | None = None
    remaining_recursion_steps: int | None = None
    deadline_exceeded: bool = False
    latency_ms: int | None = None
    agent_cost_usd: str = "0"
    judge_cost_usd: str = "0"
    bm25_fallback: str | None = None
    graph_degraded: bool = False


class AgentJudgeResult(BaseModel):
    """Typed optional LLM-judge payload. One call per case.

    Attributes:
        correctness: Closed unit interval.
        groundedness: Closed unit interval.
        refusal_quality: Closed unit interval.
        rationale: One short sentence without source text.
        cost_usd: Decimal string of this call's USD.
        failed: True when the judge timed out or returned invalid JSON.
        failure_kind: Named judge failure, if any.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    correctness: float = Field(ge=0.0, le=1.0)
    groundedness: float = Field(ge=0.0, le=1.0)
    refusal_quality: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=240)
    cost_usd: str = "0"
    failed: bool = False
    failure_kind: str | None = None


class AgentEvalSummary(BaseModel):
    """Local machine-readable experiment summary. No secrets or source text.

    Attributes:
        dataset_name: Versioned LangSmith dataset name.
        manifest_hash: SHA-256 of selected case ids and hashes.
        experiment_url: LangSmith experiment URL, when a live run occurred.
        case_ids: Ordered selected case identifiers.
        query_classes: Ordered unique query classes.
        evaluator_aggregates: Mean scores keyed by evaluator name.
        failed_case_ids: Cases with any zero hard metric or target failure.
        hard_failures: case_id to reason list, including ACL leaks.
        run_ids: Application run ids keyed by case id.
        agent_cost_usd: Sum of agent USD.
        judge_cost_usd: Sum of judge USD.
        latency_ms_p50: Median latency across completed cases.
        bm25_degraded: True when any case used BM25 fallback.
        graph_degraded: True when any case ran with graph unbound/failed.
        holdout_opened: Always false for this tool.
        dry_run: True when no LangSmith, database, agent, or provider work ran.
        mock_mode: Whether mock model mode was required.
        judge_enabled: Whether the optional judge was requested.
        selected_case_count: Number of selected cases.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_name: str
    manifest_hash: str
    experiment_url: str | None = None
    case_ids: tuple[str, ...]
    query_classes: tuple[str, ...]
    evaluator_aggregates: dict[str, float] = Field(default_factory=dict)
    failed_case_ids: tuple[str, ...] = ()
    hard_failures: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    run_ids: dict[str, str] = Field(default_factory=dict)
    agent_cost_usd: str = "0"
    judge_cost_usd: str = "0"
    latency_ms_p50: int | None = None
    bm25_degraded: bool = False
    graph_degraded: bool = False
    holdout_opened: Literal[False] = False
    dry_run: bool = False
    mock_mode: bool = True
    judge_enabled: bool = False
    selected_case_count: int = Field(ge=0, le=ONLINE_EVAL_MAX_CASES)


class AgentEvalSelection(BaseModel):
    """Validated development-only case selection plus dataset identity.

    Attributes:
        cases: Ordered selected development cases.
        dataset_name: Versioned dataset name including the 12-char manifest.
        manifest_hash: Full SHA-256 of ordered ids and hashes.
        case_hashes: Mapping of case id to content hash.
        example_ids: Stable UUIDv5 example ids keyed by case id.
        query_class_filters: Explicit class filters recorded in metadata.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: tuple[EvaluationCase, ...]
    dataset_name: str
    manifest_hash: str
    case_hashes: dict[str, str]
    example_ids: dict[str, UUID]
    query_class_filters: tuple[str, ...] = ()

    @field_validator("cases")
    @classmethod
    def _development_only(
        cls, cases: tuple[EvaluationCase, ...]
    ) -> tuple[EvaluationCase, ...]:
        """Reject empty, oversized, or non-development selections.

        Args:
            cases: Candidate cases.

        Returns:
            The unchanged tuple when every case is a synthetic development row.

        Raises:
            AgentEvalError: Split, redaction, or size bounds fail.
        """

        if not cases:
            raise AgentEvalError("sample_exceeds_ceiling")
        if len(cases) > ONLINE_EVAL_MAX_CASES:
            raise AgentEvalError("sample_exceeds_ceiling")
        for case in cases:
            if case.split is not DatasetSplit.DEVELOPMENT:
                raise AgentEvalError("development_split_required")
            if case.redaction_class != "synthetic":
                raise AgentEvalError("synthetic_content_required")
        return cases


def sanitize_experiment_prefix(raw: str | None) -> str:
    """Sanitize and bound an optional experiment prefix suffix.

    Args:
        raw: Operator-supplied suffix, or None.

    Returns:
        Safe suffix of at most 40 characters, or empty string.

    Raises:
        AgentEvalError: When sanitization would leave an empty non-None value.
    """

    if raw is None:
        return ""
    cleaned = _EXPERIMENT_PREFIX_RE.sub("-", raw.strip()).strip("-_")
    cleaned = cleaned[:MAX_EXPERIMENT_PREFIX_CHARS]
    if raw.strip() and not cleaned:
        raise AgentEvalError("experiment_prefix_invalid")
    return cleaned
