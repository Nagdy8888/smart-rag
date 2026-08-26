"""Framework-independent optional-tool orchestration. No LangGraph nodes."""

from __future__ import annotations

import time

from smart_rag_core.security.identity import CallerContext
from smart_rag_core.tools.budgets import assert_context_budgets
from smart_rag_core.tools.catalog import default_registry, get_tool
from smart_rag_core.tools.compare import (
    RUNTIME_SELECTION_POLICY,
    evaluate_discovery_justification,
)
from smart_rag_core.tools.disclosure import (
    assemble_optional_prompt,
    level0_payload,
    load_guidance,
    load_manifests,
)
from smart_rag_core.tools.discovery import run_catalog_search, select_from_cards
from smart_rag_core.tools.exceptions import ToolError
from smart_rag_core.tools.executor import execute_optional_tool
from smart_rag_core.tools.intents import detect_optional_intent
from smart_rag_core.tools.mapping import map_optional_intent
from smart_rag_core.tools.mcp import reject_arbitrary_mcp
from smart_rag_core.tools.models import (
    ComparisonMetrics,
    ExecutionResult,
    OptionalIntent,
    OptionalTelemetry,
    PlannedInvocation,
    SelectionPolicy,
    ToolDefinition,
)
from smart_rag_core.tools.permissions import visible_tools
from smart_rag_core.tools.progress import (
    ToolProgressReporter,
    report_phase,
    report_selected,
)
from smart_rag_core.tools.ranking import Embedder
from smart_rag_core.tools.telemetry import build_telemetry


def assert_discovery_not_unjustified(
    policy: SelectionPolicy, metrics: ComparisonMetrics
) -> None:
    """Fail if runtime retained catalog discovery without the fixture gain.

    Args:
        policy: Policy the runtime is about to use.
        metrics: Measured comparison.

    Raises:
        ToolError: Unjustified discovery retained.
    """

    justified = evaluate_discovery_justification(metrics)
    if (
        policy is SelectionPolicy.CATALOG_DISCOVERY
        and justified is not SelectionPolicy.CATALOG_DISCOVERY
    ):
        raise ToolError("unjustified_discovery_retained")


