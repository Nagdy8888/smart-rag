"""Route-family envelopes. USD and call ceilings must match SQL."""

from __future__ import annotations

from dataclasses import dataclass
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
    Phase6RouteFamily.COMPOSITE: 75,
    Phase6RouteFamily.GRAPH_INSPECTION: 10,
    # QUALITY_TARGETS has no sixth deadline. Packet 1 uses the Hybrid 25s envelope.
    Phase6RouteFamily.NO_RETRIEVAL: 25,
    Phase6RouteFamily.SCOPED_REFUSAL: 25,
    Phase6RouteFamily.WEB_RESEARCH: 50,
}

FAMILY_MODEL_CALL_CEILING: dict[Phase6RouteFamily, int] = {
    Phase6RouteFamily.HYBRID: 7,
    Phase6RouteFamily.COMBINED: 8,
    Phase6RouteFamily.STRUCTURED_TABLE: 6,
    Phase6RouteFamily.COMPOSITE: 9,
    Phase6RouteFamily.GRAPH_INSPECTION: 3,
    Phase6RouteFamily.NO_RETRIEVAL: 7,
    Phase6RouteFamily.SCOPED_REFUSAL: 7,
    Phase6RouteFamily.WEB_RESEARCH: 5,
}
"""Signed call ceilings already include retrieve-time work.

Hybrid 7 is batched query embed + one rerank + answer-class headroom
(profile/answer/verifier/correction). Combined 8 adds LightRAG consume.
The defect is unpaid retrieve, not an undersized number. Envelope USD is
``ceiling *`` the family max kind cap (answer 0.40 except inspection 0.25)
and therefore already covers smaller embedding/rerank/lightrag kind caps.
"""

FAMILY_TOOL_CEILING: dict[Phase6RouteFamily, int] = {
    Phase6RouteFamily.HYBRID: 4,
    Phase6RouteFamily.COMBINED: 4,
    Phase6RouteFamily.STRUCTURED_TABLE: 4,
    Phase6RouteFamily.COMPOSITE: 5,
    Phase6RouteFamily.GRAPH_INSPECTION: 4,
    Phase6RouteFamily.NO_RETRIEVAL: 4,
    Phase6RouteFamily.SCOPED_REFUSAL: 4,
    Phase6RouteFamily.WEB_RESEARCH: 5,
}

FAMILY_PER_CALL_USD_CAP: dict[Phase6RouteFamily, Decimal] = {
    Phase6RouteFamily.HYBRID: Decimal("0.40"),
    Phase6RouteFamily.COMBINED: Decimal("0.40"),
    Phase6RouteFamily.STRUCTURED_TABLE: Decimal("0.40"),
    Phase6RouteFamily.COMPOSITE: Decimal("0.40"),
    Phase6RouteFamily.GRAPH_INSPECTION: Decimal("0.25"),
    Phase6RouteFamily.NO_RETRIEVAL: Decimal("0.40"),
    Phase6RouteFamily.SCOPED_REFUSAL: Decimal("0.40"),
    Phase6RouteFamily.WEB_RESEARCH: Decimal("0.40"),
}

FAMILY_PROMPT_TOKENS_PER_CALL: dict[Phase6RouteFamily, int] = {
    Phase6RouteFamily.HYBRID: 8000,
    Phase6RouteFamily.COMBINED: 8000,
    Phase6RouteFamily.STRUCTURED_TABLE: 8000,
    Phase6RouteFamily.COMPOSITE: 8000,
    Phase6RouteFamily.GRAPH_INSPECTION: 4000,
    Phase6RouteFamily.NO_RETRIEVAL: 8000,
    Phase6RouteFamily.SCOPED_REFUSAL: 8000,
    Phase6RouteFamily.WEB_RESEARCH: 8000,
}

FAMILY_COMPLETION_TOKENS_PER_CALL: dict[Phase6RouteFamily, int] = {
    Phase6RouteFamily.HYBRID: 2000,
    Phase6RouteFamily.COMBINED: 2000,
    Phase6RouteFamily.STRUCTURED_TABLE: 2000,
    Phase6RouteFamily.COMPOSITE: 2000,
    Phase6RouteFamily.GRAPH_INSPECTION: 1500,
    Phase6RouteFamily.NO_RETRIEVAL: 2000,
    Phase6RouteFamily.SCOPED_REFUSAL: 2000,
    Phase6RouteFamily.WEB_RESEARCH: 2000,
}


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
        model_call_ceiling: Maximum gateway calls including retrieve-time
            query embedding, OpenAI rerank, and LightRAG consume (QT-MC-*).
        tool_ceiling: Maximum tool executions (QT-TL-001).
        discovery_ceiling: Optional discovery rounds (QT-TL-002).
        manifest_ceiling: Optional manifests (global contract: three).
        side_effect_ceiling: Side-effecting tools (QT-TL-003).
        per_call_usd_cap: Conservative per-call USD cap for this family.
        envelope_usd: ``model_call_ceiling * per_call_usd_cap``. Retrieve
            kinds debit this same hold; they do not enlarge it.
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
    correction = 0 if family is Phase6RouteFamily.WEB_RESEARCH else CORRECTION_CEILING
    return RouteCeiling(
        family=family,
        deadline_seconds=FAMILY_DEADLINE_SECONDS[family],
        recursion_limit=RECURSION_LIMIT,
        correction_ceiling=correction,
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
