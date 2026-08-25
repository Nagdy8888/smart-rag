---
title: Phase 8 frontend integration evidence
owner: engineering-lead
status: draft
last-reviewed: 2026-08-25
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

## P08-14 — Build the streamlined role-aware shell and routes

Quoted requirement: compose the final information architecture on top of
P08-13 without mixing Ask/Documents/Tables/Graph body rewrites into the
shell packet.

### Acceptance checks

- One shell: 232px desktop rail, 72px collapsed rail, 56px topbar, mobile nav sheet.
- Primary nav order Ask, Documents, Tables, Graph.
- One Admin item only when live `GET /me.role` is owner/admin (convenience).
- Account in one topbar menu: live `/me` fields, upload state, Sign out; never `mfa_enrolled`.
- `Link`/router only; no internal `window.location.assign`.
- Command menu: supported routes plus Sign out.
- One shell readiness popover; retired `/review-fixtures` and `/unavailable/*` 404.
- `/team|/tools|/curation|/usage` redirect to `/admin?tab=...`; `/profile` to `/account`.

### Changed paths

- `apps/frontend/src/lib/shell-navigation.ts` (+ test)
- `apps/frontend/src/components/ui/app-nav.tsx` (+ test)
- `apps/frontend/src/components/ui/app-shell.tsx` / `app-shell.module.css` / `app-shell.test.tsx`
- `apps/frontend/src/components/ui/command-menu.tsx`, `menu.tsx`, `readiness-indicator.tsx`
- `apps/frontend/src/components/admin-workspace.tsx`
- `apps/frontend/src/app/(console)/admin/page.tsx`, `account/page.tsx`
- Redirect pages: `team`, `tools`, `curation`, `usage`, `profile`
- Deleted: `(auth)/review-fixtures`, `(auth)/unavailable/[gap]`
- `apps/frontend/src/proxy.ts`, `lib/auth/paths.ts`
- e2e specs, `docs/frontend/action-inventory.json`, AUTH/ADMINISTRATION docs

### Authorization / failure / fallback / idempotency

- Admin nav uses live `GET /me.role` via `isOwnerOrAdmin`. Members do not see Admin.
- Forged member clients can still open `/admin`; FastAPI remains the denial boundary.
- Retired product paths skip the login redirect so they 404 instead of bouncing to `/login`.
- Account menu never renders `mfa_enrolled`.
- `window.location.assign` is absent from `apps/frontend/src`.
- Command palette remounts on each open so filter/active index reset without setState-in-effect.

### Verification

```text
npx vitest run src/lib/shell-navigation.test.ts src/lib/auth/auth.test.ts src/components/ui/app-shell.test.tsx src/components/ui/app-nav.test.tsx
npx vitest run
npx next typegen
npx tsc --noEmit
npx eslint src/components/ui/command-menu.tsx src/components/ui/app-nav.tsx
```

Results:

- Targeted Vitest: 4 files, 8 passed.
- Full frontend Vitest: 36 files, 206 passed.
- `npx next typegen`: types generated.
- `npx tsc --noEmit`: passed.
- ESLint on command menu/nav after remount fix: 0 errors.

### Unverified

- Playwright journeys in this packet were updated but not executed here (P08-21/22).
- 390/768/1024/1280 keyboard proof in a real browser waits for P08-21/22.
- Live owner-vs-member Admin visibility against a running API waits for P08-22.

### Deviations

- Readiness popover blocking copy uses the visual-contract sentence rather than
  `QUERY_NOT_READY_COPY` (handshake still uses the latter for Ask send gating).
- `ReadinessPanel` remains in the tree as an unmounted helper; only the
  review-fixtures route that mounted it was removed.

### Rollback

Revert this commit. Restore `/review-fixtures` and `/unavailable/[gap]` only if
a later packet proves those routes are still required contracts.

### Handoff

P08-14 shell and routes are complete. P08-15 may rebuild Ask without changing
the rail/topbar IA. Do not reintroduce Team/Tools/Curation/Usage/Profile as
primary nav items.

## P08-15 — Rebuild Ask around verified final answers

Quoted requirement: produce a focused RAG workspace using only real
conversation/run/SSE contracts and the explicit verified-final-delivery
decision.

### Acceptance checks

- Two-region desktop layout: 248px Sessions rail at `>=1280px`; mobile Sessions sheet; no permanent sources column.
- Sessions use `GET /conversations`. New, Continue (`GET /conversations/{id}`), and Delete are real. Continue clears local transcript and states prior messages are unavailable.
- Prompt chips fill the composer only and never POST.
- Sticky composer with one Send/Stop control, Enter to send, Shift+Enter newline, IME-safe.
- Real stages only. Generating then Verifying, then immediate verified `token_delta` insertion. No caret/typewriter.
- Safe text with `dir="auto"`. Delivered text kept on later failure/cancel.
- Citation chips for real IDs; one provenance drawer; no fake preview/download.
- Diagnostics collapsed in Run details. No Hybrid/Combined/Table/Inspect send controls and no nDCG/TTFB.
- Feedback only after a terminal non-empty answer, using the server tag catalog.
- Polite live regions for progress/answer; assertive banners for blocking errors.

### Changed paths

- Moved `apps/frontend/src/components/chat-app.tsx` once to `apps/frontend/src/components/chat/chat-app.tsx`
- `apps/frontend/src/components/chat/answer-surface.tsx`, `chat-composer.tsx`, `conversation-rail.tsx`, `feedback-popover.tsx`, `run-progress.tsx`, `chat-workspace.tsx`, `chat.module.css`
- `apps/frontend/src/components/chat-app.test.tsx`, `core-rag-surfaces.test.tsx`
- `apps/frontend/src/app/(console)/page.tsx`
- e2e heading updates: `core-rag-surfaces.spec.ts`, `visual-routes.spec.ts`
- `docs/frontend/CORE_RAG_SURFACES.md`, `AUTH_AND_STREAMING.md`, `PHASE8_JOURNEY_MATRIX.md`, `action-inventory.json`

