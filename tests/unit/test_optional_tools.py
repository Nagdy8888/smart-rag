"""Unit tests for optional-tool registry, disclosure, executor, and ceilings."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.tools.budgets import (
    assert_context_budgets,
    assert_model_input_budget,
)
from smart_rag_core.tools.catalog import default_registry, get_tool
from smart_rag_core.tools.compare import (
    RUNTIME_SELECTION_POLICY,
    compare_discovery_vs_mapping,
)
from smart_rag_core.tools.constants import CORE_FORBIDDEN_TOOL_KEYS
from smart_rag_core.tools.disclosure import (
    assemble_optional_prompt,
    level0_payload,
    level1_cards,
    load_guidance,
    load_manifests,
)
from smart_rag_core.tools.exceptions import ToolError
from smart_rag_core.tools.executor import execute_optional_tool
from smart_rag_core.tools.intents import detect_optional_intent
from smart_rag_core.tools.mcp import (
    McpMetadataImport,
    bind_or_execute_mcp,
    import_mcp_metadata,
    reject_arbitrary_mcp,
)
from smart_rag_core.tools.models import (
    OptionalIntent,
    PlannedInvocation,
    SelectionPolicy,
    ToolDefinition,
)
from smart_rag_core.tools.permissions import visible_tools
from smart_rag_core.tools.service import (
    assert_discovery_not_unjustified,
    resolve_optional_tools,
)

_MEMBER = "11111111-1111-4111-8111-111111111111"
_TABLE = "22222222-2222-4222-8222-222222222222"


def _caller(role: UserRole = UserRole.MEMBER) -> CallerContext:
    """Build a live caller for executor tests.

    Args:
        role: Live role.

    Returns:
        Frozen caller context.
    """

    return CallerContext(user_id=_MEMBER, role=role, authorization_version=1)


def _export_plan(tool_key: str = "export_csv") -> PlannedInvocation:
    """Build a planned CSV/XLSX export.

    Args:
        tool_key: Export catalog key.

    Returns:
        Planner output. Not authorization.
    """

    fmt = "csv" if tool_key == "export_csv" else "xlsx"
    return PlannedInvocation(
        tool_key=tool_key,
        version_label="v1",
        arguments={
            "table_id": _TABLE,
            "format": fmt,
            "idempotency_key": f"{tool_key}-1",
        },
        planned_role=UserRole.MEMBER,
        planned_user_id=_MEMBER,
        idempotency_key=f"{tool_key}-1",
    )


def test_registry_excludes_core_tools_and_has_at_least_twenty() -> None:
    """Catalog is ≥20 tools and never includes core retrieve/answer keys."""

    registry = default_registry()
    keys = {item.tool_key for item in registry}
    assert len(registry) >= 20
    assert keys.isdisjoint(CORE_FORBIDDEN_TOOL_KEYS)
    with pytest.raises((ToolError, ValidationError), match="core_tool_not_catalogable"):
        ToolDefinition(
            tool_key="hybrid_retrieve",
            version_label="v1",
            short_name="hybrid",
            description="forbidden",
            one_line_purpose="forbidden",
            risk_class="low",  # type: ignore[arg-type]
            required_role=UserRole.MEMBER,
            json_schema={"type": "object", "properties": {}},
            policy="no",
            side_effect_class="none",  # type: ignore[arg-type]
        )


def test_role_filter_hides_admin_names_and_counts_from_viewers() -> None:
    """Viewers must not see admin names or a hidden-tool count."""

    registry = default_registry()
    viewer = visible_tools(registry, role=UserRole.VIEWER)
    member = visible_tools(registry, role=UserRole.MEMBER)
    names = {item.tool_key for item in viewer}
    assert "admin_user_invite" not in names
    assert "export_csv" not in names
    assert "viewer_help_card" in names
    payload = level1_cards("invite user", role=UserRole.VIEWER, registry=registry)
    dumped = json.dumps(payload.model_dump(mode="json"))
    assert "admin_user_invite" not in dumped
    assert "invite_email" not in dumped
    assert payload.disclosed_count == len(payload.cards)
    assert payload.disclosed_count != len(registry)
    assert len(viewer) < len(member)


def test_level0_has_no_catalog_names() -> None:
    """Level 0 exposes only meta capabilities and safety rules."""

    payload = level0_payload()
    blob = json.dumps(payload.model_dump(mode="json"))
    assert "search_tool_catalog" in blob
    assert "load_tool_manifest" in blob
    assert "export_csv" not in blob
    assert "hybrid_retrieve" not in blob
    assert "structured_table_query" not in blob


def test_unselected_schema_stays_out_of_prompt() -> None:
    """Level 2 for export_csv must not include admin or xlsx schemas."""

    manifests, remaining = load_manifests(
        ("export_csv",),
        role=UserRole.MEMBER,
        remaining_manifests=3,
    )
    assert remaining == 2
    prompt = assemble_optional_prompt(level0=level0_payload(), manifests=manifests)
    assert "export_csv" in prompt
    assert "invite_email" not in prompt
    assert '"const":"xlsx"' not in prompt
    assert "admin_user_invite" not in prompt
    assert "structured_table_query" not in prompt


def test_fourth_manifest_fails() -> None:
    """A fourth optional manifest is rejected."""

    with pytest.raises(ToolError, match="manifest_exhausted"):
        load_manifests(
            ("export_csv", "export_xlsx", "export_json", "export_parquet"),
            role=UserRole.MEMBER,
            remaining_manifests=3,
        )


def test_second_discovery_fails() -> None:
    """A second catalog search round fails closed."""

    from smart_rag_core.tools.discovery import run_catalog_search

    _level0, _cards, remaining, _searched = run_catalog_search(
        "export this table",
        role=UserRole.MEMBER,
        remaining_discovery_rounds=1,
    )
    assert remaining == 0
    with pytest.raises(ToolError, match="discovery_exhausted"):
        run_catalog_search(
            "export this table",
            role=UserRole.MEMBER,
            remaining_discovery_rounds=remaining,
        )


def test_second_side_effect_fails() -> None:
    """A second side-effecting tool fails after a successful export."""

    first = execute_optional_tool(
        _export_plan("export_csv"),
        current_caller=_caller(),
        remaining_tool_calls=4,
        remaining_side_effects=1,
        remaining_manifests=2,
        authorized_table_ids=(_TABLE,),
    )
    assert first.status == "ok"
    with pytest.raises(ToolError, match="side_effect_exhausted"):
        execute_optional_tool(
            _export_plan("export_xlsx"),
            current_caller=_caller(),
            remaining_tool_calls=first.remaining_tool_calls,
            remaining_side_effects=first.remaining_side_effects,
            remaining_manifests=2,
            authorized_table_ids=(_TABLE,),
        )


def test_idempotent_replay_does_not_consume_second_side_effect() -> None:
    """The same idempotency key replays without a second side effect."""

    first = execute_optional_tool(
        _export_plan("export_csv"),
        current_caller=_caller(),
        remaining_tool_calls=4,
        remaining_side_effects=1,
        remaining_manifests=2,
        authorized_table_ids=(_TABLE,),
    )
    replay = execute_optional_tool(
        _export_plan("export_csv"),
        current_caller=_caller(),
        remaining_tool_calls=first.remaining_tool_calls,
        remaining_side_effects=first.remaining_side_effects,
        remaining_manifests=2,
        authorized_table_ids=(_TABLE,),
        used_idempotency_keys=frozenset({"export_csv-1"}),
    )
    assert replay.status == "replayed"
    assert replay.remaining_side_effects == first.remaining_side_effects


def test_core_path_zero_catalog_rounds() -> None:
    """Hybrid factual queries never start catalog search or bind schemas."""

    mode, prompt, keys, result, telemetry, _tools, _disc, _man, _side, _models, llm = (
        resolve_optional_tools(
            query="What is the status of INV-SR-1001?",
            caller=_caller(),
            remaining_tool_calls=4,
            remaining_discovery_rounds=1,
            remaining_manifests=3,
            remaining_side_effects=1,
            remaining_model_calls=7,
        )
    )
    assert (
        detect_optional_intent("What is the status of INV-SR-1001?")
        is OptionalIntent.NONE
    )
    assert mode is SelectionPolicy.SKIPPED
    assert prompt == ""
    assert keys == ()
    assert result is None
    assert llm == 0
    assert telemetry.catalog_llm_call_count == 0
    assert telemetry.selection_mode is SelectionPolicy.SKIPPED


def test_mcp_target_rejected_and_metadata_cannot_bind() -> None:
    """Arbitrary MCP execution is absent; metadata import cannot authorize."""

    with pytest.raises(ToolError, match="arbitrary_mcp_rejected"):
        reject_arbitrary_mcp("https://evil.example/mcp")
    with pytest.raises(ToolError, match="arbitrary_mcp_rejected"):
        bind_or_execute_mcp("https://evil.example/mcp")
    imported = import_mcp_metadata(
        McpMetadataImport(
            tool_key="mcp_imported_remote",
            short_name="remote",
            description="imported metadata",
            json_schema={"type": "object", "properties": {}},
            mcp_server_url="https://evil.example/mcp",
            mcp_tool_name="steal",
        )
    )
    assert imported.mcp_origin is True
    assert imported.active is False
    with pytest.raises(ToolError, match="stale_or_disabled_manifest"):
        get_tool(imported.tool_key, registry=(imported,))


def test_role_change_after_plan_fails() -> None:
    """Executor uses live role; planner membership is not authority."""

    with pytest.raises(ToolError, match="role_changed_after_plan"):
        execute_optional_tool(
            _export_plan(),
            current_caller=_caller(UserRole.VIEWER),
            remaining_tool_calls=4,
            remaining_side_effects=1,
            remaining_manifests=2,
            authorized_table_ids=(_TABLE,),
        )


def test_stale_disabled_manifest_fails() -> None:
    """Disabled export_ods cannot be loaded or executed."""

    with pytest.raises(ToolError, match="stale_or_disabled_manifest"):
        get_tool("retired_export_ods")


def test_oversized_guidance_rejected_before_prompt() -> None:
    """Level 3 guidance over the byte cap fails closed."""

    tool = next(
        item
        for item in default_registry()
        if item.tool_key == "oversized_guidance_admin"
    )
    with pytest.raises(ToolError, match="oversized_guidance"):
        load_guidance(tool)


def test_over_budget_model_input_and_context_fail() -> None:
    """Chunk, parent, summary, and total input budgets fail before prompts."""

    with pytest.raises(ToolError, match="over_budget_model_input"):
        assert_context_budgets(
            retrieval_chunks=13,
            parent_expansion=0,
            conversation_summary="",
        )
    with pytest.raises(ToolError, match="over_budget_model_input"):
        assert_model_input_budget("token " * 20_000)


def test_argument_quota_and_table_recheck() -> None:
    """Executor rejects extra args, oversize rows, and unknown table IDs."""

    bad_args = PlannedInvocation(
        tool_key="export_csv",
        version_label="v1",
        arguments={
            "table_id": _TABLE,
            "format": "csv",
            "idempotency_key": "exp-1",
            "unexpected": True,
        },
        planned_role=UserRole.MEMBER,
        planned_user_id=_MEMBER,
        idempotency_key="exp-1",
    )
    with pytest.raises(ToolError, match="argument_violation"):
        execute_optional_tool(
            bad_args,
            current_caller=_caller(),
            remaining_tool_calls=4,
            remaining_side_effects=1,
            remaining_manifests=2,
            authorized_table_ids=(_TABLE,),
        )
    quota = PlannedInvocation(
        tool_key="export_csv",
        version_label="v1",
        arguments={
            "table_id": _TABLE,
            "format": "csv",
            "idempotency_key": "exp-1",
            "max_rows": 50_000,
        },
        planned_role=UserRole.MEMBER,
        planned_user_id=_MEMBER,
        idempotency_key="exp-1",
    )
    with pytest.raises(ToolError, match="quota_violation"):
        execute_optional_tool(
            quota,
            current_caller=_caller(),
            remaining_tool_calls=4,
            remaining_side_effects=1,
            remaining_manifests=2,
            authorized_table_ids=(_TABLE,),
        )
    with pytest.raises(ToolError, match="unauthorized_table"):
        execute_optional_tool(
            _export_plan(),
            current_caller=_caller(),
            remaining_tool_calls=4,
            remaining_side_effects=1,
            remaining_manifests=2,
            authorized_table_ids=(),
        )


def test_unjustified_discovery_retained_fails() -> None:
    """Runtime cannot keep catalog discovery when the fixture rejects it."""

    metrics = compare_discovery_vs_mapping()
    assert metrics.tool_count >= 20
    assert metrics.selected_policy is SelectionPolicy.DETERMINISTIC_MAPPING
    assert RUNTIME_SELECTION_POLICY is SelectionPolicy.DETERMINISTIC_MAPPING
    with pytest.raises(ToolError, match="unjustified_discovery_retained"):
        assert_discovery_not_unjustified(SelectionPolicy.CATALOG_DISCOVERY, metrics)


def test_l0_prompt_file_contains_safety_rules() -> None:
    """Agents prompt file matches the immutable Level 0 rules."""

    from smart_rag_agents.prompts import optional_catalog_prompt_text
    from smart_rag_core.tools.constants import L0_SAFETY_RULES

    body = optional_catalog_prompt_text()
    for rule in L0_SAFETY_RULES:
        assert rule in body
    assert "structured_table_query" in body or "StructuredTable" in body
