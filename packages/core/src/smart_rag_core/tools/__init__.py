"""Optional-tool registry, progressive disclosure, and executor reauthorization.

Core Hybrid, LightRAG, StructuredTable, citation lookup, answer, and
verifier tools are not catalog-discoverable. LangGraph node wrappers live
in ``smart_rag_agents.query.nodes``.
"""

from smart_rag_core.tools.catalog import (
    default_registry,
    get_tool,
    registry_by_key,
    registry_version,
)
from smart_rag_core.tools.compare import (
    RUNTIME_SELECTION_POLICY,
    compare_discovery_vs_mapping,
    evaluate_discovery_justification,
)
from smart_rag_core.tools.constants import (
    CORE_FORBIDDEN_TOOL_KEYS,
    MAX_OPTIONAL_MANIFESTS,
    REGISTRY_VERSION,
)
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
from smart_rag_core.tools.mapping import map_optional_intent
from smart_rag_core.tools.mcp import (
    McpMetadataImport,
    bind_or_execute_mcp,
    import_mcp_metadata,
    reject_arbitrary_mcp,
)
from smart_rag_core.tools.models import (
    ComparisonMetrics,
    ExecutionResult,
    OptionalIntent,
    OptionalTelemetry,
    PlannedInvocation,
    SelectionPolicy,
    ToolDefinition,
)
from smart_rag_core.tools.permissions import features_for_role, visible_tools
from smart_rag_core.tools.service import (
    assert_discovery_not_unjustified,
    resolve_optional_tools,
)

__all__ = [
    "CORE_FORBIDDEN_TOOL_KEYS",
    "MAX_OPTIONAL_MANIFESTS",
    "REGISTRY_VERSION",
    "RUNTIME_SELECTION_POLICY",
    "ComparisonMetrics",
    "ExecutionResult",
    "McpMetadataImport",
    "OptionalIntent",
    "OptionalTelemetry",
    "PlannedInvocation",
    "SelectionPolicy",
    "ToolDefinition",
    "ToolError",
    "assemble_optional_prompt",
    "assert_discovery_not_unjustified",
    "bind_or_execute_mcp",
    "compare_discovery_vs_mapping",
    "default_registry",
    "detect_optional_intent",
    "evaluate_discovery_justification",
    "execute_optional_tool",
    "features_for_role",
    "get_tool",
    "import_mcp_metadata",
    "level0_payload",
    "level1_cards",
    "load_guidance",
    "load_manifests",
    "map_optional_intent",
    "registry_by_key",
    "registry_version",
    "reject_arbitrary_mcp",
    "resolve_optional_tools",
    "visible_tools",
]
