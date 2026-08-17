---
phase: 8
packet: 5
status: complete
title: "Apply strict escaping, CSP/security headers, WCAG AA behavior, Arabic RTL/bidirectional text, keyboard navigation, responsive layouts, and generic production errors. Treat the lack of RTL/mobile-specific Stitch frames as missing design evidence, not a waiver: add reviewed Arabic/mixed-direction fixtures, logical citation highlighting, responsive breakpoints, focus/live-region behavior, reduced-motion behavior, and security tests while rejecting every prohibited generated-HTML pattern above."
requirement_ids: [P08-05]
---

# Packet 5 — Apply strict escaping, CSP/security headers, WCAG AA behavior, Arabic RTL/bidirectional text, keyboard navigation, responsive layouts, and generic production errors. Treat the lack of RTL/mobile-specific Stitch frames as missing design evidence, not a waiver: add reviewed Arabic/mixed-direction fixtures, logical citation highlighting, responsive breakpoints, focus/live-region behavior, reduced-motion behavior, and security tests while rejecting every prohibited generated-HTML pattern above.

Read the [Phase 8 shared contracts](../00-shared-contracts.md) and [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

- `P08-01` through `P08-04` implement all production surfaces.
- Approved localization, bidi, token, CSP, and accessibility decisions are available.
- Arabic/mixed-direction, mobile, keyboard, reduced-motion, and hostile-text fixtures are defined.

## Allowed outputs

- Cross-cutting accessibility, responsive, bidi, escaping, CSP/header, generic-error, and security changes in the frontend.
- Reviewed RTL/mobile gap designs, tests, and evidence.

## Forbidden outputs

- Any prohibited production pattern in the Phase 8 shared contract.
- `dangerouslySetInnerHTML` for retrieved content, unsafe markup, visual-order citation offsets, client-only authorization, or production test-auth bypass.
- Accessibility, RTL, or mobile waivers based on missing Stitch frames.

## Ordered actions

1. Apply strict framework escaping to every untrusted filename, document, snippet, citation, entity, relation, tool, table, and model string.
2. Configure CSP/security headers, approved local/hosted assets, safe navigation, sanitized telemetry, and generic production errors.
3. Implement the approved RTL layout and `dir="auto"`/bidi isolation for messages, evidence, citations, entities, codes, URLs, and source snippets.
4. Keep citation/highlight offsets tied to canonical logical text; test punctuation, diacritics, IME/caret, long URLs/codes, and mixed scripts.
5. Complete keyboard/focus order, visible focus/error states, live regions, reduced motion, accessible names, WCAG AA contrast, responsive breakpoints, overflow, and mobile navigation/dialogs.
6. Review and evidence primitive-based RTL/mobile gap fills on every critical surface; scan out all prohibited generated patterns.

## Acceptance checks

- XSS fixtures render as inert text and CSP/security-header tests pass.
- Desktop/mobile LTR/RTL tasks are complete at required breakpoints and zoom, with correct logical citation interaction.
- Keyboard, focus, live-region, reduced-motion, and WCAG AA checks pass across auth, chat, documents, graph, tables, and administration.
- Errors are generic in production while retaining safe recovery and correlation behavior.
- No runtime Tailwind CDN, inline handler/script, `innerHTML`, mock/random auth, placeholder link, third-party avatar, static live diagnostic, CSP-violating dependency, demo data, dead link, unsafe markup, or test bypass remains.

## Negative tests

- Inject hostile HTML/script/URL/bidi-control payloads into every untrusted content class and verify inert rendering.
- Test keyboard-only use, 200% zoom, narrow mobile widths, Arabic-primary RTL, mixed Arabic/English, long codes/URLs, screen-reader announcements, and reduced motion.
- Forge permissions, request unauthorized sources, trigger internal/provider errors, and attempt CSP violations.
- Run repository scans for every prohibited generated-HTML pattern.

## Stop routes

- Treat any escaping, CSP, authorization, WCAG AA, keyboard/focus, logical-offset, RTL, or mobile critical failure as blocking.
- Return unimplementable localization/mapping or server-security gaps to their owner; do not waive them.

## Required evidence

Append `P08-05` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): RTL/mobile gap designs, bidi/logical-offset fixtures, accessibility results, CSP/header and XSS tests, prohibited-pattern scan, generic-error proof, defects/dispositions, and changed paths.