### Authorization / failure / fallback / idempotency

- Continue validates `GET /conversations/{id}` before selecting the session; classified API failures surface in the existing failure banner.
- Send remains handshake/`query_ready` gated. Draft clears only after successful admission.
- Stop posts `POST /runs/{id}/cancel` without `X-Client-Version`.
- Empty-success `completed` still maps to the protocol `empty_answer` error in `chat-view`.
- Feedback is hidden until a terminal answer with text; submit uses the existing ten-tag catalog.

### Verification

```text
npx vitest run src/components/chat-app.test.tsx
npx vitest run
npx tsc --noEmit
npx eslint src/components/chat src/components/chat-app.test.tsx
```

Results:

- Targeted Vitest: 1 file, 14 passed (chip fill, Continue GET, Generating then Verifying then verified answer, Stop cancel, no Hybrid/Combined/Inspect send).
- Full frontend Vitest: 36 files, 209 passed.
- `npx tsc --noEmit`: passed.
- ESLint on Ask components/tests: 0 errors.

### Unverified

- Playwright journeys were retargeted from "Auto chat" to "Ask" but not executed here (P08-21/22).
- Live Generating/Verifying against a running executor waits for P08-22.
- 390/1280 visual snapshots of Ask empty/generating/verifying/completed wait for P08-21/22.

### Deviations

- `GET /conversations` returns a single page with no cursor, so Sessions has no Load more control.
- Shared `CitationChip` still labels `Citation {n}` rather than `[n] Source`; chips still open the real sources drawer.
- Give feedback is the post-terminal trigger; thumbs/tag/comment live inside that popover instead of always-visible footer thumbs.

### Rollback

Revert this commit. Restore `apps/frontend/src/components/chat-app.tsx` only if a later packet proves the unscoped path is still required.

### Handoff

P08-15 Ask is complete. P08-16 may rebuild Documents without changing the shell IA or Ask body.

## P08-16 — Rebuild Documents as one complete ingestion workflow

Quoted requirement: make document ingestion, status, pagination, and
deletion understandable and fully backed by existing APIs.

### Acceptance checks

- One responsive list/table with name, visibility, search/graph status, created, and overflow actions.
- Frontend `DocumentResponse` includes existing FastAPI `created_at`. No backend schema/router edit.
- Keyset pagination uses the real `created_at,id` cursor and page-length continuation. No invented `next_cursor`.
- Local filter is labeled as filtering loaded rows.
- `IngestionStatus` is shared: compact pills on the list (after Load status), timeline on detail.
- Upload remains reserve → Storage JWT → finalize with one stable idempotency key until success. Stages are real; no simulated percentages.
- Website crawl is owner/admin convenience, keeps one retry key, and exposes current API depth/pages.
- Retry is shown only when `retry_allowed`.
- `DELETE /documents/{id}` is wired behind “Delete document?” confirmation; 204/403/404/429 handled; list/detail invalidated; detail navigates safely.
- `DOCUMENT_DELETE_UNAVAILABLE`, source preview/download, and unsupported GAP panels are removed from Documents.

### Changed paths

- Moved `apps/frontend/src/components/document-library.tsx` and `document-detail.tsx` once under `apps/frontend/src/components/documents/`
- `apps/frontend/src/components/documents/document-list.tsx`, `ingestion-status.tsx`, `ingestion-inspector.tsx`, `processing-timeline.tsx`, `import-source-sheet.tsx`, `documents.module.css`, `document-library.test.tsx`
- `apps/frontend/src/lib/api.ts`, `types.ts`, `ingestion-status.ts`, `citation-drawer.ts`
- Tests: `api.test.ts`, `core-rag-surfaces.test.tsx`, `core-rag-helpers.test.ts`, `prohibited-patterns.test.ts`, `ingestion-status.test.ts`
- Docs: `CORE_RAG_SURFACES.md`, `PHASE8_JOURNEY_MATRIX.md`, `API_UI_MAPPING.md`, `action-inventory.json`

### Authorization / failure / fallback / idempotency

- Delete is owner/admin convenience only. Member list has no Delete item. Server 403 maps to “You cannot delete this document.” 404 maps to “Document not found.” or safe navigation from detail. 429 maps to retry copy.
- Upload is handshake-gated. Duplicate submit is pending-blocked; the same idempotency key is reused until success.
- Crawl 403/422/429 are classified `ClassifiedApiError` kinds `auth` / `validation` / `rate`. Members still do not see the Website tab.
- Pagination appends unique `document_id`s and hides Load more when the page is short or `created_at` is missing.
- Version polling stops when the inspector is closed, the tab is hidden, the status is terminal, or the tree unmounts.

### Verification

```text
npx vitest run src/components/documents/document-library.test.tsx src/components/core-rag-surfaces.test.tsx src/lib/api.test.ts src/lib/ingestion-status.test.ts
npx vitest run
npx tsc --noEmit
npx eslint src/components/documents src/lib/api.ts src/lib/ingestion-status.ts src/lib/citation-drawer.ts src/components/core-rag-surfaces.test.tsx
```

Results:

- Targeted Vitest: 4 files, 81 passed (upload idempotency, handshake-disabled Upload, crawl 403, delete 204/403, keyset append, detail graph seed, 404 navigation).
- Full frontend Vitest: 37 files, 226 passed.
- `npx tsc --noEmit`: passed.
- ESLint on Documents/API files: 0 errors.

### Unverified

- Playwright Documents populated / Import source / Document detail snapshots wait for P08-21/22.
- Live reserve → Storage JWT → finalize against a running stack waits for P08-22.

### Deviations

- List search/graph pills stay em dash until `GET /ingestion/versions/{id}/status` is loaded. The list HTTP body has no status fields; Ready is never inferred from upload.
- Compact pills keep the last loaded version after the inspector closes so polling can stop without inventing a list-status API.
- Import empty-state and header both expose “Import source” when import is allowed.

