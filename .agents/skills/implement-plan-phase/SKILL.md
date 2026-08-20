---
name: implement-plan-phase
description: Executes or closes one evidence-gated work packet from an approved Hybrid/Graph RAG phase, enforcing reading order, named skills, acceptance criteria, exit evidence, and user-approved phase advancement. Use when the user asks to begin, implement, continue, or complete a plan phase.
disable-model-invocation: true
---

# Implement a Plan Phase

Read the [canonical index](../../plans/hybrid-graph-rag_ab5281ef.plan.md), the [global contract](../../plans/hybrid-graph-rag/00-global-contracts.md), and exactly one active phase wrapper completely. For inline Phases 1–5, use the selected embedded packet contract. For a phase with `split_source: true`, read its phase shared contract, exactly one linked active packet, and only the additional shared concern contracts named by that packet. Never implement from the index, coverage manifest, audit, todo summary, sibling packets, or a later phase.

## Workflow

1. Confirm every prerequisite phase and required sign-off from the active phase wrapper.
2. Select exactly one unchecked ordered work packet for this model run. In a split phase, resolve it only through the wrapper's ordered packet link; do not load sibling packet files or implement the whole phase.
3. Load every workspace skill named by the active phase that applies to this packet.
4. Quote the selected packet and state its concrete acceptance checks before editing.
5. Inspect the repository state. Never assume a planned file, schema, endpoint, dependency, or command already exists.
6. Build the smallest complete slice that ends in observable behavior and tests without later-phase infrastructure.
7. Before calling an external API:
   - inspect the pinned package version;
   - fetch current primary documentation;
   - confirm parameter names, async/lifecycle behavior, storage schema, and deprecations;
   - add a contract test for unstable dependencies.
8. Implement through the planned boundaries:
   - transport in FastAPI/Next.js;
   - behavior in services/LangGraph nodes;
   - persistence in repositories/migrations;
   - all model calls through the shared gateway.
9. Verify failure, authorization, retry, idempotency, timeout, budget, bounded-resource, and degraded paths—not only success.
10. Run the narrow checks first, then every phase gate applicable to the packet.
11. Write the packet evidence handoff. Check the packet only when the evidence passes.
12. Do not mark the phase complete or start the next phase until every `Done when` item is proven in the exit record and the user accepts it.

## Anti-hallucination gate

Do not write code until each item is evidenced:

- Existing path/class/table/setting: confirmed by repository search or migration.
- Library API: confirmed by current docs for the pinned version.
- Database feature/version: confirmed locally and against the managed target.
- Security assumption: enforced in SQL/service code and tested negatively.
- Retrieval claim: measured by ranked-evidence tests, not an answer that merely sounds correct.
- Completion claim: backed by command output or clearly marked unverified.

If a required decision is absent and changes security, persistence, cost, or public contracts, ask the user. Otherwise follow the plan's explicit default.

## Completion report

Return:

- implemented plan requirements;
- files and migrations changed;
- checks run and results;
- measured behavior where relevant;
- unverified external/staging requirements;
- deviations or follow-up gates.

When closing a phase, also return the complete exit record, unresolved managed/external blockers, rollback notes, and an explicit request for user acceptance before advancing.
