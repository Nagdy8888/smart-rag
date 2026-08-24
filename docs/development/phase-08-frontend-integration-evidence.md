---
title: Phase 8 frontend integration evidence
owner: engineering-lead
status: draft
last-reviewed: 2026-08-24
audience: engineering, reviewers, client-approver
---

# Phase 8 — Frontend integration evidence

Canonical packet evidence for
[Phase 8](../../.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration.md).
Do not check a packet from file presence alone. Phase status remains
`pending`. Journey coverage for packet 6 lives in
[PHASE8_JOURNEY_MATRIX.md](../frontend/PHASE8_JOURNEY_MATRIX.md).

## Packet 1 — Integrate the approved design system without replacing Phase 6 contracts

### Requirement (quoted)

> Integrate the approved design system into the existing Next.js workspace
> without replacing real Phase 6 contracts with mocks. Convert the approved
> `DESIGN.md` tokens and frame-00 primitives into build-time Tailwind/theme
> and reusable typed components; preserve the high-density light shell, 280px
> desktop navigation, responsive diagnostic treatment, 48px enterprise rows,
> status/citation patterns, typography, and tonal elevation without shipping
> runtime Tailwind CDN or generated inline scripts.

### Concrete acceptance checks

- Approved token values have one source of truth and no unresolved
  generated-frame conflict.
- Primitives are typed, accessible, reusable, CSP-compatible, and safe for
  hostile text.
- Desktop shell density, navigation width, row height, typography,
  elevation, and responsive diagnostics match accepted references.
- Existing Phase 6 real Auth/API/SSE behavior remains intact.

### Token reconciliation

[STITCH_BRIEF.md](../frontend/STITCH_BRIEF.md) wins.

| Source | Disposition |
| --- | --- |
| Brief table | Canonical: canvas `#F8FAFC`, accent `#2563EB`, radius-md `8px`, tonal shadows, no blur |
| `DESIGN.md` YAML | Rejected lavender `#faf8ff` and `#004ac6` |
| `DESIGN.md` prose 10px radius | Rejected |
| Teal `#0F766E` as canvas/accent | Rejected |
| Gallery `backdrop-filter` / `blur(` | Rejected |
| Tailwind `@theme` | Maps `:root` variables to utilities; does not introduce a second hex table |

CSS `:root` in `apps/frontend/src/app/globals.css` and
`apps/frontend/src/lib/design-tokens.ts` are the implementation source of
truth and are locked by `design-tokens.test.ts`.

### Frame-00 traceability

Primitives (buttons, badges, citation chips, inputs, drop zone, table,
focus/error, loading, status, limitations, live region, AppShell) were
recreated as typed components under `apps/frontend/src/components/ui/`.

**No frame-00 route** exists. [STITCH_REVIEW.md](../frontend/STITCH_REVIEW.md)
round 2 forbids adding Stitch frames as product layout. App Router still
exposes only `/` and `/_not-found`.

### Visual / component / accessibility results

- Playwright 1280×800: `app-shell-nav` computed width **280px**; skip link
  `href="#main"`; Console → `/`.
- Playwright 390×844: nav stacks above `#main` (nav `y` < main `y`, width
  > 300px).
- Playwright `prefers-reduced-motion: reduce`: authored `transition-duration: 1s`
  computes to `1e-05s` (0.01ms).
- Vitest component tests: skip link, button names, `role="status"` banners,
  XSS fixtures rendered as text (`queryByRole("img")` is null; no `script`).
- Diagnostics on the signed-in console use `<details>` opened from
  `(min-width: 801px)` so they collapse on mobile.

### Prohibited-pattern scan

`src/lib/prohibited-patterns.test.ts` walks frontend source (excluding
`*.test.*` and the hostile-fixture module) and fails on Tailwind CDN,
`dangerouslySetInnerHTML`, `.innerHTML`, `href="#"`, `backdrop-filter`,
`blur(`, Google Fonts, Material Symbols, placeholder avatars,
`Math.random(`, `next/font/google`, and gitignored Stitch imports. Also
asserts no `frame_00` / `design-system` / gallery App Router folders.

### Preserved-contract proof

No behavior edits in:

- `apps/frontend/src/lib/api.ts`
- `apps/frontend/src/lib/sse.ts`
- `apps/frontend/src/lib/chat-view.ts`
- `apps/frontend/src/lib/auth/browser.ts`

`DeveloperApp` still uses the same TanStack Query keys, `signInWithPassword`,
Bearer fetch SSE, idempotency UUID, upload reserve, and citation list.
Incidental UI-only edits: wrap in `AppShell`, tokenized CSS, Status/Citation
primitives, `<main>` inside chat replaced with `<section>` so AppShell owns
the landmark, diagnostics `<details>`.

### Files changed

| File | Action |
| --- | --- |
| `apps/frontend/package.json` / `pnpm-lock.yaml` | Tailwind 4.3.3, PostCSS, Testing Library, jsdom 27.4.0 |
| `apps/frontend/postcss.config.mjs` | Created (`@tailwindcss/postcss`) |
| `apps/frontend/src/app/globals.css` | Light brief tokens + `@theme` + reduced motion |
| `apps/frontend/src/app/layout.tsx` | System stack; no Google font loader |
| `apps/frontend/src/app/page.tsx` | Wrap `DeveloperApp` in `AppShell` |
| `apps/frontend/src/app/page.module.css` | Drop unused Geist variables |
| `apps/frontend/next.config.ts` | Explicit `font-src 'self'` |
| `apps/frontend/vitest.config.mts` | Include `*.test.tsx`; Node default |
| `apps/frontend/src/lib/design-tokens.ts` | TS token map |
| `apps/frontend/src/lib/client-authorization.ts` | Nav is not authz |
| `apps/frontend/src/components/ui/*` | Typed primitives + AppShell |
| `apps/frontend/src/components/developer-app.tsx` | Shell primitives; contracts unchanged |
| `apps/frontend/src/components/developer-app.module.css` | Tokens, 48px rows |
| `apps/frontend/tests/e2e/design-system.spec.ts` | Shell metrics |
| `docs/frontend/DESIGN_SYSTEM.md` | Created |
| `docs/frontend/STITCH_BRIEF.md` | Reciprocal link |
| `docs/frontend/STITCH_REVIEW.md` | Reciprocal link |
| `docs/frontend/THIN_DEVELOPER_UI.md` | Hosted-in-shell note |
| `docs/README.md` | Index rows |
| `.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration.md` | Packet 1 checkbox after this proof |

### Commands and results

| Command | Exit |
| --- | --- |
| `pnpm --filter smart-rag-frontend lint` | 0 |
| `pnpm --filter smart-rag-frontend exec next typegen` | 0 |
| `pnpm --filter smart-rag-frontend exec tsc --noEmit` | 0 |
| `pnpm --filter smart-rag-frontend test` | 0 (12 files, 35 passed) |
| `pnpm --filter smart-rag-frontend build` | 0 (routes `/`, `/_not-found`) |
| `pnpm exec playwright test` (cwd `apps/frontend`) | 0 (4 passed, 1 skipped) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 after this file exists |

Playwright skip: `browser readiness panel matches live GET /health/ready`
when FastAPI is not on `127.0.0.1:8000`. Login chrome, 280px nav, stacked
mobile nav, and reduced-motion still passed.

jsdom is pinned at **27.4.0** (Node 20). jest-dom is **6.9.1** (jest-dom 7
and jsdom 30 require Node 22+). Tailwind / `@tailwindcss/postcss` **4.3.3**.

### Negative findings

- XSS filename and `</script>شركة` remain text nodes.
- Omitting a nav item does not imply 403
  (`CLIENT_NAV_IS_NOT_AUTHORIZATION`, `hiddenNavImpliesForbidden`).
- No Tailwind CDN, no Google Fonts loader, no blur utilities.

### Unverified

- Full `uv run python scripts/check.py --tier frontend` in this run
  (Playwright was invoked directly; Chromium was already installed).
- Live FastAPI `/health/ready` panel match (Playwright skipped).
- Contrast lab measurement beyond the brief's AA claims.
- Self-hosted Arabic font files (none in repo; system fallback only).
- Phase 7 / Phase 6 wrapper user acceptance (still pending).

### Open gaps for P08-02

- SSR Auth, MFA recovery/permission states, API-version handshake UX,
  typed clients beyond the thin console, and streaming reconnect chrome
  are **not** in this packet.
- Sign-up, reset/callback, invitation, and owner-setup surfaces are still
  the Phase 6 password form plus later packets.
- File drop zone exists as a primitive and is **not** wired to upload
  reserve (that would change Phase 6 behavior).

### Rollback

Revert the frontend token/primitive/shell files, restore Geist in
`layout.tsx`, drop Tailwind/PostCSS/testing-library pins from
`apps/frontend/package.json` and the lockfile, and delete
`docs/frontend/DESIGN_SYSTEM.md` plus this evidence section.

## Packet 2 — Implement SSR Auth, handshake, typed clients, and streaming UX

### Requirement (quoted)

> Implement SSR Auth, audited MFA recovery/permission states, API-version handshake, typed API clients, query state, safe Bearer POST streaming, reconnect, and idempotency UX. Match frame 01's transactional sign-in and frame 03's gated owner setup where approved; fill the absent sign-up, reset/callback, MFA enrollment/challenge/lost-factor recovery, invitation/team entry, upload-MFA denial, and incompatible-client surfaces from real contracts rather than design mocks.