### Rollback

Revert this commit. Restore the previous Documents GAP copy only if a later packet reverts `DELETE /documents/{id}` wiring.

### Handoff

P08-16 Documents is complete. P08-17 may rebuild Tables without changing Documents contracts.

## P08-17 — Rebuild deterministic Tables

Quoted requirement: retain bounded structured-table analysis while removing
unsupported controls and isolating this surface from Graph work.

### Acceptance checks

- URL `tableId` / `documentId` preselects only a manifest returned by `GET /tables`.
- Guided `TableQueryPlan` covers columns, filters, aggregations, group by, sort, and comparison. No SQL editor.
- One Analyze primary action. The exact posted plan stays visible on 403/422/429/server failure.
- Deterministic rows render first. Display sort is labeled as not changing the submitted plan.
- Provenance drawer lists document/version/table/sheet/range. No fake source link.
- Export/Save/Share are absent. Unknown columns and SQL-shaped values are rejected before POST.
- Empty manifests: “No structured tables are available.” Empty success: “The analysis returned no rows.”
- Graph files were not edited.

### Changed paths

- Moved `apps/frontend/src/components/tables-app.tsx` once to `apps/frontend/src/components/tables/tables-app.tsx`
- `apps/frontend/src/components/tables/analysis-plan.tsx`, `analysis-results.tsx`, `tables.module.css`, `tables-app.test.tsx`
- `apps/frontend/src/app/(console)/tables/page.tsx`
- `apps/frontend/src/lib/table-plan.ts`, `table-plan.test.ts`, `api.ts`
- `apps/frontend/src/components/ui/data-table.tsx` optional numeric `align`
- Document Open tables href seeds `?documentId=`
- Tests: `core-rag-surfaces.test.tsx`, `api.test.ts`, `document-library.test.tsx`
- Docs: `CORE_RAG_SURFACES.md`, `PHASE8_JOURNEY_MATRIX.md`, `API_UI_MAPPING.md`, `STITCH_BRIEF.md`, `STITCH_STATES.md`, `action-inventory.json`

### Authorization / failure / fallback / idempotency

- `listTables` and `analyzeTable` throw `ClassifiedApiError`. 400 `table_plan_rejected` maps to `validation`.
- Inaccessible `tableId` stays unselected even when `documentId` matches another row.
- Client compile rejects unknown column ids and SQL/path-shaped values before fetch.
- Result keys that are not internal identifiers are omitted.
- Analyze POST body remains `{ plan }` with extra SQL keys omitted. Duplicate submit is pending-blocked.
- `/tables` never renders Export.

### Verification

```text
npx vitest run src/components/tables/tables-app.test.tsx src/lib/table-plan.test.ts src/components/core-rag-surfaces.test.tsx src/lib/api.test.ts src/components/documents/document-library.test.tsx
npx vitest run
npx tsc --noEmit
npx eslint src/components/tables src/lib/table-plan.ts src/lib/api.ts src/components/ui/data-table.tsx src/components/core-rag-surfaces.test.tsx
```

Results:

- Targeted Vitest: 5 files, 99 passed (URL preselect, unknown column/SQL before POST, 403 plan preservation, provenance drawer, no Export, empty manifests, list 403).
- Full frontend Vitest: 38 files, 245 passed.
- `npx tsc --noEmit`: passed.
- ESLint on Tables/API files: 0 errors.

### Unverified

- Playwright Tables snapshots wait for P08-21/22.
- Live `POST /tables/analyze` against a running stack waits for P08-22.

### Deviations

- `GET /tables` has no column schema. Allow-listed columns are internal identifier regex plus operator/aggregation enums, not workbook headers.
- Manifest picker Select is shown below 1024px; the sidebar stays in the DOM and is hidden with CSS.
- Chat prompt-chip test now waits for the chip instead of the Ask heading so it does not match the restoring-session chrome.

### Rollback

Revert this commit. Restore `apps/frontend/src/components/tables-app.tsx` only if a later packet proves the unscoped path is still required.

### Handoff

P08-17 Tables is complete. P08-18 may rebuild Graph without changing Tables contracts.

## P08-18 — Rebuild bounded Graph inspection

Quoted requirement: retain graph evidence inspection while removing the
duplicate custom SVG and unsupported relationship editing.

### Acceptance checks

- Entity search submits only when trimmed `q` length is at least 1.
- Selecting a search hit adds a chip; Inspect graph is a separate POST.
- URL `?documentId=` seeds inspect without requiring chips.
- Depth Select is 1/2/3. Entity chips cap at 12 with helper copy. Results cap at 200.
- List is the default. Canvas is optional `@xyflow/react`. The custom SVG neighborhood is gone.
- Inspector shows Type, Object ID, Document ID, Version ID, Chunk ID, Hop, Support, locators, and signed limitation copy. ACL blindness ignores `count`.
- Empty inspect: “No authorized graph evidence matched this inspection.”
- No Edit, Add relationship, Export, or Save. Mixed-direction labels render as text.
- Tables files were not edited in this packet.

### Changed paths

- Moved `apps/frontend/src/components/graph-explorer.tsx` once to `apps/frontend/src/components/graph/graph-explorer.tsx`
- `apps/frontend/src/components/graph/entity-search.tsx`, `graph-list-fallback.tsx`, `graph-inspector.tsx`, `graph-canvas.tsx`, `graph.module.css`, `graph-explorer.test.tsx`
- `apps/frontend/src/app/(console)/graph/page.tsx`
- `apps/frontend/src/lib/graph-client.ts`, `graph-client.test.ts`, `api.ts`, `api.test.ts`
- Tests: `core-rag-surfaces.test.tsx`
- Docs: `CORE_RAG_SURFACES.md`, `PHASE8_JOURNEY_MATRIX.md`, `API_UI_MAPPING.md`, `STITCH_BRIEF.md`, `STITCH_STATES.md`, `action-inventory.json`

