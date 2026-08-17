---
title: Phase 8 frontend integration evidence
owner: engineering-lead
status: draft
last-reviewed: 2026-08-17
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
| `pnpm exec playwright test` (cwd `apps/frontend`) | 0 (25 passed, 4 skipped) |
| `uv run python -m pytest tests/unit/test_phase08_journey_matrix.py -q` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (118 markdown files, 0 lint issues; links + Mermaid render) |

`uv run python scripts/check.py --tier frontend` was not run as one process.
The frontend-tier commands above are the same vector `check.py` uses
(lint, typegen, tsc, vitest, build, playwright), invoked separately.

Playwright skips (live FastAPI/Auth down; same assertions exist in Vitest):

- `browser readiness panel matches live GET /health/ready`
- `authenticated Auto chrome when a session exists`
- `stubbed document 404 shows Not found without a title`
- `stubbed company usage 403 stays forbidden copy when signed in`

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

- Local GoTrue sign-in / MFA verify / aal2 upload (no test-auth bypass)
- Live FastAPI `/health/ready` panel match
- Authenticated Playwright Auto chrome, document 404, company-usage 403
- `tests/contract/test_thin_developer_ui_live.py` (FastAPI+Auth HTTP, not Next chrome)
- Abandoned / expired / oversize quarantine as distinct public JSON enums
  (version status prints the server `status` string; those labels are not
  invented)
- Live WCAG lab measurement of every computed style
- Hosted Auth throttling (GAP-07-20 / Phase 10)

Existing live HTTP proof to keep citing:
`tests/contract/test_thin_developer_ui_live.py` talks to FastAPI+Auth, not
Next chrome.

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
| `docs/frontend/PHASE8_JOURNEY_MATRIX.md` | Created |
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
| `@supabase/ssr` Auth: sign-in/up, Google disabled, reset/callback, invitation accept, MFA enroll/challenge, lost-factor GAP-07-07, owner bootstrap GAP-07-08, revoked sessions, upload MFA; no client authz shortcut | **proven** in Vitest; **unverified-live** against local GoTrue |
| Handshake blocks unsupported clients before paid work | **proven** (9.0.0 stub + 426 POST) |
| Typed SSE clients tolerate unknown additive events | **proven** |
| Idempotent submit, sequenced reconnect, heartbeat, cancel, route correction, deadline/partial, BM25 degrade, LightRAG `graph_outage`, figure/media, temporal, ACL, summary, negation, citations without snippets, inference GAP-07-02 copy, table provenance, diagnostics, feedback chrome, generic errors | **proven** in unit/component |
| Document upload/quota/crawl/quarantine/scan/parse/BM25/Hybrid-Graph/backlog/retry/version/anomaly/deletion journeys | **proven** for mapped contracts; **unverified-live** Storage JWT upload; abandoned/expired/oversize are not distinct public enums |
| Graph explorer, tables, tools, curation, team, usage/budget/rate, restricted audit GAP-07-12, profile, company settings enforce roles | **proven** in component tests; **unverified-live** FastAPI mutations |
| Responsive LTR/RTL, ACME logical highlight, keyboard/skip/reduced-motion, WCAG AA tokens, CSP, strict escaping, XSS fixtures | **proven** |
| Playwright unauth + public stubs for roles chrome, MFA recovery, API skew, BM25 copy, Graph/ACL (component), RTL fixtures, restricted audit (component) | **proven**; authenticated Playwright **unverified-live** |
| No mock data, test-auth bypass, `dangerouslySetInnerHTML`, or unescaped retrieved markup | **proven** |

### Phase 9 handoff blockers

- User acceptance of this Phase 8 exit record
- Optional: run `test_thin_developer_ui_live.py` and authenticated Playwright
  when local FastAPI + GoTrue are up
- Do not start Phase 9 local release-candidate load/eval until accepted