### Concrete acceptance checks

- All required Auth/MFA/recovery/invitation/session/upload-permission journeys use real contracts and auditable server behavior.
- Minimum-client rejection occurs before paid work; unknown additive SSE events do not break an active answer.
- Retries/reconnects reuse one run, apply monotonic sequences, and never duplicate paid submission.
- Frame 01/03 traceability and all absent-surface gap decisions are evidenced.

### Frame 01/03 and gap traceability

Stitch is a template, not a layout. No `frame_01` or `frame_03` routes.

| Surface | Disposition |
| --- | --- |
| Sign in | Native `/login` (`signInWithPassword`). Generic "Sign in failed". GAP-07-20: copy does not claim FastAPI throttles the form |
| Sign up | Native `/signup`. Invitation still required for FastAPI membership |
| Forgot / reset / callback | `/forgot-password`, `/auth/reset`, `/auth/callback` PKCE |
| Google | Disabled button GAP-07-04. `maybeSignInWithGoogle(false)` never calls OAuth |
| MFA enroll/challenge | Auth-direct TOTP. FastAPI 403 `MFA required` banner |
| MFA recovery | Unavailable GAP-07-07. `mfa_recovery.py` has no router. No recovery-code input |
| Owner bootstrap | Unavailable GAP-07-08. Invitation accept is in scope |
| Invitation accept | Authenticated `POST /invitations/accept` `{ token }` only |
| Chat/docs/graph | Still Phase 6 DeveloperApp on `/` after Auth |

### Contract versions

- Next.js 16.3.0 `src/proxy.ts` (not `middleware.ts`)
- `@supabase/ssr` 0.7.0 `createServerClient` / `createBrowserClient` / `exchangeCodeForSession`
- `@supabase/supabase-js` 2.57.4 MFA `enroll({ factorType: "totp" })`
- TanStack Query 5.85.5 session-aware keys
- FastAPI OpenAPI `docs/api/openapi.foundation.json` invitation accept and `/api/meta`

### Handshake-before-spend

`evaluatePaidHandshake` compares `CLIENT_VERSION` `0.1.0` to `GET /api/meta`
`min_client_version`. Below min or unreachable meta: composer Send disabled;
`startMessageStream` is not called. Resume GET omits `X-Client-Version`.
Newer `sse_schema_version` continues. Server 426 remains classified.

### Streaming / idempotency

`startOrResumeMessageStream` skips POST when `runId` is set and `terminal`
is null. Duplicate/older SSE sequences are ignored. Unknown events log and
continue. 402/429/503 classified as budget/rate/fail_closed.

### Files changed

| File | Action |
| --- | --- |
| `apps/frontend/src/proxy.ts` | Next 16 cookie refresh + optimistic redirects |
| `apps/frontend/src/lib/auth/*` | Server client, session provider, Google/MFA-recovery guards |
| `apps/frontend/src/lib/handshake.ts` | Min-client compare; fail closed; schema-newer continue |
| `apps/frontend/src/lib/api.ts` | 402/429 classify; `acceptInvitation`; resume-over-POST |
| `apps/frontend/src/lib/chat-view.ts` | Ignore duplicate/older SSE sequences |
| `apps/frontend/src/app/login` and Auth routes | Native Auth-direct surfaces |
| `apps/frontend/src/components/developer-app.tsx` | Session restore; handshake-gated Send |
| `docs/frontend/AUTH_AND_STREAMING.md` | Canonical Auth/streaming doc |

### Commands and results

| Command | Exit |
| --- | --- |
| `pnpm --filter smart-rag-frontend lint` | 0 |
| `pnpm --filter smart-rag-frontend exec next typegen` | 0 |
| `pnpm --filter smart-rag-frontend exec tsc --noEmit` | 0 |
| `pnpm --filter smart-rag-frontend test` | 0 (15 files, 59 passed) |
| `pnpm --filter smart-rag-frontend build` | 0 (Proxy plus `/`, `/login`, `/signup`, `/forgot-password`, `/auth/callback`, `/auth/reset`, `/mfa/*`, `/invitations/accept`, `/unavailable/[gap]`) |
| `pnpm exec playwright test` (cwd `apps/frontend`) | 0 (9 passed, 1 skipped) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

Playwright skip: `browser readiness panel matches live GET /health/ready`
when FastAPI is not on `127.0.0.1:8000`.

### Negative findings

- Forged `role=owner` does not add a role header; Bearer only
- Hidden MFA recovery control is not an HTTP call (`mfaRecoveryRequestUrl()` is null)
- Google disabled does not call `signInWithOAuth`
- Callback without `code` shows "Sign-in could not be completed"
- XSS email remains a text value
- No `NEXT_PUBLIC_*SERVICE_ROLE*` in frontend source

### Unverified

- Live GoTrue sign-in/MFA verify against local Auth (Playwright does not use a test-auth bypass)
- Hosted Auth throttling (GAP-07-20 / Phase 10)
- Packet 3 chat redesign and packet 4 team admin

### Open gaps for P08-03

- Chat/test limitation diagnostics, citations, document library, graph, tables, feedback chrome beyond the Phase 6 DeveloperApp
- Do not start until this packet's evidence is accepted

### Rollback

Revert `apps/frontend/src/proxy.ts`, Auth routes, session provider, handshake
helpers, and `docs/frontend/AUTH_AND_STREAMING.md`. Restore DeveloperApp
inline password `useState` sign-in on `/`. Leave packet 1 primitives in place.

## Packet 3 — Implement core RAG surfaces

### Requirement (quoted)

> Implement chat/test limitation diagnostics, citations/inferences, quota-aware document upload/status/quarantine, graph-blindness states, tables, and feedback. Preserve frame 04's Auto-first shell, route controls, pipeline/inference/scope/citation patterns and state-gallery families; frame 05's deterministic-versus-generated table separation; frames 06/07/09's document, attestation, quarantine, and chunk-review patterns; and frame 10's three-pane graph/evidence layout. Add every required BM25, deadline, temporal, figure/media, negation, summary, quota, version, backlog, fallback, Graph Pending, and authorized ACL-blindness state absent from Stitch.

### Concrete acceptance checks

- Frame behavior is traceable and every required missing state has an approved primitive-based implementation.
- `Auto` is default; diagnostics distinguish requested/effective/corrected routes, dense+term BM25 degradation, Hybrid fallback, limitations, and partial readiness.
- Citations open authorized canonical sources; inference links cite atomic support; table results retain exact deterministic provenance.
- `Graph Pending` differs from authorized ACL blindness, and unauthorized actors receive no count, title, entity, relation, or source leakage.
- Upload/quarantine/quota/readiness/backlog/retry/version/anomaly/deletion journeys use real server state.

### Frame / gap traceability

Stitch is a template, not a layout. No `frame_04` / `05` / `06` / `07` / `09` / `10` routes.

| Surface | Disposition |
| --- | --- |
| Chat Auto | Native `/`. `SubmitMessageRequest` is `{ message, idempotency_key? }` only (GAP-07-01) |
| Advanced panel | Closed `<details>` of catalog events. No Hybrid/Combined/Table/Inspect send |
| Inference chains | GAP-07-02: not in SSE catalog; citation chips only |
| Source drawer | Ids + provenance text. No privileged href (GAP-07-09) |
| Documents | `/documents` library, reserve, Storage JWT, SHA-256 finalize, crawl convenience |
| Document detail | `/documents/[documentId]`. 404 is "Not found" with no title. No audit/PII/preview tabs |
| Delete document | Unavailable GAP-07-14. `deletion_pending` pill only |
| Graph | `/graph` search + inspect, hop cap 3, list-first. ACL copy ignores count |
| Tables | `/tables` typed plan. No SQL. No client total. No export without chat disclosure |
| Admin/tools/usage | Packet 4. Not started |

### Contract versions

- Next.js 16.3.0 App Router; `@supabase/ssr` 0.7.0 Storage JWT upload
- FastAPI OpenAPI `docs/api/openapi.foundation.json` finalize, crawls, graph inspect/search, tables analyze
- SSE catalog in `smart_rag_core.sse.catalog`
- Attestation policy version `2026-08-13`

### Files changed

| File | Action |
| --- | --- |
| `apps/frontend/src/lib/api.ts` | finalize, crawl, retry, document GET, graph, tables |
| `apps/frontend/src/lib/limitations.ts` | GraphLimitationCode copy |
| `apps/frontend/src/components/chat-app.tsx` | Auto chat at `/` |
| `apps/frontend/src/components/document-library.tsx` | Library + upload + crawl |
| `apps/frontend/src/components/document-detail.tsx` | Detail + 404 |
| `apps/frontend/src/components/graph-explorer.tsx` | Search + inspect |
| `apps/frontend/src/components/tables-app.tsx` | Plan builder |
| `apps/frontend/src/components/ui/app-nav.tsx` | Chat/Documents/Graph/Tables `Link` |
| `apps/frontend/src/app/documents` `/graph` `/tables` | Native routes |
| `docs/frontend/CORE_RAG_SURFACES.md` | Canonical packet 3 doc |

`DeveloperApp` was removed. Upload moved off `/`.

### Commands and results