### Authorization / failure / fallback / idempotency

- `searchGraphEntities` and `inspectGraph` throw `ClassifiedApiError`. Inspect 400 maps to `validation`; 403 is `auth`.
- Inspect 403 keeps selected chips and shows classified copy.
- ACL blindness never interpolates unauthorized counts. Graph outage is distinct from Graph Pending.
- Inspect POST is pending-blocked. Duplicate SVG and relationship-edit chrome are absent rather than disabled.
- Canvas is not an editor (`nodesConnectable={false}`, `deleteKeyCode={null}`). No MiniMap.

### Verification

```text
npx vitest run src/components/graph/graph-explorer.test.tsx src/lib/graph-client.test.ts src/components/core-rag-surfaces.test.tsx src/lib/api.test.ts
npx vitest run
npx tsc --noEmit
npx eslint src/components/graph src/lib/graph-client.ts src/lib/api.ts src/components/core-rag-surfaces.test.tsx
```

Results:

- Targeted Graph Vitest: 8 GraphExplorer tests passed; graph-client and API inspect 403 passed.
- Full frontend Vitest: 39 files, 254 passed.
- `npx tsc --noEmit`: passed after `BackgroundVariant.Dots`.
- ESLint on Graph/API files: 0 errors.

### Unverified

- Playwright Graph snapshots wait for P08-21/22.
- Live `POST /graph/inspect` against a running stack waits for P08-22.
- React Flow canvas rendering in jsdom is not asserted; Canvas tab is toggled and the duplicate SVG is proven absent.

### Deviations

- Inspect payloads have no edge list. The canvas does not invent edges; hop/support stay on nodes.
- Fit lives with labeled zoom controls on the canvas, not as a third toolbar button beside List/Canvas.
- Compact inspector uses `matchMedia("(max-width: 1279px)")` so jsdom (no `matchMedia`) keeps the dock only and avoids duplicate inspector copy in tests.

### Rollback

Revert this commit. Restore `apps/frontend/src/components/graph-explorer.tsx` only if a later packet proves the unscoped path is still required.

### Handoff

P08-18 Graph is complete. P08-19 may consolidate Admin without changing Graph contracts.

## P08-19 — Consolidate Admin and supported Account operations

Quoted requirement: replace four top-level management routes and dead settings
panels with one compact role-aware admin workspace after the final
single-factor model.

### Acceptance checks

- `/admin` tabs are Team & access, Tools, Curation, and Usage. Tabs update
  `?tab=` and remain keyboard-operable.
- Owner/admin invite, offboard, tool enable/permissions, glossary, and
  entity-rule mutations run without MFA/AAL2 copy.
- Member/viewer never see Admin in nav. Direct `/admin` confirms with
  `GET /admin/graph/entity-rules` and shows “You don’t have access.” on 403.
- Stale entity-rule PATCH `row_version` shows recoverable 409 and Reload rule.
- `listTools` URL-encodes `q`. Ordinary Tools UI has no seed form.
- Usage shows caller/company totals only. No budget slider, audit panel, or
  `*-unavailable` GAP chrome.
- Account renders four `/me` fields. No profile editor, locale editor, or
  company-settings save.
- Hostile invitation email remains an input text value, not HTML.

### Changed paths

- Moved once: `admin-workspace.tsx` → `apps/frontend/src/components/admin/admin-app.tsx`;
  `team-app.tsx` → `admin/team-access-panel.tsx`; `tools-app.tsx` →
  `admin/tools-panel.tsx`; `curation-app.tsx` → `admin/curation-panel.tsx`;
  `usage-app.tsx` → `admin/usage-panel.tsx`; `profile-app.tsx` →
  `admin/account-panel.tsx`
- `apps/frontend/src/app/(console)/admin/page.tsx`, `account/page.tsx`
- `apps/frontend/src/lib/api.ts`, `api.test.ts`, `types.ts`, `query-keys.ts`,
  `admin-bodies.ts`
- Tests: `administration-surfaces.test.tsx`,
  `apps/frontend/tests/e2e/administration-surfaces.spec.ts`
- Docs: `ADMINISTRATION.md`, `PHASE8_JOURNEY_MATRIX.md`, `API_UI_MAPPING.md`,
  `STITCH_BRIEF.md`, `STITCH_STATES.md`, `admin-and-auth-screens.md`,
  `action-inventory.json`, `docs/README.md`

### Authorization / failure / fallback / idempotency

- Admin gate is a real 403 from `listEntityRules`, not client-only hiding.
- `createInvitation` / `offboardUser` / `enableTool` remain callable; FastAPI
  still 403s forged roles. Offboard posts Bearer only (no MFA step).
- `patchEntityRule` classifies 409 `stale_row_version`. UI offers Reload rule.
- Tool search uses `encodeURIComponent` on `q`.
- Unsupported bootstrap, budget, audit, profile-editor, company-settings, and
  member-directory chrome are omitted, not permanent-disabled Unavailable
  panels.

### Verification

```text
npx vitest run src/components/administration-surfaces.test.tsx src/lib/api.test.ts src/lib/admin-bodies.test.ts src/lib/shell-navigation.test.ts
npx vitest run
npx tsc --noEmit
npx eslint src/components/admin "src/app/(console)/admin/page.tsx" "src/app/(console)/account/page.tsx" src/lib/api.ts src/lib/query-keys.ts src/lib/types.ts src/lib/admin-bodies.ts src/components/administration-surfaces.test.tsx src/lib/api.test.ts
```

Results:

- Targeted Admin Vitest: 4 files, 83 passed (12 administration-surfaces).
- Full frontend Vitest: 39 files, 260 passed.
- `npx tsc --noEmit`: passed.
- ESLint on Admin/API files: 0 errors.

### Unverified

