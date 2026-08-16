---
title: Stitch review and component-system fallback
owner: engineering-lead
status: draft
last-reviewed: 2026-08-17
audience: frontend, reviewers, client-approver
packet: P07-06
---

# Stitch review and Phase 8 handoff

Bounded review for Phase 7. Google Stitch generation is user-run. This
record selects the **component-system fallback** so Phase 8 has one
implementation input and does not restart design generation.

Related: [STITCH_BRIEF.md](./STITCH_BRIEF.md) ·
[STITCH_STATES.md](./STITCH_STATES.md) ·
[STITCH_A11Y_SECURITY.md](./STITCH_A11Y_SECURITY.md) ·
[API_UI_MAPPING.md](./API_UI_MAPPING.md) ·
[phase-07 evidence](../development/phase-07-stitch-specification-evidence.md) ·
[docs index](../README.md)

## Review window

| Field | Value |
| --- | --- |
| Opened | 2026-08-17 |
| Timebox | five business days / two revision rounds |
| Hard close | 2026-08-17 (same day) |
| Rounds used | 0 of 2 |
| Approver | user (Cursor chat; no legal name provided) |
| Instruction | implement the whole phase, do not stop, expert disposition of missing Stitch export |
| Stitch references accepted | **none** |
| Fallback selected | **yes** — accessible native HTML + brief tokens |

`docs/stitch_smart_rag_enterprise_console/` is excluded from docs checks and
is **not** an approved implementable accessible export
([QUALITY_COMMANDS.md](../development/QUALITY_COMMANDS.md)). Bundle presence
is not approval.

A third revision round is forbidden. Open-ended waiting is forbidden.

## Why fallback, not Stitch export

1. No reviewed accessible Stitch frames were delivered in this window.
2. Historical HTML exports are not current evidence and must not be ported.
3. [API_UI_MAPPING.md](./API_UI_MAPPING.md) already binds every control to
   Auth/API/SSE or a GAP. Generated mock diagnostics would violate that map.
4. [STITCH_A11Y_SECURITY.md](./STITCH_A11Y_SECURITY.md) A11Y-01: missing
   frames are not a WCAG waiver; fallback primitives must meet that review.

## Selected fallback primitives

Phase 8 implements `apps/frontend` with:

| Piece | Choice |
| --- | --- |
| Framework | Next.js App Router 16.3, React 19, TypeScript strict (already pinned) |
| Server state | TanStack Query 5.85.5 |
| Auth | `@supabase/ssr` 0.7.0 browser client; Bearer to FastAPI |
| Styling | CSS variables from the brief token table; optional **build-time** Tailwind that compiles those tokens. **No** runtime Tailwind CDN |
| Components | native `button`, `dialog`, `textarea`, `table`, `details`; no required animation |
| Graph | search + list first; optional SVG later; no vendor canvas HTML |
| Text | React text nodes; `displayText`; `isSafeHttpUrl`; no retrieved `dangerouslySetInnerHTML` |
| Blur | rejected |

Do not copy Stitch `code.html`. Do not keep mock data. Do not replace server
403/404 with client-only guards.

## Localization and tokens (frozen)

- English chrome; Arabic/mixed **content** with `dir="auto"` isolate.
- Token table in [STITCH_BRIEF.md](./STITCH_BRIEF.md) is canonical.
- GAP-07-19 blocks Arabic chrome until `GET /me` grows a locale.

## Gap dispositions for Phase 8

| ID | Phase 8 behavior |
| --- | --- |
| GAP-07-01 | Advanced panel read-only |
| GAP-07-02 | SSE catalog only |
| GAP-07-03–06, 15–18 | Implement Auth-direct / existing FastAPI UI |
| GAP-07-04 | Disabled Google button until provider enabled |
| GAP-07-07, 08, 09, 10, 11, 12, 13, 14, 19 | Honest Unavailable; do not mock |
| GAP-07-20 | Do not claim FastAPI throttles login |

Blocking for Phase 8 start: **none** that prevent implementing available
contracts. Blocking for those Unavailable screens: owning-phase HTTP.

## Phase 8 handoff artifacts

| Artifact | Role |
| --- | --- |
| `docs/frontend/STITCH_BRIEF.md` | prompts, tokens, fixtures |
| `docs/frontend/STITCH_STATES.md` | state matrix |
| `docs/frontend/STITCH_A11Y_SECURITY.md` | a11y/security |
| `docs/frontend/API_UI_MAPPING.md` | typed map + gaps |
| this file | fallback selection |

Phase 8 must not recreate these documents.

## Rejected approvals

- Approval by visual appeal or unmapped frames
- Inaccessible exports
- Conflicting tokens or blur
- Mock-dependent interactions
- Indefinite wait for Google Stitch

## Rollback

Delete this review file and reopen a five-day Stitch window only with an
explicit user instruction. Do not un-check packets 1–5.
