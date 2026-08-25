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

7. [ ] [Canonical remediation amendment and baseline](./08-phase-frontend-integration/packets/07-canonical-remediation-amendment-and-baseline.md)
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

Additive Phase 6/Phase 8 co-owned UI amendment: [P06-14](./06-phase-agent-intelligence/packets/14-chat-origin-ux.md) records answer-origin, clarification, and citation-safe Ask behavior. Do not uncheck historical completed Phase 8 packets or renumber P08-22/P08-23.

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

Detailed requirements are redistributed by link: the phase execution and template-not-layout contract is [`08-phase-frontend-integration/00-shared-contracts.md`](./08-phase-frontend-integration/00-shared-contracts.md), the visual brief is [`08-phase-frontend-integration/00-visual-contract.md`](./08-phase-frontend-integration/00-visual-contract.md), and canonical legacy Section 12 requirements are owned once in [`shared/frontend/stitch-nextjs-contract.md`](./shared/frontend/stitch-nextjs-contract.md). Phase 7 [`STITCH_REVIEW.md`](../../../docs/frontend/STITCH_REVIEW.md) round 2 supersedes packet titles that still mention Stitch frames: do not add those frames as screens. Remediation packets P08-07 through P08-23 are redistributed into packet files in this directory; P08-09 also amends Phase 6-owned durability/SSE contracts without unchecking completed Phase 6 packets. After P08-11 and P08-12 evidence pass, MFA/TOTP/AAL2 product requirements in the historical done gate are superseded by the approved complete-removal deviation.

## Phase deliver, review, and done gate

### Phase 8 — Frontend integration

- Deliver: production-quality Next.js implementation of the component-system fallback in `STITCH_REVIEW.md`, using only contract-mapped surfaces. Do not add Stitch template frames or missing-number placeholders.
- Review: approved token reconciliation; mapping coverage; no extra Stitch routes; usability; permissions; Arabic/bidirectional and mobile layout; version-mismatch behavior; BM25 projection/degradation behavior; citation logical offsets; limitation notices; and loading/failure behavior.
- Done when: the production Next.js build, strict types, lint, component tests, and accessibility checks pass; the implementation matches `STITCH_REVIEW.md` (no Stitch template routes; no Unavailable-gap pages); no prohibited generated-HTML pattern ships; real `@supabase/ssr` Auth covers sign-in/up, Google OAuth, reset/callback, invitation/owner setup, MFA enrollment/challenge plus audited lost-factor recovery/re-enrollment, disabled/revoked sessions, and upload-permission states with no client authorization shortcut; the startup/API handshake blocks unsupported clients before paid work and typed query/SSE clients tolerate additive unknown events while proving idempotent submission, sequenced reconnect, heartbeat, cancellation, route correction, deadline/partial/fallback/BM25-degraded/figure-temporal-ACL-summary-negation limitation states, citations, inference links, table provenance, diagnostics, feedback, and generic errors; document upload/URL approval, quota exceeded, abandoned/expired/oversize quarantine, scan, parse/OCR/media-only, BM25 projection, Hybrid/Graph readiness, backlog, retry, version, anomaly, and deletion journeys work; graph explorer, table analysis, tool/admin, alias/entity curation, team, usage/budget/rate, restricted read/download audit, profile, and company-settings surfaces enforce roles; responsive desktop/mobile LTR/RTL, mixed Arabic/English citation/highlight rendering, keyboard/focus/live-region/reduced-motion behavior, WCAG AA contrast, CSP/security headers, and strict text escaping pass; and Playwright covers auth/roles/MFA recovery, upload quota/crawl, direct/current-relationship/historical-relationship/broad/full-summary-pass-or-refusal/negation/media/comparison/table/composite routing, BM25 projection/outage, version switchover/API skew, manual diagnostics, partial readiness/authorized ACL graph blindness with unauthorized silence, graph inspection/mapping evidence, mixed-direction citations/inferences, private run ownership, LightRAG fallback, rate limits, reconnect/idempotency, curation, and deletion with no mock data, test-auth bypass, `dangerouslySetInnerHTML`, or unescaped retrieved markup.