- Playwright Admin snapshots and live owner mutations wait for P08-21/22.
- Keyboard Home/End on Admin tabs is implemented; a dedicated keydown case
  is not asserted beyond URL tab clicks.

### Deviations

- Admin access is confirmed with `GET /admin/graph/entity-rules` because that
  list is already owner/admin-only. Members hitting `/usage` or `/tools`
  bookmarks redirect into `/admin` and receive the same 403 ErrorState.
- `GET /me` may still emit deprecated `mfa_enrolled=false`. Account does not
  render it.
- `POST /admin/tools` seed remains an API helper; the Tools tab has no seed
  form.

### Rollback

Revert this commit. Restore unscoped `*-app.tsx` files only if a later packet
proves those paths are still required.

### Handoff

P08-19 Admin is complete. P08-20 may enforce action-inventory, accessibility,
CSP, and documentation integrity without restoring MFA, bootstrap, budget,
audit, or seed chrome.

## P08-20 — Enforce action, accessibility, security, and documentation integrity

Quoted requirement: apply the cross-cutting quality contract after all final
surfaces and paths exist.

### Acceptance checks

- Unique `data-action-id` values match `docs/frontend/action-inventory.json`.
- Keep actions name an existing test file and a failure/authorization state.
- Removed-target IDs are absent from production source.
- CSS-source geometry locks buttons, inputs, pills, dialogs, nav, topbar, and
  table rows. Playwright measures login controls at 390/768/1024/1280 with no
  page overflow.
- GAP Unavailable pages, bootstrap chrome, and duplicate ingestion wrappers
  are omitted rather than disabled.
- Hostile text, CSP, and prohibited-pattern suites remain green.
- Docs and Phase 6 P08-09 evidence stay synchronized.

### Changed paths

- `scripts/check_frontend_action_inventory.py`, `scripts/check.py` docs tier
- `tests/unit/test_frontend_action_inventory.py`
- `docs/frontend/action-inventory.json`
- Action IDs on Auth, Ask, Documents, Admin, and shell skip link
- Removed `UnavailableGap`, `readiness-panel.tsx`,
  `ingestion-inspector.tsx`, `processing-timeline.tsx`
- `apps/frontend/src/lib/geometry.test.ts`,
  `apps/frontend/tests/e2e/quality-audit.spec.ts`,
  `visual-routes.spec.ts`, `phase08-journeys.spec.ts`,
  `prohibited-patterns.test.ts`
- Docs: `A11Y_SECURITY_IMPLEMENTATION.md`, `AUTH_AND_STREAMING.md`,
  `DESIGN_SYSTEM.md`, `PHASE8_JOURNEY_MATRIX.md`, `docs/README.md`,
  `docs/development/phase-06-agent-intelligence-evidence.md`

### Authorization / failure / fallback / idempotency

- Inventory keep rows require a non-placeholder `failure_state` except
  local-state controls.
- Invitation accept no longer renders owner-bootstrap GAP copy.
- `/unavailable/*` remains a 404. Auth tests prove recovery and bootstrap
  chrome are absent on Sign in.

### Verification

```text
py -3 scripts/check_frontend_action_inventory.py
.\.venv\Scripts\pytest.exe tests/unit/test_frontend_action_inventory.py tests/unit/test_check_runner.py -q
npx vitest run
npx tsc --noEmit
npx eslint src/components/auth src/components/chat src/components/admin src/components/documents src/components/ui/app-shell.tsx src/lib/geometry.test.ts src/lib/prohibited-patterns.test.ts
.\.venv\Scripts\ruff.exe check scripts/check_frontend_action_inventory.py scripts/check.py tests/unit/test_frontend_action_inventory.py
```

Results:

- Action inventory: verified (64 actions).
- Pytest: inventory + check-runner passed.
- Full frontend Vitest: 39 files, 260 passed.
- `npx tsc --noEmit`: passed.
- ESLint and Ruff: 0 errors.

### Unverified

- Playwright `quality-audit.spec.ts` login geometry waits for P08-21
  Chromium. Signed-in overflow still skips when FastAPI is down.
- `uv run python scripts/check.py --tier docs` Mermaid rendering waits for
  P08-21.

### Deviations

- Desktop nav remains the shipped `232px` token, not the historical 280px
  Stitch column. Geometry tests lock the CSS variable and Playwright live
  width together.
- Login primary remains the 40px control height used by `Button`; Auth does
  not switch to `buttonLarge` 44px.
- Authenticated unmapped-action audit allows unlabeled overflow Menu/Actions
  chrome; primary shipped submits use inventory IDs.

### Rollback

Revert this commit. Restoring `UnavailableGap` or ingestion wrapper files
would reintroduce GAP chrome and duplicate status UI.

### Handoff

P08-20 quality integrity is complete. P08-21 may run deterministic release
gates, including docs Mermaid and Playwright Chromium.

## P08-21 — Run deterministic release gates

Quoted requirement: isolate repeatable CPU and local checks from
credentialed stack verification so failures are attributable and the
weak-model run remains bounded.

### Acceptance checks

- Production executor test binds
  `create_model_gateway(mock_model_mode=True)` and maps generate/verify
  node output. An SSE fixture that injects `token_delta` events is
  insufficient.
- Record command, exit code, duration, and test count for every listed
  gate.
- Do not run the real OpenAI provider.
- Do not claim production-like verification.

### Changed paths

- Production executor proof:
  `tests/unit/test_query_graph_runtime.py`
  (`test_bound_mock_gateway_drives_sse_without_token_injection`)
- Windows table sandbox start:
  `packages/core/src/smart_rag_core/tables/limits.py`
  (`TABLE_WORKER_WINDOWS_STARTUP_SECONDS = 7.0`),
  `executor.py`, `sandbox_worker.py` (DuckDB parquet load),
  `tables/__init__.py` (lazy exports)
