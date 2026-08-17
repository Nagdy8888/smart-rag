---
title: Stitch review and component-system fallback
owner: engineering-lead
status: draft
last-reviewed: 2026-08-17
audience: frontend, reviewers, client-approver
packet: P07-06
---

# Stitch review and Phase 8 handoff

Bounded review for Phase 7. The user delivered a Stitch export under
`docs/stitch_smart_rag_enterprise_console/` (gitignored; not a CI docs
target). Round 2 (user): **it is a template, not a layout for us; if a
frame is not necessary, do not add it.**

Production implementation is the **component-system fallback**. Do not
port `code.html`. Do not add Stitch frames as product routes, pages, or
IA. Do not fill missing Stitch numbers 02/08/11/12/13 with extra screens.

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
| Round 1 | 2026-08-17 — user delivered the bundle |
| Round 2 | 2026-08-17 — template, not layout; do not add unnecessary frames |
| Rounds used | 2 of 2 |
| Approver | user (Cursor chat; no legal name provided) |
| Stitch HTML accepted as production | **no** |
| Stitch accepted as product layout | **no** |
| Stitch frames added as routes | **none** |
| Implementation | **component-system fallback** (native HTML + brief tokens) |

A third revision round is forbidden. Open-ended waiting is forbidden.
Bundle presence alone is not production approval.

## What Phase 8 ships (contracts, not Stitch)

Ship a screen only when [API_UI_MAPPING.md](./API_UI_MAPPING.md) has a
typed owner. Compose upload on the library, table results on `/tables` or
in chat, and 426/402/429 on the chat banner — do not add extra Stitch
pages for those.

| Surface | Ship? | Why |
| --- | --- | --- |
| Sign in (email/password) | yes | Auth-direct; Phase 6 thin UI |
| Sign up, forgot/reset, `/auth/callback` | yes | Auth-direct (GAP-07-03/05); not a Stitch frame |
| MFA enroll/challenge + MFA-required banner | yes | Auth-direct (GAP-07-06); recovery stays Unavailable |
| Chat Auto, conversations, citations, feedback | yes | FastAPI + SSE catalog |
| Document library + upload/crawl/status | yes | FastAPI; one library surface, not a separate Stitch ingest wizard |
| Document detail (metadata + ingestion status) | yes | `GET /documents/{id}`; no audit/PII/source tabs |
| Graph search/inspect | yes | FastAPI; list-first; hop cap 3 |
| Structured tables | yes | `GET /tables`, `POST /tables/analyze` |
| Tools, glossary, entity rules | yes | FastAPI; simple catalog/admin, not a Stitch frame 11 |
| Invitations + offboard | yes | FastAPI; no owner-bootstrap wizard |
| Usage `/usage/me` and `/usage/company` | yes | totals only |
| Profile | read-only `GET /me` | five fields; no editor |
| Google OAuth button | disabled until enabled | GAP-07-04 |

## Do not add (template or gap)

| Item | Why not |
| --- | --- |
| Design-system page (`frame_00`) | template primitives, not a product route |
| Chat state gallery (`frame_04_chat_state_gallery`) | template; states live on real chat |
| Stitch Combined/Hybrid send chrome | GAP-07-01; Auto only |
| Stitch nDCG/TTFB/confidence drawers | GAP-07-02 |
| Owner-setup wizard (`frame_03` extras) | GAP-07-08; invites/offboard only |
| Dedicated Stitch upload-flow page | upload belongs on the library |
| Audit / PII / source-preview tabs | GAP-07-12 / GAP-07-09 |
| Graph Edit Relationship / depth 5 | no HTTP; inspect max depth 3 |
| Budget sliders, Slack, hard-cap editor | GAP-07-11 |
| Company settings page | GAP-07-13 |
| MFA recovery page | GAP-07-07 |
| Document delete control | GAP-07-14 |
| Profile name/locale editor | GAP-07-19 |
| Placeholder pages for Stitch 02/08/11/12/13 | numbering is not product IA |
| RTL chrome layout from Stitch | none delivered; `dir="auto"` on content still required |

The gitignored export may stay on disk as an unused template. Phase 8 must
not import it.

## Round-1 defects still forbidden

| Defect | Disposition |
| --- | --- |
| Tailwind CDN, Google Fonts, Material Symbols | not in production |
| Inline `<script>` / `innerHTML` / `href="#"` | not in production |
| Glass blur | rejected |
| Mock users/docs/costs | replace with live contracts only on shipped surfaces |

## Why fallback owns implementation

1. The export is a template, not our layout.
2. HTML is not accessible, CSP-safe, or typed.
3. [API_UI_MAPPING.md](./API_UI_MAPPING.md) is the screen list.
4. Tokens stay as frozen in [STITCH_BRIEF.md](./STITCH_BRIEF.md)
   (accent `#2563EB`, canvas `#F8FAFC`, radius 8px, no blur).

## Selected fallback primitives

Phase 8 implements `apps/frontend` with:

| Piece | Choice |
| --- | --- |
| Framework | Next.js App Router 16.3, React 19, TypeScript strict (already pinned) |
| Server state | TanStack Query 5.85.5 |
| Auth | `@supabase/ssr` 0.7.0 browser client; Bearer to FastAPI |
| Visual intent | brief tokens + native hierarchy; **not** Stitch frame layout |
| Styling | CSS variables from the brief token table; optional **build-time** Tailwind. **No** runtime Tailwind CDN |
| Components | native `button`, `dialog`, `textarea`, `table`, `details`; no required animation |
| Graph | search + list first; optional SVG later; hop cap 3 |
| Text | React text nodes; `displayText`; `isSafeHttpUrl`; no retrieved `dangerouslySetInnerHTML` |
| Blur | rejected |

Do not copy Stitch `code.html`. Do not keep mock data. Do not replace server
403/404 with client-only guards.

## Localization and tokens

- English chrome; Arabic/mixed **content** with `dir="auto"` isolate.
- Token table in [STITCH_BRIEF.md](./STITCH_BRIEF.md) is canonical.
- GAP-07-19 blocks Arabic chrome until `GET /me` grows a locale.

## Gap dispositions for Phase 8

| ID | Phase 8 behavior |
| --- | --- |
| GAP-07-01 | no extra route-send UI |
| GAP-07-02 | SSE catalog only |
| GAP-07-03, 05, 06, 15–18 | implement because Auth/FastAPI exist, with simple native UI |
| GAP-07-04 | disabled Google button until provider enabled |
| GAP-07-07, 08, 09, 10, 11, 12, 13, 14, 19 | do not add a page or control |
| GAP-07-20 | do not claim FastAPI throttles login |

## Phase 8 handoff artifacts

| Artifact | Role |
| --- | --- |
| `docs/frontend/STITCH_BRIEF.md` | prompts, tokens, fixtures (specification, not Stitch IA) |
| `docs/frontend/STITCH_STATES.md` | state matrix on shipped surfaces |
| `docs/frontend/STITCH_A11Y_SECURITY.md` | a11y/security |
| `docs/frontend/API_UI_MAPPING.md` | typed map + gaps = screen list |
| this file | template discarded as layout; fallback |

Phase 8 must not recreate the specification documents, restart Stitch, or
add Stitch frames.

## Rejected approvals

- Approval by visual appeal or unmapped frames
- Treating the template as product layout
- Adding unnecessary Stitch frames or missing-number placeholders
- Treating CDN HTML as production
- Inaccessible exports as a WCAG waiver
- Conflicting tokens or blur
- Mock-dependent interactions
- Indefinite wait for another Stitch round

## Rollback

Revert this round-2 section only with an explicit user instruction. Do not
un-check packets 1–5.
