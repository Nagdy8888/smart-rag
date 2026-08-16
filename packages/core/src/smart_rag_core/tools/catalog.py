"""Versioned in-code optional-tool allow-list. Core retrieve tools are absent."""

from __future__ import annotations

from typing import cast

from smart_rag_core.security.identity import UserRole
from smart_rag_core.tools.constants import CORE_FORBIDDEN_TOOL_KEYS, REGISTRY_VERSION
from smart_rag_core.tools.exceptions import ToolError
from smart_rag_core.tools.models import (
    ExecutorContract,
    RiskClass,
    SideEffectClass,
    ToolDefinition,
    ToolQuotas,
)

_EXPORT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "table_id": {"type": "string", "minLength": 1, "maxLength": 36},
        "format": {"type": "string"},
        "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 128},
        "max_rows": {"type": "integer", "minimum": 1, "maximum": 10000},
    },
    "required": ["table_id", "format", "idempotency_key"],
}


def _export_schema(fmt: str) -> dict[str, object]:
    """Return an export argument schema locked to one format.

    Args:
        fmt: Allow-listed format token.

    Returns:
        JSON Schema object.
    """

    schema: dict[str, object] = dict(_EXPORT_SCHEMA)
    raw_props = _EXPORT_SCHEMA["properties"]
    if not isinstance(raw_props, dict):
        raise ToolError("invalid_schema")
    raw_items = cast(dict[object, object], raw_props)
    properties: dict[str, object] = {
        str(key): value for key, value in raw_items.items()
    }
    properties["format"] = {"type": "string", "const": fmt}
    schema["properties"] = properties
    return schema


def _tool(
    *,
    tool_key: str,
    short_name: str,
    purpose: str,
    description: str,
    tags: tuple[str, ...],
    capabilities: tuple[str, ...],
    risk: RiskClass,
    role: UserRole,
    features: tuple[str, ...],
    schema: dict[str, object],
    examples: tuple[str, ...],
    policy: str,
    guidance: str,
    side_effect: SideEffectClass,
    active: bool = True,
    discoverable: bool = True,
    mcp_origin: bool = False,
    compact_card: str = "",
) -> ToolDefinition:
    """Build one allow-listed definition.

    Args:
        tool_key: Catalog id.
        short_name: Display name.
        purpose: Level 1 one-liner.
        description: Ranking description.
        tags: Ranking tags.
        capabilities: Capability tokens.
        risk: Risk class.
        role: Minimum role.
        features: Required features.
        schema: Argument JSON Schema.
        examples: Level 2 examples.
        policy: Level 2 policy.
        guidance: Level 3 guidance.
        side_effect: Side-effect class.
        active: Whether the tool may execute.
        discoverable: Whether it may appear after filtering.
        mcp_origin: MCP metadata import flag.
        compact_card: Extra Level 1 text.

    Returns:
        Frozen tool definition.
    """

    return ToolDefinition(
        tool_key=tool_key,
        version_label="v1",
        short_name=short_name,
        description=description,
        one_line_purpose=purpose,
        tags=tags,
        capabilities=capabilities,
        risk_class=risk,
        required_role=role,
        required_features=features,
        compact_card=compact_card or purpose,
        json_schema=schema,
        examples=examples,
        policy=policy,
        long_guidance=guidance,
        side_effect_class=side_effect,
        quotas=ToolQuotas(),
        executor_contract=ExecutorContract(),
        active=active,
        catalog_discoverable=discoverable,
        mcp_origin=mcp_origin,
    )


