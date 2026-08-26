# Packet 4 — optional-tool registry and progressive disclosure

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

## Quoted requirement

> Implement the optional-tool registry/disclosure contract while keeping
> core retrieval and verification outside catalog discovery.

## Acceptance checks restated

- Core retrieval/answer/verification call paths incur zero catalog-search
  model rounds and expose no optional schema unless the typed request
  requires it.
- Level 0–3 payloads are bounded and permission-filtered; only selected
  manifests/guidance enter the next call; executor reauthorization cannot
  be bypassed by the planner.
- One discovery round, three optional manifests, route tool ceilings
  (4, or 5 Composite), one side-effecting tool, and byte/token/chunk/
  summary/input budgets are enforced.
- ≥20-tool fixture proves zero unrelated schema leakage and either
  justified selection improvement **or** documented deterministic mapping
  fallback.
- Arbitrary MCP execution is absent; metadata import alone cannot
  authorize or bind a remote tool.

## Inspected pins / APIs

| Item | Found |
| --- | --- |
| `langgraph` | `1.2.11` in `apps/agents/pyproject.toml` |
| `langchain-core` | `1.5.4` transitive in `uv.lock` |
| `langchain.agents` middleware | **absent** (no top-level `langchain` agents package) |
| Query graph | `StateGraph` in `apps/agents/src/smart_rag_agents/query/graph.py`, not `create_agent` |
| Current docs | [Dynamic tool selection](https://docs.langchain.com/oss/python/langchain/tools#dynamic-tool-selection) (`wrap_model_call` + `request.override(tools=...)`) apply to unpinned `langchain.agents` |
| `BaseChatModel.bind_tools` | Raises `NotImplementedError` on the fake chat model; `Runnable.bind(tools=...)` returns a **new** runnable |
| Latest app migration | `20260816180000_query_memory_routing_v1.sql` (no Packet 4 SQL) |
| Existing catalog tables | `app.tool_catalog` / `tool_versions` / `tool_permissions` / `tool_usage_events` from `20260812135100_tools_catalog_v1.sql` |
| Registry version | `optional_tools_v1` in-code allow-list (runtime authority) |
| L0 prompt | `optional_catalog_v1.md` |

## Binding approach (pin-compatible equivalent)

Pinned middleware cannot use `langchain.agents` `wrap_model_call`. The
packet stop (“stop if pinned middleware cannot bind only the next call”)
does **not** fire: `langchain-core` `Runnable.bind(tools=...)` binds
selected schemas onto a **new** runnable for that invocation. The original
chat model is not mutated, so the following call does not receive
unselected schemas. Wrapper:
`smart_rag_agents.query.nodes.binding.bind_selected_tools_next_call`.
Contract: `test_bind_tools_next_call_does_not_leak_unselected_schemas`.

Core (`smart_rag_core`) defines no LangGraph nodes and does not import
langgraph/langchain.

## Registry / role matrix

23 allow-listed tools. Forbidden core keys are absent:
`hybrid_retrieve`, `lightrag_retrieve`, `graph_retrieve`,
`structured_table_query`, `citation_lookup`, `source_lookup`, `answer`,
`verifier`, `answer_generate`, `verify_answer`.

Catalog holds **export format** cards, member helpers, admin/owner
administration fixtures, disabled connectors, an MCP metadata fixture,
a stale ODS export, and an oversized-guidance admin fixture.

| Role | Visible count | Notes |
| --- | --- | --- |
| viewer | 1 (`viewer_help_card`) | No export/admin names or counts |
| member | 11 | export + feedback; no admin |
| admin | 18 | no owner-only `admin_budget_adjust` |
| owner | 19 | still hides disabled/undiscoverable MCP/connectors/stale ODS |

Hidden/disabled tools contribute **neither names nor counts**.

## Disclosure sizes (member, query `export this table`)

| Level | Bytes | Tokens (cl100k) | Content |
| --- | --- | --- | --- |
| L0 | 497 | 105 | capabilities + safety rules; no catalog names |
| L1 | 886 | 199 | top-5 export cards after role filter |
| L2 (`export_csv` only) | 1515 | 367 | selected schema/examples/policy |
| L3 (+ CSV guidance) | 1660 | 400 | bounded operational section |

Prompt capture: L2 for `export_csv` does **not** contain `invite_email`,
`admin_user_invite`, `structured_table_query`, or `"const":"xlsx"`.
`xlsx` may appear on L1 cards (visible export ranking) but the unselected
XLSX **schema** does not enter the selected manifest.

## ≥20-tool comparison (10 cases)

Measured by `compare_discovery_vs_mapping()` against the 23-tool catalog.

| Metric | Deterministic mapping | Catalog discovery |
| --- | --- | --- |
| Accuracy | `0.80` (8/10) | `0.70` (7/10) |
| Accuracy gain | — | **−10.0 pp** |
| Latency | `0.08 ms` | `9.04 ms` |
| Tokens in selection payload | `12` | `3099` (ratio ≫ 2.0) |

Thresholds: retain discovery only if gain ≥ **10 pp** and token ratio ≤
**2.0**. Discovery failed both. Runtime policy:
`SelectionPolicy.DETERMINISTIC_MAPPING`. Unjustified discovery retained
in runtime fails with `unjustified_discovery_retained`.

Discovery latency is recorded on `OptionalTelemetry.discovery_latency_ms`
and is **not** mixed with Hybrid/LightRAG retrieval latency. Core Hybrid
path skips optional selection (`optional_selection_mode=skipped`), so
catalog discovery latency is zero there.

## Graph wiring

`compose_tables` → `disclose_optional_tools` → `generate_answer` →
`verify_answer` → END.

Table-plus-export: `structured_table_query` remains packet 3 deterministic
composition; catalog loads one export manifest; executor rechecks table
IDs, format, live role, quotas, and idempotency. Viewers never see
member/admin cards.

Hybrid `INV-SR-1001` invoke: `catalog_llm_call_count=0`,
`keyword_extract_count=0`, `optional_selection_mode` skipped. Answer and
verifier nodes preserve the catalog counter (they do not call the
catalog).

## Negative tests

Unauthorized card/name/count leakage, core-tool catalog membership,
fourth manifest, second discovery, unselected schema in prompt, stale/
disabled manifest, role change after planning, argument/quota/table-id
violation, oversized guidance, over-budget model input, second side
effect, arbitrary MCP target, metadata-import-cannot-bind, and
unjustified discovery retained in runtime all fail closed. Core path
zero catalog rounds. Next-call bind does not leak unselected schemas
onto the original model.

## Commands and results

Recorded on Windows PowerShell. DSN passwords are not logged.

| Command | Exit |
| --- | --- |
| `uv run ruff format` on changed Python paths | 0 |
| `uv run ruff check` on changed Python paths | 0 |
| `uv run python -m pyright` on changed Python paths | 0 errors |
| `uv run python -m pytest tests/unit/test_optional_tools.py tests/unit/test_optional_tools_discovery.py tests/contract/test_langgraph_config.py tests/unit/test_package_imports.py tests/contract/test_import_boundaries.py -q` | 0; **40 passed**, 5 warnings (SwigPy worker import), 0 failed |
| `uv run python scripts/ci/check_migrations.py` | 0 (48 reviewed files; no Packet 4 SQL) |

## Deviations

- No new SQL migration. v1 authority is the in-code `optional_tools_v1`
  registry plus live role from `CallerContext` /
  `AuthorizedRuntimeContext`. Existing `app.tool_catalog` rows are
  expand-ready for a later admin UI seed, not runtime authorization.
- Catalog LLM is **not** a new `llm_usage` kind. Runtime mapping spends
  zero catalog model rounds. `force_discovery` is test-only.
- `langchain.agents` dynamic-tool middleware is **not** added. The
  StateGraph `Runnable.bind(tools=...)` equivalent is documented in
  [OPTIONAL_TOOLS.md](../../agent/OPTIONAL_TOOLS.md).
- `smart_rag_core.gateways` model exports are lazy so
  `from smart_rag_core.gateways.storage import StorageGateway` does not
  import `query_answer` while `query_admission.ceilings` is still loading.
- SSE, FastAPI catalog admin UI, and the testing UI remain later packets.

## Rollback

Forward-fix: skip `disclose_optional_tools` (wire `compose_tables` →
`generate_answer`) and stop binding optional schemas. No DROP. No new
migration to revert. Restore eager `gateways` model imports only after
breaking the ceilings ↔ routing cycle another way.

## Packet 5 handoff

- Thin FastAPI routers/services, Supabase-Auth/FastAPI rate ownership,
  authorization-safe retrieval caching, endpoint-specific authorization,
  CPU offload, and prompt/data isolation.
- Tools endpoints (catalog search / admin create/version/enable/
  permission) must not treat DB seed as authority unless they recheck the
  same live role + in-code allow-list (or an additive catalog expansion
  that preserves executor reauthorization).
- Auto admit should still reserve `composite` so Combined and
  Hybrid→Combined escalation fit the envelope.
- Keep `keyword_extract_count=0` and `catalog_llm_call_count=0` on the
  core retrieve/answer/verify path.
- SSE, reconnect, heartbeats, and UI remain packets 6 and 8.
- Do **not** mark Phase 6 complete. Do **not** check the wrapper checkbox.

## Unverified (packet 4)

- Live FastAPI catalog search/admin routes (packet 5 HTTP unit tests now
  cover in-code registry + live role; live Postgres seed writes remain
  unverified).
- Live `app.tool_usage_events` inserts against Postgres.
- Hosted Auth throttling (carried from packet 1).
- QT-EVAL-009 and Combined p95 latency (carried from packet 3).
