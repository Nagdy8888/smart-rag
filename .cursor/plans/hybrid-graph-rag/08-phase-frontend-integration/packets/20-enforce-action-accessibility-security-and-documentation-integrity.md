---
phase: 8
packet: 20
status: pending
title: "Enforce action, accessibility, security, and documentation integrity"
requirement_ids: [P08-20]
---

# Packet 20 — Enforce action, accessibility, security, and documentation integrity

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-13 through P08-19 surfaces and final file paths exist.

## Allowed outputs

Action inventory check, geometry contracts, rendered-route audit, a11y/bidi/CSP, dead-code removal, doc sync.

## Forbidden outputs

Removing still-referenced code. Weakening CSP. Leaving old source paths.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-20 — Enforce action, accessibility, security, and documentation integrity

Purpose: apply the cross-cutting quality contract after all final surfaces and paths exist.

Primary files:

- [`docs/frontend/action-inventory.json`](docs/frontend/action-inventory.json)
- frontend tests/CI checks, global/component styles, CSP/security configuration, maintained frontend docs, and Phase 8 evidence.

Implementation:

- Add a repository check for unique `data-action-id` values and matching inventory entries. Recognize submits, links, and local-state actions without a fragile all-buttons regex.
- Add computed-style contracts for representative buttons, inputs, cards, pills, dialogs, nav, topbar, and table rows at required viewports.
- Add a rendered-route audit for permanent-disabled buttons, empty/hash links, unnamed controls, and unresolved GAP copy.
- Require every shipped inventory action to name a positive and applicable failure/authorization test.
- Enforce WCAG AA, visible focus, landmarks/headings, mobile targets, focus trap/return, Escape, arrow-key tabs/lists, live-region discipline, and reduced motion.
- Test 390px, 768px, 1024px, and 1280px with no page-level overflow.
- Apply `dir="auto"` and bidi isolation to messages, filenames, entities, citations, URLs, codes, cells, and errors.
- Preserve CSP, bundled fonts/icons, strict escaping, safe URL allow-listing, no `dangerouslySetInnerHTML`, and no trace leakage.
- Remove dead components/styles/helpers/tests only after reference search.
- Update API/UI mapping, Stitch review, design/admin/chat/document docs, docs index, Phase 6 evidence for P08-09, and Phase 8 evidence.

Acceptance tests:

- Action integrity passes with zero unmapped visible actions.
- Accessibility, hostile text, XSS, CSP, bidi, responsive, reduced-motion, and geometry suites pass.
- No dead page, duplicate component, old source path, permanent-disabled control, placeholder copy, or unowned visible field remains.
- Documentation links and Mermaid checks pass.

## Acceptance checks

Zero unmapped visible actions. Accessibility/XSS/CSP/bidi/responsive suites pass. Docs links and Mermaid validate.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop on unmapped actions or unresolved GAP copy. Do not snapshot-approve security defects.

## Required evidence

Append `P08-20` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
