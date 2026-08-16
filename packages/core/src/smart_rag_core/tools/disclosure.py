"""Level 0-3 progressive disclosure. Unselected schemas never enter payloads."""

from __future__ import annotations

from smart_rag_core.security.identity import UserRole
from smart_rag_core.tools.budgets import (
    assert_card_budget,
    assert_guidance_budget,
    assert_manifest_budget,
    assert_model_input_budget,
)
from smart_rag_core.tools.catalog import default_registry, get_tool
from smart_rag_core.tools.constants import (
    L0_CAPABILITIES,
    L0_SAFETY_RULES,
    L1_TOP_K,
    MAX_OPTIONAL_MANIFESTS,
    MAX_SELECTED_TOOL_SCHEMAS,
    REGISTRY_VERSION,
    consume_remaining,
)
from smart_rag_core.tools.exceptions import ToolError
from smart_rag_core.tools.models import (
    Level0Payload,
    Level1Card,
    Level1Payload,
    Level2Manifest,
    Level3Guidance,
    ToolDefinition,
)
from smart_rag_core.tools.permissions import visible_tools
from smart_rag_core.tools.ranking import Embedder, rank_tools


def level0_payload() -> Level0Payload:
    """Build Level 0 meta capabilities and immutable safety rules.

    Returns:
        Payload with no catalog names, schemas, or hidden counts.
    """

    return Level0Payload(
        capabilities=L0_CAPABILITIES,
        safety_rules=L0_SAFETY_RULES,
        registry_version=REGISTRY_VERSION,
    )


def level1_cards(
    query: str,
    *,
    role: UserRole,
    registry: tuple[ToolDefinition, ...] | None = None,
    embedder: Embedder | None = None,
    top_k: int = L1_TOP_K,
) -> Level1Payload:
    """Build permission-filtered Level 1 cards.

    Hidden tools contribute neither names nor a residual count. Ranking is
    lexical, plus an optional embedder that must not be a catalog LLM.

    Args:
        query: Untrusted user text.
        role: Live role.
        registry: Optional catalog.
        embedder: Optional embedding ranker.
        top_k: Card cap, at most ``L1_TOP_K``.

    Returns:
        Bounded visible cards.

    Raises:
        ToolError: Oversized card.
    """

    catalog = registry if registry is not None else default_registry()
    visible = visible_tools(catalog, role=role)
    ranked = rank_tools(query, visible, embedder=embedder, limit=min(top_k, L1_TOP_K))
    cards: list[Level1Card] = []
    for tool in ranked:
        card = Level1Card(
            tool_key=tool.tool_key,
            short_name=tool.short_name,
            one_line_purpose=tool.one_line_purpose,
            risk_class=tool.risk_class,
            required_role=tool.required_role,
        )
        assert_card_budget(card)
        cards.append(card)
    return Level1Payload(cards=tuple(cards), disclosed_count=len(cards))


def load_manifests(
    keys: tuple[str, ...],
    *,
    role: UserRole,
    remaining_manifests: int,
    registry: tuple[ToolDefinition, ...] | None = None,
) -> tuple[tuple[Level2Manifest, ...], int]:
    """Load Level 2 manifests for selected keys only.

    Args:
        keys: Selected tool keys. At most three unique keys.
        role: Live role used to hide unauthorized selections.
        remaining_manifests: Remaining manifest slots.
        registry: Optional catalog.

    Returns:
        Manifests and remaining slots after consume.

    Raises:
        ToolError: Fourth key, unauthorized key, disabled/stale tool, or
            oversized manifest.
    """

    unique: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        unique.append(key)
    if len(unique) > MAX_OPTIONAL_MANIFESTS or len(unique) > MAX_SELECTED_TOOL_SCHEMAS:
        raise ToolError("manifest_exhausted")
    remaining = remaining_manifests
    loaded: list[Level2Manifest] = []
    catalog = registry if registry is not None else default_registry()
    visible = {item.tool_key for item in visible_tools(catalog, role=role)}
    for key in unique:
        remaining = consume_remaining(remaining, reason="manifest_exhausted")
        if key not in visible:
            raise ToolError("unauthorized_tool")
        tool = get_tool(key, registry=catalog)
        manifest = Level2Manifest(
            tool_key=tool.tool_key,
            version_label=tool.version_label,
            json_schema=tool.json_schema,
            examples=tool.examples,
            policy=tool.policy,
            side_effect_class=tool.side_effect_class,
            risk_class=tool.risk_class,
        )
        assert_manifest_budget(manifest)
        loaded.append(manifest)
    return tuple(loaded), remaining


def load_guidance(tool: ToolDefinition) -> Level3Guidance:
    """Load bounded Level 3 guidance after budget checks.

    Args:
        tool: Selected definition.

    Returns:
        Guidance section.

    Raises:
        ToolError: Oversized guidance.
    """

    section = assert_guidance_budget(tool)
    return Level3Guidance(tool_key=tool.tool_key, section=section)


def assemble_optional_prompt(
    *,
    level0: Level0Payload,
    level1: Level1Payload | None = None,
    manifests: tuple[Level2Manifest, ...] = (),
    guidance: tuple[Level3Guidance, ...] = (),
) -> str:
    """Assemble the next-call prompt from selected disclosure only.

    Args:
        level0: Meta capabilities and safety rules.
        level1: Optional visible cards.
        manifests: Selected Level 2 manifests only.
        guidance: Selected Level 3 sections only.

    Returns:
        Prompt text that has passed the model-input budget.

    Raises:
        ToolError: Over-budget model input.
    """

    import json

    parts = [
        "OPTIONAL_TOOL_DISCLOSURE",
        f"registry={level0.registry_version}",
        "capabilities=" + ",".join(level0.capabilities),
        "rules=" + " | ".join(level0.safety_rules),
    ]
    if level1 is not None:
        parts.append("L1_CARDS")
        for card in level1.cards:
            parts.append(
                f"{card.tool_key}|{card.short_name}|{card.one_line_purpose}|"
                f"{card.risk_class.value}|{card.required_role.value}"
            )
    if manifests:
        parts.append("L2_MANIFESTS")
        for manifest in manifests:
            parts.append(
                json.dumps(manifest.model_dump(mode="json"), separators=(",", ":"))
            )
    if guidance:
        parts.append("L3_GUIDANCE")
        for item in guidance:
            parts.append(f"{item.tool_key}:{item.section}")
    prompt = "\n".join(parts)
    assert_model_input_budget(prompt)
    return prompt