def _export_tool(tool_key: str, fmt: str, purpose: str) -> ToolDefinition:
    """Build one table-export format card.

    Args:
        tool_key: Catalog id.
        fmt: Format token.
        purpose: One-line purpose.

    Returns:
        Member-visible write tool.
    """

    return _tool(
        tool_key=tool_key,
        short_name=tool_key.replace("_", " "),
        purpose=purpose,
        description=f"Export authorized structured-table results as {fmt}.",
        tags=("export", "table", fmt),
        capabilities=("export", fmt),
        risk=RiskClass.MEDIUM,
        role=UserRole.MEMBER,
        features=("export",),
        schema=_export_schema(fmt),
        examples=(
            f'{{"table_id":"<uuid>","format":"{fmt}","idempotency_key":"exp-1"}}',
        ),
        policy="Executor rechecks table IDs, role, quotas, format, and idempotency.",
        guidance=(
            f"Export only composed StructuredTable provenance as {fmt}. "
            "Do not re-run structured_table_query. Bound rows and bytes apply."
        ),
        side_effect=SideEffectClass.WRITE,
    )


def default_registry() -> tuple[ToolDefinition, ...]:
    """Return the v1 internal allow-list of at least 20 optional tools.

    Returns:
        Frozen catalog. Core retrieve/answer/verifier keys are absent.

    Raises:
        ToolError: If a forbidden core key slipped into the allow-list.
    """

    invite_schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "invite_email": {"type": "string"},
            "idempotency_key": {"type": "string"},
        },
        "required": ["invite_email", "idempotency_key"],
    }
    admin_schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "target_user_id": {"type": "string"},
            "idempotency_key": {"type": "string"},
        },
        "required": ["target_user_id", "idempotency_key"],
    }
    empty_read: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
        "required": [],
    }
    mcp_schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "mcp_server_url": {"type": "string"},
            "tool_name": {"type": "string"},
        },
        "required": ["mcp_server_url", "tool_name"],
    }
    tools = (
        _export_tool("export_csv", "csv", "Download table results as CSV."),
        _export_tool("export_xlsx", "xlsx", "Download table results as XLSX."),
        _export_tool("export_json", "json", "Download table results as JSON."),
        _export_tool("export_parquet", "parquet", "Download table results as Parquet."),
        _export_tool(
            "export_markdown_table",
            "md",
            "Download table results as Markdown.",
        ),
        _tool(
            tool_key="conversation_export_md",
            short_name="conversation export",
            purpose="Export the current conversation as Markdown.",
            description="Write a bounded Markdown export of creator-owned messages.",
            tags=("export", "conversation", "markdown"),
            capabilities=("export", "conversation"),
            risk=RiskClass.MEDIUM,
            role=UserRole.MEMBER,
            features=("export",),
            schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "conversation_id": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                },
                "required": ["conversation_id", "idempotency_key"],
            },
            examples=('{"conversation_id":"<uuid>","idempotency_key":"conv-1"}',),
            policy="Creator-owned conversation only. Executor rechecks user id.",
            guidance="Export at most the last 12 messages. No source documents.",
            side_effect=SideEffectClass.WRITE,
        ),
        _tool(
            tool_key="citation_pack_zip",
            short_name="citation pack",
            purpose="Bundle already-cited IDs into a zip receipt.",
            description="Package citation IDs from this run. Not source lookup.",
            tags=("export", "citations", "zip"),
            capabilities=("export", "citations"),
            risk=RiskClass.LOW,
            role=UserRole.MEMBER,
            features=("export",),
            schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "run_id": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                },
                "required": ["run_id", "idempotency_key"],
            },
            examples=('{"run_id":"<uuid>","idempotency_key":"cite-1"}',),
            policy="Only citation IDs already on the run. Not citation_lookup.",
            guidance="Do not fetch new passages. Pack existing citation IDs only.",
            side_effect=SideEffectClass.WRITE,
        ),
        _tool(
            tool_key="glossary_suggest",
            short_name="glossary suggest",
            purpose="Suggest a glossary alias for admin review.",
            description="Member suggestion. Does not mutate the glossary.",
            tags=("glossary", "suggest"),
            capabilities=("glossary",),
            risk=RiskClass.LOW,
            role=UserRole.MEMBER,
            features=("feedback",),
            schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "term": {"type": "string"},
                    "alias": {"type": "string"},
                },
                "required": ["term", "alias"],
            },
            examples=('{"term":"INV","alias":"invoice"}',),
            policy="Suggestion only. No side-effecting write in v1.",
            guidance="Record a suggestion payload. Admins apply glossary imports.",
            side_effect=SideEffectClass.NONE,
        ),
        _tool(
            tool_key="feedback_tag",
            short_name="feedback tag",
            purpose="Tag the current answer with a feedback label.",
            description="Non-mutating feedback tag for later evaluation.",
            tags=("feedback", "tag"),
            capabilities=("feedback",),
            risk=RiskClass.LOW,
            role=UserRole.MEMBER,
            features=("feedback",),
            schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"label": {"type": "string"}},
                "required": ["label"],
            },
            examples=('{"label":"helpful"}',),
            policy="Does not change retrieval or authorization.",
            guidance="Labels are stored with the run in a later packet.",
            side_effect=SideEffectClass.NONE,
        ),
        _tool(
            tool_key="admin_user_invite",
            short_name="invite user",
            purpose="Invite a company user by email.",
            description="Administration invite. Hidden from members and viewers.",
            tags=("admin", "invite", "email"),
            capabilities=("admin", "invite"),
            risk=RiskClass.HIGH,
            role=UserRole.ADMIN,
            features=("admin",),
            schema=invite_schema,
            examples=('{"invite_email":"a@b.test","idempotency_key":"inv-1"}',),
            policy="Admin or owner. Executor rechecks live role.",
            guidance="Invites go through the identity packet, not MCP.",
            side_effect=SideEffectClass.ADMIN,
        ),
        _tool(
            tool_key="admin_role_change",
            short_name="change role",
            purpose="Change another user's company role.",
            description="Administration role mutation. Hidden from members.",
            tags=("admin", "role"),
            capabilities=("admin", "role"),
            risk=RiskClass.CRITICAL,
            role=UserRole.ADMIN,
            features=("admin",),
            schema=admin_schema,
            examples=('{"target_user_id":"<uuid>","idempotency_key":"role-1"}',),
            policy="Admin or owner. Cannot target self in v1.",
            guidance="Recheck live role. Planner authorization is ignored.",
            side_effect=SideEffectClass.ADMIN,
        ),
        _tool(
            tool_key="admin_tool_grant",
            short_name="grant tool",
            purpose="Grant a catalog permission to a role or user.",
            description="Administration of tool_permissions. Hidden from members.",
            tags=("admin", "permissions"),
            capabilities=("admin", "permissions"),
            risk=RiskClass.HIGH,
            role=UserRole.ADMIN,
            features=("admin",),
            schema=admin_schema,
            examples=('{"target_user_id":"<uuid>","idempotency_key":"grant-1"}',),
            policy="Does not bind remote MCP tools.",
            guidance="Grants affect future runs after live profile reload.",
            side_effect=SideEffectClass.ADMIN,
        ),
        _tool(
            tool_key="admin_budget_adjust",
            short_name="adjust budget",
            purpose="Adjust the company monthly LLM budget.",
            description="Owner-only budget mutation.",
            tags=("admin", "budget", "owner"),
            capabilities=("admin", "budget"),
            risk=RiskClass.CRITICAL,
            role=UserRole.OWNER,
            features=("owner",),
            schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "amount_usd": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                },
                "required": ["amount_usd", "idempotency_key"],
            },
            examples=('{"amount_usd":"200.00","idempotency_key":"bud-1"}',),
            policy="Owner only. Packet 1 durable budgets remain authoritative.",
            guidance="Never enlarge a run envelope from this tool.",
            side_effect=SideEffectClass.ADMIN,
        ),
        _tool(
            tool_key="audit_log_export",
            short_name="audit export",
            purpose="Export a bounded audit-event window.",
            description="Admin export of audit metadata, not source text.",
            tags=("admin", "audit", "export"),
            capabilities=("admin", "export"),
            risk=RiskClass.HIGH,
            role=UserRole.ADMIN,
            features=("admin",),
            schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "idempotency_key": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["idempotency_key"],
            },
            examples=('{"idempotency_key":"aud-1","limit":50}',),
            policy="Content-minimized audit rows only.",
            guidance="Do not include raw source passages.",
            side_effect=SideEffectClass.WRITE,
        ),
        _tool(
            tool_key="document_acl_report",
            short_name="ACL report",
            purpose="Summarize document ACL counts for admins.",
            description="Read-only ACL cardinality. Hidden from members.",
            tags=("admin", "acl", "report"),
            capabilities=("admin", "acl"),
            risk=RiskClass.MEDIUM,
            role=UserRole.ADMIN,
            features=("admin",),
            schema=empty_read,
            examples=("{}",),
            policy="Counts only. No document names for unauthorized ACLs.",
            guidance="Return integer counts, not hidden document titles.",
            side_effect=SideEffectClass.READ,
        ),
        _tool(
            tool_key="workspace_usage_card",
            short_name="usage card",
            purpose="Show remaining company LLM budget.",
            description="Read-only usage card for admins.",
            tags=("admin", "usage"),
            capabilities=("admin", "usage"),
            risk=RiskClass.LOW,
            role=UserRole.ADMIN,
            features=("admin",),
            schema=empty_read,
            examples=("{}",),
            policy="Does not enlarge reservations.",
            guidance="Read remaining USD from durable budget rows in a later packet.",
            side_effect=SideEffectClass.READ,
        ),
        _tool(
            tool_key="connector_slack_notify",
            short_name="slack notify",
            purpose="Future Slack connector. Disabled in v1.",
            description="Disabled future connector. Metadata only.",
            tags=("connector", "slack"),
            capabilities=("connector",),
            risk=RiskClass.HIGH,
            role=UserRole.ADMIN,
            features=("admin",),
            schema=mcp_schema,
            examples=("{}",),
            policy="Disabled. Cannot execute.",
            guidance="Future connector. Not an MCP runtime bind.",
            side_effect=SideEffectClass.REMOTE,
            active=False,
            discoverable=False,
        ),
        _tool(
            tool_key="connector_webhook",
            short_name="webhook",
            purpose="Future webhook connector. Disabled in v1.",
            description="Disabled future connector.",
            tags=("connector", "webhook"),
            capabilities=("connector",),
            risk=RiskClass.HIGH,
            role=UserRole.ADMIN,
            features=("admin",),
            schema=mcp_schema,
            examples=("{}",),
            policy="Disabled. Cannot execute.",
            guidance="Future connector. Not an MCP runtime bind.",
            side_effect=SideEffectClass.REMOTE,
            active=False,
            discoverable=False,
        ),
        _tool(
            tool_key="mcp_untrusted_probe",
            short_name="mcp probe",
            purpose="Imported MCP metadata. Cannot bind or execute.",
            description="MCP metadata import fixture. Execution is forbidden.",
            tags=("mcp", "remote"),
            capabilities=("mcp",),
            risk=RiskClass.CRITICAL,
            role=UserRole.OWNER,
            features=("owner",),
            schema=mcp_schema,
            examples=('{"mcp_server_url":"https://evil.example","tool_name":"x"}',),
            policy="Metadata import cannot authorize or bind a remote tool.",
            guidance="Reject arbitrary MCP targets at the executor.",
            side_effect=SideEffectClass.REMOTE,
            active=False,
            discoverable=False,
            mcp_origin=True,
        ),
        _tool(
            tool_key="retired_export_ods",
            short_name="export ods",
            purpose="Retired ODS export. Disabled.",
            description="Stale disabled export format.",
            tags=("export", "ods", "retired"),
            capabilities=("export", "ods"),
            risk=RiskClass.MEDIUM,
            role=UserRole.MEMBER,
            features=("export",),
            schema=_export_schema("ods"),
            examples=("{}",),
            policy="Disabled stale manifest.",
            guidance="Do not load. Executor rejects disabled versions.",
            side_effect=SideEffectClass.WRITE,
            active=False,
            discoverable=False,
        ),
        _tool(
            tool_key="viewer_help_card",
            short_name="help",
            purpose="Explain which optional exports exist for this role.",
            description="Viewer-visible help. Does not name hidden admin tools.",
            tags=("help", "catalog"),
            capabilities=("help",),
            risk=RiskClass.LOW,
            role=UserRole.VIEWER,
            features=(),
            schema=empty_read,
            examples=("{}",),
            policy="Must not list unauthorized catalog names.",
            guidance="Say that export requires member role. Do not name admin tools.",
            side_effect=SideEffectClass.NONE,
        ),
        _tool(
            tool_key="oversized_guidance_admin",
            short_name="oversized guidance",
            purpose="Admin fixture whose Level 3 guidance exceeds the byte cap.",
            description="Negative-test fixture for oversized guidance rejection.",
            tags=("admin", "fixture", "guidance"),
            capabilities=("admin", "fixture"),
            risk=RiskClass.LOW,
            role=UserRole.ADMIN,
            features=("admin",),
            schema=empty_read,
            examples=("{}",),
            policy="Guidance must be rejected before prompt construction.",
            guidance="G" * 4096,
            side_effect=SideEffectClass.NONE,
        ),
        _tool(
            tool_key="member_saved_view",
            short_name="saved view",
            purpose="Save a named table filter view for the caller.",
            description="Member-only saved view. Not a StructuredTable execute.",
            tags=("table", "view", "save"),
            capabilities=("table", "view"),
            risk=RiskClass.LOW,
            role=UserRole.MEMBER,
            features=("export",),
            schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                },
                "required": ["name", "idempotency_key"],
            },
            examples=('{"name":"q1","idempotency_key":"view-1"}',),
            policy="Does not execute structured_table_query.",
            guidance="Persist a name only. Recheck caller id.",
            side_effect=SideEffectClass.WRITE,
        ),
    )
    keys = [item.tool_key for item in tools]
    if len(keys) != len(set(keys)):
        raise ToolError("duplicate_tool_key")
    forbidden = CORE_FORBIDDEN_TOOL_KEYS.intersection(keys)
    if forbidden:
        raise ToolError("core_tool_not_catalogable")
    if len(tools) < 20:
        raise ToolError("catalog_too_small")
    return tools


def registry_by_key(
    registry: tuple[ToolDefinition, ...] | None = None,
) -> dict[str, ToolDefinition]:
    """Index the allow-list by tool_key.

    Args:
        registry: Optional catalog. Defaults to ``default_registry``.

    Returns:
        Key to definition map.
    """

    items = registry if registry is not None else default_registry()
    return {item.tool_key: item for item in items}


def get_tool(
    tool_key: str,
    *,
    version_label: str | None = None,
    registry: tuple[ToolDefinition, ...] | None = None,
) -> ToolDefinition:
    """Return one catalog definition after key/version checks.

    Args:
        tool_key: Requested key.
        version_label: Optional version that must match.
        registry: Optional catalog.

    Returns:
        The definition.

    Raises:
        ToolError: Unknown, disabled, or stale version.
    """

    found = registry_by_key(registry).get(tool_key)
    if found is None:
        raise ToolError("unknown_tool")
    if not found.active:
        raise ToolError("stale_or_disabled_manifest")
    if version_label is not None and found.version_label != version_label:
        raise ToolError("stale_or_disabled_manifest")
    return found


def registry_version() -> str:
    """Return the in-code allow-list version label.

    Returns:
        ``REGISTRY_VERSION``.
    """

    return REGISTRY_VERSION
