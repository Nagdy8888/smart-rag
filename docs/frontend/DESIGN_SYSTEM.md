---
title: Production console design system
owner: engineering-lead
status: draft
last-reviewed: 2026-08-25
audience: frontend, reviewers
packet: P08-01
---

# Design system (Phase 8 packet 1)

Build-time tokens and typed primitives for the production console shell.
Canonical hex, type, radius, and motion values are the Ink & Indigo refresh
in [ADR-ink-indigo-visual-refresh.md](../adr/ADR-ink-indigo-visual-refresh.md)
(user-approved 2026-08-25). That ADR supersedes the Precision Workspace
table in [STITCH_BRIEF.md](./STITCH_BRIEF.md). Stitch `screen.png` files
are historical references, not the live composition target. The Stitch
export remains a **template, not a layout**: there is no `frame_00` route
and no design-system gallery page. See
[VISUAL_MAP.md](./VISUAL_MAP.md) and
[ADR-stitch-first-ux.md](../adr/ADR-stitch-first-ux.md).

Related: [ADR-ink-indigo-visual-refresh.md](../adr/ADR-ink-indigo-visual-refresh.md) ·
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
| `ADR-ink-indigo-visual-refresh.md` | Accepted visual deviation from Precision Workspace |
| `apps/frontend/src/app/globals.css` `:root` | CSS implementation |
| `apps/frontend/src/lib/design-tokens.ts` | TypeScript copy for tests |
| Tailwind `@theme` | Maps variables to utilities (`bg-page`, `text-brand`) without a second hex table. Do not re-bind `--color-ink` here. |

`DESIGN.md` YAML (`#faf8ff`, `#004ac6`), prose 10px radius, teal `#0F766E`
as canvas/accent, and gallery `backdrop-filter` are **rejected**. Do not
reintroduce them.

## Tokens

| Token | Value |
| --- | --- |
| `--color-bg` | `#F6F7F9` |
| `--color-surface` | `#FFFFFF` |
| `--color-surface-muted` | `#F1F3F6` |
| `--color-text` | `#101828` |
| `--color-text-muted` | `#667085` |
| `--color-border` | `#E4E7EC` |
| `--color-accent` | `#4F46E5` |
| `--color-accent-fg` | `#FFFFFF` |
| `--color-ink` | `#0F1420` |
| `--color-danger` | `#B91C1C` |
| `--color-warning` | `#A16207` |
| `--color-success` | `#166534` |
| `--color-focus` | `#4F46E5` (2px solid ring, offset 1px) |
| `--radius-control` / `--radius-sm` | `10px` |
| `--radius-card` / `--radius-md` | `14px` |
| `--space` | `4px` grid |
| `--shadow-1` | `0 1px 3px rgb(16 24 40 / 0.10)` |
| `--shadow-2` | `0 12px 32px rgb(16 24 40 / 0.14)` |
| `--shadow-composer` | `0 8px 24px rgb(16 24 40 / 0.12)` |
| `--font-sans` | `"Inter", "Segoe UI", "IBM Plex Sans Arabic", "Noto Naskh Arabic", sans-serif` |
| `--font-display` | `"Inter Display", Inter, "Segoe UI", sans-serif` |
| `--font-mono` | `ui-monospace, "Cascadia Code", monospace` |
| `--line-height-ar` | `1.75` |
| `--line-height-en` | `1.5` |
| `--nav-width` | `232px` |
| `--row-height` | `48px` |
| `--motion-fast` | `150ms ease-out` |
| `--motion-drawer` | `200ms ease-out` |

Light scheme only. Motion honors `prefers-reduced-motion`. Fonts are
self-hosted Inter plus Inter Display SemiBold under
`apps/frontend/public/fonts`. No Google Fonts CDN and no `next/font/google`.
`--gradient-brand` is allowed only on the auth brand panel, empty-state
icon tile, and nav logo tile.

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
- Component tests missing DOM: `*.test.tsx` files need
  `// @vitest-environment jsdom`.
