"""Bounded optional-tool ceilings. Core retrieval tools are never cataloged."""

from __future__ import annotations

from smart_rag_core.tools.exceptions import ToolError

REGISTRY_VERSION = "optional_tools_v1"
"""In-code allow-list version. Not a database seed version."""

CORE_FORBIDDEN_TOOL_KEYS: frozenset[str] = frozenset(
    {
        "hybrid_retrieve",
        "lightrag_retrieve",
        "graph_retrieve",
        "structured_table_query",
        "citation_lookup",
        "source_lookup",
        "answer",
        "verifier",
        "answer_generate",
        "verify_answer",
        "web_search",
    }
)
"""Keys that must never appear in the optional catalog."""

L0_CAPABILITIES: tuple[str, ...] = ("search_tool_catalog", "load_tool_manifest")

L0_SAFETY_RULES: tuple[str, ...] = (
    "Executor reauthorization is independent of planner output.",
    "Never connect to or execute arbitrary MCP or remote servers.",
    "Hybrid, LightRAG, StructuredTable, citation lookup, answer, and "
    "verification are not catalog-discoverable tools.",
    "At most one discovery round, three optional manifests, and one "
    "side-effecting tool per run.",
    "Unselected schemas must not enter the next model call.",
)

L1_TOP_K = 5
L1_CARD_MAX_BYTES = 256
L2_MANIFEST_MAX_BYTES = 4096
L2_MANIFEST_MAX_TOKENS = 800
L3_GUIDANCE_MAX_BYTES = 2048
L3_GUIDANCE_MAX_TOKENS = 400
MAX_OPTIONAL_MANIFESTS = 3
MAX_DISCOVERY_ROUNDS = 1
MAX_SIDE_EFFECTING_TOOLS = 1
MAX_RETRIEVAL_CHUNKS_IN_TOOL_PROMPT = 12
MAX_PARENT_EXPANSION_IN_TOOL_PROMPT = 4
MAX_CONVERSATION_SUMMARY_TOKENS = 400
MAX_MODEL_INPUT_TOKENS = 8000
MAX_SELECTED_TOOL_SCHEMAS = 3

MIN_DISCOVERY_ACCURACY_GAIN_PP = 10.0
"""Discovery must beat deterministic mapping by this many percentage points."""

MAX_DISCOVERY_TOKEN_RATIO = 2.0
"""Discovery may not cost more than this multiple of deterministic tokens."""

DEFAULT_AMBIGUOUS_EXPORT_KEY = "export_csv"
"""Deterministic default when export format is unspecified."""


def consume_remaining(remaining: int, *, reason: str) -> int:
    """Decrement a remaining ceiling or fail closed.

    Args:
        remaining: Current remaining units.
        reason: ToolError reason when exhausted.

    Returns:
        ``remaining - 1``.

    Raises:
        ToolError: When ``remaining`` is already ``0`` or negative.
    """

    if remaining <= 0:
        raise ToolError(reason)
    return remaining - 1
