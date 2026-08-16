"""Pydantic contracts for the versioned optional-tool registry."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smart_rag_core.security.identity import UserRole
from smart_rag_core.tools.constants import (
    CORE_FORBIDDEN_TOOL_KEYS,
    L0_CAPABILITIES,
    L0_SAFETY_RULES,
    L1_TOP_K,
    L3_GUIDANCE_MAX_BYTES,
    MAX_OPTIONAL_MANIFESTS,
)
from smart_rag_core.tools.exceptions import ToolError


class RiskClass(StrEnum):
    """Coarse risk label disclosed on Level 1 cards."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SideEffectClass(StrEnum):
    """Side-effect class independently rechecked by the executor."""

    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    REMOTE = "remote"


class SelectionPolicy(StrEnum):
    """How optional tools are chosen after the comparative fixture."""

    DETERMINISTIC_MAPPING = "deterministic_mapping"
    CATALOG_DISCOVERY = "catalog_discovery"
    SKIPPED = "skipped"


class OptionalIntent(StrEnum):
    """Typed optional intents. Core retrieval is never one of these."""

    NONE = "none"
    EXPORT_CSV = "export_csv"
    EXPORT_XLSX = "export_xlsx"
    AMBIGUOUS_EXPORT = "ambiguous_export"
    ADMINISTRATION = "administration"


class ToolQuotas(BaseModel):
    """Per-invocation resource ceilings enforced before side effects.

    Attributes:
        max_rows: Maximum result or export rows.
        max_bytes: Maximum payload bytes.
        max_calls_per_run: Maximum executions of this tool key per run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_rows: int = Field(default=10_000, ge=1, le=50_000)
    max_bytes: int = Field(default=1_048_576, ge=1, le=8_388_608)
    max_calls_per_run: int = Field(default=1, ge=1, le=5)


class ExecutorContract(BaseModel):
    """What the executor must recheck. Planner output is not authority.

    Attributes:
        recheck_role: Live role from ``CallerContext`` / runtime.
        recheck_arguments: Schema-validate arguments.
        recheck_quotas: Enforce row/byte/call quotas.
        recheck_idempotency: Require and replay idempotency keys for writes.
        recheck_side_effect: Enforce the one side-effecting-tool ceiling.
        recheck_resource_ids: Recheck table IDs and similar resource limits.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recheck_role: bool = True
    recheck_arguments: bool = True
    recheck_quotas: bool = True
    recheck_idempotency: bool = True
    recheck_side_effect: bool = True
    recheck_resource_ids: bool = True


class ToolDefinition(BaseModel):
    """One versioned allow-listed optional tool. Never a core retrieve tool.

    Attributes:
        tool_key: Stable catalog id.
        version_label: Manifest version the executor rechecks.
        short_name: Compact display name.
        description: Longer description used for ranking, not default prompts.
        one_line_purpose: Level 1 purpose line.
        tags: Lexical ranking tags.
        capabilities: Capability tokens for ranking.
        risk_class: Disclosed risk class.
        required_role: Minimum live role.
        required_features: Feature flags implied by role in v1.
        compact_card: Extra bounded Level 1 text.
        json_schema: JSON Schema object for arguments.
        examples: Short argument examples for Level 2.
        policy: Side-effect and authorization policy for Level 2.
        long_guidance: Level 3 operational guidance.
        side_effect_class: Executor side-effect class.
        quotas: Resource ceilings.
        executor_contract: Independent recheck flags.
        active: Disabled/stale tools cannot execute.
        catalog_discoverable: False for MCP imports that are metadata-only.
        mcp_origin: True when the row was imported from MCP metadata.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_key: str = Field(min_length=1, max_length=64)
    version_label: str = Field(min_length=1, max_length=32)
    short_name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=512)
    one_line_purpose: str = Field(min_length=1, max_length=160)
    tags: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    risk_class: RiskClass
    required_role: UserRole
    required_features: tuple[str, ...] = ()
    compact_card: str = Field(default="", max_length=200)
    json_schema: dict[str, object]
    examples: tuple[str, ...] = ()
    policy: str = Field(min_length=1, max_length=512)
    long_guidance: str = Field(default="", max_length=16_384)
    side_effect_class: SideEffectClass
    quotas: ToolQuotas = Field(default_factory=ToolQuotas)
    executor_contract: ExecutorContract = Field(default_factory=ExecutorContract)
    active: bool = True
    catalog_discoverable: bool = True
    mcp_origin: bool = False

    @model_validator(mode="after")
    def _forbid_core_keys(self) -> ToolDefinition:
        """Reject core retrieval/answer keys from the optional catalog.

        Returns:
            This definition.

        Raises:
            ToolError: If ``tool_key`` is a forbidden core tool.
        """

        if self.tool_key in CORE_FORBIDDEN_TOOL_KEYS:
            raise ToolError("core_tool_not_catalogable")
        return self


class Level0Payload(BaseModel):
    """Level 0 disclosure: meta capabilities and immutable safety rules.

    Attributes:
        capabilities: ``search_tool_catalog`` / ``load_tool_manifest`` only.
        safety_rules: Immutable rules. No catalog names.
        registry_version: Allow-list version.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    capabilities: tuple[str, ...] = L0_CAPABILITIES
    safety_rules: tuple[str, ...] = L0_SAFETY_RULES
    registry_version: str


