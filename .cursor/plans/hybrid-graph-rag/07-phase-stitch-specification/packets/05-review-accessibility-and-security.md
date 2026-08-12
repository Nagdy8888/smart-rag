---
phase: 7
packet: 5
status: pending
title: "Review accessibility, RTL keyboard/focus behavior, mobile layouts, mixed-direction citation/highlight interactions, safe text rendering, and security boundaries."
requirement_ids: [P07-05]
---

# Packet 5 — Review accessibility, RTL keyboard/focus behavior, mobile layouts, mixed-direction citation/highlight interactions, safe text rendering, and security boundaries.

Read the [Phase 7 shared contracts](../00-shared-contracts.md) and [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

- `P07-01` through `P07-04` have complete screens, states, and real contract mappings.
- Localization, token, and responsive-frame decisions are recorded.
- Representative Arabic/mixed-direction and hostile-text fixtures exist.

## Allowed outputs

- Reviewed accessibility, responsive, RTL/bidi, safe-rendering, and security requirements in Phase 7 documents.
- Documented defects/gaps and evidence; revised specification copy or frames.

## Forbidden outputs

- Accessibility waivers based on missing generated frames.
- Raw retrieved HTML, unsafe rich-content assumptions, client-only authorization, or privileged client secrets.
- Unreviewed visual-order citation offsets or LTR-only keyboard/focus behavior.

## Ordered actions

1. Review keyboard-only flow, directional focus order, focus/error states, accessible names, status/live-region announcements, reduced motion, and WCAG AA contrast.
2. Review desktop/mobile layouts and overflow for every critical auth, chat, document, graph, table, and administration flow.
3. Test Arabic-primary RTL and mixed-direction fixtures, bidi isolation, LTR codes/URLs, punctuation, diacritics, IME/caret behavior, and logical citation/highlight offsets.
4. Specify strict framework escaping for every document/entity/relation/tool/filename/citation/table/model string and prohibit retrieved-content `dangerouslySetInnerHTML`.
5. Review CSP/security headers, generic production errors, source URL handling, forged-role denial, authorization leakage, and production test-auth exclusion.

## Acceptance checks

- Equivalent tasks are specified for keyboard, mobile, LTR, and RTL use.
- Citation/highlight ranges stay tied to canonical logical text and remain usable with mixed scripts.
- Screen-reader announcements distinguish streaming, reconnect, partial, refusal, limitation, degraded, and terminal states without noise.
- Security boundaries rely on real server enforcement and all untrusted text is safely rendered.

## Negative tests

- Include hostile markup in filenames, snippets, entity/relation labels, citations, tools, table cells, and answer text.
- Include narrow screens, 200% zoom, long Arabic/English strings, long URLs/codes, keyboard-only dialogs/drawers, and reduced-motion preference.
- Attempt forged admin actions, unauthorized source access, diagnostic leakage, raw error display, and test-auth use.

## Stop routes

- Stop approval for WCAG AA, keyboard/focus, RTL logical-offset, unsafe rendering, CSP, or authorization failures.
- Record missing mobile/RTL design evidence as a required gap; it is not a waiver.

## Required evidence

Append `P07-05` proof to [`docs/development/phase-07-stitch-specification-evidence.md`](../../../../../docs/development/phase-07-stitch-specification-evidence.md): accessibility review, responsive/RTL fixtures, logical-offset results, XSS/security scenarios, defects and dispositions, and commands/tools used.
