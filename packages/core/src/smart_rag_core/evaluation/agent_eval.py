"""Versioned LangSmith agent-eval schema, mapping, and deterministic scorers.

This module never loads holdout labels, never relabels cases, and never
constructs an OpenAI client. Judge invocation stays behind the shared gateway.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.hashes import (
    canonical_dumps,
    case_content_hash,
    sha256_text,
)
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.loader import load_development_cases
from smart_rag_core.evaluation.online import (
    ONLINE_EVAL_MAX_CASES,
    ONLINE_EVAL_MAX_USD,
    ONLINE_EVAL_MOCK_DEFAULT,
    assert_online_eval_permitted,
)
from smart_rag_core.evaluation.schema import (
    DATASET_SCHEMA_VERSION,
    LABEL_REVISION,
    DatasetSplit,
    EvaluationCase,
    ExpectedRoute,
    RefusalKind,
)

AGENT_EVAL_SCHEMA_VERSION = "agent-eval-v1"
AGENT_EVAL_DATASET_PREFIX = "smart-rag-agent-eval"
REFUSAL_ROUTE_ALIASES = frozenset({"refusal", "scoped_refusal"})
MAX_EXPERIMENT_PREFIX_CHARS = 40
_EXPERIMENT_PREFIX_RE = re.compile(r"[^A-Za-z0-9_-]+")
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

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


def select_development_cases(
    *,
    limit: int,
    case_ids: Sequence[str] = (),
    query_classes: Sequence[str] = (),
    holdout_access: HoldoutAccess | None = None,
) -> AgentEvalSelection:
    """Load and bound synthetic development cases. Holdout stays sealed.

    Args:
        limit: Maximum cases. Valid range ``1..20``.
        case_ids: Optional repeatable ids. Every id must be development.
        query_classes: Optional class filters. Unknown classes fail closed.
        holdout_access: Must remain denied even if settings accidentally allow.

    Returns:
        Validated selection with dataset name and stable example ids.

    Raises:
        AgentEvalError: Bounds, split, class, or holdout checks fail.
        OnlineEvalError: Online ceiling checks fail.
    """

    access = holdout_access if holdout_access is not None else HoldoutAccess.denied()
    if access.allowed:
        raise AgentEvalError("holdout_forbidden")
    if limit < 1 or limit > ONLINE_EVAL_MAX_CASES:
        raise AgentEvalError("sample_exceeds_ceiling")
    development = load_development_cases()
    by_id = {case.case_id: case for case in development}
    requested_ids = tuple(dict.fromkeys(case_ids))
    if requested_ids:
        selected: list[EvaluationCase] = []
        for case_id in requested_ids:
            case = by_id.get(case_id)
            if case is None:
                raise AgentEvalError("development_case_required")
            selected.append(case)
    else:
        selected = list(development)
    class_filters = tuple(dict.fromkeys(query_classes))
    if class_filters:
        known = {item.value for item in QueryClass}
        unknown = [item for item in class_filters if item not in known]
        if unknown:
            raise AgentEvalError("unsupported_query_class")
        matching = [
            case for case in selected if case.query_class.value in class_filters
        ]
        present = {case.query_class.value for case in matching}
        missing = [item for item in class_filters if item not in present]
        if missing:
            raise AgentEvalError("unsupported_query_class")
        selected = matching
    if len(selected) < 1:
        raise AgentEvalError("sample_exceeds_ceiling")
    selected = selected[:limit]
    assert_online_eval_permitted(
        mock_mode=ONLINE_EVAL_MOCK_DEFAULT,
        case_count=len(selected),
        max_usd=ONLINE_EVAL_MAX_USD,
        holdout_access=HoldoutAccess.denied(),
        unlimited_openai=False,
    )
    hashes = {case.case_id: case_content_hash(case) for case in selected}
    manifest_hash = selected_manifest_hash(selected)
    dataset_name = agent_eval_dataset_name(manifest_hash)
    example_ids = {
        case.case_id: example_uuid(dataset_name, case.case_id, hashes[case.case_id])
        for case in selected
    }
    return AgentEvalSelection(
        cases=tuple(selected),
        dataset_name=dataset_name,
        manifest_hash=manifest_hash,
        case_hashes=hashes,
        example_ids=example_ids,
        query_class_filters=class_filters,
    )


def selected_manifest_hash(cases: Sequence[EvaluationCase]) -> str:
    """Hash ordered selected case ids and content hashes.

    Args:
        cases: Ordered selected cases.

    Returns:
        SHA-256 hex digest.
    """

    material = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "label_revision": LABEL_REVISION,
        "split": DatasetSplit.DEVELOPMENT.value,
        "case_ids": [case.case_id for case in cases],
        "case_hashes": {case.case_id: case_content_hash(case) for case in cases},
    }
    return sha256_text(canonical_dumps(material))


def agent_eval_dataset_name(manifest_hash: str) -> str:
    """Return the versioned LangSmith dataset name.

    Args:
        manifest_hash: Full SHA-256 of the selected manifest.

    Returns:
        ``smart-rag-agent-eval-{schema}-{labels}-development-{12}``.
    """

    return (
        f"{AGENT_EVAL_DATASET_PREFIX}-{DATASET_SCHEMA_VERSION}-{LABEL_REVISION}"
        f"-development-{manifest_hash[:12]}"
    )


def example_uuid(dataset_name: str, case_id: str, case_hash: str) -> UUID:
    """Return a stable UUIDv5 example id.

    Args:
        dataset_name: Versioned dataset name.
        case_id: Frozen case identifier.
        case_hash: Case content SHA-256.

    Returns:
        UUIDv5 derived from dataset name, case id, and case hash.
    """

    return uuid5(NAMESPACE_URL, f"{dataset_name}:{case_id}:{case_hash}")


def case_to_input(case: EvaluationCase) -> AgentEvalInput:
    """Map one evaluation case to LangSmith example inputs.

    Args:
        case: Synthetic development case.

    Returns:
        Typed input payload.
    """

    return AgentEvalInput(
        case_id=case.case_id,
        query=case.query,
        language=case.language,
        query_class=case.query_class.value,
    )


def case_to_reference(case: EvaluationCase) -> AgentEvalReference:
    """Map one evaluation case to LangSmith reference outputs.

    Args:
        case: Synthetic development case.

    Returns:
        Typed reference payload for deterministic scorers.
    """

    visible_chunks: list[str] = []
    visible_tables: list[str] = []
    forbidden: list[str] = []
    for link in case.evidence_links:
        identifiers = tuple(item for item in (link.chunk_id, link.table_id) if item)
        if link.visible_to_actor:
            if link.chunk_id:
                visible_chunks.append(link.chunk_id)
            if link.table_id:
                visible_tables.append(link.table_id)
        else:
            forbidden.extend(identifiers)
    profile = case.expected_profile
    expected_fields = {
        "language": _profile_value(profile.language.value),
        "query_type": _profile_value(profile.query_type.value),
        "exact_terms": _profile_value(profile.exact_terms.value),
        "codes": _profile_value(profile.codes.value),
        "entities": _profile_value(profile.entities.value),
    }
    return AgentEvalReference(
        acceptable_answers=tuple(case.acceptable_answers),
        expected_route=case.expected_route.value,
        refusal_kind=case.refusal_kind.value,
        visible_chunk_ids=tuple(dict.fromkeys(visible_chunks)),
        visible_table_ids=tuple(dict.fromkeys(visible_tables)),
        forbidden_evidence_ids=tuple(dict.fromkeys(forbidden)),
        expected_profile_fields=expected_fields,
    )


def case_to_example_metadata(
    case: EvaluationCase,
    *,
    case_hash: str,
    manifest_hash: str,
) -> dict[str, object]:
    """Build LangSmith example metadata. No secrets.

    Args:
        case: Synthetic development case.
        case_hash: Case content SHA-256.
        manifest_hash: Selected-set manifest SHA-256.

    Returns:
        Exportable metadata mapping.
    """

    return {
        "schema_version": case.schema_version,
        "label_revision": case.label_revision,
        "split": DatasetSplit.DEVELOPMENT.value,
        "source_family_id": case.source_family_id,
        "query_class": case.query_class.value,
        "language": case.language,
        "redaction_class": case.redaction_class,
        "case_content_hash": case_hash,
        "manifest_hash": manifest_hash,
        "agent_eval_schema_version": AGENT_EVAL_SCHEMA_VERSION,
    }


def failed_target_output(case_id: str, *, failure_kind: str) -> AgentEvalOutput:
    """Return a scored failed target output so LangSmith still records the case.

    Args:
        case_id: Case identifier.
        failure_kind: Named infrastructure failure.

    Returns:
        Output with ``completed=False`` and empty citations.
    """

    return AgentEvalOutput(
        case_id=case_id,
        completed=False,
        failure_kind=failure_kind,
        answer_status="",
    )


def output_from_graph_state(
    case_id: str,
    state: Mapping[str, Any],
    *,
    run_id: str | None = None,
    conversation_id: str | None = None,
    latency_ms: int | None = None,
    agent_cost_usd: str = "0",
    bm25_fallback: str | None = None,
    graph_degraded: bool = False,
) -> AgentEvalOutput:
    """Extract evaluation output from final query-graph state.

    Args:
        case_id: Case identifier.
        state: Final graph state mapping.
        run_id: Application run id.
        conversation_id: Synthetic conversation id.
        latency_ms: End-to-end latency.
        agent_cost_usd: Recorded agent USD.
        bm25_fallback: Named BM25 fallback.
        graph_degraded: Whether graph retrieve was unbound or failed.

    Returns:
        Normalized output. Missing answer fields yield an incomplete row.
    """

    answer = _as_mapping(state.get("answer"))
    fusion = _as_mapping(state.get("fusion"))
    preparation = _as_mapping(state.get("preparation"))
    citations = _as_sequence(answer.get("citations"))
    table_citations = _as_sequence(answer.get("table_citations"))
    cited_chunks = _collect_ids(citations, "chunk_id")
    cited_tables = _collect_ids(citations, "table_id") | _collect_ids(
        table_citations, "table_id"
    )
    selected = _collect_ids(_as_sequence(fusion.get("evidence")), "chunk_id")
    selected |= _collect_ids(_as_sequence(fusion.get("evidence")), "table_id")
    status = str(answer.get("status") or "")
    refusal = None
    if status == "refused":
        refusal = "refused"
    elif status == "partial":
        refusal = "approved_limitation"
    profile_fields = _extract_profile_fields(preparation)
    remaining_model = _optional_int(state.get("remaining_model_calls"))
    completed = bool(answer) and status in {"complete", "partial", "refused"}
    return AgentEvalOutput(
        case_id=case_id,
        run_id=run_id,
        conversation_id=conversation_id,
        completed=completed,
        failure_kind=None if completed else "target_incomplete",
        answer_text=str(answer.get("answer_text") or ""),
        answer_status=status,
        requested_route=_optional_str(state.get("requested_route")),
        effective_route=_optional_str(state.get("effective_route")),
        corrected_route=_optional_str(state.get("corrected_route")),
        cited_chunk_ids=tuple(sorted(cited_chunks)),
        cited_table_ids=tuple(sorted(cited_tables)),
        selected_evidence_ids=tuple(sorted(selected)),
        refusal_kind=refusal,
        profile_fields=profile_fields,
        remaining_model_calls=remaining_model,
        remaining_tool_calls=_optional_int(state.get("remaining_tool_calls")),
        remaining_corrections=_optional_int(state.get("remaining_corrections")),
        remaining_subquestions=_optional_int(state.get("remaining_subquestions")),
        remaining_recursion_steps=_optional_int(state.get("remaining_recursion_steps")),
        deadline_exceeded=bool(state.get("deadline_exceeded")),
        latency_ms=latency_ms,
        agent_cost_usd=agent_cost_usd,
        bm25_fallback=bm25_fallback,
        graph_degraded=graph_degraded,
    )


def score_route_correct(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Score whether the effective route matches the labeled route.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        ``1.0`` on an allowed mapping, otherwise ``0.0``.
    """

    effective = (output.effective_route or "").strip().lower()
    expected = reference.expected_route.strip().lower()
    if expected == ExpectedRoute.REFUSAL.value:
        return 1.0 if effective in REFUSAL_ROUTE_ALIASES else 0.0
    return 1.0 if effective == expected else 0.0


