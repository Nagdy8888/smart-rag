---
title: Accessibility, RTL, and security review
owner: engineering-lead
status: draft
last-reviewed: 2026-08-17
audience: frontend, security, reviewers
packet: P07-05
---

# Accessibility, bidirectional, and security review (Phase 7)

Review of [STITCH_BRIEF.md](./STITCH_BRIEF.md), [STITCH_STATES.md](./STITCH_STATES.md),
and [API_UI_MAPPING.md](./API_UI_MAPPING.md). Delivered Stitch HTML is
not an accessibility waiver. Do not add a Stitch RTL page; mixed-direction
content rules in this file still apply.

Related: [STITCH_BRIEF.md](./STITCH_BRIEF.md) ·
[API_UI_MAPPING.md](./API_UI_MAPPING.md) ·
[FASTAPI_SECURITY.md](../api/FASTAPI_SECURITY.md) ·
[docs index](../README.md)

## Keyboard, focus, live regions

| Requirement | Specification | Pass? |
| --- | --- | --- |
| Skip link | First focusable control to `#main` | specified |
| Tab order | Chrome LTR, then isolated content widgets | specified |
| Focus visible | 2px `#2563EB` ring, 2px offset | specified |
| Error focus | move focus to `StatusBanner` on 426/402/MFA/error | specified |
| Drawers | Escape closes; focus trap; restore trigger | specified |
| Lists | arrow keys in conversation/document lists | specified |
| Composer | native textarea; Enter+modifier optional, not required | specified |
| Hit target | ≥24px mobile | specified |
| Live polite | tokens (throttled), reconnect, completed, limitations | specified |
| Live assertive | 426, 402, MFA, terminal error | specified |
| Heartbeat | not announced every 15s | specified |
| Reduced motion | no required stream animation | specified |
| Names | buttons have visible English names; citation chips `Citation {index}` | specified |

Equivalent tasks (keyboard, mouse, mobile, LTR chrome, mixed content): sign
in, send Auto question, cancel, reconnect, open citation chip, reserve
upload, graph search, read BM25 degrade, read ACL blindness.

## Contrast (WCAG AA)

Token pairs in the brief: `#0F172A` on `#F8FAFC`/`#FFFFFF`; `#FFFFFF` on
`#2563EB`; `#B91C1C` and `#A16207` used as text on white only when they meet
4.5:1 (warning `#A16207` on white is AA for large text; body warning uses
the sentence plus an icon, not warning-colored small text alone). Muted
`#475569` on white is AA. Do not place muted text on `#CBD5E1`.

## Mobile and overflow

| Frame | Rule |
| --- | --- |
| 390px | stacked shell; diagnostics collapsed `<details>` |
| 200% zoom | no loss of composer, banners, or citation chips |
| Long Arabic | wrap; line-height 1.75; no overflow clip |
| Long URL/code | wrap or horizontal scroll **inside** isolate, not the page |
| Graph | bounded canvas; empty/limitation first on small screens |

## Mixed-direction citations and highlights

Logical offsets on canonical UTF-8 text, never visual order. Highlight
`ACME` in `الشركة ACME وقعت العقد.` using codepoint range 7–11 as in the
brief fixture. `dir="auto"` + isolate on the paragraph; LTR isolate on the
code/URL. Screen readers must announce the citation index, not a visual
highlight color alone.

IME/caret: native textarea only. No custom bidi editor in v1.

## Safe text rendering

| Content | Render |
| --- | --- |
| Answers, filenames, entities, tools, table cells, citations | React/text nodes / `displayText` |
| URLs | `isSafeHttpUrl` before `href`; else text |
| Markdown | optional later sanitizer; **no** `dangerouslySetInnerHTML` on retrieved content |
| XSS fixtures | `<img src=x onerror=alert(1)>.pdf`, `</script>شركة` must remain inert |

Phase 6 thin UI already forbids raw HTML. Phase 8 keeps that contract.

## Security boundaries

| Boundary | Specification |
| --- | --- |
| Authz | server 403/404; UI hide convenience only |
| Secrets | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` only |
| CSP | FastAPI already sends `nosniff`, `DENY` frame, `no-store`, empty `default-src`; Phase 8 frontend headers must allow only self + Auth origin + API origin; no CDN scripts |
| Fonts/icons | self-host; no external placeholder CDNs |
| Errors | sanitized `detail` codes |
| Source URLs | GAP-07-09; never embed service-role or Storage privileged URLs |
| Test auth | `APP_ENV=test` bypass is server-only; production UI has no bypass |
| Forged role | mapped 403 |
| SSE | ignore unknown types; no forbidden payload keys |

## Defects and dispositions

| ID | Finding | Disposition |
| --- | --- | --- |
| A11Y-01 | Delivered Stitch HTML is a template, not layout; almost no `aria-*` | Not a waiver; do not add those frames; Phase 8 implements this file |
| A11Y-04 | Sign-in uses `loader.innerHTML` | Forbidden in production; React text nodes only |
| A11Y-02 | Warning color `#A16207` as small text may be tight AA | Use as icon + `#0F172A` sentence |
| A11Y-03 | Graph canvas keyboard path is underspecified in Stitch | Phase 8: search field + list of nodes first, canvas optional |
| SEC-01 | Source drawer has no HTTP | Unavailable GAP-07-09 |
| SEC-02 | Audit history has no HTTP | Unavailable GAP-07-12 |
| LOC-01 | No locale on `GET /me` | English chrome (GAP-07-19) |

## Negative review scenarios

Hostile markup in filenames, snippets, entities, citations, tools, table
cells, and answers must not execute. Narrow 390px, 200% zoom, long mixed
strings, keyboard-only drawers, `prefers-reduced-motion`. Forged admin POST,
unauthorized source href, diagnostic leakage, raw errors, test-auth in
production UI: all denied or absent.
