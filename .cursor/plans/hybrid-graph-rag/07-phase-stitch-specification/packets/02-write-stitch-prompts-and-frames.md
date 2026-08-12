---
phase: 7
packet: 2
status: pending
title: "Write copy-ready Stitch prompts, responsive LTR/RTL frames, Arabic/bidirectional behavior, information hierarchy, component inventory, localization decision, and design tokens."
requirement_ids: [P07-02]
---

# Packet 2 — Write copy-ready Stitch prompts, responsive LTR/RTL frames, Arabic/bidirectional behavior, information hierarchy, component inventory, localization decision, and design tokens.

Read the [Phase 7 shared contracts](../00-shared-contracts.md) and [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

- `P07-01` has a verified contract inventory and unresolved-gap list.
- The Phase 6 thin UI and delivered Stitch references are available for comparison.
- No unresolved contract gap makes a requested screen materially fictional.

## Allowed outputs

- `docs/frontend/STITCH_BRIEF.md` with copy-ready prompts, frames, fixtures, hierarchy, components, copy, and tokens.
- Token/localization decision records and Phase 7 evidence.

## Forbidden outputs

- Production React/Next.js implementation, generated HTML porting, or backend redesign.
- Invented controls, diagnostics, data, endpoints, or success states.
- Silent selection among conflicting palette, radius, elevation, typography, spacing, or blur guidance.

## Ordered actions

1. Write copy-ready prompts for every canonical auth, team, chat/diagnostic, document, graph, table, tool/curation, usage/audit, profile, and company-settings surface.
2. Define desktop/mobile LTR and RTL frames, information hierarchy, reusable component inventory, status/citation patterns, and responsive diagnostic behavior.
3. Record whether v1 uses Arabic chrome or English chrome with Arabic content support; specify `dir="rtl"`, `dir="auto"`, and safe bidi isolation behavior.
4. Add concrete mixed Arabic/English, LTR code/URL, punctuation, citation/highlight, diacritic, IME/caret, overflow, keyboard, and focus examples.
5. Reconcile `DESIGN.md`, frame values, and prose into one canonical token set, explicitly retaining or rejecting blur.

## Acceptance checks

- Prompts are copy-ready and cover every canonical surface without mock behavior.
- LTR/RTL and mobile/desktop frames show equivalent task completion and diagnostic readability.
- Localization, direction, logical text-offset, typography, and overflow decisions are unambiguous.
- Components and tokens are reusable by both accepted Stitch references and the fallback system.

## Negative tests

- Review prompts for invented API fields, unauthorized diagnostics, leaked source metadata, fake quotas/readiness, and graph-only answer behavior.
- Test fixtures with mixed scripts, long codes/URLs, diacritics, narrow viewports, and logical citation ranges.
- Reject runtime Tailwind CDN, inline-script, random-data, external-placeholder, and prohibited blur assumptions.

## Stop routes

- Stop when the contract inventory cannot support a requested interaction or conflicting token/localization decisions lack an approver.
- Record the gap or decision blocker; do not conceal it in design copy.

## Required evidence

Append `P07-02` proof to [`docs/development/phase-07-stitch-specification-evidence.md`](../../../../../docs/development/phase-07-stitch-specification-evidence.md): prompt/screen coverage, token reconciliation, localization decision, reviewed fixtures, responsive/RTL checks, unresolved gaps, and changed artifacts.
