"""MCP metadata import is allowed; arbitrary runtime execution is not."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.security.identity import UserRole
from smart_rag_core.tools.exceptions import ToolError
from smart_rag_core.tools.models import (
    RiskClass,
    SideEffectClass,
    ToolDefinition,
    ToolQuotas,
)


class McpMetadataImport(BaseModel):
    """Trusted administrator-approved MCP metadata. Not an execution grant.

    Attributes:
        tool_key: Proposed catalog key.
        short_name: Display name.
        description: Imported description.
        json_schema: Imported argument schema.
        mcp_server_url: Remote server URL recorded as metadata only.
        mcp_tool_name: Remote tool name recorded as metadata only.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_key: str = Field(min_length=1, max_length=64)
    short_name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=512)
    json_schema: dict[str, object]
    mcp_server_url: str = Field(min_length=1, max_length=512)
    mcp_tool_name: str = Field(min_length=1, max_length=128)


def import_mcp_metadata(metadata: McpMetadataImport) -> ToolDefinition:
    """Import MCP metadata into the registry as inactive and undiscoverable.

    The model cannot connect to the recorded server or execute the remote
    tool. A later administrator must promote an internal allow-listed
    implementation; this import is not that promotion.

    Args:
        metadata: Administrator-supplied metadata.

    Returns:
        Disabled catalog definition.

    Raises:
        ToolError: If the import tries to use a core retrieve key.
    """

    return ToolDefinition(
        tool_key=metadata.tool_key,
        version_label="mcp-meta-v1",
        short_name=metadata.short_name,
        description=metadata.description,
        one_line_purpose="Imported MCP metadata. Not executable.",
        tags=("mcp", "metadata"),
        capabilities=("mcp",),
        risk_class=RiskClass.CRITICAL,
        required_role=UserRole.OWNER,
        required_features=("owner",),
        json_schema=metadata.json_schema,
        examples=(),
        policy="Metadata import cannot authorize or bind a remote tool.",
        long_guidance=f"source={metadata.mcp_server_url} name={metadata.mcp_tool_name}",
        side_effect_class=SideEffectClass.REMOTE,
        quotas=ToolQuotas(),
        active=False,
        catalog_discoverable=False,
        mcp_origin=True,
    )


def reject_arbitrary_mcp(target: str) -> None:
    """Reject model-proposed MCP or remote-server execution.

    Args:
        target: Requested server URL, tool name, or combined target.

    Raises:
        ToolError: Always ``arbitrary_mcp_rejected``.
    """

    del target
    raise ToolError("arbitrary_mcp_rejected")


def bind_or_execute_mcp(target: str) -> None:
    """Refuse to bind or execute a newly discovered remote tool.

    Args:
        target: Requested MCP target.

    Raises:
        ToolError: Always ``arbitrary_mcp_rejected``.
    """

    reject_arbitrary_mcp(target)