| Command | Exit |
| --- | --- |
| `pnpm --filter smart-rag-frontend lint` | 0 |
| `pnpm --filter smart-rag-frontend exec next typegen` | 0 |
| `pnpm --filter smart-rag-frontend exec tsc --noEmit` | 0 |
| `pnpm --filter smart-rag-frontend test` | 0 (21 files, 86 passed) |
| `pnpm --filter smart-rag-frontend build` | 0 (routes `/`, `/documents`, `/documents/[documentId]`, `/graph`, `/tables`, plus Auth; no `/chat`) |
| `pnpm exec playwright test` (cwd `apps/frontend`) | 0 (13 passed, 3 skipped) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

Playwright skips: live FastAPI `/health/ready` when 127.0.0.1:8000 is down;
authenticated Auto chrome and authenticated document 404 when no Auth session
exists. Component tests cover Auto POST body, handshake-gated Send, 404
"Not found" with no title, and public chrome for documents/graph/tables.

### Negative findings

- Auto POST body has no route field
- ACL blindness copy has no unauthorized title or count
- Graph inspect depth clamps to 3
- Table client omits SQL-like extra fields and does not sum rows
- Document 404 does not parse a title
- No `deleteDocument` helper (GAP-07-14)
- Citation chip href is always null (GAP-07-09)
- XSS fixtures remain text nodes
- Handshake still blocks Send
- Upload MFA maps to `mfa_required`
- Crawl helper still posts and 403s; UI hides for non-admin

### Unverified

- Live Storage JWT upload against local Supabase RLS (finalize client is mocked in unit tests)
- Live FastAPI graph/table/document journeys
- Authenticated Playwright Auto chrome when no Auth session exists

### Open gaps for P08-04

- Team, tools, glossary, entity rules, usage/company, profile editor
- Do not start until this packet's evidence is accepted

### Rollback

Revert the new App Router folders, restore `DeveloperApp` on `/`, restore
single-item Console nav, and delete `docs/frontend/CORE_RAG_SURFACES.md`
plus this evidence section. Leave packet 1--2 Auth/primitives in place.

## Packet 4 — Implement administration surfaces

### Requirement (quoted)

> Implement team, tools, alias/entity curation, usage, budgets, restricted read/download audit, profile, and company settings with server-enforced permissions. Preserve frame 14's usage/budget information hierarchy and degradation/critical-reserve patterns. Because the remaining administration surfaces have no delivered frame, derive them from `API_UI_MAPPING.md`, reuse approved primitives and shell patterns, and list the design gap in exit evidence.

### Concrete acceptance checks

- Server denial protects every mutation and restricted read even if controls are forged or revealed.
- Frame 14 hierarchy and degradation/critical-reserve patterns match the accepted reference (tokens + usage meters; no budget sliders).
- Tool/curation changes display version, permission, enable state, and auditable outcomes.
- Audit history exposes only authorized metadata and records restricted access consistently — GAP-07-12 has no HTTP, so Unavailable, do not mock events.
- Every absent administration frame has an approved, mapped, primitive-based solution in evidence.

### Frame / gap traceability

Stitch is a template, not a layout. No `frame_02` / `08` / `11` / `12` / `13` / `14` routes. No `app/admin` folder.

| Surface | Disposition |
| --- | --- |
| Team | Native `/team`. Invite `{ email, role, upload_enabled }`. Offboard by `user_id`. No member directory HTTP |
| Invitation accept | Existing `/invitations/accept`. Linked from team |
| Owner bootstrap | Unavailable GAP-07-08. No bootstrap HTTP |
| Tools | Native `/tools`. `GET /tools` for any member. Enable/permissions owner/admin convenience; server 403 |
| Curation | Native `/curation`. Glossary import/approve/rollback + entity rules with `row_version` |
| Usage | Native `/usage`. `GET /usage/me` for all; `GET /usage/company` owner/admin. Totals only |
| Frame 14 budget sliders / critical reserve | Unavailable GAP-07-11. 402 `budget_exhausted` copy + token meters. No `/budgets` |
| Audit list/export | Unavailable GAP-07-12. No fake events or passages |
| Profile | Native `/profile`. Five `GET /me` fields. GAP-07-19 no name/locale editor |
| Company settings | Unavailable GAP-07-13 on profile. No save control |

Missing-frame decision: frame 14's information hierarchy is recreated as caller/company token meters plus honest 402/rate banners. Budget-policy editors are not shipped.

### Role matrix and forged-request results

- Viewer/member convenience hides invite, offboard, and enable. `createInvitation` / `offboardUser` / `enableTool` still post Bearer only.
- Forged client `role=owner` does not add `X-Role`, `X-Test-Role`, or `X-Test-User-Id`.
- 403 `forbidden`, 403 `MFA required`, 402 `budget_exhausted`, and 429 `rate_limited` are classified.
- Company usage 403 for member.
- Unauthorized tool names are omitted from the catalog fixture; the client does not invent redacted titles.
- Entity-rule approve posts `{ row_version }`. Glossary extra SQL-like fields are not posted.

### Files changed

| File | Action |
| --- | --- |
| `apps/frontend/src/lib/api.ts` | Invitation, offboard, tools, glossary, entity-rule, company usage clients |
| `apps/frontend/src/lib/admin-bodies.ts` | Extra-forbid builders |
| `apps/frontend/src/lib/admin-copy.ts` | Gap copy |
| `apps/frontend/src/lib/roles.ts` | Invite/offboard/enable convenience helpers |
| `apps/frontend/src/components/team-app.tsx` `/tools-app.tsx` `/curation-app.tsx` `/usage-app.tsx` `/profile-app.tsx` | Native surfaces |
| `apps/frontend/src/app/team` `/tools` `/curation` `/usage` `/profile` | App Router pages |
| `apps/frontend/src/components/ui/app-nav.tsx` | Team, Tools, Curation, Usage, Profile `Link`s |
| `docs/frontend/ADMINISTRATION.md` | Canonical packet 4 doc |

### Commands and results

| Command | Exit |
| --- | --- |
| `pnpm --filter smart-rag-frontend lint` | 0 |
| `pnpm --filter smart-rag-frontend exec next typegen` | 0 |
| `pnpm --filter smart-rag-frontend exec tsc --noEmit` | 0 |
| `pnpm --filter smart-rag-frontend test` | 0 (23 files, 106 passed) |
| `pnpm --filter smart-rag-frontend build` | 0 (routes `/team`, `/tools`, `/curation`, `/usage`, `/profile`; no `/admin`) |
| `pnpm exec playwright test` (cwd `apps/frontend`) | 0 (15 passed, 4 skipped) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

### Negative findings

- No budget slider, no fake audit table, no company-settings save
- `raw_token` is text once; hostile invitation email remains a text node
- Viewer/member helpers hide mutations; server 403 remains
- Prohibited-pattern scan still forbids `admin`, `frame_*`, `gallery`, `design-system`, `chat`, `docs`

### Unverified

- Live FastAPI invitation/offboard/tool/glossary/entity-rule journeys
- Authenticated Playwright company-usage 403 when no Auth session exists
- AAL2 offboard against local GoTrue

### Open gaps for P08-05

- Accessibility, RTL, CSP/security headers, and generic production errors are **not** in this packet
- Do not start packet 5 until this evidence is accepted

### Rollback

Revert the new App Router folders and administration clients, restore
Chat/Documents/Graph/Tables-only nav, and delete
`docs/frontend/ADMINISTRATION.md` plus this evidence section. Leave
packets 1--3 primitives, Auth, and core RAG surfaces in place.

## Packet 5 — Apply accessibility, RTL, CSP, and generic production errors

### Requirement (quoted)

> Apply strict escaping, CSP/security headers, WCAG AA behavior, Arabic RTL/bidirectional text, keyboard navigation, responsive layouts, and generic production errors. Treat the lack of RTL/mobile-specific Stitch frames as missing design evidence, not a waiver: add reviewed Arabic/mixed-direction fixtures, logical citation highlighting, responsive breakpoints, focus/live-region behavior, reduced-motion behavior, and security tests while rejecting every prohibited generated-HTML pattern above.

### Concrete acceptance checks

- XSS fixtures render as inert text and CSP/security-header tests pass.
- Desktop/mobile LTR/RTL tasks are complete at required breakpoints and zoom, with correct logical citation interaction.
- Keyboard, focus, live-region, reduced-motion, and WCAG AA checks pass across auth, chat, documents, graph, tables, and administration.
- Errors are generic in production while retaining safe recovery and correlation behavior.
- No runtime Tailwind CDN, inline handler/script, `innerHTML`, mock/random auth, placeholder link, third-party avatar, static live diagnostic, CSP-violating dependency, demo data, dead link, unsafe markup, or test bypass remains.

### RTL / mobile gap fills (missing Stitch frames are not a waiver)

The delivered export still has no RTL or mobile frames. Packet 5 ships
reviewed fixtures rather than inventing Stitch routes:

| Gap | Fill |
| --- | --- |
| Mixed message | `راجع INV-SR-8801 في https://example.com/q?id=12 — القسم 3.` in `ReviewedContentFixtures` |
| Logical highlight | `الشركة ACME وقعت العقد.` codepoint offsets 7–11 (`ACME`) via `highlightLogicalRange` |
| Diacritics | `إِنَّ` at line-height 1.75 |
| Long URL | wrap inside `dir="ltr"` isolate |
| XSS / `javascript:` / `\u202E` | `UserText` / `CodeText` only |
| 390px nav overflow | `<details>` Menu (no hash placeholder) plus scrollable nav |
| 200% zoom | Playwright viewport 640×400 on `/login` stub composer, banners, chips |

