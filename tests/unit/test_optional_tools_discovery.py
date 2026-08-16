"""Discovery comparison, next-call bind_tools, and table-plus-export tests."""

from __future__ import annotations

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from smart_rag_agents.query.nodes.binding import (
    bind_selected_tools_next_call,
    bound_tool_names,
)
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.tools.catalog import default_registry
from smart_rag_core.tools.compare import (
    RUNTIME_SELECTION_POLICY,
    compare_discovery_vs_mapping,
)
from smart_rag_core.tools.disclosure import level1_cards
from smart_rag_core.tools.models import SelectionPolicy
from smart_rag_core.tools.permissions import visible_tools
from smart_rag_core.tools.service import resolve_optional_tools

_MEMBER = "11111111-1111-4111-8111-111111111111"
_TABLE = "22222222-2222-4222-8222-222222222222"


def _caller(role: UserRole = UserRole.MEMBER) -> CallerContext:
    """Build a live caller.

    Args:
        role: Live role.

    Returns:
        Caller context.
    """

    return CallerContext(user_id=_MEMBER, role=role, authorization_version=1)


def _schema(name: str) -> dict[str, object]:
    """Build a compact OpenAI tool schema.

    Args:
        name: Function name.

    Returns:
        Schema dict.
    """

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {"type": "object", "properties": {}},
        },
    }


def test_twenty_tool_comparison_rejects_unjustified_discovery() -> None:
    """Discovery must not be retained unless it beats mapping on the fixture."""

    metrics = compare_discovery_vs_mapping()
    assert metrics.tool_count >= 20
    assert metrics.case_count >= 8
    assert metrics.discovery_tokens >= metrics.deterministic_tokens
    assert metrics.selected_policy is SelectionPolicy.DETERMINISTIC_MAPPING
    assert RUNTIME_SELECTION_POLICY is SelectionPolicy.DETERMINISTIC_MAPPING
    assert "deterministic mapping" in metrics.justification.lower()


def test_bind_tools_next_call_does_not_leak_unselected_schemas() -> None:
    """``bind``/``bind_tools`` applies to one runnable; the original stays clean.

    Current docs use ``wrap_model_call`` and ``request.override(tools=...)``
    on unpinned ``langchain.agents``. This test proves the langchain-core
    equivalent: a new bound runnable for the next call only.
    """

    model = GenericFakeChatModel(messages=iter((AIMessage(content="ok"),)))
    selected = bind_selected_tools_next_call(model, (_schema("export_csv"),))
    assert bound_tool_names(selected) == ("export_csv",)
    assert "admin_user_invite" not in bound_tool_names(selected)
    assert bound_tool_names(model) == ()
    later = bind_selected_tools_next_call(model, (_schema("export_xlsx"),))
    assert bound_tool_names(later) == ("export_xlsx",)
    assert "export_csv" not in bound_tool_names(later)
    assert bound_tool_names(model) == ()


def test_table_plus_export_binds_export_not_structured_table() -> None:
    """StructuredTable stays deterministic; catalog loads one export manifest."""

    (
        mode,
        prompt,
        keys,
        result,
        telemetry,
        tools_left,
        _d,
        manifests_left,
        sides,
        models,
        llm,
    ) = resolve_optional_tools(
        query="export the table as csv",
        caller=_caller(),
        remaining_tool_calls=4,
        remaining_discovery_rounds=1,
        remaining_manifests=3,
        remaining_side_effects=1,
        remaining_model_calls=6,
        authorized_table_ids=(_TABLE,),
    )
    assert mode is SelectionPolicy.DETERMINISTIC_MAPPING
    assert keys == ("export_csv",)
    assert result is not None
    assert result.status == "ok"
    assert result.payload.get("format") == "csv"
    assert "structured_table_query" not in prompt
    assert "invite_email" not in prompt
    assert "admin_user_invite" not in prompt
    assert llm == 0
    assert telemetry.catalog_llm_call_count == 0
    assert tools_left == 3
    assert sides == 0
    assert manifests_left == 2
    assert models == 6


def test_viewer_export_is_skipped_without_naming_member_tools() -> None:
    """Viewers do not receive member export schemas or hidden counts."""

    mode, prompt, keys, result, telemetry, *_rest = resolve_optional_tools(
        query="export the table as csv",
        caller=_caller(UserRole.VIEWER),
        remaining_tool_calls=4,
        remaining_discovery_rounds=1,
        remaining_manifests=3,
        remaining_side_effects=1,
        remaining_model_calls=6,
        authorized_table_ids=(_TABLE,),
    )
    assert mode is SelectionPolicy.SKIPPED
    assert keys == ()
    assert result is None
    assert prompt == ""
    assert "export_csv" not in json_cards(UserRole.VIEWER)
    assert telemetry.tools_searched == len(
        visible_tools(default_registry(), role=UserRole.VIEWER)
    )


def json_cards(role: UserRole) -> str:
    """Serialize Level 1 cards for leakage assertions.

    Args:
        role: Live role.

    Returns:
        JSON text of visible cards.
    """

    import json

    payload = level1_cards("export csv", role=role)
    return json.dumps(payload.model_dump(mode="json"))


def test_force_discovery_ambiguous_export_one_round() -> None:
    """Ambiguous export may search export cards once without a second round."""

    mode, prompt, keys, result, telemetry, _t, _d, _m, _s, _mc, llm = (
        resolve_optional_tools(
            query="export this table",
            caller=_caller(),
            remaining_tool_calls=4,
            remaining_discovery_rounds=1,
            remaining_manifests=3,
            remaining_side_effects=1,
            remaining_model_calls=6,
            authorized_table_ids=(_TABLE,),
            force_discovery=True,
        )
    )
    assert mode is SelectionPolicy.CATALOG_DISCOVERY
    assert llm == 1
    assert telemetry.catalog_llm_call_count == 1
    assert telemetry.tools_disclosed <= 5
    assert "structured_table_query" not in prompt
    assert keys
    assert keys[0].startswith("export_")
    assert result is not None


def test_core_graph_path_stays_zero_catalog_llm() -> None:
    """Compiled query graph Hybrid path never spends a catalog LLM round."""

    from datetime import UTC, datetime, timedelta
    from decimal import Decimal
    from uuid import uuid4

    from smart_rag_agents.query.graph import graph as query_graph
    from smart_rag_agents.query.graph import pending_query_state
    from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
    from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily

    now = datetime.now(UTC)
    context = AuthorizedRuntimeContext(
        user_id=uuid4(),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=Phase6RouteFamily.HYBRID,
        deadline_at=now + timedelta(seconds=25),
        recursion_limit=24,
        correction_ceiling=1,
        subquestion_ceiling=3,
        model_call_ceiling=7,
        tool_ceiling=4,
        discovery_ceiling=1,
        manifest_ceiling=3,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("2.80"),
        remaining_usd=Decimal("2.80"),
        remaining_prompt_tokens=56000,
        remaining_completion_tokens=14000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="a" * 64,
        status="pending",
    )
    routed = query_graph.invoke(  # pyright: ignore[reportUnknownMemberType]
        pending_query_state(
            context.model_dump(mode="json"),
            user_query="What is the status of INV-SR-1001?",
        )
    )
    assert routed["catalog_llm_call_count"] == 0
    assert routed["keyword_extract_count"] == 0
    assert routed["optional_selection_mode"] == "skipped"
    assert routed["optional_prompt_capture"] == ""
    assert "invite_email" not in routed["optional_prompt_capture"]
    assert routed["optional_bound_tool_names"] == []
