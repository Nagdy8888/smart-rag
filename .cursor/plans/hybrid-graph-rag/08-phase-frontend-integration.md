---
name: hybrid-graph-rag-phase-08-frontend-integration
phase: 8
status: pending
split_source: true
depends_on: [1, 2, 3, 4, 5, 6, 7]
source_plan: ../hybrid-graph-rag_ab5281ef.plan.md
global_contract: ./00-global-contracts.md
---

# Phase 8: Frontend integration

## Mandatory model loading contract

1. Read [`00-global-contracts.md`](./00-global-contracts.md) first.
2. Read this wrapper completely.
3. Read [`08-phase-frontend-integration/00-shared-contracts.md`](./08-phase-frontend-integration/00-shared-contracts.md) completely.
4. Select exactly one unchecked packet below and read only that linked packet file.
5. Read only the packet-linked shared frontend contract, [`shared/frontend/stitch-nextjs-contract.md`](./shared/frontend/stitch-nextjs-contract.md); do not load another phase, packet, coverage, audit, or lock file.
6. Inspect repository reality and load the named workspace skill before editing. State the selected requirement and acceptance checks, implement the smallest complete packet, verify unstable APIs from pinned primary documentation, test applicable positive and negative paths, and record proof.

## Prerequisites

[Phase 1: Foundation](./01-phase-foundation.md), [Phase 2: Identity and data](./02-phase-identity-data.md), [Phase 3: Ingestion](./03-phase-ingestion.md), [Phase 4: Hybrid RAG](./04-phase-hybrid-rag.md), [Phase 5: GraphRAG](./05-phase-graphrag.md), [Phase 6: Agent intelligence](./06-phase-agent-intelligence.md), [Phase 7: Stitch specification](./07-phase-stitch-specification.md)

## Relevant workspace skills

- [`.cursor/skills/implement-rag-frontend/SKILL.md`](../../../.cursor/skills/implement-rag-frontend/SKILL.md)

## Scope lock

**In scope:** Production Next.js integration of the approved Stitch design or fallback system, with real Auth/API/streaming contracts, all user/admin surfaces, security, accessibility, and E2E coverage.

**Out of scope:** Release sizing, managed infrastructure, production provisioning, and backend redesign outside defects required by the approved contracts.

The scope lock controls implementation sequencing; it does not weaken any security, authorization, durability, budget, grounding, bounded-work, or documentation invariant in the global contract.

## Delivered Stitch template (not product layout)

The user-approved Phase 7 review records the Stitch bundle as a **template,
not a layout**. Do not add Stitch frames as product routes. The normative
screen list is [`docs/frontend/STITCH_REVIEW.md`](../../../docs/frontend/STITCH_REVIEW.md)
and [`docs/frontend/API_UI_MAPPING.md`](../../../docs/frontend/API_UI_MAPPING.md).
Token and prohibited-pattern rules remain in
[`08-phase-frontend-integration/00-shared-contracts.md`](./08-phase-frontend-integration/00-shared-contracts.md).

## Ordered work packets

Complete these in order. A checked box requires committed implementation evidence in the phase exit record, not only code presence.