- Windows walk isolation:
  `tests/contract/docstring_scanner.py`,
  `tests/contract/boundary_scanner.py`,
  `tests/unit/test_collect_runtime_shared_libs.py`
  (skip `node_modules` / undici junctions)
- Environment-boundary reads via `get_process_environ` in agents,
  parser launcher, and hybrid/BM25 release helpers
- Migrations allowlist:
  `scripts/ci/check_migrations.py` adds
  `20260824130000_query_run_messages_runtime_v1.sql` and
  `20260824140000_remove_mfa_aal2_enforcement_v1.sql`
- Frontend build: Suspense around `useSearchParams` on
  `documents/page.tsx` and `tables/page.tsx`
- Playwright local reuse of an existing `:3010` Next process when `CI`
  is unset; Auth skip link `data-action-id="shell.skip"`;
  live sign-in uses `getByRole("textbox", { name: "Password" })`
- Docs lint and Mermaid quote/reserved-id fixes under `docs/`
- Nested helper docstrings required by the contract scanner

### Authorization / failure / idempotency / fallback

- `test_bound_mock_gateway_drives_sse_without_token_injection` constructs
  `QueryGraphDeps.model_gateway` from `create_model_gateway` with
  `mock_model_mode=True`, runs `generate_answer_node` and
  `verify_answer_node`, then maps real chunk output through
  `QuerySseMapper`. Token events are not injected by the test fixture.
- Unbound Hybrid stays `insufficient_evidence`. Unbound gateway with
  Hybrid stays `verified_partial` / `model_gateway_unbound`.
- Table `statement_deadline` is still 3.0s on Linux. Windows only adds
  process-start allowance; the two structured-table unit tests passed
  in the recorded unit tier and in an isolated file run (6429 ms).
- Local Playwright reuses `:3010` only when `CI` is unset so a leftover
  developer-console Next process does not fail the frontend tier. CI
  still starts a fresh server.

### Verification

Host: Windows PowerShell, repo root, `.\.venv\Scripts\python.exe`.
`MOCK_MODEL_MODE=true` for unit and contract. No real OpenAI calls.

| Gate | Command | Exit | Duration (ms) | Counts |
| --- | --- | --- | --- | --- |
| format | `.\.venv\Scripts\python.exe scripts/check.py --tier format` | 0 | 642 | 778 files already formatted |
| lint | `.\.venv\Scripts\python.exe scripts/check.py --tier lint` | 0 | 643 | Ruff all checks passed |
| types | `.\.venv\Scripts\python.exe scripts/check.py --tier types` | 1 | 35926 | Pyright ratchet 0 to 340 (+340). Documented pre-existing deviation. Second pyright command did not run after ratchet fail. |
| unit | `$env:MOCK_MODEL_MODE='true'; .\.venv\Scripts\python.exe scripts/check.py --tier unit` | 0 | 44444 | 1038 passed, 3 skipped, 7 warnings. Isolated `test_structured_table.py` 6429 ms, exit 0. |
| contract | `$env:MOCK_MODEL_MODE='true'; .\.venv\Scripts\python.exe scripts/check.py --tier contract` | 1 | 590769 | 8 failed, 415 passed, 21 skipped, 7 warnings. Live stack failures, not CPU fixtures. |
| docs | `.\.venv\Scripts\python.exe scripts/check.py --tier docs` | 0 | 313491 | markdownlint 0 issues in 186 files; Mermaid and links OK; action inventory verified |
| frontend | `.\.venv\Scripts\python.exe scripts/check.py --tier frontend` | 1 | 90402 | ESLint 0 errors; typegen OK; `tsc --noEmit` OK; Vitest 39 files / 260 passed; `next build` 20 routes. Playwright then failed because `:3010` was already bound (`reuseExistingServer` was false). |
| frontend Playwright retry | `pnpm --filter smart-rag-frontend exec playwright test` with `CI` unset | 1 | 25935 | 28 passed, 7 failed of 35. Signed-in and visual journeys remain P08-22. |
| OpenAPI | `.\.venv\Scripts\python.exe scripts/ci/check_openapi.py` | 0 | 3334 | snapshot matches |
| migrations | `.\.venv\Scripts\python.exe scripts/ci/check_migrations.py` | 0 | 163 | 63 reviewed files after allowlisting the two P08-09/11 migrations |
| git diff --check | `git diff --check` | 0 | 155 | CRLF warnings only; no conflict markers |
| secret scan | `docker run --rm -v "${PWD}:/repo" ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f detect --source=/repo --config=/repo/.gitleaks.toml --no-banner --redact` | 1 | 1160247 | 134 commits, ~158.66 MB in 19m19s. 7 `generic-api-key` findings. Values not printed. |

Contract failures (live Postgres/API, hand off to P08-22):

- `tests/contract/test_bm25_reconcile.py::test_reconcile_upsert_verify_fail_does_not_complete_outbox`
- `tests/contract/test_hybrid_fusion.py::test_live_bm25_recheck_drops_restricted_before_fusion`
- `tests/contract/test_hybrid_retrieval.py::test_bm25_typed_query_and_injection`
- `tests/contract/test_query_run_admission.py::test_over_budget_and_concurrency_cap_reject_without_reservation`
- `tests/contract/test_rls_matrix.py::test_runtime_roles_are_non_privileged_and_schema_isolated`
- `tests/contract/test_schema_reset.py::test_schema_fingerprint_covers_reset_determinism_contract`
- `tests/contract/test_thin_developer_ui_live.py::test_upload_enabled_aal1_can_reserve_without_mfa`
- `tests/contract/test_thin_developer_ui_live.py::test_live_public_ready_omits_named_dependencies`

Playwright failures after the locator and skip-link fixes (not claimed as
production-like):

- visual `login-desktop` pixel ratio 0.04 greater than 0.03; authenticated
  route snapshots are absent on this host
- signed-in mobile menu, usage 403 copy, Ask heading strict mode, Ask
  unmapped-action audit, compact brand visibility

