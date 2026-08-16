"""Server-owned route envelopes, ceilings, and exhaustion helpers.

Numbers here are Phase 6 engineering defaults derived from signed
``QUALITY_TARGETS.md`` rows (QT-DL-*, QT-MC-*, QT-TL-*, QT-COST-001,
QT-CAP-004). They are not client-signed replacements of those rows.
SQL ``app.query_route_envelope`` must stay byte-identical for USD and
call/tool ceilings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from smart_rag_core.query_admission.exceptions import QueryCeilingError
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily

DEFAULT_MONTHLY_LLM_BUDGET_USD = Decimal("200.00")
"""QT-COST-001 normal-operation monthly ceiling used when profile and company are null."""

MAX_CONCURRENT_QUERY_RUNS = 5
"""QT-CAP-004 company-wide simultaneous pending/running query runs."""

RECURSION_LIMIT = 24
CORRECTION_CEILING = 1
SUBQUESTION_CEILING = 3
DISCOVERY_CEILING = 1
MANIFEST_CEILING = 3
SIDE_EFFECT_CEILING = 1

FAMILY_DEADLINE_SECONDS: dict[Phase6RouteFamily, int] = {
    Phase6RouteFamily.HYBRID: 25,
    Phase6RouteFamily.COMBINED: 45,
    Phase6RouteFamily.STRUCTURED_TABLE: 30,
    Phase6RouteFamily.COMPOSITE: 50,
    Phase6RouteFamily.GRAPH_INSPECTION: 10,
    # QUALITY_TARGETS has no sixth deadline. Packet 1 uses the Hybrid 25s envelope.
    Phase6RouteFamily.NO_RETRIEVAL: 25,
    Phase6RouteFamily.SCOPED_REFUSAL: 25,
}

FAMILY_MODEL_CALL_CEILING: dict[Phase6RouteFamily, int] = {
    Phase6RouteFamily.HYBRID: 7,
    Phase6RouteFamily.COMBINED: 8,
    Phase6RouteFamily.STRUCTURED_TABLE: 6,
    Phase6RouteFamily.COMPOSITE: 9,
    Phase6RouteFamily.GRAPH_INSPECTION: 3,
    Phase6RouteFamily.NO_RETRIEVAL: 7,
    Phase6RouteFamily.SCOPED_REFUSAL: 7,
}

FAMILY_TOOL_CEILING: dict[Phase6RouteFamily, int] = {
    Phase6RouteFamily.HYBRID: 4,
    Phase6RouteFamily.COMBINED: 4,
    Phase6RouteFamily.STRUCTURED_TABLE: 4,
    Phase6RouteFamily.COMPOSITE: 5,
    Phase6RouteFamily.GRAPH_INSPECTION: 4,
    Phase6RouteFamily.NO_RETRIEVAL: 4,
    Phase6RouteFamily.SCOPED_REFUSAL: 4,
}

FAMILY_PER_CALL_USD_CAP: dict[Phase6RouteFamily, Decimal] = {
    Phase6RouteFamily.HYBRID: Decimal("0.40"),
    Phase6RouteFamily.COMBINED: Decimal("0.40"),
    Phase6RouteFamily.STRUCTURED_TABLE: Decimal("0.40"),
    Phase6RouteFamily.COMPOSITE: Decimal("0.40"),
    Phase6RouteFamily.GRAPH_INSPECTION: Decimal("0.25"),
    Phase6RouteFamily.NO_RETRIEVAL: Decimal("0.40"),
    Phase6RouteFamily.SCOPED_REFUSAL: Decimal("0.40"),
}

FAMILY_PROMPT_TOKENS_PER_CALL: dict[Phase6RouteFamily, int] = {
    Phase6RouteFamily.HYBRID: 8000,
    Phase6RouteFamily.COMBINED: 8000,
    Phase6RouteFamily.STRUCTURED_TABLE: 8000,
    Phase6RouteFamily.COMPOSITE: 8000,
    Phase6RouteFamily.GRAPH_INSPECTION: 4000,
    Phase6RouteFamily.NO_RETRIEVAL: 8000,
    Phase6RouteFamily.SCOPED_REFUSAL: 8000,
}

FAMILY_COMPLETION_TOKENS_PER_CALL: dict[Phase6RouteFamily, int] = {
    Phase6RouteFamily.HYBRID: 2000,
    Phase6RouteFamily.COMBINED: 2000,
    Phase6RouteFamily.STRUCTURED_TABLE: 2000,
    Phase6RouteFamily.COMPOSITE: 2000,
    Phase6RouteFamily.GRAPH_INSPECTION: 1500,
    Phase6RouteFamily.NO_RETRIEVAL: 2000,
    Phase6RouteFamily.SCOPED_REFUSAL: 2000,
}

USAGE_KIND_USD_CAPS: dict[str, Decimal] = {
    "profile": Decimal("0.08"),
    "rewrite": Decimal("0.08"),
    "embedding": Decimal("0.02"),
    "lightrag": Decimal("0.25"),
    "rerank": Decimal("0.20"),
    "answer": Decimal("0.40"),
    "summary": Decimal("0.25"),
    "verifier": Decimal("0.20"),
}

USAGE_KIND_PROMPT_TOKEN_CAPS: dict[str, int] = {
    "profile": 4000,
    "rewrite": 4000,
    "embedding": 8000,
    "lightrag": 8000,
    "rerank": 12000,
    "answer": 8000,
    "summary": 6000,
    "verifier": 4000,
}

USAGE_KIND_COMPLETION_TOKEN_CAPS: dict[str, int] = {
    "profile": 1500,
    "rewrite": 1500,
    "embedding": 0,
    "lightrag": 2000,
    "rerank": 2000,
    "answer": 2000,
    "summary": 1500,
    "verifier": 1000,
}

ALLOWED_USAGE_KINDS: frozenset[str] = frozenset(USAGE_KIND_USD_CAPS)


@dataclass(frozen=True, slots=True)
class RouteCeiling:
    """Server-assigned envelope for one Phase 6 route family.

    Attributes:
        family: Allow-listed ``Phase6RouteFamily``.
        deadline_seconds: Hard run deadline from QT-DL-* (or Hybrid for
            unspecified no_retrieval/scoped_refusal).
        recursion_limit: LangGraph superstep cap (QT-DL-008).
        correction_ceiling: Maximum routing/retrieval corrections (QT-DL-006).
        subquestion_ceiling: Maximum subquestions (QT-DL-007).
        model_call_ceiling: Maximum gateway calls including one batched
            query embedding per retrieve (QT-MC-*).
        tool_ceiling: Maximum tool executions (QT-TL-001).
        discovery_ceiling: Optional discovery rounds (QT-TL-002).
        manifest_ceiling: Optional manifests (global contract: three).
        side_effect_ceiling: Side-effecting tools (QT-TL-003).
        per_call_usd_cap: Conservative per-call USD cap for this family.
        envelope_usd: ``model_call_ceiling * per_call_usd_cap``.
        envelope_prompt_tokens: Prompt-token hold for the reservation.
        envelope_completion_tokens: Completion-token hold for the reservation.
    """

    family: Phase6RouteFamily
    deadline_seconds: int
    recursion_limit: int
    correction_ceiling: int
    subquestion_ceiling: int
    model_call_ceiling: int
    tool_ceiling: int
    discovery_ceiling: int
    manifest_ceiling: int
    side_effect_ceiling: int
    per_call_usd_cap: Decimal
    envelope_usd: Decimal
    envelope_prompt_tokens: int
    envelope_completion_tokens: int


def envelope_for_family(family: Phase6RouteFamily) -> RouteCeiling:
    """Return the server-owned ceiling table row for one route family.

    Args:
        family: Allow-listed Phase 6 family. Client strings must be parsed
            before calling; unknown values never enlarge this table.

    Returns:
        Frozen ceiling and reservation envelope.

    Raises:
        QueryCeilingError: If ``family`` is not in the server table.
    """

    if family not in FAMILY_DEADLINE_SECONDS:
        raise QueryCeilingError("unknown_route_family")
    model_calls = FAMILY_MODEL_CALL_CEILING[family]
    per_call = FAMILY_PER_CALL_USD_CAP[family]
    return RouteCeiling(
        family=family,
        deadline_seconds=FAMILY_DEADLINE_SECONDS[family],
        recursion_limit=RECURSION_LIMIT,
        correction_ceiling=CORRECTION_CEILING,
        subquestion_ceiling=SUBQUESTION_CEILING,
        model_call_ceiling=model_calls,
        tool_ceiling=FAMILY_TOOL_CEILING[family],
        discovery_ceiling=DISCOVERY_CEILING,
        manifest_ceiling=MANIFEST_CEILING,
        side_effect_ceiling=SIDE_EFFECT_CEILING,
        per_call_usd_cap=per_call,
        envelope_usd=per_call * model_calls,
        envelope_prompt_tokens=(FAMILY_PROMPT_TOKENS_PER_CALL[family] * model_calls),
        envelope_completion_tokens=(
            FAMILY_COMPLETION_TOKENS_PER_CALL[family] * model_calls
        ),
    )


def usage_kind_caps(usage_kind: str) -> tuple[Decimal, int, int]:
    """Return conservative per-call USD and token caps for one usage kind.

    Args:
        usage_kind: One of the allow-listed ``llm_usage.usage_kind`` values.

    Returns:
        ``(usd_cap, prompt_token_cap, completion_token_cap)``.

    Raises:
        QueryCeilingError: If the kind is not allow-listed.
    """

    if usage_kind not in ALLOWED_USAGE_KINDS:
        raise QueryCeilingError("unknown_usage_kind")
    return (
        USAGE_KIND_USD_CAPS[usage_kind],
        USAGE_KIND_PROMPT_TOKEN_CAPS[usage_kind],
        USAGE_KIND_COMPLETION_TOKEN_CAPS[usage_kind],
    )


def assert_deadline_open(*, now: datetime, deadline_at: datetime) -> None:
    """Refuse further work after the run deadline.

    Args:
        now: Current UTC timestamp.
        deadline_at: Server-assigned run deadline.

    Raises:
        QueryCeilingError: When ``now`` is at or after ``deadline_at``.
    """

    if now >= deadline_at:
        raise QueryCeilingError("deadline_exhausted")


def _assert_remaining(remaining: int, *, reason: str) -> int:
    """Decrement a remaining counter or fail closed.

    Args:
        remaining: Current remaining units.
        reason: Reason code when the counter is exhausted.

    Returns:
        ``remaining - 1``.

    Raises:
        QueryCeilingError: When ``remaining`` is already ``0`` or negative.
    """

    if remaining <= 0:
        raise QueryCeilingError(reason)
    return remaining - 1


def assert_call_available(remaining_model_calls: int) -> int:
    """Consume one gateway model call from the remaining ceiling.

    Hybrid's seventh call is reserved for a correction rerank or a
    non-deferrable summary. Later packets enforce that policy; this helper
    only enforces the numeric ceiling.

    Args:
        remaining_model_calls: Remaining counted gateway calls.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When the model-call ceiling is exhausted.
    """

    return _assert_remaining(remaining_model_calls, reason="model_call_exhausted")


def assert_tool_available(remaining_tool_calls: int) -> int:
    """Consume one tool execution from the remaining ceiling.

    Args:
        remaining_tool_calls: Remaining tool executions.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When the tool ceiling is exhausted.
    """

    return _assert_remaining(remaining_tool_calls, reason="tool_exhausted")


def assert_discovery_available(remaining_discovery_rounds: int) -> int:
    """Consume the single optional discovery round.

    Args:
        remaining_discovery_rounds: Remaining discovery rounds.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When discovery is already used.
    """

    return _assert_remaining(remaining_discovery_rounds, reason="discovery_exhausted")


def assert_manifest_available(remaining_manifests: int) -> int:
    """Consume one optional tool manifest slot.

    Args:
        remaining_manifests: Remaining optional manifests.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When the manifest ceiling is exhausted.
    """

    return _assert_remaining(remaining_manifests, reason="manifest_exhausted")


def assert_side_effect_available(remaining_side_effects: int) -> int:
    """Consume the single side-effecting tool slot.

    Args:
        remaining_side_effects: Remaining side-effecting tool slots.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When a side-effecting tool was already used.
    """

    return _assert_remaining(remaining_side_effects, reason="side_effect_exhausted")


def assert_recursion_available(remaining_recursion_steps: int) -> int:
    """Consume one LangGraph superstep from ``recursion_limit``.

    Args:
        remaining_recursion_steps: Remaining supersteps.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When recursion is exhausted.
    """

    return _assert_remaining(remaining_recursion_steps, reason="recursion_exhausted")


def assert_correction_available(remaining_corrections: int) -> int:
    """Consume the single routing/retrieval correction.

    Args:
        remaining_corrections: Remaining corrections.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When the correction was already used.
    """

    return _assert_remaining(remaining_corrections, reason="correction_exhausted")


def assert_subquestion_available(remaining_subquestions: int) -> int:
    """Consume one subquestion slot.

    Args:
        remaining_subquestions: Remaining subquestions.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When the subquestion ceiling is exhausted.
    """

    return _assert_remaining(remaining_subquestions, reason="subquestion_exhausted")
