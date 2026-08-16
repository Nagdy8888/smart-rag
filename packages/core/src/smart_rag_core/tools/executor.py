"""Independent optional-tool executor. Planner output is not authorization."""

from __future__ import annotations

from typing import cast

from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.tools.catalog import default_registry, get_tool
from smart_rag_core.tools.constants import consume_remaining
from smart_rag_core.tools.exceptions import ToolError
from smart_rag_core.tools.models import (
    ExecutionResult,
    PlannedInvocation,
    SideEffectClass,
    ToolDefinition,
)
from smart_rag_core.tools.permissions import is_authorized

_SIDE_EFFECTING = frozenset(
    {
        SideEffectClass.WRITE,
        SideEffectClass.ADMIN,
        SideEffectClass.REMOTE,
    }
)


def validate_arguments(tool: ToolDefinition, arguments: dict[str, object]) -> None:
    """Reject missing required keys or unexpected properties.

    Args:
        tool: Selected definition.
        arguments: Proposed arguments.

    Raises:
        ToolError: Argument/schema violation.
    """

    schema = tool.json_schema
    properties_raw = schema.get("properties")
    properties: dict[str, object] = {}
    if isinstance(properties_raw, dict):
        raw_items = cast(dict[object, object], properties_raw)
        properties = {str(key): value for key, value in raw_items.items()}
    required_raw = schema.get("required")
    required: tuple[str, ...] = ()
    if isinstance(required_raw, list):
        required = tuple(str(item) for item in cast(list[object], required_raw))
    for key in required:
        if key not in arguments:
            raise ToolError("argument_violation")
    for key in arguments:
        if key not in properties:
            raise ToolError("argument_violation")
    fmt_schema = properties.get("format")
    if isinstance(fmt_schema, dict):
        fmt_typed = cast(dict[str, object], fmt_schema)
        expected = fmt_typed.get("const")
        if expected is not None and arguments.get("format") != expected:
            raise ToolError("argument_violation")


def _is_side_effecting(tool: ToolDefinition) -> bool:
    """Return whether executing ``tool`` consumes the side-effect slot.

    Args:
        tool: Definition.

    Returns:
        True for write/admin/remote classes.
    """

    return tool.side_effect_class in _SIDE_EFFECTING


def execute_optional_tool(
    planned: PlannedInvocation,
    *,
    current_caller: CallerContext,
    remaining_tool_calls: int,
    remaining_side_effects: int,
    remaining_manifests: int,
    authorized_table_ids: tuple[str, ...] = (),
    used_idempotency_keys: frozenset[str] = frozenset(),
    registry: tuple[ToolDefinition, ...] | None = None,
) -> ExecutionResult:
    """Execute one optional tool after independent reauthorization.

    Rechecks tool id/version, live user/role, arguments, quotas,
    idempotency, side-effect policy, and current authorization. A role
    change after planning fails closed. MCP-origin tools cannot execute.

    Args:
        planned: Planner output. Not authority.
        current_caller: Live ``CallerContext`` from JWT + profile.
        remaining_tool_calls: Shared packet 1 tool ceiling.
        remaining_side_effects: Remaining side-effecting tools.
        remaining_manifests: Remaining manifest slots (informational here).
        authorized_table_ids: Table IDs from deterministic composition.
        used_idempotency_keys: Keys already consumed this run.
        registry: Optional catalog.

    Returns:
        Execution result, including idempotent replay.

    Raises:
        ToolError: Authorization, argument, quota, idempotency, side-effect,
            stale manifest, MCP, or ceiling violations.
    """

    if current_caller.disabled or not current_caller.is_active():
        raise ToolError("authorization_rejected")
    if current_caller.user_id != planned.planned_user_id:
        raise ToolError("caller_mismatch")
    if current_caller.role is not planned.planned_role:
        raise ToolError("role_changed_after_plan")
    catalog = registry if registry is not None else default_registry()
    tool = get_tool(
        planned.tool_key,
        version_label=planned.version_label,
        registry=catalog,
    )
    if tool.mcp_origin:
        raise ToolError("arbitrary_mcp_rejected")
    if not is_authorized(tool, role=current_caller.role):
        raise ToolError("unauthorized_tool")
    validate_arguments(tool, planned.arguments)
    if tool.executor_contract.recheck_resource_ids:
        table_id = planned.arguments.get("table_id")
        if isinstance(table_id, str) and table_id not in authorized_table_ids:
            raise ToolError("unauthorized_table")
        max_rows = planned.arguments.get("max_rows")
        if isinstance(max_rows, int) and max_rows > tool.quotas.max_rows:
            raise ToolError("quota_violation")
    replay_key = planned.idempotency_key
    if _is_side_effecting(tool):
        if not replay_key:
            raise ToolError("idempotency_required")
        if replay_key in used_idempotency_keys:
            return ExecutionResult(
                tool_key=tool.tool_key,
                version_label=tool.version_label,
                status="replayed",
                payload={"replayed": True, "idempotency_key": replay_key},
                side_effect=False,
                remaining_tool_calls=remaining_tool_calls,
                remaining_side_effects=remaining_side_effects,
                remaining_manifests=remaining_manifests,
            )
    remaining_tools = consume_remaining(remaining_tool_calls, reason="tool_exhausted")
    remaining_side = remaining_side_effects
    consumed_side = False
    if _is_side_effecting(tool):
        remaining_side = consume_remaining(
            remaining_side_effects, reason="side_effect_exhausted"
        )
        consumed_side = True
    payload = _run_allow_listed(
        tool,
        planned.arguments,
        role=current_caller.role,
        authorized_table_ids=authorized_table_ids,
    )
    return ExecutionResult(
        tool_key=tool.tool_key,
        version_label=tool.version_label,
        status="ok",
        payload=payload,
        side_effect=consumed_side,
        remaining_tool_calls=remaining_tools,
        remaining_side_effects=remaining_side,
        remaining_manifests=remaining_manifests,
    )


def _run_allow_listed(
    tool: ToolDefinition,
    arguments: dict[str, object],
    *,
    role: UserRole,
    authorized_table_ids: tuple[str, ...],
) -> dict[str, object]:
    """Dispatch one allow-listed v1 implementation.

    Args:
        tool: Rechecked definition.
        arguments: Validated arguments.
        role: Live role.
        authorized_table_ids: Composed table IDs.

    Returns:
        Bounded JSON-safe payload.

    Raises:
        ToolError: Unknown implementation or remote/MCP attempt.
    """

    del role
    if tool.side_effect_class is SideEffectClass.REMOTE:
        raise ToolError("arbitrary_mcp_rejected")
    if tool.tool_key.startswith("export_"):
        table_id = str(arguments["table_id"])
        fmt = str(arguments["format"])
        return {
            "format": fmt,
            "table_id": table_id,
            "authorized_table": table_id in authorized_table_ids,
            "row_count": 0,
            "bytes": 0,
            "status": "exported",
        }
    if tool.tool_key == "viewer_help_card":
        return {"status": "ok", "hint": "export requires member role"}
    if tool.tool_key in {"glossary_suggest", "feedback_tag", "member_saved_view"}:
        return {"status": "ok", "accepted": True}
    if tool.tool_key in {
        "conversation_export_md",
        "citation_pack_zip",
        "document_acl_report",
        "workspace_usage_card",
        "audit_log_export",
    }:
        return {"status": "ok", "bounded": True}
    if tool.tool_key.startswith("admin_"):
        return {"status": "ok", "admin": True}
    raise ToolError("unknown_tool")
