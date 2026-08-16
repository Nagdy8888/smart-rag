---
phase: 6
packet: 4
status: complete
title: "Implement the optional-tool registry/disclosure contract while keeping core retrieval and verification outside catalog discovery."
requirement_ids: [P06-04]
---

# Packet 4 — Implement the optional-tool registry/disclosure contract while keeping core retrieval and verification outside catalog discovery.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

## Preconditions

- Packets 1–3 are accepted; core QueryProfile routes directly bind Hybrid, LightRAG, StructuredTable, source lookup, answer generation, and verification.
- Phase 2 role/feature/permission and audit contracts plus typed tool argument/side-effect policies exist; packet 1 supplies authorized user, reservation, ceilings, and idempotency context.
- Inspect the actual LangChain/LangGraph pinned middleware APIs from primary documentation and contract-test unstable binding behavior.

## Allowed outputs

- Framework-independent registry, manifests, permission filtering, lexical/embedding catalog ranking, progressive disclosure, executor validation, LangGraph wrappers, synthetic fixtures, telemetry, documentation, tests, and evidence.
- Core services live in [`packages/core/src/smart_rag_core/tools/`](../../../../../packages/core/src/smart_rag_core/tools/); discovery/selection node wrappers live in [`apps/agents/src/smart_rag_agents/query/nodes/`](../../../../../apps/agents/src/smart_rag_agents/query/nodes/) and core defines no LangGraph nodes.

## Forbidden outputs

- Catalog/model discovery for Hybrid, LightRAG, StructuredTable, source lookup, answer generation, or verification; sending all schemas by default; binding unselected tools; trusting planner authorization; or arbitrary runtime MCP/server execution.
- More than one discovery round, more than three optional manifests, unbounded manifest guidance/input, a second side-effecting tool, or claiming discovery value without the required comparative fixture.

## Ordered actions

1. Define an internal allow-listed, versioned registry with short names, descriptions, tags, capabilities, risk class, required role/features, compact card, full schema/examples/policy, long guidance sections, side-effect class, quotas, and executor contract.
2. Map explicit known optional intents deterministically and load only that manifest. Run catalog search only for genuinely ambiguous optional capabilities such as export format, administration, or a future approved connector.
3. Implement disclosure levels:
   - Level 0: compact `search_tool_catalog`/`load_tool_manifest` capabilities and immutable safety rules only.
   - Level 1: a bounded small top-k of ID, name, one-line purpose, risk class, and required role after role/feature filtering plus lexical/embedding ranking.
   - Level 2: full schema, examples, and policy only for selected tools.
   - Level 3: bounded sections of long operational guidance only when execution requires them.
4. Bind selected tools through dynamic LangChain middleware for the next model call only. Independently recheck tool ID/version, user/company/role, arguments, quotas, idempotency, side-effect policy, and current authorization at execution.
5. Enforce the shared ceilings: one discovery/selection round, at most three optional manifests, at most four total tool executions or five for Composite, and at most one side-effecting tool.
6. Add hard budgets for selected tools, manifest bytes/tokens, retrieval chunks, parent expansion, conversation summary, and total model input. Reject over-limit cards/manifests/guidance before prompt construction.
7. Record discovery latency separately from retrieval latency and record tools searched, disclosed, loaded, called, rejected, and useful without exposing hidden/unauthorized catalog entries.
8. Keep v1 tools internal and allow-listed. Future MCP adapters may import trusted administrator-approved metadata into this registry; the model cannot connect to arbitrary servers or execute a newly discovered remote tool.
9. Build a synthetic catalog of at least 20 tools. Prove unselected schemas never enter prompts and compare optional discovery against compact cards/deterministic mappings for selection quality, latency, and token cost.
10. Exercise the table-plus-export example: bind `structured_table_query` deterministically; search only ambiguous export cards; load one selected export manifest; keep administration/member tools hidden; executor rechecks table IDs, plan, role, resource limits, and format.
11. If discovery does not improve selection enough to justify latency/token cost, use deterministic profile-to-tool mapping and record the evaluated rejection instead of retaining unnecessary model work.

## Acceptance checks

- Core retrieval/answer/verification call paths incur zero catalog-search model rounds and expose no optional schema unless the typed request requires it.
- Level 0–3 payloads are bounded and permission-filtered; only selected manifests/guidance enter the next call, and executor reauthorization cannot be bypassed by the planner.
- One discovery round, three optional manifests, route tool ceilings, one side-effecting tool, and all byte/token/chunk/summary/input budgets are enforced.
- The at-least-20-tool fixture proves zero unrelated schema leakage and either justified selection improvement or a documented deterministic mapping fallback.
- Arbitrary MCP execution is absent; metadata import alone cannot authorize or bind a remote tool.

## Negative tests

- Unauthorized card/name/count leakage, core-tool catalog round trip, fourth manifest, second discovery, unselected schema in prompt, stale/disabled manifest, role change after planning, argument/quota/idempotency/side-effect violation, oversized guidance, over-budget model input, second side effect, arbitrary MCP target, or unjustified discovery retained in runtime fails.

## Stop routes

- Stop if current pinned middleware cannot bind only the next call, executor-side reauthorization cannot be made independent, registry permissions cannot hide unauthorized metadata, or synthetic comparison cannot be measured.
- Do not enable arbitrary remote execution or weaken the core deterministic route to make discovery easier.

## Required evidence

- Append to [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md): registry/manifest versions, disclosure payload/token sizes, role/feature matrices, prompt captures proving omitted schemas, middleware binding lifetime, executor rejection tests, at-least-20-tool comparison metrics, discovery-versus-retrieval latency, selected fallback decision, exact commands/exit codes, deviations, rollback, and packet 5 handoff.
