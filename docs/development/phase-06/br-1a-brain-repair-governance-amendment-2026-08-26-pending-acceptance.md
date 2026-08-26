# BR-1A — Brain-repair governance amendment (2026-08-26, pending acceptance)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Markdown-only remediation of the 2026-08-25 strict-split contracts. No
Python, TypeScript, SQL, prompt, or graph-registration behavior changed.

Requirement: draft the four additional decisions before any profile-gateway
or graph-topology code. Record them in P06-09, the ADR, the global/Phase 6
deviation text, P06-10, P06-12, and agent routing/budget docs. Do not treat
the amendment as accepted until the user explicitly accepts it.

Drafted decisions:

1. One counted live `usage_kind="profile"` call is allowed on the production
   query path under existing caps.
2. Unavailable, malformed, or low-confidence profile inference records a
   typed degradation reason and may produce an honest general answer. It does
   not become mixed-scope clarification.
3. Pure greetings and bounded small talk are model-classified and
   model-answered, normally one profile call plus one answer call.
4. After `compile_plan`, a validated `RetrievalPlan` selects explicit
   company, general, mixed, or fail-closed graph paths. Direct paths skip
   retrieval and still receive deterministic verification.

Superseded 2026-08-25 clauses:

- P06-10: full greeting → `DETERMINISTIC`; unavailable/invalid/low-confidence
  → `AMBIGUOUS`; `DETERMINISTIC` → `DETERMINISTIC_CHAT`.
- P06-12: greetings → canned deterministic origin with zero model calls.
- ADR / global / Phase 6: "uncertain scope returns clarification" for profile
  failure.

Files:

- [`.cursor/plans/hybrid-graph-rag/00-global-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/00-global-contracts.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/09-canonical-general-chat-amendment.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/09-canonical-general-chat-amendment.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/10-knowledge-scope-routing.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/10-knowledge-scope-routing.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/12-general-chat-execution.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/12-general-chat-execution.md)
- [`.cursor/plans/hybrid-graph-rag/99-source-coverage.md`](../../../.cursor/plans/hybrid-graph-rag/99-source-coverage.md)
- [`docs/adr/ADR-general-chat-strict-split.md`](../../adr/ADR-general-chat-strict-split.md)
- [`docs/agent/QUERY_ROUTING.md`](../../agent/QUERY_ROUTING.md)
- [`docs/agent/QUERY_BUDGETS.md`](../../agent/QUERY_BUDGETS.md)
- [`.cursor/plans/agent_brain_repair_8c84c1f7.plan.md`](../../../.cursor/plans/agent_brain_repair_8c84c1f7.plan.md)
  marked superseded by
  [`.cursor/plans/scope_graph_nodes_916779e1.plan.md`](../../../.cursor/plans/scope_graph_nodes_916779e1.plan.md)

Verification:

| Command | Exit |
| --- | --- |
| `uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py` | 0 after lock refresh (107 canonical files) |
| Docs lint (`markdownlint-cli2 docs/**/*.md`) | 0 (190 files) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

Proven: packet titles match the Phase 6 wrapper, plan integrity verifies
after the approved-structure lock refresh, docs lint/links/Mermaid pass,
and no application code was changed in this packet.

Unverified: explicit user acceptance of the four decisions.

Rollback: restore the 2026-08-25 deviation/ADR/packet wording and the
previous integrity lock. Do not start BR-2 or Packet 2 code until the user
accepts the amendment.