def resolve_optional_tools(
    *,
    query: str,
    caller: CallerContext,
    remaining_tool_calls: int,
    remaining_discovery_rounds: int,
    remaining_manifests: int,
    remaining_side_effects: int,
    remaining_model_calls: int,
    authorized_table_ids: tuple[str, ...] = (),
    retrieval_chunks: int = 0,
    parent_expansion: int = 0,
    conversation_summary: str = "",
    catalog_llm_call_count: int = 0,
    policy: SelectionPolicy = RUNTIME_SELECTION_POLICY,
    force_discovery: bool = False,
    mcp_target: str | None = None,
    used_idempotency_keys: frozenset[str] = frozenset(),
    registry: tuple[ToolDefinition, ...] | None = None,
    embedder: Embedder | None = None,
    current_caller: CallerContext | None = None,
    idempotency_key: str = "optional-run-1",
    comparison_metrics: ComparisonMetrics | None = None,
    progress: ToolProgressReporter | None = None,
) -> tuple[
    SelectionPolicy,
    str,
    tuple[str, ...],
    ExecutionResult | None,
    OptionalTelemetry,
    int,
    int,
    int,
    int,
    int,
    int,
]:
    """Resolve optional tools without touching core retrieve/answer paths.

    Deterministic mapping is the v1 runtime default. Catalog search runs
    only when ``force_discovery`` is true and the intent is genuinely
    ambiguous. Core queries skip this function's catalog path entirely
    when intent is ``NONE``.

    Args:
        query: Original user text.
        caller: Role used at plan time.
        remaining_tool_calls: Shared tool ceiling.
        remaining_discovery_rounds: Discovery ceiling.
        remaining_manifests: Manifest ceiling.
        remaining_side_effects: Side-effect ceiling.
        remaining_model_calls: Model-call ceiling. Discovery spends one.
        authorized_table_ids: StructuredTable IDs already composed.
        retrieval_chunks: Chunks proposed for the optional prompt.
        parent_expansion: Parent passages proposed for the optional prompt.
        conversation_summary: Summary text proposed for the optional prompt.
        catalog_llm_call_count: Incoming count. Core path must stay 0.
        policy: Runtime selection policy.
        force_discovery: Test hook to exercise the discovery path.
        mcp_target: If set, rejected before any bind.
        used_idempotency_keys: Keys already used this run.
        registry: Optional catalog.
        embedder: Optional embedding ranker.
        current_caller: Live caller for executor recheck. Defaults to ``caller``.
        idempotency_key: Key for write tools.
        comparison_metrics: Optional metrics for unjustified-discovery checks.
        progress: Optional observer for selected keys and execution phases.

    Returns:
        Selection mode, prompt capture, bound tool names, execution result,
        telemetry, remaining tool/discovery/manifest/side-effect/model
        ceilings, and catalog LLM count.

    Raises:
        ToolError: MCP, unjustified discovery, budgets, or executor failures.
    """

    if mcp_target:
        reject_arbitrary_mcp(mcp_target)
    if comparison_metrics is not None:
        assert_discovery_not_unjustified(policy, comparison_metrics)
    live = current_caller if current_caller is not None else caller
    intent = detect_optional_intent(query)
    empty_telemetry = build_telemetry(
        discovery_latency_ms=0.0,
        tools_searched=0,
        tools_disclosed=0,
        tools_loaded=0,
        tools_called=0,
        tools_rejected=0,
        tools_useful=0,
        selection_mode=SelectionPolicy.SKIPPED,
        catalog_llm_call_count=catalog_llm_call_count,
    )
    if intent is OptionalIntent.NONE:
        return (
            SelectionPolicy.SKIPPED,
            "",
            (),
            None,
            empty_telemetry,
            remaining_tool_calls,
            remaining_discovery_rounds,
            remaining_manifests,
            remaining_side_effects,
            remaining_model_calls,
            catalog_llm_call_count,
        )
    assert_context_budgets(
        retrieval_chunks=retrieval_chunks,
        parent_expansion=parent_expansion,
        conversation_summary=conversation_summary,
    )
    catalog = registry if registry is not None else default_registry()
    use_discovery = force_discovery and (
        intent is OptionalIntent.AMBIGUOUS_EXPORT
        or intent is OptionalIntent.ADMINISTRATION
    )
    start = time.perf_counter()
    selected_keys: tuple[str, ...]
    prompt: str
    searched = 0
    disclosed = 0
    loaded = 0
    remaining_discovery = remaining_discovery_rounds
    remaining_manifest = remaining_manifests
    remaining_models = remaining_model_calls
    llm_count = catalog_llm_call_count
    mode: SelectionPolicy
    if use_discovery:
        if (
            policy is SelectionPolicy.CATALOG_DISCOVERY
            and comparison_metrics is not None
        ):
            assert_discovery_not_unjustified(policy, comparison_metrics)
        level0, cards, remaining_discovery, searched = run_catalog_search(
            query,
            role=caller.role,
            remaining_discovery_rounds=remaining_discovery_rounds,
            registry=catalog,
            embedder=embedder,
        )
        disclosed = cards.disclosed_count
        if remaining_models <= 0:
            raise ToolError("model_call_exhausted")
        remaining_models -= 1
        llm_count = 1
        selected_keys = select_from_cards(query, cards, limit=1)
        manifests, remaining_manifest = load_manifests(
            selected_keys,
            role=caller.role,
            remaining_manifests=remaining_manifests,
            registry=catalog,
        )
        loaded = len(manifests)
        prompt = assemble_optional_prompt(
            level0=level0,
            level1=cards,
            manifests=manifests,
        )
        mode = SelectionPolicy.CATALOG_DISCOVERY
    else:
        mapped = map_optional_intent(intent)
        visible = {item.tool_key for item in visible_tools(catalog, role=caller.role)}
        if mapped is None or mapped not in visible:
            latency = (time.perf_counter() - start) * 1000.0
            telemetry = build_telemetry(
                discovery_latency_ms=latency,
                tools_searched=len(visible),
                tools_disclosed=0,
                tools_loaded=0,
                tools_called=0,
                tools_rejected=0,
                tools_useful=0,
                selection_mode=SelectionPolicy.SKIPPED,
                catalog_llm_call_count=catalog_llm_call_count,
            )
            return (
                SelectionPolicy.SKIPPED,
                "",
                (),
                None,
                telemetry,
                remaining_tool_calls,
                remaining_discovery_rounds,
                remaining_manifests,
                remaining_side_effects,
                remaining_model_calls,
                catalog_llm_call_count,
            )
        selected_keys = (mapped,)
        manifests, remaining_manifest = load_manifests(
            selected_keys,
            role=caller.role,
            remaining_manifests=remaining_manifests,
            registry=catalog,
        )
        loaded = len(manifests)
        searched = len(visible_tools(catalog, role=caller.role))
        disclosed = 0
        prompt = assemble_optional_prompt(
            level0=level0_payload(),
            manifests=manifests,
        )
        mode = SelectionPolicy.DETERMINISTIC_MAPPING
    latency = (time.perf_counter() - start) * 1000.0
    if not selected_keys:
        telemetry = build_telemetry(
            discovery_latency_ms=latency,
            tools_searched=searched,
            tools_disclosed=disclosed,
            tools_loaded=loaded,
            tools_called=0,
            tools_rejected=0,
            tools_useful=0,
            selection_mode=mode,
            catalog_llm_call_count=llm_count,
        )
        return (
            mode,
            prompt,
            (),
            None,
            telemetry,
            remaining_tool_calls,
            remaining_discovery,
            remaining_manifest,
            remaining_side_effects,
            remaining_models,
            llm_count,
        )
    tool = get_tool(selected_keys[0], registry=catalog)
    guidance = ()
    if planned_needs_guidance(tool):
        guidance = (load_guidance(tool),)
        prompt = assemble_optional_prompt(
            level0=level0_payload(),
            manifests=manifests,
            guidance=guidance,
        )
    arguments = _default_arguments(
        tool,
        authorized_table_ids=authorized_table_ids,
        idempotency_key=idempotency_key,
        query=query,
    )
    planned = PlannedInvocation(
        tool_key=tool.tool_key,
        version_label=tool.version_label,
        arguments=arguments,
        planned_role=caller.role,
        planned_user_id=caller.user_id,
        idempotency_key=str(arguments.get("idempotency_key") or "") or None,
        load_guidance=bool(guidance),
    )
    called = 0
    rejected = 0
    useful = 0
    result: ExecutionResult | None
    remaining_tools = remaining_tool_calls
    remaining_side = remaining_side_effects
    report_selected(progress, selected_keys)
    report_phase(progress, selected_keys[0], "started")
    try:
        result = execute_optional_tool(
            planned,
            current_caller=live,
            remaining_tool_calls=remaining_tool_calls,
            remaining_side_effects=remaining_side_effects,
            remaining_manifests=remaining_manifest,
            authorized_table_ids=authorized_table_ids,
            used_idempotency_keys=used_idempotency_keys,
            registry=catalog,
        )
        called = 1
        useful = 1 if result.status in {"ok", "replayed"} else 0
        remaining_tools = result.remaining_tool_calls
        remaining_side = result.remaining_side_effects
        report_phase(progress, selected_keys[0], "completed")
    except ToolError:
        called = 1
        rejected = 1
        result = None
        report_phase(progress, selected_keys[0], "failed")
        telemetry = build_telemetry(
            discovery_latency_ms=latency,
            tools_searched=searched,
            tools_disclosed=disclosed,
            tools_loaded=loaded,
            tools_called=called,
            tools_rejected=rejected,
            tools_useful=useful,
            selection_mode=mode,
            catalog_llm_call_count=llm_count,
        )
        raise
    telemetry = build_telemetry(
        discovery_latency_ms=latency,
        tools_searched=searched,
        tools_disclosed=disclosed,
        tools_loaded=loaded,
        tools_called=called,
        tools_rejected=rejected,
        tools_useful=useful,
        selection_mode=mode,
        catalog_llm_call_count=llm_count,
    )
    return (
        mode,
        prompt,
        selected_keys,
        result,
        telemetry,
        remaining_tools,
        remaining_discovery,
        remaining_manifest,
        remaining_side,
        remaining_models,
        llm_count,
    )


