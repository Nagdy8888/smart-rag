---
title: Production console design system
owner: engineering-lead
status: draft
last-reviewed: 2026-09-25
audience: frontend, reviewers
packet: P08-01
---

# Design system (Phase 8 packet 1)

Build-time tokens and typed primitives for the production console shell.
Canonical hex, type, radius, and motion values are the quiet work-tool refresh
in [ADR-quiet-tool-visual-refresh.md](../adr/ADR-quiet-tool-visual-refresh.md)
(accepted 2026-09-25). Motion is documented in [motion.md](./motion.md). That ADR supersedes Ink & Indigo and the Precision Workspace
table in [STITCH_BRIEF.md](./STITCH_BRIEF.md). Stitch `screen.png` files
are historical references, not the live composition target. The Stitch
export remains a **template, not a layout**: there is no `frame_00` route
and no design-system gallery page. See
[VISUAL_MAP.md](./VISUAL_MAP.md) and
[ADR-stitch-first-ux.md](../adr/ADR-stitch-first-ux.md).

Related: [ADR-quiet-tool-visual-refresh.md](../adr/ADR-quiet-tool-visual-refresh.md) ·
[motion.md](./motion.md) ·
[STITCH_BRIEF.md](./STITCH_BRIEF.md) ·
[STITCH_REVIEW.md](./STITCH_REVIEW.md) ·
[VISUAL_MAP.md](./VISUAL_MAP.md) ·
[THIN_DEVELOPER_UI.md](./THIN_DEVELOPER_UI.md) ·
[AUTH_AND_STREAMING.md](./AUTH_AND_STREAMING.md) ·
[CORE_RAG_SURFACES.md](./CORE_RAG_SURFACES.md) ·
[phase-08 evidence](../development/phase-08-frontend-integration-evidence.md) ·
[docs index](../README.md)

## Source of truth

| Layer | Role |
| --- | --- |
| `ADR-quiet-tool-visual-refresh.md` | Accepted visual system. Ink & Indigo is superseded |
| `apps/frontend/src/app/globals.css` `:root` | CSS implementation |
| `apps/frontend/src/lib/design-tokens.ts` | TypeScript copy for tests |
| Tailwind `@theme` | Maps variables to utilities (`bg-page`, `text-brand`) without a second hex table. Do not add a second ink or brand hex here. |

`DESIGN.md` YAML (`#faf8ff`, `#004ac6`), prose 10px radius, teal `#0F766E`
as canvas/accent, and gallery `backdrop-filter` are **rejected**. Do not
reintroduce them.

## Tokens

| Token | Value |
| --- | --- |
| `--color-bg` | `#F7F7F5` |
| `--color-surface` | `#FFFFFF` |
| `--color-surface-muted` | `#F2F2EF` |
| `--color-text` | `#1D1D1B` |
| `--color-text-muted` | `#6B6B66` |
| `--color-border` | `#E3E3DF` |
| `--color-primary` | `#1D1D1B` (ink primary button) |
| `--color-accent` | `#3B5B8C` (slate blue) |
| `--color-evidence` | `#0A6F6E` (citations only) |
| `--color-danger` | `#B91C1C` |
| `--color-warning` | `#A16207` |
| `--color-success` | `#166534` |
| `--color-focus` | `#3B5B8C` (2px solid ring, offset 1px) |
| `--radius-control` / `--radius-sm` | `6px` |
| `--radius-card` / `--radius-md` | `8px` |
| `--radius-lg` | `10px` |
| `--space` | `4px` grid |
| `--shadow-1` | `none` |
| `--shadow-2` | `0 8px 24px rgb(29 29 27 / 0.12)` |
| `--font-sans` | `"IBM Plex Sans", "IBM Plex Sans Arabic", "Segoe UI", "Noto Naskh Arabic", sans-serif` |
| `--font-mono` | `ui-monospace, "Cascadia Code", "SFMono-Regular", Consolas, monospace` |
| `--line-height-ar` | `1.75` |
| `--line-height-en` | `1.5` |
| `--nav-width` | `232px` |
| `--row-height` | `48px` |
| `--motion-fast` | `150ms cubic-bezier(0.22, 1, 0.36, 1)` |
| `--motion-drawer` | `200ms ease-out` |

