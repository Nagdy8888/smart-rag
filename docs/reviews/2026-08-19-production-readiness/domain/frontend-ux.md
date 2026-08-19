---
title: Domain review — frontend and UX
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: frontend, design, security
reviewed_commit: 09a102a
---

# Domain: frontend and UX

Canonical findings: [high](../02-high.md) H-002 H-009 H-021 · [medium](../03-medium.md) M-006 M-010 M-014 M-025 M-026 · [low](../04-low.md) L-001 L-003 L-004 L-011 L-013.

## Scorecard

| Journey | Rating | Notes |
| --- | --- | --- |
| Sign-in / MFA / session revoked | Strong chrome, no recovery HTTP | Dedicated copy; GAP-07-07 (H-026) |
| Auto chat + SSE | Console-shaped | Cancel aborts the reader; admit/resume fetch has no `signal` (H-021) |
| Citations | Strong safety, fixture preview | Drawer has no privileged href; live highlight is the ACME fixture (M-026) |
| Limitations | Strong | Locked codes in journey matrix; LimitationCallout |
| Documents / upload | Good | Viewer hide + server deny; MFA on upload |
| Graph explorer | Safe, visually weak | Caps; pending vs ACL blindness split |
| Tables | Present | Structured-table surface exists |
| Team / tools / usage | Chrome gated by role helpers | Server remains source of truth |
| RTL / Arabic chrome | Weak | `lang=en dir=ltr` root |
| Mobile | Unknown | 280px nav contract; not a phone-first app |
| CSP | Weak for production | localhost + unsafe-inline |

## What is excellent

- Hostile-text fixtures and `UserText` `dir="auto"` / `unicode-bidi: isolate`.
- Prohibited `dangerouslySetInnerHTML`.
- Handshake blocks paid POST when API/client disagree or mock not query-ready.
- Generic production error copy (`GENERIC_PRODUCTION_ERROR`) instead of raw exception text.
- Playwright + Vitest journey matrix keyed to real surfaces, not Stitch frame numbers.
- Graph inspect refuses unauthorized titles.

## UX production gaps (not all blockers)

1. **English LTR shell** for an Arabic-capable retriever (H-009).
2. **Metadata claims "Production"** (L-001).
3. **Graph vis is a circle grid** (M-006) — prefer list-first and say so in UI copy.
4. **Long Combined runs** — heartbeats exist; user needs route-specific progress ("reranking", "verifying") from SSE event types. Confirm chat-app maps those events, not only tokens.
5. **Limitation fatigue** — many locked codes; keep them, but write one human sentence each (partially done in `limitations.ts`).
6. **Vercel env** — `NEXT_PUBLIC_` must stay non-secret; connect-src must not ship localhost (H-002).

## Ship vs polish vs blocker

| Item | Bucket |
| --- | --- |
| CSP localhost / unsafe-inline | Blocker for internet |
| RTL chrome | Blocker if Arabic-primary company |
| Stitch density / developer CSS names | Polish |
| Graph SVG | Polish |
| Session revoke + MFA copy | Ship (already) |
| Citation XSS | Ship (already) |