def planned_needs_guidance(tool: ToolDefinition) -> bool:
    """Return whether execution should load Level 3 guidance.

    Export format cards carry enough Level 2 policy. Admin mutations load
    guidance. Oversized guidance still fails the budget check.

    Args:
        tool: Selected definition.

    Returns:
        True when Level 3 should be loaded.
    """

    return (
        tool.tool_key.startswith("admin_")
        or tool.tool_key == "oversized_guidance_admin"
    )


def _default_arguments(
    tool: ToolDefinition,
    *,
    authorized_table_ids: tuple[str, ...],
    idempotency_key: str,
    query: str,
) -> dict[str, object]:
    """Build schema-valid default arguments for v1 allow-listed tools.

    Args:
        tool: Selected definition.
        authorized_table_ids: Composed table IDs.
        idempotency_key: Run-local idempotency key.
        query: Original query, used for invite email extraction.

    Returns:
        Argument mapping.
    """

    if tool.tool_key.startswith("export_"):
        table_id = authorized_table_ids[0] if authorized_table_ids else ""
        fmt = tool.tool_key.removeprefix("export_")
        if fmt == "markdown_table":
            fmt = "md"
        return {
            "table_id": table_id,
            "format": fmt,
            "idempotency_key": idempotency_key,
        }
    if tool.tool_key == "admin_user_invite":
        email = "user@example.test"
        for token in query.split():
            if "@" in token:
                email = token.strip()
                break
        return {"invite_email": email, "idempotency_key": idempotency_key}
    if tool.tool_key in {"glossary_suggest"}:
        return {"term": "INV", "alias": "invoice"}
    if tool.tool_key == "feedback_tag":
        return {"label": "helpful"}
    if tool.tool_key == "member_saved_view":
        return {"name": "view", "idempotency_key": idempotency_key}
    if tool.tool_key in {
        "conversation_export_md",
        "citation_pack_zip",
        "audit_log_export",
        "admin_role_change",
        "admin_tool_grant",
        "admin_budget_adjust",
    }:
        payload: dict[str, object] = {"idempotency_key": idempotency_key}
        if "conversation_id" in str(tool.json_schema):
            payload["conversation_id"] = "00000000-0000-4000-8000-000000000001"
        if "run_id" in str(tool.json_schema):
            payload["run_id"] = "00000000-0000-4000-8000-000000000002"
        if "target_user_id" in str(tool.json_schema):
            payload["target_user_id"] = "00000000-0000-4000-8000-000000000003"
        if "amount_usd" in str(tool.json_schema):
            payload["amount_usd"] = "200.00"
        return payload
    return {}