Citations HTTP has no offset fields (GAP-07-09). The helper and drawer
demo use the reviewed fixture; no invented API offset fields.

### CSP / headers

Production `script-src` is `'self' 'unsafe-inline'`. `'unsafe-eval'` is
development-only. Next.js 16.3 documents that React uses `eval` for
debug info in development and that production React/Next do not require
`'unsafe-eval'` by default. `'unsafe-inline'` remains because this app
does not emit CSP nonces. Added `Permissions-Policy` and
`X-DNS-Prefetch-Control: off`. No CDN hosts. `api.ts` does not send
`X-Test-*`.

### Generic production errors

Unknown 5xx and unclassified mutation `Error.message` values map to
**Something went wrong.** Login still shows only **Sign in failed**.
Traceback-shaped FastAPI `detail` is discarded. Reconnect/retry remain.

### Files changed

| File | Action |
| --- | --- |
| `apps/frontend/next.config.ts` | Dev-only `'unsafe-eval'`; Permissions-Policy; DNS prefetch off |
| `apps/frontend/src/lib/highlight-logical-range.ts` | Codepoint highlight helper + ACME fixture |
| `apps/frontend/src/lib/contrast.ts` | WCAG relative-luminance helper |
| `apps/frontend/src/lib/failure-copy.ts` | Generic 5xx copy |
| `apps/frontend/src/lib/api.ts` | `server` failure kind; safe detail codes |
| `apps/frontend/src/components/ui/*` | Error focus, drawer trap, roving list, fixtures, warning icon |
| `apps/frontend/src/components/chat-app.tsx` | Drawer restore, conversation listbox, generic terminal error |
| `apps/frontend/src/components/document-library.tsx` | Document listbox |
| `apps/frontend/src/components/auth/auth-screens.tsx` | Fixtures on login; invitation errors generic |
| `apps/frontend/tests/e2e/a11y-security.spec.ts` | Skip-link Tab, zoom, Menu, no Auth traces |
| `docs/frontend/A11Y_SECURITY_IMPLEMENTATION.md` | Created |
| `docs/frontend/STITCH_A11Y_SECURITY.md` | Phase 8 pointer |
| `docs/README.md` | Index row |

### Commands and results

| Command | Exit |
| --- | --- |
| `pnpm --filter smart-rag-frontend lint` | 0 |
| `pnpm --filter smart-rag-frontend exec next typegen` | 0 |
| `pnpm --filter smart-rag-frontend exec tsc --noEmit` | 0 |
| `pnpm --filter smart-rag-frontend test` | 0 (27 files, 123 passed) |
| `pnpm --filter smart-rag-frontend build` | 0 (no Stitch/frame/admin gallery routes) |
| `pnpm exec playwright test` (cwd `apps/frontend`) | 0 (19 passed, 4 skipped) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (117 markdown files, 0 lint issues; links + Mermaid render) |

Playwright skips: live FastAPI `/health/ready` when 127.0.0.1:8000 is down;
authenticated Auto chrome, document 404, and company-usage 403 when no
Auth session exists.

### Negative findings

- XSS filename/entity, `javascript:alert(1)`, and `\u202E` remain text nodes
- ACME highlight is codepoint offsets 7–11, not UTF-16 visual order
- Escape closes the source drawer and restores the citation chip
- Unknown 500 traceback details never appear in banners
- Production CSP source omits always-on `'unsafe-eval'`
- No `X-Test-` header literals in `api.ts`
- Prohibited-pattern scan still forbids CDN, `innerHTML`, hash placeholders, blur, Google Fonts, avatars, `Math.random`, test-auth bypass

### Unverified

- Live WCAG lab measurement of every computed style beyond token hex pairs
- Authenticated Playwright chat composer at 200% zoom (unsigned login hosts the stub composer/chip fixtures)
- Self-hosted Arabic font files (system stack only)
- Packet 6 full role/routing Playwright journeys

### Open gaps for P08-06

- Complete Playwright journeys for roles, reconnect, API skew, table provenance, curation, graph evidence, and limitation families
- Do not start packet 6 until this evidence is accepted

### Rollback

Revert the P08-05 frontend a11y/CSP/error files, restore previous
`next.config.ts` CSP, and delete
`docs/frontend/A11Y_SECURITY_IMPLEMENTATION.md` plus this evidence
section. Leave packets 1--4 surfaces in place. Phase 8 stays `pending`.

## Packet 6 — Run complete frontend verification journeys

### Requirement (quoted)

> Run complete Playwright journeys for roles, routing/limitation families, reconnect, API/deploy versioning, fallbacks, table provenance, curation, and graph evidence. Add stable visual/interaction regression coverage keyed to each delivered frame surface, plus explicit journeys for delivered gallery states and required Stitch gaps including MFA recovery, API skew, BM25 degradation, rate limits, Graph Pending/ACL blindness, RTL citations, and restricted evidence audit.

Stitch is a **template, not a layout**. Visual/interaction regression is keyed
to shipped contract surfaces, not Stitch frame numbers. Matrix:
[PHASE8_JOURNEY_MATRIX.md](../frontend/PHASE8_JOURNEY_MATRIX.md).

### Concrete acceptance checks

- Every wrapper final-gate journey has a real contract test or is listed
  **unverified-live**.
- Authorization negatives, ACL silence, citations without snippets, table
  `source_ranges`, limitation honesty, and reconnect/idempotency hold in
  unit/component tests with injected fetch.
- No mock data in production UI; no test-auth bypass; prohibited-pattern
  scan passes.
- Exact commands and exit codes recorded.

### Bounded repairs

- `listCitations` now keeps ids/coordinates and drops `snippet` / `passage` /
  `text` / `html` / `content` / `body` fields (including nested provenance).
  404 private-run citations return `[]` without parsing a title or passage.
- Evidence encoding: `×`, `→`, and `شركة` restored in packet 1 notes.

No backend redesign. No production test-auth bypass. No `X-Test-*` headers.

### Commands and results (2026-08-17)

| Command | Exit |
| --- | --- |
| `pnpm --filter smart-rag-frontend lint` | 0 |
| `pnpm --filter smart-rag-frontend exec next typegen` | 0 |
| `pnpm --filter smart-rag-frontend exec tsc --noEmit` | 0 |
| `pnpm --filter smart-rag-frontend test` | 0 (27 files, 149 passed) |
| `pnpm --filter smart-rag-frontend build` | 0 (routes `/`, `/documents`, `/graph`, `/tables`, `/team`, `/tools`, `/curation`, `/usage`, `/profile`, Auth, `/unavailable/[gap]`; no `frame_*` / gallery / admin) |
| `pnpm exec playwright test` (cwd `apps/frontend`) | 0 (29 passed, 0 skipped) |
| `uv run python -m pytest tests/unit/test_phase08_journey_matrix.py -q` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (118 markdown files, 0 lint issues; links + Mermaid render) |

`uv run python scripts/check.py --tier frontend` was not run as one process.
The frontend-tier commands above are the same vector `check.py` uses
(lint, typegen, tsc, vitest, build, playwright), invoked separately.

Playwright skips (live FastAPI/Auth down; same assertions exist in Vitest):

- none in the 2026-08-17 live re-run (29 passed, 0 skipped)

### Live stack re-run (2026-08-17)

Docker Desktop was stuck on an unresponsive WSL VM (`wsl.exe -l -v` timed
out; `vmmemWSL` would not die without elevation). After an elevated
`WSLService` restart, local GoTrue came up on `127.0.0.1:54321`. Compose
`frontend` image build failed once because the Docker context was copied
before `tests/e2e/live-auth.ts` existed; live HTTP used **host uvicorn**
against local Auth/Postgres (same overlay as Phase 6 packet 8), not the
Compose API image. `GET /health/ready` reported `database=ok`,
`paradedb=unconfigured`, `valkey_limits=unconfigured`, `model_gateway=mock`.