def score_refusal_correct(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Score refusal/limitation behavior against labeled truth.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        ``1.0`` when refusal or answer behavior matches the label.
    """

    expected_refusal = reference.refusal_kind != RefusalKind.NONE.value
    status = output.answer_status
    refused_or_limited = status in {"refused", "partial"}
    complete_answer = status == "complete"
    if expected_refusal:
        return 1.0 if refused_or_limited else 0.0
    if complete_answer:
        return 1.0
    return 0.0


def score_citation_precision(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Score citation precision against visible gold ids.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        Precision in ``[0, 1]``. Empty/empty is ``1.0``. Citations with no
        visible gold score ``0.0``.
    """

    cited = _cited_ids(output)
    gold = _visible_gold_ids(reference)
    if not cited and not gold:
        return 1.0
    if cited and not gold:
        return 0.0
    if not cited:
        return 0.0
    return len(cited & gold) / len(cited)


def score_citation_recall(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Score citation recall against visible gold ids.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        Recall in ``[0, 1]``. Empty/empty is ``1.0``.
    """

    cited = _cited_ids(output)
    gold = _visible_gold_ids(reference)
    if not cited and not gold:
        return 1.0
    if not gold:
        return 1.0 if not cited else 0.0
    return len(cited & gold) / len(gold)


def score_acl_leak_free(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Score whether cited or selected ids stay outside forbidden evidence.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        ``1.0`` only when no cited/selected id is forbidden or invisible.
    """

    used = _cited_ids(output) | set(output.selected_evidence_ids)
    forbidden = set(reference.forbidden_evidence_ids)
    if used & forbidden:
        return 0.0
    return 1.0


def score_profile_fields_correct(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> tuple[float, dict[str, float]]:
    """Compare structured preparation fields with the frozen expected profile.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        Aggregate score in ``[0, 1]`` and per-field scores.
    """

    expected = reference.expected_profile_fields
    if not expected:
        return 1.0, {}
    observed = output.profile_fields
    per_field: dict[str, float] = {}
    for key, gold in expected.items():
        got = observed.get(key)
        per_field[key] = 1.0 if _values_equal(got, gold) else 0.0
    aggregate = sum(per_field.values()) / len(per_field)
    return aggregate, per_field


def score_bounds_respected(output: AgentEvalOutput) -> float:
    """Score whether deadline and remaining ceilings stayed non-negative.

    Args:
        output: Target output.

    Returns:
        ``1.0`` when all remaining counters are present and non-negative and
        the deadline was not exceeded. Infrastructure gaps score ``0.0``.
    """

    remaining = (
        output.remaining_model_calls,
        output.remaining_tool_calls,
        output.remaining_corrections,
        output.remaining_subquestions,
        output.remaining_recursion_steps,
    )
    if any(value is None for value in remaining):
        return 0.0
    if any(int(value or 0) < 0 for value in remaining):
        return 0.0
    if output.deadline_exceeded:
        return 0.0
    return 1.0


def score_answer_reference_overlap(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Diagnostic token overlap against acceptable answers. Not a release gate.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        Overlap in ``[0, 1]``. Empty acceptable answers yield ``1.0`` when the
        agent also produced no answer text.
    """

    answer_tokens = _tokens(output.answer_text)
    gold_sets = [_tokens(item) for item in reference.acceptable_answers]
    if not gold_sets:
        return 1.0 if not answer_tokens else 0.0
    if not answer_tokens:
        return 0.0
    best = 0.0
    for gold in gold_sets:
        if not gold:
            continue
        overlap = len(answer_tokens & gold) / len(answer_tokens | gold)
        if overlap > best:
            best = overlap
    return best


def score_target_completed(output: AgentEvalOutput) -> float:
    """Score whether the target produced a valid terminal output.

    Args:
        output: Target output.

    Returns:
        ``1.0`` when completed, otherwise ``0.0``.
    """

    return 1.0 if output.completed else 0.0


def score_all(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> dict[str, float]:
    """Return every deterministic evaluator score for one case.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        Mapping of stable evaluator keys to numeric scores.
    """

    profile_score, _per_field = score_profile_fields_correct(output, reference)
    return {
        "route_correct": score_route_correct(output, reference),
        "refusal_correct": score_refusal_correct(output, reference),
        "citation_precision": score_citation_precision(output, reference),
        "citation_recall": score_citation_recall(output, reference),
        "acl_leak_free": score_acl_leak_free(output, reference),
        "profile_fields_correct": profile_score,
        "bounds_respected": score_bounds_respected(output),
        "answer_reference_overlap": score_answer_reference_overlap(output, reference),
        "target_completed": score_target_completed(output),
    }


def hard_failure_reasons(
    output: AgentEvalOutput, scores: Mapping[str, float]
) -> tuple[str, ...]:
    """Return hard-failure reasons that must not be averaged away.

    Args:
        output: Target output.
        scores: Deterministic scores.

    Returns:
        Ordered reason tokens. ACL leaks are always included when scored 0.
    """

    reasons: list[str] = []
    if scores.get("acl_leak_free", 1.0) == 0.0:
        reasons.append("acl_leak_free")
    if scores.get("target_completed", 1.0) == 0.0:
        reasons.append(output.failure_kind or "target_incomplete")
    return tuple(reasons)


def parse_target_output(
    payload: Mapping[str, Any] | AgentEvalOutput,
) -> AgentEvalOutput:
    """Parse a LangSmith target payload into ``AgentEvalOutput``.

    Args:
        payload: Target return mapping or already-typed output.

    Returns:
        Typed output. Unknown mappings become an incomplete failed row.
    """

    if isinstance(payload, AgentEvalOutput):
        return payload
    try:
        return AgentEvalOutput.model_validate(payload)
    except (TypeError, ValueError):
        case_id = str(payload.get("case_id") or "unknown")
        return failed_target_output(case_id, failure_kind="target_output_invalid")


def parse_reference(
    payload: Mapping[str, Any] | AgentEvalReference,
) -> AgentEvalReference:
    """Parse a LangSmith example reference into ``AgentEvalReference``.

    Args:
        payload: Example outputs mapping or already-typed reference.

    Returns:
        Typed reference.

    Raises:
        AgentEvalError: When the reference cannot be validated.
    """

    if isinstance(payload, AgentEvalReference):
        return payload
    try:
        return AgentEvalReference.model_validate(payload)
    except (TypeError, ValueError) as exc:
        raise AgentEvalError("reference_invalid") from exc


def _evaluator(
    key: str,
    score_fn: Callable[[AgentEvalOutput, AgentEvalReference], float],
    *,
    comment: str,
) -> LangSmithEvaluator:
    """Build one LangSmith evaluator callback.

    Args:
        key: Stable evaluator key.
        score_fn: Deterministic scorer.
        comment: Bounded comment without source text.

    Returns:
        Callback compatible with ``Client.evaluate``.
    """

    def _run(run: Any, example: Any) -> EvaluatorResult:
        """Score one LangSmith run against its example reference.

        Args:
            run: LangSmith run with ``outputs``.
            example: LangSmith example with ``outputs``.

        Returns:
            Evaluator dict with ``key``, ``score``, and ``comment``.
        """

        outputs = _run_outputs(run)
        reference = parse_reference(_example_outputs(example))
        output = parse_target_output(outputs)
        score = score_fn(output, reference)
        return {"key": key, "score": score, "comment": comment}

    _run.__name__ = f"eval_{key}"
    _run.__qualname__ = f"eval_{key}"
    return _run


def deterministic_evaluators() -> tuple[LangSmithEvaluator, ...]:
    """Return the pinned deterministic LangSmith evaluators.

    Returns:
        Ordered evaluator callbacks. ``answer_reference_overlap`` is labeled
        diagnostic in its comment and is not a release gate.
    """

    return (
        _evaluator(
            "route_correct",
            score_route_correct,
            comment="effective route equals labeled route, with refusal aliases",
        ),
        _evaluator(
            "refusal_correct",
            score_refusal_correct,
            comment="refusal or complete-answer behavior matches labeled truth",
        ),
        _evaluator(
            "citation_precision",
            score_citation_precision,
            comment="cited ids versus visible gold; empty/empty=1",
        ),
        _evaluator(
            "citation_recall",
            score_citation_recall,
            comment="visible gold coverage; empty/empty=1",
        ),
        _evaluator(
            "acl_leak_free",
            score_acl_leak_free,
            comment="hard failure when cited or selected ids are forbidden",
        ),
        _evaluator(
            "profile_fields_correct",
            lambda output, reference: score_profile_fields_correct(output, reference)[
                0
            ],
            comment="preparation fields versus frozen expected profile",
        ),
        _evaluator(
            "bounds_respected",
            lambda output, _reference: score_bounds_respected(output),
            comment="deadline and remaining ceilings stayed non-negative",
        ),
        _evaluator(
            "answer_reference_overlap",
            score_answer_reference_overlap,
            comment="diagnostic token overlap; not a release gate",
        ),
        _evaluator(
            "target_completed",
            lambda output, _reference: score_target_completed(output),
            comment="infrastructure errors score 0 and remain visible",
        ),
    )


def judge_evaluator(
    judge: Callable[[AgentEvalOutput, AgentEvalReference], AgentJudgeResult],
    *,
    metric: Literal["correctness", "groundedness", "refusal_quality"],
) -> LangSmithEvaluator:
    """Wrap one judge metric as a LangSmith evaluator.

    Args:
        judge: One-call-per-case judge. Failures must not raise.
        metric: Which judge field to export.

    Returns:
        Evaluator callback. Judge failure is a named evaluator failure.
    """

    def _run(run: Any, example: Any) -> EvaluatorResult:
        """Export one judge metric, or a named failure score of 0.

        Args:
            run: LangSmith run.
            example: LangSmith example.

        Returns:
            Evaluator dict.
        """

        output = parse_target_output(_run_outputs(run))
        reference = parse_reference(_example_outputs(example))
        result = judge(output, reference)
        if result.failed:
            return {
                "key": f"judge_{metric}",
                "score": 0.0,
                "comment": result.failure_kind or "judge_failed",
            }
        return {
            "key": f"judge_{metric}",
            "score": getattr(result, metric),
            "comment": "optional_llm_judge",
        }

    _run.__name__ = f"eval_judge_{metric}"
    return _run


def median_latency_ms(values: Sequence[int]) -> int | None:
    """Return the median of recorded latencies.

    Args:
        values: Latency samples in milliseconds.

    Returns:
        Median as an int, or None when empty.
    """

    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def decimal_sum(values: Sequence[str]) -> str:
    """Sum decimal strings without binary float rounding.

    Args:
        values: Decimal strings.

    Returns:
        Sum as a normalized decimal string.
    """

    total = sum((Decimal(item) for item in values), Decimal("0"))
    return format(total, "f")


def _cited_ids(output: AgentEvalOutput) -> set[str]:
    """Return cited chunk and table identifiers.

    Args:
        output: Target output.

    Returns:
        Set of cited ids.
    """

    return set(output.cited_chunk_ids) | set(output.cited_table_ids)


def _visible_gold_ids(reference: AgentEvalReference) -> set[str]:
    """Return visible gold chunk and table identifiers.

    Args:
        reference: Frozen reference.

    Returns:
        Set of visible gold ids.
    """

    return set(reference.visible_chunk_ids) | set(reference.visible_table_ids)


def _tokens(text: str) -> set[str]:
    """Return lowercase alphanumeric tokens for diagnostic overlap.

    Args:
        text: Answer or gold text.

    Returns:
        Token set.
    """

    return {item.lower() for item in _TOKEN_RE.findall(text)}


def _profile_value(value: object) -> object:
    """Return a JSON-compatible profile value.

    Args:
        value: Profile field value.

    Returns:
        Lists copied as tuples of strings when possible.
    """

    if isinstance(value, list):
        return tuple(str(item) for item in cast(list[object], value))
    return value


def _values_equal(left: object, right: object) -> bool:
    """Compare profile values with list/tuple normalization.

    Args:
        left: Observed value.
        right: Expected value.

    Returns:
        True when values are equal after sequence normalization.
    """

    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return tuple(cast(Sequence[object], left)) == tuple(
            cast(Sequence[object], right)
        )
    return left == right


def _extract_profile_fields(preparation: Mapping[str, Any]) -> dict[str, object]:
    """Extract comparable profile fields from graph preparation.

    Args:
        preparation: Preparation mapping.

    Returns:
        Mapping of stable field names to values.
    """

    nested = _as_mapping(preparation.get("profile"))
    source = nested or preparation
    fields: dict[str, object] = {}
    for key in ("language", "query_type", "exact_terms", "codes", "entities"):
        if key in source:
            value = source[key]
            if isinstance(value, Mapping) and "value" in value:
                wrapped = cast(Mapping[str, object], value)
                fields[key] = _profile_value(wrapped["value"])
            else:
                fields[key] = _profile_value(cast(object, value))
    return fields


def _as_mapping(value: object) -> dict[str, Any]:
    """Return a mapping or an empty dict.

    Args:
        value: Candidate mapping.

    Returns:
        String-keyed dict.
    """

    if isinstance(value, Mapping):
        typed = cast(Mapping[object, object], value)
        return {str(key): item for key, item in typed.items()}
    return {}


def _as_sequence(value: object) -> tuple[Any, ...]:
    """Return a tuple for a sequence, else empty.

    Args:
        value: Candidate sequence.

    Returns:
        Tuple of items.
    """

    if isinstance(value, (str, bytes)):
        return ()
    if isinstance(value, Sequence):
        return tuple(cast(Sequence[object], value))
    return ()


def _collect_ids(items: Sequence[Any], field: str) -> set[str]:
    """Collect non-empty string identifiers from mappings.

    Args:
        items: Mapping items.
        field: Identifier field name.

    Returns:
        Set of ids.
    """

    found: set[str] = set()
    for item in items:
        mapping = _as_mapping(item)
        raw = mapping.get(field)
        if isinstance(raw, str) and raw:
            found.add(raw)
    return found


def _optional_int(value: object) -> int | None:
    """Parse an optional integer remaining counter.

    Args:
        value: Candidate int.

    Returns:
        Int or None.
    """

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _optional_str(value: object) -> str | None:
    """Return a non-empty string or None.

    Args:
        value: Candidate string.

    Returns:
        String or None.
    """

    if isinstance(value, str) and value:
        return value
    return None


def _run_outputs(run: Any) -> dict[str, Any]:
    """Extract outputs from a LangSmith run-like object.

    Args:
        run: Run object or mapping.

    Returns:
        Outputs mapping.
    """

    if isinstance(run, Mapping):
        mapped = cast(Mapping[str, object], run)
        outputs = mapped.get("outputs")
        if isinstance(outputs, Mapping):
            return dict(cast(Mapping[str, Any], outputs))
        return dict(mapped)
    outputs = getattr(run, "outputs", None)
    if isinstance(outputs, Mapping):
        return dict(cast(Mapping[str, Any], outputs))
    return {}


def _example_outputs(example: Any) -> dict[str, Any]:
    """Extract reference outputs from a LangSmith example-like object.

    Args:
        example: Example object or mapping.

    Returns:
        Outputs mapping.
    """

    if isinstance(example, Mapping):
        mapped = cast(Mapping[str, object], example)
        outputs = mapped.get("outputs")
        if isinstance(outputs, Mapping):
            return dict(cast(Mapping[str, Any], outputs))
        return dict(mapped)
    outputs = getattr(example, "outputs", None)
    if isinstance(outputs, Mapping):
        return dict(cast(Mapping[str, Any], outputs))
    return {}
