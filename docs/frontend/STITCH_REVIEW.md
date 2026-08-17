---
title: Stitch review and component-system fallback
owner: engineering-lead
status: draft
last-reviewed: 2026-08-17
audience: frontend, reviewers, client-approver
packet: P07-06
---

# Stitch review and Phase 8 handoff

Bounded review for Phase 7. On 2026-08-17 the user delivered the Stitch
export under `docs/stitch_smart_rag_enterprise_console/` (gitignored; not
a CI docs target). Round 1 accepts those frames as **visual and
interaction references only**. Production implementation remains the
**component-system fallback**. Do not port `code.html`.

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
| Round 1 | 2026-08-17 — user delivered the bundle (`here you are`) |
| Rounds used | 1 of 2 |
| Approver | user (Cursor chat; no legal name provided) |
| Stitch HTML accepted as production | **no** |
| Stitch frames accepted as visual references | **yes** — table below |
| Implementation | **component-system fallback** (native HTML + brief tokens) |

A third revision round is forbidden. Open-ended waiting is forbidden.
Bundle presence alone is not production approval.

## Delivered frames (visual reference)

Paths are relative to `docs/stitch_smart_rag_enterprise_console/`. Files
are gitignored; do not add Markdown links that CI must resolve.

| Frame | Surface | Phase 8 use |
| --- | --- | --- |
| `smart_rag/DESIGN.md` | tokens/prose | reconcile only; YAML lavender and 10px radius lost |
| `frame_00_design_system/` | primitives | buttons, badges, chips, inputs, tables |
| `frame_01_sign_in/` | sign-in | layout; replace Google SSO enabled, fake "all operational", `innerHTML` |
| `frame_03_owner_setup_invitations/` | owner/invites | layout; GAP-07-08 bootstrap stays Unavailable |
| `frame_04_main_chat_auto_routing/` | chat | shell + Auto-first layout; **do not** post Combined/Hybrid; ignore mock nDCG/TTFB/confidence |
| `frame_04_chat_state_gallery/` | chat states | verified/partial/refusal/correction patterns; **drop glass blur** |
| `frame_05_structured_table_result/` | tables | split deterministic table vs commentary |
| `frame_06_document_library/` | library | filters + Hybrid/Graph ready columns from ingestion status |
| `frame_07_file_upload_ingestion_flow/` | upload | drop + attestation; local `signed_url` null |
| `frame_09_document_detail_audit/` | document detail | metadata/status/graph tabs; audit tab Unavailable GAP-07-12 |
| `frame_10_graph_explorer/` | graph | search + list first; depth cap **3** not 5; no Edit Relationship HTTP |
| `frame_14_usage_budgets_dashboard/` | usage | `/usage/me` and `/usage/company` totals; budget sliders Unavailable GAP-07-11 |

Missing numbered frames 02, 08, 11, 12, 13: sign-up, reset/callback, MFA
enroll/challenge/recovery, tools/curation, profile, company settings,
compatibility 426, RTL/mixed-direction. Implement from the mapping and
brief fixtures, reusing delivered primitives.

## Round-1 defects (must not ship)

| Defect | Evidence | Disposition |
| --- | --- | --- |
| Tailwind CDN | every `code.html` `cdn.tailwindcss.com` | build-time CSS only |
| Google Fonts + Material Symbols CDN | every frame | self-host or system + Arabic stack |
| Inline `<script>` / `onclick` | every frame; sign-in `loader.innerHTML` | typed React handlers; no innerHTML |
| `href="#"` | most frames | real App Router routes |
| Almost no ARIA / no skip link | aria count 0 except chat=1 | [STITCH_A11Y_SECURITY.md](./STITCH_A11Y_SECURITY.md) |
| No `dir="rtl"` / `dir="auto"` / `lang="ar"` | all `lang="en"` | brief fixtures still required |
| Glass blur | gallery `.glass-panel` blur 12px | rejected; DESIGN.md prose already forbids blur |
| Combined/Hybrid send toggles | chat header; screenshot Combined selected | GAP-07-01 display-only |
| Invented diagnostics | nDCG, TTFB bars, router 0.94, Hybrid_Graph | GAP-07-02; SSE catalog only |
| Graph depth 1–5 / Edit Relationship | explorer | API depth ≤3; no mutate-relationship HTTP |
| Citation snippet hover / source view | DESIGN.md + explorer evidence cards | GAP-07-09; IDs only |
| Budget policy sliders / Slack alerts | usage frame | GAP-07-11 |
| Audit / PII review as live data | document detail | GAP-07-12 |
| Google SSO enabled | sign-in | GAP-07-04 local `enabled=false` |
| "All Systems Operational" | sign-in footer | use `GET /health/ready` |
| Mock users/docs/costs | all screens | replace with live contracts |

## Why fallback still owns implementation

1. HTML is not accessible, CSP-safe, or typed.
2. [API_UI_MAPPING.md](./API_UI_MAPPING.md) already binds every control;
   generated diagnostics are not API fields.
3. Token conflicts are resolved in [STITCH_BRIEF.md](./STITCH_BRIEF.md)
   (accent `#2563EB`, canvas `#F8FAFC`, radius 8px, no blur).

## Selected fallback primitives

Phase 8 implements `apps/frontend` with:

| Piece | Choice |
| --- | --- |
| Framework | Next.js App Router 16.3, React 19, TypeScript strict (already pinned) |
| Server state | TanStack Query 5.85.5 |
| Auth | `@supabase/ssr` 0.7.0 browser client; Bearer to FastAPI |
| Visual intent | delivered frames above (layout/hierarchy/components) |
| Styling | CSS variables from the brief token table; optional **build-time** Tailwind. **No** runtime Tailwind CDN |
| Components | native `button`, `dialog`, `textarea`, `table`, `details`; no required animation |
| Graph | search + list first; optional SVG later; hop cap 3 |
| Text | React text nodes; `displayText`; `isSafeHttpUrl`; no retrieved `dangerouslySetInnerHTML` |
| Blur | rejected |

Do not copy Stitch `code.html`. Do not keep mock data. Do not replace server
403/404 with client-only guards.

## Localization and tokens (frozen after round 1)

- English chrome; Arabic/mixed **content** with `dir="auto"` isolate.
- Token table in [STITCH_BRIEF.md](./STITCH_BRIEF.md) is canonical
  (`#2563EB` accent, `#F8FAFC` canvas, 8px, no blur).
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
| this file | visual-reference list + fallback |
| `docs/stitch_smart_rag_enterprise_console/` | local visual export only |

Phase 8 must not recreate the specification documents or restart Stitch.

## Rejected approvals

- Approval by visual appeal or unmapped frames
- Treating CDN HTML as production
- Inaccessible exports as a WCAG waiver
- Conflicting tokens or blur
- Mock-dependent interactions
- Indefinite wait for a second Stitch round

## Rollback

Revert this round-1 section and restore teal-only tokens only with an
explicit user instruction. Do not un-check packets 1–5.