Auth was restarted (`pnpm exec supabase stop` then `start`, no `db reset`)
so `[auth.mfa.totp]` enroll/verify applied. TOTP enroll had been 422 before
that restart.

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/contract/test_thin_developer_ui_live.py -q -rs` | 0 (5 passed, 1 skipped: compose ParadeDB/Valkey stop; host API is `unconfigured`) |
| `pnpm exec playwright test` (cwd `apps/frontend`) | 0 (29 passed, 0 skipped) |

Proven in that run:

- `GET /api/meta` public handshake
- Password JWT chat, 426 without `X-Client-Version`, idempotent POST, SSE terminal, conversation DELETE, lingering ids 0
- Five concurrent Composite streams
- `upload_enabled` aal1 → `403 MFA required` on `/me` and reserve
- Verified TOTP aal2 + `upload_enabled` reserve: `signed_url` is null,
  `upload_method=supabase_storage_jwt`, user JWT POST to Storage returns 200/201
- Playwright live `/health/ready` panel match
- Playwright sign-in via GoTrue admin-created user (no `X-Test-*`): Auto chrome,
  document 404 “Not found” without title leak, usage 403 with no budget sliders

Playwright live sign-in helper: `apps/frontend/tests/e2e/live-auth.ts` reads
pinned `supabase status -o json` (never prints keys) and fills `/login`.

### Negative findings

- Auto POST body has no route field (GAP-07-01)
- ACL blindness copy ignores `count` 99 and titles
- Citations omit snippet/passage fields
- Table `source_ranges` render; client total is null; no Export without disclosure
- Cancel POST omits `X-Client-Version`
- Resume 404 is `deleted` without a second paid POST
- GAP-07-07/08 Unavailable pages have no recovery-code or bootstrap inputs
- GAP-07-12 Usage has no fake audit table or passages
- Login CSP has `default-src 'self'` and no Tailwind CDN
- Prohibited-pattern scan still forbids `dangerouslySetInnerHTML`, `innerHTML`,
  hash placeholders, blur, CDN fonts, `Math.random`, `X-Test-` headers

### Unverified-live

Later re-run checklist (commands, pass criteria, results log):
[phase-08-later-live-verification.md](./phase-08-later-live-verification.md).

- P08-LV-01 Compose ParadeDB/Valkey stop-visible-on-ready
- P08-LV-02 Abandoned / expired / oversize as distinct public JSON enums
- P08-LV-03 Live WCAG lab measurement of computed styles
- P08-LV-04 Hosted Auth throttling (GAP-07-20 / Phase 10)
- P08-LV-05 Signed-in Next chrome against live graph/tables/tools/curation mutations

### Files changed

| File | Action |
| --- | --- |
| `apps/frontend/src/lib/api.ts` | Strip citation snippet/passage fields |
| `apps/frontend/src/lib/api.test.ts` | 426, cancel, delete, resume 404, citations, quota 402, session_revoked |
| `apps/frontend/src/lib/chat-view.test.ts` | Heartbeat, cancel, BM25/ACL/pending/summary codes |
| `apps/frontend/src/lib/ingestion-status.test.ts` | Graph Pending vs failed; no invented quarantine enums |
| `apps/frontend/src/lib/graph-client.test.ts` | Graph Pending vs ACL blindness; count ignored |
| `apps/frontend/src/components/chat-app.test.tsx` | MFA, revoked, SSE families, cancel, reconnect 404, delete |
| `apps/frontend/src/components/core-rag-surfaces.test.tsx` | Graph Pending vs ACL, tables `source_ranges`, library status |
| `apps/frontend/src/components/administration-surfaces.test.tsx` | GAP-07-08, GAP-07-12 member, curation approve |
| `apps/frontend/src/components/auth/auth-screens.test.tsx` | GAP-07-08 no bootstrap form |
| `apps/frontend/src/components/accessibility-security.test.tsx` | ACME `mark` parent `dir="auto"` |
| `apps/frontend/tests/e2e/phase08-journeys.spec.ts` | Unauth routes, gaps, handshake stub, CSP, document 404 → login |
| `apps/frontend/tests/e2e/live-auth.ts` | Live GoTrue admin user + `/login` sign-in helper |
| `apps/frontend/tests/e2e/login.spec.ts` | Shared `fetchLocalReady` |
| `apps/frontend/tests/e2e/core-rag-surfaces.spec.ts` | Live session Auto chrome and document 404 |
| `apps/frontend/tests/e2e/administration-surfaces.spec.ts` | Live session usage 403 |
| `tests/contract/test_thin_developer_ui_live.py` | aal2 reserve then user-JWT Storage POST |
| `docs/frontend/PHASE8_JOURNEY_MATRIX.md` | Created; live rows flipped after 2026-08-17 run |
| `docs/development/phase-08-later-live-verification.md` | Later-verification IDs P08-LV-01–05 |
| `tests/unit/test_phase08_journey_matrix.py` | Lock limitation codes and GAP ids |
| `docs/README.md` | Index row |
| Reciprocal links | CORE_RAG, ADMINISTRATION, AUTH, A11Y → matrix |

### Rollback

Revert the P08-06 test/docs files and the `listCitations` sanitizer. Leave
packets 1--5 surfaces in place. Phase 8 stays `pending`.

## Phase 8 exit record (pending user acceptance)

Wrapper `status` remains **pending**. Packet 6 may be checked after this
evidence. Do not start Phase 9 until the user accepts this exit record.

### Done-when

| Done-when item | Status |
| --- | --- |
| Production Next.js build, strict types, lint, component tests, accessibility checks | **proven** (commands above) |
| Matches `STITCH_REVIEW.md`: no Stitch template routes | **proven** (build routes; prohibited-pattern scan) |
| Honest GAP Unavailable pages for missing HTTP (GAP-07-07/08), not Stitch placeholders | **proven** (Playwright + component). Wrapper text that forbids “Unavailable-gap pages” is read as forbidding Stitch-number placeholders, not these contract gap fills |
| No prohibited generated-HTML pattern | **proven** |
| `@supabase/ssr` Auth: sign-in/up, Google disabled, reset/callback, invitation accept, MFA enroll/challenge, lost-factor GAP-07-07, owner bootstrap GAP-07-08, revoked sessions, upload MFA; no client authz shortcut | **proven** in Vitest and live GoTrue (password sign-in Playwright; aal1 MFA required; TOTP aal2 reserve) |
| Handshake blocks unsupported clients before paid work | **proven** (9.0.0 stub + live 426 POST) |
| Typed SSE clients tolerate unknown additive events | **proven** |
| Idempotent submit, sequenced reconnect, heartbeat, cancel, route correction, deadline/partial, BM25 degrade, LightRAG `graph_outage`, figure/media, temporal, ACL, summary, negation, citations without snippets, inference GAP-07-02 copy, table provenance, diagnostics, feedback chrome, generic errors | **proven** in unit/component |
| Document upload/quota/crawl/quarantine/scan/parse/BM25/Hybrid-Graph/backlog/retry/version/anomaly/deletion journeys | **proven** for mapped contracts; **proven** local Storage JWT PUT after aal2 reserve (`signed_url` still null); abandoned/expired/oversize are not distinct public enums |
| Graph explorer, tables, tools, curation, team, usage/budget/rate, restricted audit GAP-07-12, profile, company settings enforce roles | **proven** in component tests; usage 403 Playwright live; remaining FastAPI mutations **unverified-live** from Next chrome |
| Responsive LTR/RTL, ACME logical highlight, keyboard/skip/reduced-motion, WCAG AA tokens, CSP, strict escaping, XSS fixtures | **proven** |
| Playwright unauth + public stubs for roles chrome, MFA recovery, API skew, BM25 copy, Graph/ACL (component), RTL fixtures, restricted audit (component) | **proven**; authenticated Playwright Auto / document 404 / usage 403 **proven** live |
| No mock data, test-auth bypass, `dangerouslySetInnerHTML`, or unescaped retrieved markup | **proven** |

### Phase 9 handoff blockers

- User acceptance of this Phase 8 exit record
- Do not start Phase 9 local release-candidate load/eval until accepted

## Stitch-first UX restoration (2026-08-20)

The user clarified that “template, not a layout” forbade extra numbered-frame
routes, not visual fidelity. Historical packet-1 notes that App Router
exposed only `/` remain true of **that packet**. Current routes and the
visual restoration are recorded in
[ADR-stitch-first-ux.md](../adr/ADR-stitch-first-ux.md) and
[VISUAL_MAP.md](../frontend/VISUAL_MAP.md).

| Check | Status |
| --- | --- |
| Round 3 review language + ADR | proven |
| Route groups: `(auth)` card vs `(console)` 280px shell; URLs unchanged | proven (`next build` route table) |
| Login has no console nav; form in first 390px viewport | proven (Playwright login + design-system) |
| Chat transcript/composer outrank collapsible diagnostics | proven in component tests; live screenshot **unverified-live** (Docker/GoTrue/FastAPI down) |
| Mapped routes follow Stitch composition without mock Hybrid/nDCG/sliders | proven in Vitest; authenticated Playwright screenshots **unverified-live** |
| Public Auth visual baselines 1280 and 390 | proven (`tests/e2e/visual-routes.spec.ts-snapshots`) |
| Frontend lint, `tsc --noEmit`, Vitest 171, production build | proven |
| Playwright Chromium | proven 23 passed, 9 skipped (live session required) |
| `test_phase07_stitch_review.py` | proven |

### Intentional deviations from Stitch frames

| Frame / control | Implementation | Reason |
| --- | --- | --- |
| Google SSO label | `Continue with Google (when enabled)` | GAP-07-04 accessible name contract |
| Request access | Sign up | Contract-backed `/signup` |
| Remember this session | omitted | No remember-me HTTP |
| System Status: All Systems Operational | omitted | Mock health chrome |
| Hybrid / Combined send, nDCG, TTFB, confidence | omitted | No client route POST; no fake metrics |
| Global search, bell, help, avatars | omitted | No APIs; placeholder avatars prohibited |
| Budget sliders, Slack, export report | honest unavailable cards | GAP-07-11 / no export tool on `/usage` |
| Edit Relationship, depth 5 | omitted; hop cap 3 | ACL-safe inspect only |
| Owner-bootstrap wizard | omitted | GAP-07-08 |
| GAP ids on product pages | `/unavailable/` and tests only | Human copy on normal journeys |
| Review fixtures | `/review-fixtures` | Not a product journey |

### Remaining live-only gaps

Docker Desktop was not running, so local GoTrue (`:54321`) and FastAPI
(`:8000`) were unreachable. Authenticated Playwright (nav 280px, Menu
drawer, Auto chrome, usage 403, product-route screenshots) skipped via
`signInLiveMember`. Re-run `pnpm exec playwright test --update-snapshots`
from `apps/frontend` after `npx supabase start` and the API are up.

## Precision Workspace restyle (2026-08-24)

Route CSS moved off the shared `developer-app.module.css` module. That file
is deleted. Chat, documents, graph, tables, and admin each own a CSS
module. Live composition is the light Precision Workspace in
[STITCH_BRIEF.md](../frontend/STITCH_BRIEF.md), not historical Stitch
`screen.png` files. New runtime UI dependencies: `lucide-react` and
`@xyflow/react` (graph canvas only, dynamically imported). Authenticated
visual snapshots remain **unverified-live**.

## Packet 7 — Canonical remediation amendment and baseline

### Requirement (quoted)

> Record this approved overhaul as additive Phase 8 packets P08-07 through
> P08-23, create `feat/frontend-functional-overhaul`, ADR, action inventory,
> visual contract, and baseline evidence. Do not edit application source,
> migrations, dependencies, or runtime config. Do not uncheck packets 1–6.
> Wrapper status stays pending.

### Concrete acceptance checks

- Plan integrity structural validation passes before `--update`.
- Wrapper `status` remains `pending`.
- Next coding packet is P08-08.
- No application/runtime files changed in this packet.

### Baseline defects (repository inspection, 2026-08-24)

- `packages/core/src/smart_rag_core/settings/backend.py`
  `resolved_checkpoint_dsn()` falls back from `LANGGRAPH_CHECKPOINT_URL` to
  `SUPABASE_DB_URL`.
- `docker-compose.yml` `api` service does not inject
  `LANGGRAPH_CHECKPOINT_URL` or `LIGHTRAG_DB_URL`.
- `apps/backend/src/smart_rag_api/services/sse_stream.py` uses
  `stream_mode="updates"` and can yield `completed` with no `token_delta`.
- Frontend chat can render an empty answer; cancel/feedback helpers currently
  collapse HTTP failure into booleans.
- MFA enroll/challenge routes and AAL2 checks still exist; complete removal is
  an approved planned deviation (P08-11 then P08-12).

### Files in this packet

- Additive Phase 8 packet files 07–23 and `00-visual-contract.md`
- ADR `docs/adr/ADR-frontend-functional-overhaul.md`
- `docs/frontend/action-inventory.json` (baseline dispositions)
- Maintained visual docs under `docs/frontend/`
- Global/Phase 8 contract amendments for MFA deviation, verified-final
  delivery, and P08-09 Phase 6 co-ownership

### Verification

Plan integrity is run after these files land. Application tests are not in
scope for P08-07.

### Unverified

Live `/health/ready` against a running stack was not re-probed in this
documentation packet. Historical empty-answer/reservation symptoms remain
the baseline until P08-08/P08-09.

## Packet 8 — Restore query runtime connectivity and deterministic readiness

### Requirement (quoted)

> Fail fast with a sanitized configuration error when a known
> transaction-pooler DSN is supplied to a session/direct-only
> integration. Do not “fix” this by disabling prepared statements.
> `query_ready=true` when the core Hybrid query path, durable run
> store/checkpointer, and model gateway prerequisites are usable.
> Missing LightRAG may produce a typed degraded dependency.

### Concrete acceptance checks

- Transaction-pooler checkpoint DSN fails closed without leaking the DSN.
- Direct/session DSN is accepted; factories refuse pooler URLs before connect.
- `/health/ready` stays bounded (1s connect probes; browser abort 8000ms).
- Core healthy plus LightRAG unavailable is degraded-but-query-capable.
- `.dockerignore` excludes `.env.local`; frontend image build-args exist.
- Compose injects `LANGGRAPH_CHECKPOINT_URL` and `LIGHTRAG_DB_URL`.

### Files in this packet

- `packages/core/src/smart_rag_core/settings/postgres_dsn.py`
- `packages/core/src/smart_rag_core/settings/backend.py`
- `packages/core/src/smart_rag_core/settings/worker.py`
- `apps/agents/src/smart_rag_agents/ingestion/checkpointer.py`
- `apps/agents/src/smart_rag_agents/query/store.py`
- `apps/agents/src/smart_rag_agents/query/checkpointer.py`
- `apps/backend/src/smart_rag_api/services/readiness.py`
- `docker-compose.yml`
- `apps/frontend/Dockerfile`
- `.dockerignore`
- `.env.example`
- `apps/frontend/src/lib/api.ts` (`HEALTH_READY_TIMEOUT_MS = 8000`)
- `docs/development/CONFIGURATION.md`
- `docs/frontend/THIN_DEVELOPER_UI.md`
- `docs/api/FASTAPI_SECURITY.md`
- unit/contract tests listed below

### Authorization / failure / fallback

- Pooler DSN (`:6543` or `pgbouncer=true`) raises `TransactionPoolerDsnError`
  / `SettingsValidationError` with setting name only. Password and host are
  absent from the exception text.
- Session-mode pooler hosts on port `5432` and local `54322` remain accepted.
- Prepared-statement threshold is unchanged (`prepare_threshold=0`, meaning
  prepare immediately, not disable).
- `query_ready` no longer requires LightRAG attach. Missing LightRAG is
  `status=degraded` with `query_ready=true` when Hybrid, checkpointer,
  Valkey, and real models are healthy. Public `/health/ready` still omits
  named dependencies.
- Checkpointer probe opens `PostgresSaver` and `PostgresStore` without
  `setup()`, applies `app_checkpointer` / `langgraph`, and closes.

### Verification

```text
.\.venv\Scripts\pytest.exe tests/unit/test_postgres_dsn.py tests/unit/test_settings.py tests/unit/test_readiness.py tests/unit/test_dockerignore.py tests/unit/test_fastapi_security.py tests/unit/test_package_imports.py tests/unit/test_backend_middleware.py tests/contract/test_checkpoint_postgres.py::test_checkpointer_factory_never_calls_setup tests/contract/test_checkpoint_postgres.py::test_session_dsn_opens_pinned_saver_and_store -q
```

Result: passing unit/contract tests; live saver/store open skipped when local
Postgres is unreachable (`s`). Ruff on the touched Python files is clean.

### Unverified

- Clean `docker compose build frontend` was not executed in this packet
  (Docker daemon not used). Source tests prove `.dockerignore` and Dockerfile
  ARG/ENV wiring.
- Image layer inspection was not run. Operators should rotate any Vercel
  token that may have lived in an ignored local env file.
- Live `/health/ready` against Compose was not re-probed.

### Rollback

Revert this commit. Hosted processes that already used a session DSN keep
working. Processes that only had a transaction-pooler `SUPABASE_DB_URL` as
the checkpoint fallback will fail closed until `LANGGRAPH_CHECKPOINT_URL` is
set to a session/direct URL.

## Packet 9 — Repair Phase 6 execution durability and verified answer delivery

### Requirement (quoted)

> Persist the admitted user message in existing `app.messages` before
> returning a successful 202. Process memory may cache execution handles
> but must not be the only copy of paid input.
> Consume LangGraph `stream_mode="updates"` as node-keyed envelopes.
> Do not emit the answer node’s draft `answer_text`. Hold the typed
> candidate until the actual verification node completes.
> Emit `completed` only after a non-empty answer/refusal payload has been
> emitted. A successful graph with no answer becomes a safe typed `error`.
> On every terminal path, call the existing reservation true-up/release
> service exactly once.

### Concrete acceptance checks

- Production executor emits status events, at least one non-empty
  `token_delta` after `verify_answer`, then exactly one terminal.
- Draft `answer_text` from `generate_answer` never appears in SSE payloads.
- Empty verified prose becomes `error` `{code: empty_answer}`, never
  `completed`.
- Fixture executors that themselves yield `completed` remain valid.
- Missing process input without a durable loader still emits
  `worker_unavailable` (Phase 6 resume contract).
- Reservation true-up runs at most once per run in-process; dummy test DSNs
  fail closed without crashing the stream.

### Files in this packet

- `supabase/migrations/20260824130000_query_run_messages_runtime_v1.sql`
- `packages/core/src/smart_rag_core/query_admission/messages.py`
- `packages/core/src/smart_rag_core/query_admission/service.py`
  (`fail_query_run`, `load_query_run_runtime`)
- `packages/core/src/smart_rag_core/query_admission/__init__.py`
- `apps/backend/src/smart_rag_api/services/query_sse_mapping.py`
- `apps/backend/src/smart_rag_api/services/sse_stream.py`
- `apps/backend/src/smart_rag_api/services/query_runs.py`
- `apps/backend/src/smart_rag_api/services/http_errors.py`
- `apps/backend/src/smart_rag_api/dependencies/services.py`
- `tests/unit/test_query_sse_mapping.py`
- `tests/unit/test_query_sse_executor.py`
- this evidence file and Phase 6 evidence

### Authorization / failure / fallback / idempotency

- User-message persist uses `app.append_query_message` under `SET ROLE app_api`.
  Failure after admit calls `fail_query_run` (settles the reservation) and
  maps `message_persist_failed` to HTTP 503.
- Reconnect persist is idempotent per `(run_id, role)` unique indexes.
- Resume reconstructs input via `app.load_query_run_runtime`; missing durable
  input stays `worker_unavailable`. Foreign runs remain 404 via existing store
  authorization.
- Executor logs `run_id` only. Answer text is never logged.
- Fallthrough when a production executor emits no terminal is `error`
  `{code: run_failed}`, not synthesized `completed`.

### Verification

```text
.\.venv\Scripts\pytest.exe tests/unit/test_query_sse_mapping.py tests/unit/test_query_sse_executor.py tests/unit/test_sse_protocol.py tests/contract/test_sse_resume.py tests/contract/test_sse_heartbeat.py -q
```

Result: 31 passed, 1 skipped. Ruff `--fix` on the touched stream/test import
blocks is clean. `from smart_rag_core.query_admission import fail_query_run,
load_query_run_runtime, append_query_message` imports.

### Unverified

- Live Postgres RPC round-trip for `append_query_message` /
  `load_query_run_runtime` / `true_up_query_reservation` on a running
  local stack was not executed in this packet.
- Live OpenAI/LangGraph answer generation remains mock-gated.

### Rollback

Revert this commit. SSE resume tests stay on in-memory stores. Applied
migration `20260824130000_query_run_messages_runtime_v1.sql` is additive
(`run_id` on `app.messages` plus RPCs); reverse only with a new down
migration if a follow-up packet requires it.

## Packet 10 — Harden the frontend chat protocol and recovery state

### Requirement (quoted)

> Change mutation helpers such as cancel and feedback from ambiguous
> booleans to typed success payloads or classified thrown errors.
> Store only `{conversationId, runId, lastSequence}` for the active run
> in `sessionStorage`.
> On page reload, fetch the owned run, resume from the durable sequence
> if running, and clear the pointer when terminal/deleted/foreign.
> Treat `completed` without answer/refusal content as a protocol failure.
> Gate paid send on compatible handshake and core `query_ready`.
> Fix caller usage labeling from “Company total” to “Your usage.”

### Concrete acceptance checks

- `cancelRun` / `submitFeedback` return typed JSON or throw
  `ClassifiedApiError`; callers never mark success on HTTP failure.
- Reload reads `GET /runs/{id}` and `GET /conversations/{id}` and resumes
  GET `/runs/{id}/events` without a second paid POST.
- Empty `completed` SSE becomes `terminal=error` with
  `{ kind: "protocol", detail: "empty_answer" }`.
- Terminal SSE `error` / protocol failure banners render in the main
  workspace with run id.
- New Send is blocked when `query_ready` is false; ParadeDB-down Hybrid
  still allows Send.
- Reconnect chrome shows attempt count, next delay, Cancel, and Retry
  after the automatic ceiling.
- Usage strip says “Your usage”, not “Company total”.

### Files in this packet

- `apps/frontend/src/lib/types.ts`
- `apps/frontend/src/lib/api.ts`
- `apps/frontend/src/lib/api.test.ts`
- `apps/frontend/src/lib/handshake.ts`
- `apps/frontend/src/lib/handshake.test.ts`
- `apps/frontend/src/lib/failure-copy.ts`
- `apps/frontend/src/lib/failure-copy.test.ts`
- `apps/frontend/src/lib/chat-view.ts`
- `apps/frontend/src/lib/chat-view.test.ts`
- `apps/frontend/src/lib/chat-pointer.ts`
- `apps/frontend/src/lib/chat-pointer.test.ts`
- `apps/frontend/src/components/chat-app.tsx`
- `apps/frontend/src/components/chat-app.test.tsx`
- `apps/frontend/src/components/chat/chat-composer.tsx`
- `apps/frontend/src/components/chat/run-details-sheet.tsx`
- this evidence file

### Authorization / failure / fallback / idempotency

- Foreign or missing run/conversation GET is 404 → `deleted`; pointer is
  cleared; no transcript fields are invented.
- Cancel/feedback 403/404/422 throw classified errors; feedback form
  values are preserved on failure.
- `402` / `403` / `404` / `409` / `422` / `426` / `429`+Retry-After /
  `503` map to approved banners without traces.
- Idempotency key stays stable until a durable terminal, then rotates.
- sessionStorage pointer never includes tokens, evidence, or answer text.
- Optional BM25/graph degradation does not block Hybrid Send.

### Verification

```text
pnpm test
pnpm typecheck
```

Result (from `apps/frontend`): 33 files, 197 tests passed. `tsc --noEmit`
is clean.

### Unverified

- Browser reload against a live FastAPI/SSE stack was not exercised in
  this packet.
- Real 429 Retry-After from a production limiter was not observed live.

### Rollback

Revert this commit. Chat returns to boolean cancel/feedback helpers and
does not persist a sessionStorage run pointer.

## Packet 11 — Remove backend and database MFA/AAL2 enforcement

### Requirement (quoted)

> Remove every live backend check that requires `aal2`, `mfa_enrolled`, an
> enrolled factor, or an `MFA required` error for upload reserve/finalize,
> offboarding, document administration, or any other route.
> Keep owner/admin/member/viewer roles, upload capability,
> authorization-version reloads, JWT verification, revoked/disabled sessions,
> RLS, rate limits, audit events, destructive confirmations, and IDOR-safe
> errors unchanged.
> Replace AAL2-gated database functions/policies with additive versions or
> compatibility wrappers that preserve existing signatures during the current
> API major while removing only the AAL2 rejection.
> Remove MFA from `GET /me` product semantics. If deleting `mfa_enrolled`
> would break additive API evolution, retain it only as a deprecated
> compatibility field fixed to `false`; no authorization decision may read it.
> This packet may leave the old optional MFA frontend visible for one
> feature-branch commit, but it may not be merged or followed by surface work.
> P08-12 is the mandatory next packet.

### Concrete acceptance checks

- Owner/admin at ordinary authenticated assurance can upload and offboard when
  all non-MFA checks pass.
- Member/viewer forged upload/admin/offboard requests still fail with the same
  403/404 semantics.
- No live backend path emits `MFA required`, checks `aal2`, or authorizes from
  `mfa_enrolled`.
- Existing JWT, revoked-session, role, capability, RLS, rate-limit, audit,
  IDOR, upload, and offboarding tests remain green after updating MFA-positive
  assertions.
- OpenAPI, current types, schema tests, RLS matrix, migration checks, security
  docs, and plan integrity pass.
- Evidence explicitly marks P08-12 as required before any UI packet or merge.

### Files in this packet

- `supabase/migrations/20260824140000_remove_mfa_aal2_enforcement_v1.sql`
- `apps/backend/src/smart_rag_api/services/profile_loader.py`
- `apps/backend/src/smart_rag_api/dependencies/identity.py`
- `apps/backend/src/smart_rag_api/auth_admin/offboarding.py`
- `apps/backend/src/smart_rag_api/auth_admin/mfa_recovery.py`
- `apps/backend/src/smart_rag_api/services/auth_team.py`
- `apps/backend/src/smart_rag_api/routers/auth_team.py`
- `apps/backend/src/smart_rag_api/schemas/fastapi_security.py`
- `packages/core/src/smart_rag_core/security/identity.py`
- `tests/unit/test_profile_loader.py`
- `tests/contract/test_mfa_aal2_removed.py`
- `tests/contract/test_invitations_auth.py`
- `tests/contract/test_upload_quota.py`
- `tests/contract/test_auth_lifecycle.py`
- `tests/contract/test_thin_developer_ui_live.py`
- `docs/api/openapi.foundation.json`
- security/API/admin docs and this evidence file

### Authorization / failure / fallback / idempotency

- `GET /me` always returns `mfa_enrolled: false`. Callers at aal1 with
  `upload_enabled` receive 200, not 403 `MFA required`.
- `app.reserve_upload_quota` still rejects viewers and members without
  `upload_enabled`, still enforces quota, and no longer raises MFA exceptions.
- `app.accept_invitation` still refuses demotion, still revokes sessions on
  privileged/upload upgrades, and ignores deprecated `p_assurance_level`.
- Offboarding still requires an active owner/admin whose asserted role matches
  the live profile; AAL2 is ignored. Members cannot offboard.
- JWT verification, revoked/disabled sessions, RLS, rate limits, audit events,
  and IDOR-safe errors are unchanged.
- Historical applied migrations were not edited. The new migration is additive
  `CREATE OR REPLACE` of the same signatures.

### Verification

```text
py -m ruff check apps/backend/src/smart_rag_api/services/profile_loader.py apps/backend/src/smart_rag_api/dependencies/identity.py apps/backend/src/smart_rag_api/auth_admin/offboarding.py apps/backend/src/smart_rag_api/auth_admin/mfa_recovery.py tests/unit/test_profile_loader.py tests/contract/test_mfa_aal2_removed.py
py -m pytest tests/unit/test_profile_loader.py tests/contract/test_mfa_aal2_removed.py tests/contract/test_invitations_auth.py tests/contract/test_upload_quota.py tests/contract/test_auth_lifecycle.py tests/unit/test_auth_admin_boundaries.py -q
py scripts/ci/check_openapi.py
py .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py
```

Results:

- `ruff check` on the listed backend/core/test modules: all checks passed.
- `pytest` unit: `tests/unit/test_profile_loader.py` and
  `tests/unit/test_auth_admin_boundaries.py` — 7 passed.
- `scripts/ci/check_openapi.py`: snapshot matched after committing the
  `mfa_enrolled` deprecation description.
- Contract tests targeting the new SQL (`test_mfa_aal2_removed`,
  invitations, upload quota, auth lifecycle) skipped: local Supabase
  Postgres is not bound on `127.0.0.1:54322` (`supabase start` failed
  because Windows reserved the port). SQL behavior is implemented in
  `20260824140000_remove_mfa_aal2_enforcement_v1.sql` and covered by
  those tests when the local database is available.

### Unverified

- Live GoTrue TOTP enroll is no longer required for upload; the remaining live
  reserve test still accepts an aal2 token as a non-blocking extra path when
  TOTP is configured.
- Frontend MFA screens remain visible until P08-12. This packet must not merge
  without P08-12.
- Local Supabase was not running (port 54322 reserved by Windows), so SQL
  contract tests skipped. Re-run them after a successful supabase start.

### Rollback

Revert this commit. Recreate MFA/AAL2 only with a new additive migration; do
not edit `20260824140000_remove_mfa_aal2_enforcement_v1.sql` after apply.

### Handoff blocker

P08-12 is mandatory next. Do not start UI surface packets and do not merge this
feature branch until frontend/provider MFA is removed.

## Packet 12 — Remove frontend/provider MFA and finish single-factor Auth

### Requirement (quoted)

> Remove `/mfa/enroll` and `/mfa/challenge` routes, forms, QR generation, challenge
> verification, recovery helpers/copy, navigation, callbacks, and unavailable-gap
> routing. Omit Google OAuth while disabled; do not render a disabled button.
> Disable TOTP enrollment/challenge in local Supabase configuration only through
> a documented supported setting. For managed Supabase, write a dry-run-first
> operator procedure using only documented provider settings/admin APIs.

### Concrete acceptance checks

- Sign-in, sign-up, reset/callback, invitation accept, revoked-session return,
  and sign-out have no MFA route or challenge.
- No production import expects TOTP/MFA product behavior.
- Google chrome is omitted (helper remains, `enabled=false`).
- Local `supabase/config.toml` sets `[auth.mfa.totp] enroll_enabled=false` and
  `verify_enabled=false` (documented CLI keys).
- Managed residue uses Auth Admin `mfa.listFactors` / `mfa.deleteFactor` only;
  SQL against `auth.mfa_factors` is forbidden. Limits are stated honestly.
- Invitation accept lives under the Auth layout at `/invitations/accept` and
  stays authenticated (`isPublicAuthPath` is false).

### Files in this packet

- `supabase/config.toml`
- deleted `apps/frontend/src/app/(auth)/mfa/enroll/page.tsx`
- deleted `apps/frontend/src/app/(auth)/mfa/challenge/page.tsx`
- deleted `apps/frontend/src/lib/auth/totp-qr.ts`
- deleted `apps/frontend/src/lib/auth/mfa-recovery.ts`
- `apps/frontend/src/app/(auth)/invitations/accept/page.tsx` (moved from console)
- `apps/frontend/src/components/auth/auth-screens.tsx`
- `apps/frontend/src/components/chat-app.tsx`
- `apps/frontend/src/components/profile-app.tsx`
- `apps/frontend/src/components/documents/import-source-sheet.tsx`
- `apps/frontend/src/lib/api.ts`, `types.ts`, `failure-copy.ts`, `auth/copy.ts`,
  `auth/paths.ts`, `auth/google.ts`
- Auth/API/chat/e2e tests and visual MFA snapshots removed
- `docs/frontend/action-inventory.json`
- `docs/runbooks/managed-auth-totp-residue.md`
- Auth/frontend docs, ADR note, skills, this evidence file

### Authorization / failure / fallback / idempotency

- `classifyApiError` no longer has an `mfa` kind. Leftover `403 MFA required`
  sanitizes to generic `auth` / `unauthorized`.
- `fetchMe` ignores deprecated `mfa_enrolled`. Profile UI does not render it.
- Upload 403 is generic rejection copy, not TOTP challenge.
- Chat has no MFA gate, `/mfa/challenge`, or `/mfa/enroll` links.
- Sign-in omits Google. `maybeSignInWithGoogle(false, ...)` still does not
  call `signInWithOAuth`.
- `/mfa/*` is not a public Auth path; unauthenticated visits redirect to login.
- GAP-07-07 remains a generic Unavailable page without recovery-code controls.
- Compensating controls (JWT verify, revoked sessions, RLS, quotas, role
  checks) stay server-side from P08-11.

### Verification

```text
npm test -- src/lib/api.test.ts src/lib/auth/auth.test.ts src/components/auth/auth-screens.test.tsx src/components/chat-app.test.tsx src/lib/prohibited-patterns.test.ts src/lib/handshake.test.ts
```

Results:

- Vitest: 6 files, 87 passed (Auth/API/chat/handshake/prohibited-patterns).
- Local `auth.mfa.totp.enroll_enabled` / `verify_enabled` are false.
- TOTP QR/recovery modules deleted; no remaining production import.

### Unverified

- Playwright e2e not re-run in this packet (no MFA snapshots remain; login
  spec now asserts `/mfa/challenge` redirects and Google count is 0).
- Hosted Auth Admin `listFactors`/`deleteFactor` not executed against a live
  project; the runbook is dry-run-first and forbids SQL deletion.
- Local Supabase still not bound on `127.0.0.1:54322` (Windows reserved
  port). P08-11 SQL contract tests remain skipped until `supabase start`.
- `npx tsc --noEmit` after `npx next typegen`: passed (stale .next validators for deleted MFA routes were regenerated).
- Full frontend Vitest: 33 files, 195 passed.
- `tests/unit/test_phase07_stitch_states.py` and brief: 7 passed.
- `verify_plan_integrity.py --update`: 100 canonical files.

### Rollback

Revert this commit. Restoring TOTP UI without restoring backend AAL2 gates
(P08-11) would be a product lie. Do not SQL-delete factors as a rollback.

### Handoff

P08-11 + P08-12 MFA removal is complete. UI surface packets P08-13+ may start.
Do not merge this branch until remaining Phase 8 remediation packets finish.

## Packet 13 — Implement exact design tokens and reusable primitives

### Requirement (quoted)

> Implement the exact styling architecture, color, typography, spacing, geometry,
> elevation, focus, motion, and responsive values in the normative UI/UX
> specification. Do not approximate or substitute framework defaults. Extend
> existing primitives before creating alternatives. Add `PageHeader`,
> `PrimaryAction`, `AsyncButton`, and `ConfirmDialog` only where an equivalent
> does not exist. Do not edit app navigation, routes, or feature-page
> composition in this packet.

### Concrete acceptance checks

- `:root` in `apps/frontend/src/app/globals.css` and
  `apps/frontend/src/lib/design-tokens.ts` carry the visual-contract palette,
  40px controls, 8px control radius, 12px card radius, 48px rows, Inter stack,
  and 2px/2px focus ring.
- CSS-source geometry tests lock those values (jsdom does not apply CSS modules).
- `Button` pending/disabledReason blocks duplicate submits; `ConfirmDialog`
  traps focus, focuses Cancel for danger, and ignores Escape while pending.
- No second token table, Google Fonts CDN, or overlay blur.

### Files in this packet

- `apps/frontend/src/app/globals.css`
- `apps/frontend/src/lib/design-tokens.ts`
- `apps/frontend/src/lib/design-tokens.test.ts`
- `apps/frontend/src/lib/geometry.test.ts`
- `apps/frontend/src/lib/contrast.test.ts` (existing AA pairs re-run)
- `apps/frontend/src/components/ui/ui.module.css`
- `apps/frontend/src/components/ui/button.tsx`
- `apps/frontend/src/components/ui/page-header.tsx`
- `apps/frontend/src/components/ui/confirm-dialog.tsx`
- `apps/frontend/src/components/ui/index.ts`
- `apps/frontend/src/components/ui/primitives.test.tsx`
- `docs/frontend/design-tokens-and-primitives.md`
- this evidence file

### Authorization / failure / fallback / idempotency

- Disabled/pending is visual only; it is not an authorization boundary.
- Pending confirm blocks overlay click, Escape, and a second confirm.
- Hostile fixtures in primitives tests remain React text nodes.
- No route/nav rewrite; no invented API.

### Verification

```text
npx vitest run src/lib/design-tokens.test.ts src/lib/geometry.test.ts src/lib/contrast.test.ts src/components/ui/primitives.test.tsx
npx vitest run
npx tsc --noEmit
```

Results:

- Targeted Vitest: 4 files, 14 passed.
- Full frontend Vitest: 34 files, 200 passed.
- `npx tsc --noEmit`: passed.
- ESLint on touched TS/TSX: 0 errors (pre-existing unused `ReactElement` warning in primitives tests).

### Unverified

- jsdom `getComputedStyle` does not apply CSS modules; geometry is locked from
  stylesheet source rather than computed pixels in the unit runner.
- Playwright visual snapshots and 390/1280 layout proof wait for P08-21/22.
- Live browser contrast at 390px/1280px was not re-measured with a meter;
  token hex pairs still meet WCAG AA in `contrast.test.ts`.

### Rollback

Revert this commit. Feature packets must not reintroduce a second palette,
lavender canvas, teal-as-canvas, overlay blur, or Google Fonts CDN.

### Handoff

P08-13 tokens and primitive extensions are complete. P08-14 may compose the
streamlined shell on top of these primitives without mixing Ask/Documents
body rewrites into that packet.