class Level1Card(BaseModel):
    """Bounded Level 1 card after role/feature filtering.

    Attributes:
        tool_key: Catalog id of a visible tool.
        short_name: Display name.
        one_line_purpose: One-line purpose.
        risk_class: Risk class.
        required_role: Minimum role.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_key: str
    short_name: str
    one_line_purpose: str
    risk_class: RiskClass
    required_role: UserRole


class Level1Payload(BaseModel):
    """Level 1 top-k cards. Hidden tools contribute neither names nor counts.

    Attributes:
        cards: At most ``L1_TOP_K`` visible cards.
        disclosed_count: Equal to ``len(cards)``. Never a hidden total.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cards: tuple[Level1Card, ...] = Field(max_length=L1_TOP_K)
    disclosed_count: int = Field(ge=0, le=L1_TOP_K)

    @model_validator(mode="after")
    def _count_matches(self) -> Level1Payload:
        """Keep disclosed_count equal to the visible card list.

        Returns:
            This payload.

        Raises:
            ToolError: If the count disagrees with the card list.
        """

        if self.disclosed_count != len(self.cards):
            raise ToolError("unauthorized_count_leakage")
        return self


class Level2Manifest(BaseModel):
    """Level 2 schema, examples, and policy for one selected tool.

    Attributes:
        tool_key: Selected catalog id.
        version_label: Version the executor will recheck.
        json_schema: Argument schema.
        examples: Short examples.
        policy: Authorization and side-effect policy.
        side_effect_class: Side-effect class.
        risk_class: Risk class.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_key: str
    version_label: str
    json_schema: dict[str, object]
    examples: tuple[str, ...]
    policy: str
    side_effect_class: SideEffectClass
    risk_class: RiskClass


class Level3Guidance(BaseModel):
    """Bounded Level 3 guidance loaded only when execution needs it.

    Attributes:
        tool_key: Selected catalog id.
        section: Truncated operational guidance.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_key: str
    section: str = Field(min_length=1, max_length=L3_GUIDANCE_MAX_BYTES)


class PlannedInvocation(BaseModel):
    """Planner-selected invocation. Not authorization.

    Attributes:
        tool_key: Selected key.
        version_label: Selected version.
        arguments: Proposed arguments.
        planned_role: Role observed at plan time.
        planned_user_id: User id observed at plan time.
        idempotency_key: Required for write/admin/remote tools.
        load_guidance: Whether Level 3 is required for execution.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_key: str
    version_label: str
    arguments: dict[str, object]
    planned_role: UserRole
    planned_user_id: str = Field(min_length=36, max_length=36)
    idempotency_key: str | None = Field(default=None, max_length=128)
    load_guidance: bool = False


class OptionalTelemetry(BaseModel):
    """Discovery telemetry that never names hidden catalog entries.

    Attributes:
        discovery_latency_ms: Catalog path latency, separate from retrieval.
        retrieval_latency_ms: Caller-supplied retrieval latency for contrast.
        tools_searched: Visible tools considered, never a hidden total.
        tools_disclosed: Level 1 cards returned.
        tools_loaded: Level 2 manifests loaded.
        tools_called: Executor invocations attempted.
        tools_rejected: Executor rejections.
        tools_useful: Successful executions.
        selection_mode: Deterministic, discovery, or skipped.
        catalog_llm_call_count: ``0`` or ``1``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    discovery_latency_ms: float = Field(ge=0.0)
    retrieval_latency_ms: float = Field(default=0.0, ge=0.0)
    tools_searched: int = Field(ge=0)
    tools_disclosed: int = Field(ge=0)
    tools_loaded: int = Field(ge=0)
    tools_called: int = Field(ge=0)
    tools_rejected: int = Field(ge=0)
    tools_useful: int = Field(ge=0)
    selection_mode: SelectionPolicy
    catalog_llm_call_count: Literal[0, 1] = 0


class ComparisonMetrics(BaseModel):
    """Deterministic mapping versus catalog discovery on the 20-tool fixture.

    Attributes:
        tool_count: Catalog size, at least 20.
        case_count: Scored queries.
        deterministic_accuracy: Fraction of gold keys matched.
        discovery_accuracy: Fraction of gold keys matched by discovery.
        accuracy_gain_pp: Discovery minus deterministic, in percentage points.
        deterministic_latency_ms: Mapping latency.
        discovery_latency_ms: Discovery latency.
        deterministic_tokens: Estimated prompt tokens for mapping cards.
        discovery_tokens: Estimated prompt tokens for L0+L1+selected L2.
        selected_policy: Policy frozen after the comparison.
        justification: Human-readable decision.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_count: int = Field(ge=20)
    case_count: int = Field(ge=1)
    deterministic_accuracy: float = Field(ge=0.0, le=1.0)
    discovery_accuracy: float = Field(ge=0.0, le=1.0)
    accuracy_gain_pp: float
    deterministic_latency_ms: float = Field(ge=0.0)
    discovery_latency_ms: float = Field(ge=0.0)
    deterministic_tokens: int = Field(ge=0)
    discovery_tokens: int = Field(ge=0)
    selected_policy: SelectionPolicy
    justification: str = Field(min_length=1, max_length=512)


class ExecutionResult(BaseModel):
    """Executor outcome. Success never implies a catalog LLM round.

    Attributes:
        tool_key: Executed key.
        version_label: Rechecked version.
        status: ``ok``, ``replayed``, or ``rejected``.
        reason: Rejection reason, or empty on success.
        payload: Bounded JSON-safe result.
        side_effect: True when a new side effect was consumed.
        remaining_tool_calls: Ceiling after this call.
        remaining_side_effects: Ceiling after this call.
        remaining_manifests: Manifest slots remaining.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_key: str
    version_label: str
    status: Literal["ok", "replayed", "rejected"]
    reason: str = ""
    payload: dict[str, object] = Field(default_factory=dict)
    side_effect: bool = False
    remaining_tool_calls: int = Field(ge=0)
    remaining_side_effects: int = Field(ge=0)
    remaining_manifests: int = Field(ge=0, le=MAX_OPTIONAL_MANIFESTS)
