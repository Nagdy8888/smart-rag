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
