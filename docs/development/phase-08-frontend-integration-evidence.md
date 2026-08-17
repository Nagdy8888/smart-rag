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
`pending`.

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

- Playwright 1280Ã—800: `app-shell-nav` computed width **280px**; skip link
  `href="#main"`; Console â†’ `/`.
- Playwright 390Ã—844: nav stacks above `#main` (nav `y` < main `y`, width
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

- XSS filename and `</script>Ø´Ø±ÙƒØ©` remain text nodes.
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