Light scheme only. `html` sets `color-scheme: only light` so Windows and
Microsoft Edge do not restyle native controls, scrollbars, or autofill
when the OS is in dark mode. Do not set `-webkit-font-smoothing:
antialiased` on `body`: DirectWrite already hints IBM Plex, and antialiased
thins glyphs. Buttons and text fields use `appearance: none` and inherit
IBM Plex Sans. The shell and the centered auth form use `100vh` then `100dvh`. Scrollbars stay
thin and light. Motion honors `prefers-reduced-motion`. Fonts are
self-hosted IBM Plex Sans and IBM Plex Sans Arabic under
`apps/frontend/public/fonts`. No Google Fonts CDN and no `next/font/google`.
There are no gradients. Primary buttons use the ink fill. The nav rail is
tinted `--color-surface-muted`. Empty states are left-aligned and borderless.

## Shell metrics

```mermaid
flowchart LR
  skip["Skip to main"]
  skip --> auth["Auth card layout"]
  skip --> nav["Nav 232px desktop"]
  nav --> topbar["Top bar"]
  topbar --> main["Main landmark"]
  nav --> drawer["Mobile nav drawer"]
  main --> product["Stitch-first product surfaces"]
  product --> diagnostics["Collapsible diagnostics"]
```

- English chrome (`lang="en"`, `dir="ltr"`).
- User/content strings: `dir="auto"` plus `unicode-bidi: isolate`.
- Codes, IDs, URLs: `dir="ltr"` isolate.
- Desktop (1280): navigation column `232px`, collapsing to `72px` between
  1024px and 1279px. Tonal `shadow-1` / `shadow-2` on overlays only.
- Mobile (390): authenticated nav is a Menu drawer; login has **no** console
  nav and the sign-in card fits the first viewport.
- List and table rows: minimum `48px`. Mobile controls: minimum `44px`.

Authenticated nav lists Ask, Documents, Tables, Graph, optional Admin, and
Account. Hidden items are not HTTP 403.
See `CLIENT_NAV_IS_NOT_AUTHORIZATION` in
`apps/frontend/src/lib/client-authorization.ts`. Public Auth routes use
`(auth)` layout; console routes use `(console)` layout.

## Primitives

Typed components live in `apps/frontend/src/components/ui/`:

`AppShell`, `StatusBanner`, `StatusPill`, `CitationChip`,
`LimitationCallout`, `LiveRegion`, `Button`, `Badge`, `Input`, `Textarea`,
`FileDropZone`, `DataTable`, `Spinner`, `Skeleton`, `EmptyState`,
`ErrorState`, `Icon`, `UserText`, `CodeText`.

Focus is the global `:focus-visible` 2px accent ring. Untrusted strings
pass through `displayText` as React text nodes.

Primitives plus the application shell implement Stitch composition for
contract-backed routes. They do not add placeholder routes or Stitch HTML.

## Prohibited patterns

Do not ship: Tailwind CDN, Google Fonts CDN, Material Symbols CDN, inline
event-handler scripts, `innerHTML` / `dangerouslySetInnerHTML`, `href="#"`,
`backdrop-filter` / `blur(`, placeholder avatars, `Math.random()` as live
diagnostics or auth, gitignored Stitch imports, `code.html`, or frame
routes.

## Failure modes

| Failure | Behavior |
| --- | --- |
| Token drift between brief, CSS, and TS | `design-tokens.test.ts` fails |
| CDN, blur, or `innerHTML` in source | `prohibited-patterns.test.ts` fails |
| Hostile filename/entity in a primitive | Renders as text; `img` count stays 0 |
| Hidden nav item | UI convenience only; FastAPI still authorizes |
| Tailwind PostCSS missing | Production build fails closed |

## Verification

```text
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend exec next typegen
pnpm --filter smart-rag-frontend exec tsc --noEmit
pnpm --filter smart-rag-frontend test
pnpm --filter smart-rag-frontend build
pnpm --filter smart-rag-frontend exec playwright test tests/e2e/design-system.spec.ts tests/e2e/login.spec.ts tests/e2e/visual-routes.spec.ts
uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json
```

## Troubleshooting

- Nav not 232px: confirm `globals.css` `--nav-width` and
  `app-shell.module.css` desktop media query (`min-width: 801px`).
- Geist / Google Fonts returning: `layout.tsx` must not import
  `next/font` loaders; CSP `font-src 'self'` forbids CDN hosts.
- Thin gray type or dark native widgets in Edge on Windows: confirm
  `globals.css` uses `color-scheme: only light`, does not set
  `-webkit-font-smoothing: antialiased` on `body`, and resets form
  `appearance` plus autofill.
- Component tests missing DOM: `*.test.tsx` files need
  `// @vitest-environment jsdom`.
