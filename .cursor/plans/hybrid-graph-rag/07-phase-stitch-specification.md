---
name: hybrid-graph-rag-phase-07-stitch-specification
phase: 7
status: in_progress
split_source: true
depends_on: [1, 2, 3, 4, 5, 6]
source_plan: ../hybrid-graph-rag_ab5281ef.plan.md
global_contract: ./00-global-contracts.md
---

# Phase 7: Stitch specification

## Mandatory model loading contract

1. Read [`00-global-contracts.md`](./00-global-contracts.md) first.
2. Read this wrapper completely.
3. Read [`07-phase-stitch-specification/00-shared-contracts.md`](./07-phase-stitch-specification/00-shared-contracts.md) completely.
4. Select exactly one unchecked packet below and read only that linked packet file.
5. Read only the packet-linked shared frontend contract, [`shared/frontend/stitch-nextjs-contract.md`](./shared/frontend/stitch-nextjs-contract.md); do not load another phase, packet, coverage, audit, or lock file.
6. Inspect repository reality and load the named workspace skill before editing. State the selected requirement and acceptance checks, implement the smallest complete packet, verify unstable APIs from pinned primary documentation, test applicable positive and negative paths, and record proof.

## Prerequisites

[Phase 1: Foundation](./01-phase-foundation.md), [Phase 2: Identity and data](./02-phase-identity-data.md), [Phase 3: Ingestion](./03-phase-ingestion.md), [Phase 4: Hybrid RAG](./04-phase-hybrid-rag.md), [Phase 5: GraphRAG](./05-phase-graphrag.md), [Phase 6: Agent intelligence](./06-phase-agent-intelligence.md)

## Relevant workspace skills

- [`.cursor/skills/implement-rag-frontend/SKILL.md`](../../../.cursor/skills/implement-rag-frontend/SKILL.md)

## Scope lock

**In scope:** The complete Stitch design brief, API/UI mapping, screen and component states, accessibility/responsiveness requirements, review loop, and fallback decision.

**Out of scope:** Production frontend coding beyond any minimal artifact needed to validate the specification.

The scope lock controls implementation sequencing; it does not weaken any security, authorization, durability, budget, grounding, bounded-work, or documentation invariant in the global contract.

## Ordered work packets

Complete these in order. A checked box requires committed implementation evidence in the phase exit record, not only code presence.

1. [x] [Inventory real Phase 6 API, Auth, streaming, route-diagnostic, document, graph, tool, usage, and administration contracts.](./07-phase-stitch-specification/packets/01-inventory-real-phase-6-contracts.md)
2. [ ] [Write copy-ready Stitch prompts, responsive LTR/RTL frames, Arabic/bidirectional behavior, information hierarchy, component inventory, localization decision, and design tokens.](./07-phase-stitch-specification/packets/02-write-stitch-prompts-and-frames.md)
3. [ ] [Specify every loading, empty, error, permission, quarantine, quota, compatibility, limitation, fallback, partial-readiness, budget, and degraded state.](./07-phase-stitch-specification/packets/03-specify-visible-states.md)
4. [ ] [Map each visible action and field to a real typed API/Auth contract; identify gaps instead of inventing mock behavior.](./07-phase-stitch-specification/packets/04-map-ui-to-real-contracts.md)
5. [ ] [Review accessibility, RTL keyboard/focus behavior, mobile layouts, mixed-direction citation/highlight interactions, safe text rendering, and security boundaries.](./07-phase-stitch-specification/packets/05-review-accessibility-and-security.md)
6. [ ] [Timebox user generation/review to five business days and two rounds; record approval or explicitly select the component-system fallback.](./07-phase-stitch-specification/packets/06-record-approval-or-fallback.md)

## Phase sequence requirement

**Program sequence item 7:** Stitch specification delivers the Stitch brief and API/UI map, then pauses for the generated UX and review.

## Stop conditions

Stop this phase and report the blocker instead of improvising when:

- a prerequisite phase or required sign-off is incomplete;
- the actual repository contradicts the plan and the difference changes security, data, cost, or acceptance semantics;
- a required dependency contract cannot be verified from its pinned version and primary documentation;
- an authorization, idempotency, deadline, budget, provenance, or fallback test cannot exercise the real boundary;
- a required integration is unavailable and only a fake or skipped test would pass;
- any launch-blocking check fails after bounded repair attempts.

## Required exit record

Create or update [`docs/development/phase-07-stitch-specification-evidence.md`](../../../docs/development/phase-07-stitch-specification-evidence.md) with:

- plan requirement and work-packet number;
- files, migrations, APIs, environment variables, and documentation changed;
- exact verification commands discovered from the repository;
- test/build/lint/type/migration results and relevant measured metrics;
- authorization, failure, idempotency, fallback, and bounded-resource evidence;
- unverified external assumptions or unavailable managed-environment checks;
- deviations, ADR approval, and rollback notes;
- explicit handoff inputs and open blockers for the next phase.

Do not set `status: complete` until every `Done when` item below is proven.

## Canonical detailed requirements

Detailed requirements are redistributed by link: the phase execution contract is [`07-phase-stitch-specification/00-shared-contracts.md`](./07-phase-stitch-specification/00-shared-contracts.md), and canonical legacy Section 12 requirements are owned once in [`shared/frontend/stitch-nextjs-contract.md`](./shared/frontend/stitch-nextjs-contract.md).

## Phase deliver, review, and done gate

### Phase 7 — Stitch specification

- Deliver: copy-ready Stitch prompts, screen requirements, LTR/RTL and mixed-direction fixtures, localization decision, component/state/limitation inventory, responsive behavior, accessibility rules, API/UI/version-handshake mapping, timebox, and component-library fallback.
- Review: user flow, Arabic/bidirectional citation behavior, limitation and authorization messaging, compatibility/quota states, and visual requirements before any generated design is treated as final.
- Done when: complete reviewed [`docs/frontend/STITCH_BRIEF.md`](../../../docs/frontend/STITCH_BRIEF.md) and [`docs/frontend/API_UI_MAPPING.md`](../../../docs/frontend/API_UI_MAPPING.md) exist and are linked; the brief contains copy-ready prompts, responsive LTR/RTL frames, localization decision, mixed-direction chat/citation/highlight examples, information hierarchy, component inventory, copy, accessibility/keyboard/WCAG requirements, and every loading/empty/error/permission/quarantine/quota/version-mismatch/BM25-projection-or-degradation/partial-readiness/figure-temporal-ACL-summary-negation limitation state for all listed auth, team, chat/diagnostic, document, graph, tool/curation, usage, audit, profile, and company-settings screens; the API/UI map ties every visible field/action/state to a real Phase 2/6 Auth/API/SSE contract and records unresolved gaps without inventing mocks; and within five business days/two revision rounds the user either approves usable accessible Stitch references or explicitly selects and documents the component-library fallback so Phase 8 has an unambiguous implementation input.