### Unverified

- Full-repo Pyright remains red (340 errors vs baseline 0 recorded
  2026-08-16 on 417 files). Phase 5 already records this as a standing
  types-tier deviation. This packet did not treat the 340 as a new
  overhaul regression and did not raise the baseline.
- Eight live contract tests failed against the partial local stack. The
  database was not reset or migrated in this packet.
- Playwright Chromium signed-in and visual journeys failed. This is not
  production-like stack, role, or real-answer proof.
- Real OpenAI was not invoked.
- Secret scan exit 1 with 7 `generic-api-key` hits, all in historical
  commits: two inert `sk-canarysecretFORBID` unit canaries (same family
  as the existing LangSmith allowlist; paths now allowlisted), one empty
  example env key name, one Phase 10 capability token name, and three
  Phase 9 image-digest JSON lines. No live provider values were printed.
  A follow-up redacted scan after allowlist edits was not re-run (19 min
  Windows bind-mount). Do not treat the repository as secret-clean.

### Deviations

- Types tier exit 1 is an approved documented pre-existing deviation,
  not a P08-21 waiver of `FAST_TIERS` membership or of the zero
  baseline file.
- Contract and frontend Playwright exits are recorded as failed, not
  skipped. They belong to P08-22 credentialed/visual verification.
- `TABLE_WORKER_WINDOWS_STARTUP_SECONDS` is 7.0. The Linux 3.0s SQL
  bound is unchanged.
- Local Playwright `reuseExistingServer` is `!process.env.CI`.
- Secret scan exit 1 is recorded, not waived. Two inert canary paths were
  added to `.gitleaks.toml`. The other five hits are historical
  example/digest/name matches. The 19-minute scan was not repeated.

### Rollback

Revert this commit. Restoring token-injecting SSE fixtures as the
production-executor proof, or removing the Windows table start
allowance without a replacement, would break the P08-21 attribution
split.

### Handoff

P08-21 deterministic CPU and local static gates are recorded. Wrapper
item 21 may be checked. Item 7 stays unchecked. Items 1-6 stay checked.
P08-22 owns live contract repair, signed-in Playwright, visual
baselines, and one bounded real-provider answer. Do not claim
production-like verification from this packet.

## P08-22 — Run production-like stack, role, visual, and real-answer verification

**Status: BLOCKED.** Wrapper item 22 stays unchecked. Packet YAML stays
`pending`. P08-23 may not merge.

Quoted requirement: prove the application against the real local topology
and one bounded provider call. Required: Docker, local Supabase/Compose,
valid OpenAI credential, and available query budget. The query must show
real Generating/Verifying, then a non-empty verified answer or grounded
refusal, at least one durable `token_delta`, exactly one terminal, and
correct settlement.

### Acceptance checks

- Live Generating/Verifying (`li.pipelineStep[data-active="true"]`), not
  the static pipeline labels.
- Non-empty verified answer or grounded refusal.
- Durable `token_delta`, exactly one terminal, correct settlement.
- Role journeys pass, or the packet stays explicitly blocked.

### Prerequisite checks (no secret values)

| Check | Result |
| --- | --- |
| Docker Engine | 29.6.1, up |
| Process `OPENAI_API_KEY` | Not required; compose/API key length 164, not `sk-unit` |
| `MOCK_MODEL_MODE` in API container | `false` |
| Holdout | `SMART_RAG_HOLDOUT_ACCESS` absent |
| Local budget | Member profile monthly 200 USD; month spend 0 |
| Corpus | 0 documents; grounded refusal would have been acceptable |

### Topology

`.env.compose` still points documented compose interpolation at hosted
Supabase and a `:6543` pooler. Files were not rewritten. API/worker were
rebuilt from HEAD `218ee48` and recreated with process-env local session
DSNs (`host.docker.internal:54321` / `:54322` as `app_runtime`). In-container
DSN hosts after recreate:

- `SUPABASE_URL` host `host.docker.internal` port `54321`
- `SUPABASE_DB_URL` / checkpoint / LightRAG host `host.docker.internal` port `54322`
- Never `:6543` after the pin

The first running image still contained the literal `MFA required` in
`identity.py`. Host source does not. Rebuild was required before admit.

`GET /health/live` 200 `live`. `GET /health/ready` 200
`query_ready=true`. `GET /api/meta` 200 handshake `0.1.0` / `1` / `0.1.0`.
Member `GET /ops/ready` 403.

Rebuilt worker is unhealthy: `parser_sandbox_docker_required`. Ask
execution is API-side; ingestion is not proven.

### Admit reproduce (local JWT)

`_tmp_p08_22_admit.py` (not committed): admin create 200, password grant
200, `POST /conversations` 201, `POST /messages` 202, `run_id` present,
`route_family=composite`, `reconnect=false`. Local `127.0.0.1:54322`
counts: conversations 1, messages 1, runs 1, `run_by_id` 1.

### Bounded browser query

Frontend `http://127.0.0.1:3010` with local `NEXT_PUBLIC_*`. Member
`p08-22-browser-8d480fb455@example.com`. Ready. New session. Question:
`What documents are in the corpus?`

| Step | Result |
| --- | --- |
| `POST /conversations` | 201 `29a65e3f-c8e5-44c0-b334-e74df8127aa1` |
| `POST .../messages` | 202 `run_id=952d26fd-4c19-4fab-bcac-4c135854c772` |
| `GET /runs/.../events?after=0` | 200 |
| UI terminal | `error` / `run_failed` |
| UI copy | generic “Something went wrong.” |
| Pipeline `data-active` Generating/Verifying | Not observed; collapsed “Run status” after error |
| Local `token_delta` | 0 |
| Local terminals | 1 (`error`) |
| `app.run_events` types | `schema,error` |
| `app.llm_usage` | 0 rows, 0 tokens, 0 USD |