1. [x] [Integrate the approved design system into the existing Next.js workspace without replacing real Phase 6 contracts with mocks. Convert the approved `DESIGN.md` tokens and frame-00 primitives into build-time Tailwind/theme and reusable typed components; preserve the high-density light shell, 280px desktop navigation, responsive diagnostic treatment, 48px enterprise rows, status/citation patterns, typography, and tonal elevation without shipping runtime Tailwind CDN or generated inline scripts.](./08-phase-frontend-integration/packets/01-integrate-approved-design-system.md)
2. [x] [Implement SSR Auth, audited MFA recovery/permission states, API-version handshake, typed API clients, query state, safe Bearer POST streaming, reconnect, and idempotency UX. Match frame 01's transactional sign-in and frame 03's gated owner setup where approved; fill the absent sign-up, reset/callback, MFA enrollment/challenge/lost-factor recovery, invitation/team entry, upload-MFA denial, and incompatible-client surfaces from real contracts rather than design mocks.](./08-phase-frontend-integration/packets/02-implement-auth-and-streaming.md)
3. [x] [Implement chat/test limitation diagnostics, citations/inferences, quota-aware document upload/status/quarantine, graph-blindness states, tables, and feedback. Preserve frame 04's Auto-first shell, route controls, pipeline/inference/scope/citation patterns and state-gallery families; frame 05's deterministic-versus-generated table separation; frames 06/07/09's document, attestation, quarantine, and chunk-review patterns; and frame 10's three-pane graph/evidence layout. Add every required BM25, deadline, temporal, figure/media, negation, summary, quota, version, backlog, fallback, Graph Pending, and authorized ACL-blindness state absent from Stitch.](./08-phase-frontend-integration/packets/03-implement-core-rag-surfaces.md)
4. [x] [Implement team, tools, alias/entity curation, usage, budgets, restricted read/download audit, profile, and company settings with server-enforced permissions. Preserve frame 14's usage/budget information hierarchy and degradation/critical-reserve patterns. Because the remaining administration surfaces have no delivered frame, derive them from `API_UI_MAPPING.md`, reuse approved primitives and shell patterns, and list the design gap in exit evidence.](./08-phase-frontend-integration/packets/04-implement-administration-surfaces.md)
5. [x] [Apply strict escaping, CSP/security headers, WCAG AA behavior, Arabic RTL/bidirectional text, keyboard navigation, responsive layouts, and generic production errors. Treat the lack of RTL/mobile-specific Stitch frames as missing design evidence, not a waiver: add reviewed Arabic/mixed-direction fixtures, logical citation highlighting, responsive breakpoints, focus/live-region behavior, reduced-motion behavior, and security tests while rejecting every prohibited generated-HTML pattern above.](./08-phase-frontend-integration/packets/05-apply-accessibility-and-security.md)
6. [x] [Run complete Playwright journeys for roles, routing/limitation families, reconnect, API/deploy versioning, fallbacks, table provenance, curation, and graph evidence. Add stable visual/interaction regression coverage keyed to each delivered frame surface, plus explicit journeys for delivered gallery states and required Stitch gaps including MFA recovery, API skew, BM25 degradation, rate limits, Graph Pending/ACL blindness, RTL citations, and restricted evidence audit.](./08-phase-frontend-integration/packets/06-run-frontend-verification.md)


Remediation packets P08-07 through P08-23 are additive. Do not uncheck packets 1-6. Frontend visual packets must also read [`08-phase-frontend-integration/00-visual-contract.md`](./08-phase-frontend-integration/00-visual-contract.md).

7. [x] [Canonical remediation amendment and baseline](./08-phase-frontend-integration/packets/07-canonical-remediation-amendment-and-baseline.md)
8. [x] [Restore query runtime connectivity and deterministic readiness](./08-phase-frontend-integration/packets/08-restore-query-runtime-connectivity-and-readiness.md)
9. [x] [Repair Phase 6 execution durability and verified answer delivery](./08-phase-frontend-integration/packets/09-repair-phase-6-execution-durability-and-verified-answers.md)
10. [x] [Harden the frontend chat protocol and recovery state](./08-phase-frontend-integration/packets/10-harden-frontend-chat-protocol-and-recovery.md)
11. [x] [Remove backend and database MFA/AAL2 enforcement](./08-phase-frontend-integration/packets/11-remove-backend-and-database-mfa-aal2-enforcement.md)
12. [x] [Remove frontend/provider MFA and finish single-factor Auth](./08-phase-frontend-integration/packets/12-remove-frontend-provider-mfa-and-finish-single-factor-auth.md)
13. [x] [Implement exact design tokens and reusable primitives](./08-phase-frontend-integration/packets/13-implement-exact-design-tokens-and-reusable-primitives.md)
14. [x] [Build the streamlined role-aware shell and routes](./08-phase-frontend-integration/packets/14-build-the-streamlined-role-aware-shell-and-routes.md)
15. [x] [Rebuild Ask around verified final answers](./08-phase-frontend-integration/packets/15-rebuild-ask-around-verified-final-answers.md)
16. [x] [Rebuild Documents as one complete ingestion workflow](./08-phase-frontend-integration/packets/16-rebuild-documents-as-one-complete-ingestion-workflow.md)
17. [x] [Rebuild deterministic Tables](./08-phase-frontend-integration/packets/17-rebuild-deterministic-tables.md)
18. [x] [Rebuild bounded Graph inspection](./08-phase-frontend-integration/packets/18-rebuild-bounded-graph-inspection.md)
19. [x] [Consolidate Admin and supported Account operations](./08-phase-frontend-integration/packets/19-consolidate-admin-and-supported-account-operations.md)
20. [x] [Enforce action, accessibility, security, and documentation integrity](./08-phase-frontend-integration/packets/20-enforce-action-accessibility-security-and-documentation-integrity.md)
21. [x] [Run deterministic release gates](./08-phase-frontend-integration/packets/21-run-deterministic-release-gates.md)
22. [ ] [Run production-like stack, role, visual, and real-answer verification](./08-phase-frontend-integration/packets/22-run-production-like-stack-role-visual-and-real-answer-verification.md)
23. [ ] [Final review, pull request, and normal merge](./08-phase-frontend-integration/packets/23-final-review-pull-request-and-normal-merge.md)

Packets P08-24 through P08-87 are additive after P08-07 through P08-23. Do not uncheck historical packets or renumber P08-22/P08-23. P08-22 remains blocked until the hosted diagnosis/repair packets and truthful progress/reveal proof pass.

24. [x] [Canonical streaming overhaul amendment and policy ADR](./08-phase-frontend-integration/packets/24-canonical-streaming-overhaul-amendment-and-policy-adr.md)
25. [ ] [Reject slash and encoded open-redirect forms at the auth callback](./08-phase-frontend-integration/packets/25-reject-slash-and-encoded-open-redirect-forms-at-the-auth-callback.md)
26. [ ] [Reproduce and classify the hosted P08-22 failures](./08-phase-frontend-integration/packets/26-reproduce-and-classify-the-hosted-p08-22-failures.md)
27. [ ] [Extract bound graph-node construction](./08-phase-frontend-integration/packets/27-extract-bound-graph-node-construction.md)
28. [ ] [Extract executor protocol and fixture](./08-phase-frontend-integration/packets/28-extract-executor-protocol-and-fixture.md)
29. [ ] [Extract LangGraph runtime and checkpointer setup](./08-phase-frontend-integration/packets/29-extract-langgraph-runtime-and-checkpointer-setup.md)
30. [ ] [Split executor lifecycle support](./08-phase-frontend-integration/packets/30-split-executor-lifecycle-support.md)
31. [ ] [Isolate the production LangGraph executor](./08-phase-frontend-integration/packets/31-isolate-the-production-langgraph-executor.md)
32. [ ] [Decompose the current SSE mapper](./08-phase-frontend-integration/packets/32-decompose-the-current-sse-mapper.md)
33. [ ] [Split stream attach and run orchestration](./08-phase-frontend-integration/packets/33-split-stream-attach-and-run-orchestration.md)
34. [ ] [Split persistence, append, replay, and cancel helpers](./08-phase-frontend-integration/packets/34-split-persistence-append-replay-and-cancel-helpers.md)
35. [ ] [Enforce stream-path architecture budgets](./08-phase-frontend-integration/packets/35-enforce-stream-path-architecture-budgets.md)
36. [ ] [Apply hosted migration parity without destructive reset](./08-phase-frontend-integration/packets/36-apply-hosted-migration-parity-without-destructive-reset.md)
37. [ ] [Finalize reservations with exactly-once durable usage settlement](./08-phase-frontend-integration/packets/37-finalize-reservations-with-exactly-once-durable-usage-settlement.md)
38. [ ] [Synchronize durable terminals with frontend run state](./08-phase-frontend-integration/packets/38-synchronize-durable-terminals-with-frontend-run-state.md)
39. [ ] [Align revoked-session contract and remove effect mirroring](./08-phase-frontend-integration/packets/39-align-revoked-session-contract-and-remove-effect-mirroring.md)
40. [ ] [Split frontend domain types into a compatibility barrel](./08-phase-frontend-integration/packets/40-split-frontend-domain-types-into-a-compatibility-barrel.md)
41. [ ] [Split API transport primitives without changing requests](./08-phase-frontend-integration/packets/41-split-api-transport-primitives-without-changing-requests.md)
42. [ ] [Split API domain modules into an exports-only barrel](./08-phase-frontend-integration/packets/42-split-api-domain-modules-into-an-exports-only-barrel.md)
43. [ ] [Extract citation drawer and chat query ownership](./08-phase-frontend-integration/packets/43-extract-citation-drawer-and-chat-query-ownership.md)
44. [ ] [Extract the single chat-run controller](./08-phase-frontend-integration/packets/44-extract-the-single-chat-run-controller.md)
45. [ ] [Make ChatApp composition-only and enforce frontend budgets](./08-phase-frontend-integration/packets/45-make-chatapp-composition-only-and-enforce-frontend-budgets.md)
46. [ ] [Isolate conversation-message cache by JWT subject](./08-phase-frontend-integration/packets/46-isolate-conversation-message-cache-by-jwt-subject.md)
47. [ ] [Classify resume failures and abort stale reconnect work](./08-phase-frontend-integration/packets/47-classify-resume-failures-and-abort-stale-reconnect-work.md)
48. [ ] [Add additive SSE progress catalog fields](./08-phase-frontend-integration/packets/48-add-additive-sse-progress-catalog-fields.md)
49. [ ] [Add the LangGraph v2 stream-part adapter](./08-phase-frontend-integration/packets/49-add-the-langgraph-v2-stream-part-adapter.md)
50. [ ] [Emit truthful node-start progress from bound wrappers](./08-phase-frontend-integration/packets/50-emit-truthful-node-start-progress-from-bound-wrappers.md)
51. [ ] [Report framework-neutral optional-tool progress](./08-phase-frontend-integration/packets/51-report-framework-neutral-optional-tool-progress.md)
52. [ ] [Map custom progress events in the decomposed SSE mapper](./08-phase-frontend-integration/packets/52-map-custom-progress-events-in-the-decomposed-sse-mapper.md)
53. [ ] [Dispatch production v2 updates and custom stream parts](./08-phase-frontend-integration/packets/53-dispatch-production-v2-updates-and-custom-stream-parts.md)
54. [ ] [Prove route-aware progress, replay, and leakage bounds](./08-phase-frontend-integration/packets/54-prove-route-aware-progress-replay-and-leakage-bounds.md)
55. [ ] [Reduce persisted events into a replay-safe progress timeline](./08-phase-frontend-integration/packets/55-reduce-persisted-events-into-a-replay-safe-progress-timeline.md)
56. [ ] [Render the truthful node and tool progress timeline](./08-phase-frontend-integration/packets/56-render-the-truthful-node-and-tool-progress-timeline.md)
57. [ ] [Reveal verified answers with a Unicode-safe presentation engine](./08-phase-frontend-integration/packets/57-reveal-verified-answers-with-a-unicode-safe-presentation-engine.md)
58. [ ] [Integrate paced verified-answer presentation without delaying protocol](./08-phase-frontend-integration/packets/58-integrate-paced-verified-answer-presentation-without-delaying-protocol.md)
59. [ ] [Pin conversation scroll only while the user stays at the bottom](./08-phase-frontend-integration/packets/59-pin-conversation-scroll-only-while-the-user-stays-at-the-bottom.md)
60. [ ] [Split pure table-plan logic into a compatibility barrel](./08-phase-frontend-integration/packets/60-split-pure-table-plan-logic-into-a-compatibility-barrel.md)
61. [ ] [Split AnalysisPlan presentation into focused sections](./08-phase-frontend-integration/packets/61-split-analysisplan-presentation-into-focused-sections.md)
62. [ ] [Extract shared auth, current-user, and idempotency owners](./08-phase-frontend-integration/packets/62-extract-shared-auth-current-user-and-idempotency-owners.md)
63. [ ] [Extract the document-library controller](./08-phase-frontend-integration/packets/63-extract-the-document-library-controller.md)
64. [ ] [Split curation ownership into glossary and entity-rule panels](./08-phase-frontend-integration/packets/64-split-curation-ownership-into-glossary-and-entity-rule-panels.md)
65. [ ] [Split auth screens into one form per file](./08-phase-frontend-integration/packets/65-split-auth-screens-into-one-form-per-file.md)
66. [ ] [Split UI controls and data-display CSS](./08-phase-frontend-integration/packets/66-split-ui-controls-and-data-display-css.md)
67. [ ] [Split overlay CSS and primitives](./08-phase-frontend-integration/packets/67-split-overlay-css-and-primitives.md)
68. [ ] [Split admin request builders](./08-phase-frontend-integration/packets/68-split-admin-request-builders.md)
69. [ ] [Split graph explorer controller](./08-phase-frontend-integration/packets/69-split-graph-explorer-controller.md)
70. [ ] [Split document detail and import tabs](./08-phase-frontend-integration/packets/70-split-document-detail-and-import-tabs.md)
71. [ ] [Coalesce stream publications without losing events](./08-phase-frontend-integration/packets/71-coalesce-stream-publications-without-losing-events.md)
72. [ ] [Deduplicate role-aware readiness polling](./08-phase-frontend-integration/packets/72-deduplicate-role-aware-readiness-polling.md)
73. [ ] [Enforce numeric render, publication, and request ceilings](./08-phase-frontend-integration/packets/73-enforce-numeric-render-publication-and-request-ceilings.md)
74. [ ] [Stabilize shell hydration and the 390px topbar](./08-phase-frontend-integration/packets/74-stabilize-shell-hydration-and-the-390px-topbar.md)
75. [ ] [Render truthful loading, error, and empty states](./08-phase-frontend-integration/packets/75-render-truthful-loading-error-and-empty-states.md)
76. [ ] [Fix session-list semantics and confirmable delete](./08-phase-frontend-integration/packets/76-fix-session-list-semantics-and-confirmable-delete.md)
77. [ ] [Bring drawer, command menu, and menu focus to parity](./08-phase-frontend-integration/packets/77-bring-drawer-command-menu-and-menu-focus-to-parity.md)
78. [ ] [Provide keyboard-equivalent graph selection](./08-phase-frontend-integration/packets/78-provide-keyboard-equivalent-graph-selection.md)
79. [ ] [Isolate load-earlier races and pagination errors](./08-phase-frontend-integration/packets/79-isolate-load-earlier-races-and-pagination-errors.md)
80. [ ] [Split chat CSS by extracted owner](./08-phase-frontend-integration/packets/80-split-chat-css-by-extracted-owner.md)
81. [ ] [Split shell and admin CSS owners](./08-phase-frontend-integration/packets/81-split-shell-and-admin-css-owners.md)
82. [ ] [Surface only catalog-backed diagnostics](./08-phase-frontend-integration/packets/82-surface-only-catalog-backed-diagnostics.md)
83. [ ] [Remove the framework disclosure header and document HSTS ownership](./08-phase-frontend-integration/packets/83-remove-the-framework-disclosure-header-and-document-hsts-ownership.md)
84. [ ] [Synchronize public streaming and progress documentation](./08-phase-frontend-integration/packets/84-synchronize-public-streaming-and-progress-documentation.md)
85. [ ] [Run deterministic contract and browser gates](./08-phase-frontend-integration/packets/85-run-deterministic-contract-and-browser-gates.md)
86. [ ] [Prove real Verifying progress on the hosted stack](./08-phase-frontend-integration/packets/86-prove-real-verifying-progress-on-the-hosted-stack.md)
87. [ ] [Repeat hosted production-like closure after repairs](./08-phase-frontend-integration/packets/87-repeat-hosted-production-like-closure-after-repairs.md)

Additive Phase 6/Phase 8 co-owned UI amendment: [P06-14](./06-phase-agent-intelligence/packets/14-chat-origin-ux.md) records answer-origin, clarification, and citation-safe Ask behavior. Additive Phase 6/Phase 8 co-owned streaming amendment: [P06-16](./06-phase-agent-intelligence/packets/16-sse-custom-progress.md) records custom node/tool progress and paced verified-answer presentation. Do not uncheck historical completed Phase 8 packets or renumber P08-22/P08-23.

## Phase sequence requirement

Phase 8 implements the approved Stitch output, auth, chat test bench, documents, graph explorer, tools, settings, accessibility, and E2E tests.

## Stop conditions

Stop this phase and report the blocker instead of improvising when:

- a prerequisite phase or required sign-off is incomplete;
- the actual repository contradicts the plan and the difference changes security, data, cost, or acceptance semantics;
- a required dependency contract cannot be verified from its pinned version and primary documentation;
- an authorization, idempotency, deadline, budget, provenance, or fallback test cannot exercise the real boundary;
- a required integration is unavailable and only a fake or skipped test would pass;
- any launch-blocking check fails after bounded repair attempts.

## Required exit record

Create or update [`docs/development/phase-08-frontend-integration-evidence.md`](../../../docs/development/phase-08-frontend-integration-evidence.md) with:

- plan requirement and work-packet number;
- files, migrations, APIs, environment variables, and documentation changed;
- exact verification commands discovered from the repository;
- test/build/lint/type/migration results and relevant measured metrics;
- authorization, failure, idempotency, fallback, and bounded-resource evidence;
- delivered-frame traceability is **not** required; record why each Stitch frame was not added as a route;
- unverified external assumptions or unavailable managed-environment checks;
- deviations, ADR approval, and rollback notes;
- explicit handoff inputs and open blockers for the next phase.

Do not set `status: complete` until every `Done when` item below is proven.

## Canonical detailed requirements

Detailed requirements are redistributed by link: the phase execution and template-not-layout contract is [`08-phase-frontend-integration/00-shared-contracts.md`](./08-phase-frontend-integration/00-shared-contracts.md), the visual brief is [`08-phase-frontend-integration/00-visual-contract.md`](./08-phase-frontend-integration/00-visual-contract.md), and canonical legacy Section 12 requirements are owned once in [`shared/frontend/stitch-nextjs-contract.md`](./shared/frontend/stitch-nextjs-contract.md). Phase 7 [`STITCH_REVIEW.md`](../../../docs/frontend/STITCH_REVIEW.md) round 2 supersedes packet titles that still mention Stitch frames: do not add those frames as screens. Remediation packets P08-07 through P08-23 are redistributed into packet files in this directory; P08-09 also amends Phase 6-owned durability/SSE contracts without unchecking completed Phase 6 packets. After P08-11 and P08-12 evidence pass, MFA/TOTP/AAL2 product requirements in the historical done gate are superseded by the approved complete-removal deviation. Additive packets P08-24 through P08-87 record the user-approved 2026-08-26 streaming/modularization overhaul; P08-24 and P06-16 supersede the P08-09/P08-15 updates-only and no-artificial-delay presentation rules without unchecking those completed packets.

## Phase deliver, review, and done gate

### Phase 8 — Frontend integration

- Deliver: production-quality Next.js implementation of the component-system fallback in `STITCH_REVIEW.md`, using only contract-mapped surfaces. Do not add Stitch template frames or missing-number placeholders.
- Review: approved token reconciliation; mapping coverage; no extra Stitch routes; usability; permissions; Arabic/bidirectional and mobile layout; version-mismatch behavior; BM25 projection/degradation behavior; citation logical offsets; limitation notices; and loading/failure behavior.
- Done when: the production Next.js build, strict types, lint, component tests, and accessibility checks pass; the implementation matches `STITCH_REVIEW.md` (no Stitch template routes; no Unavailable-gap pages); no prohibited generated-HTML pattern ships; real `@supabase/ssr` Auth covers sign-in/up, Google OAuth, reset/callback, invitation/owner setup, MFA enrollment/challenge plus audited lost-factor recovery/re-enrollment, disabled/revoked sessions, and upload-permission states with no client authorization shortcut; the startup/API handshake blocks unsupported clients before paid work and typed query/SSE clients tolerate additive unknown events while proving idempotent submission, sequenced reconnect, heartbeat, cancellation, route correction, deadline/partial/fallback/BM25-degraded/figure-temporal-ACL-summary-negation limitation states, citations, inference links, table provenance, diagnostics, feedback, and generic errors; document upload/URL approval, quota exceeded, abandoned/expired/oversize quarantine, scan, parse/OCR/media-only, BM25 projection, Hybrid/Graph readiness, backlog, retry, version, anomaly, and deletion journeys work; graph explorer, table analysis, tool/admin, alias/entity curation, team, usage/budget/rate, restricted read/download audit, profile, and company-settings surfaces enforce roles; responsive desktop/mobile LTR/RTL, mixed Arabic/English citation/highlight rendering, keyboard/focus/live-region/reduced-motion behavior, WCAG AA contrast, CSP/security headers, and strict text escaping pass; and Playwright covers auth/roles/MFA recovery, upload quota/crawl, direct/current-relationship/historical-relationship/broad/full-summary-pass-or-refusal/negation/media/comparison/table/composite routing, BM25 projection/outage, version switchover/API skew, manual diagnostics, partial readiness/authorized ACL graph blindness with unauthorized silence, graph inspection/mapping evidence, mixed-direction citations/inferences, private run ownership, LightRAG fallback, rate limits, reconnect/idempotency, curation, and deletion with no mock data, test-auth bypass, `dangerouslySetInnerHTML`, or unescaped retrieved markup.
