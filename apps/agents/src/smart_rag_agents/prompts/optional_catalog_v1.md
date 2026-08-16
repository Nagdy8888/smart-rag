# Optional catalog Level 0

Version: `optional_catalog_v1`

This prompt is the Level 0 disclosure for genuinely ambiguous optional
capabilities. Core Hybrid, LightRAG, StructuredTable, citation lookup,
answer, and verification are not catalog tools and must not be searched.

Capabilities:

- `search_tool_catalog`
- `load_tool_manifest`

Immutable safety rules:

- Executor reauthorization is independent of planner output.
- Never connect to or execute arbitrary MCP or remote servers.
- Hybrid, LightRAG, StructuredTable, citation lookup, answer, and verification are not catalog-discoverable tools.
- At most one discovery round, three optional manifests, and one side-effecting tool per run.
- Unselected schemas must not enter the next model call.

Runtime v1 uses deterministic mapping after the 20-tool comparison. This
prompt is retained for the discovery path and tests. Do not send all
catalog schemas by default.