API log: `query.sse.started` then `sse.executor_failed` 14 ms later.
Persisted payload `{"code":"run_failed"}` (sanitized; exception type is
not in the public event). Treating 202/SSE 200/generic error as a
successful chat outcome is forbidden.

### Authorization / failure / fallback

- Member `/ops/ready` 403. Proven.
- Public `/health/ready` omits named dependencies. Proven.
- Empty-success 202 without a local run is no longer the defect after
  rebuild+pin. The remaining defect is immediate production-executor
  failure after durable admit.
- Worker parser-sandbox crash does not explain the 14 ms API executor
  failure by itself.

### Unverified / not run

- Role Playwright journeys and 390/1280 visual baselines.
- Reconnect/resume, cancel, 402/403/426/429, revoked session,
  BM25/graph degradation.
- Clean image-layer secret inspection beyond `test_dockerignore.py`
  (already recorded in P08-21).
- Exception type/message for `sse.executor_failed` (logger extra
  `error_type` is not present in the JSON line).
- Live contract 8 failures and Playwright 28/7 from P08-21.

### Deviations

- Did not rewrite `.env.compose`. Used process-env local overlay.
- Did not `reset.ps1`.
- Rebuilt api/worker because the previous image still enforced MFA.
- One bounded browser query after the pin. No second provider retry.
- Host `:3010` used for Ask; compose frontend `:3000` was not the
  signed-in surface.

### Rollback

Leave local Supabase and Compose up. Recreating api/worker without the
local process-env overlay returns them to hosted `:6543`. Do not attach
LightRAG to the hosted pooler. Do not check wrapper item 22.

### Handoff

P08-22 is **BLOCKED**. Do not mark the packet complete. P08-23 may open
a PR but must not merge. Next owner: identify the 14 ms
`sse.executor_failed` after `query.sse.started` on the rebuilt API
(first LangGraph `astream` tick), then repeat one bounded Ask query
until Generating/Verifying, a verified answer or grounded refusal,
`token_delta`, and one non-error terminal are durable on local `54322`.

## P08-22 hosted-runtime amendment (2026-08-25)

Historical evidence above used a local `54322` overlay and remains a
test-fixture record. It is not the current operator path.

Accepted ADR:
[ADR-hosted-runtime-local-test-fixture.md](../adr/ADR-hosted-runtime-local-test-fixture.md).

Binding contract language now requires hosted `smart-rag` for runtime
Auth/Postgres/Storage. Local Supabase is a labelled destructive-test
fixture only. P08-22 live proof is hosted Auth/Postgres plus laptop
Compose sidecars. Chat rows must be durable on hosted Postgres and
absent from local `:54322`.

Implementation in this change:

- Compose interpolation fails closed without hosted `SUPABASE_URL`,
  `API_SUPABASE_DB_URL`, `WORKER_SUPABASE_DB_URL`,
  `LANGGRAPH_CHECKPOINT_URL`, and frontend public Auth values.
- `scripts/dev.ps1` no longer starts or resets local Supabase.
- Query `astream` uses `AsyncPostgresSaver`; ingestion keeps the sync
  saver.
- Chat `run_failed` renders one generic alert plus at most one run
  reference.

Wrapper item 22 stays unchecked until the hosted browser proof below
records live Generating/Verifying, a durable `token_delta`, exactly one
terminal, hosted settlement, and absence of those IDs on local
`:54322`.

### Hosted proof actuals (2026-08-25)

Hosted project `smart-rag` (`qsjivtwtmlmtksufqjik`) was missing
`app.append_query_message` and `app.messages.run_id`. Applied existing
repo migration `query_run_messages_runtime_v1` via Supabase MCP
`apply_migration` (one apply, no parallel). `messages.run_id` and the
four query-message RPCs are now present.

Runtime topology (redacted): Auth `*.supabase.co`; API SQL transaction
pooler `:6543`; worker/checkpoint/LightRAG session `:5432`.
`GET /health/ready` 200 `query_ready=true`. Worker parser-sandbox
restart is separate; chat runs in the API process.

| Probe | Result |
| --- | --- |
| API admit `POST /messages` | 202; SSE 200 |
| Hosted API run `ddefe043-eae1-46ef-9eb8-14c55e2246c2` | conversations=1 messages=2 (user+assistant) runs=1 status=`partial` events=22 `token_delta`=1 checkpoints=13 |
| Hosted browser run `78f354b6-dd57-4ebf-b5ff-8b2b3dcfda8f` | status=`partial` `token_delta`=1 events include `token_delta,deadline,partial` |
| Local `:54322` for both run IDs | conversations=0 messages=0 runs=0 events=0 checkpoints=0 |
| Reservation | `remaining_usd` changed vs amount (true-up). `app.llm_usage` rows=0 |
| Browser `http://127.0.0.1:3000` | Hosted password grant 200; Ask signed in; Service readiness Ready |
| Live pipeline | `li[data-active="true"]` **Generating** observed. Stage `generate_answer / verified_partial`. Heartbeats 6. No user-visible `run_failed` |
| Verifying `data-active` | **Not observed.** UI stayed on Generating through `verified_partial` |
| Terminals | Protocol emits `deadline` then `partial` (mapper `_emit_verified`). Two catalog terminal types, one close sequence |

Remaining P08-22 blocks (do not check wrapper item 22):

1. Live Verifying `data-active="true"` was not captured.
2. `app.llm_usage` settlement rows stay 0.
3. UI `Terminal` can remain `running` after hosted `partial` is durable.
4. Hosted schema still lacks later repo names
   (`ingestion_status_acl_v1` through `lightrag_chunk_map_vendor_chunk_uq_v1`,
   `remove_mfa_aal2_enforcement_v1`).

Executor repairs proven on this path: async query checkpointer (13
checkpoints), temporal `SET ROLE app_api` (hosted pooler cannot become
`postgres`), idle context-loader for `retrieval_transaction`, generate
timeout from run deadline not model-call count.
