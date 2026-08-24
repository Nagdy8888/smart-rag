---
phase: 8
packet: 14
status: pending
title: "Build the streamlined role-aware shell and routes"
requirement_ids: [P08-14]
---

# Packet 14 — Build the streamlined role-aware shell and routes

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-13 primitives exist. Do not rewrite Ask/Documents/Tables/Graph bodies here.

## Allowed outputs

Shell, nav, account menu, command menu, readiness popover, redirects, removal of review-fixtures/unavailable routes.

## Forbidden outputs

Feature-page rebuilds. Rendering mfa_enrolled. Internal window.location.assign. Client-only authorization.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-14 — Build the streamlined role-aware shell and routes

Purpose: compose the final information architecture on top of P08-13 without mixing feature-page rewrites into the shell packet.

Primary files:

- [`apps/frontend/src/components/ui/app-shell.tsx`](apps/frontend/src/components/ui/app-shell.tsx)
- [`apps/frontend/src/components/ui/app-nav.tsx`](apps/frontend/src/components/ui/app-nav.tsx)
- [`apps/frontend/src/components/ui/command-menu.tsx`](apps/frontend/src/components/ui/command-menu.tsx)
- route layouts/pages, role/query providers, redirects, shell tests/docs, and action inventory.

Implementation:

- Build one responsive shell with the specified 232px desktop rail, deliberate 72px collapsed rail, 56px topbar, and mobile navigation sheet.
- Primary nav order is Ask, Documents, Tables, Graph. Show one Admin item only when live `/me.role` is owner/admin; server authorization remains authoritative.
- Put Account in one topbar menu/drawer showing only supported live `/me` fields, upload state, and Sign out. Never render `mfa_enrolled`.
- Use `Link`/router APIs for internal navigation and remove internal `window.location.assign`.
- Limit the command menu to supported routes and real Sign out.
- Centralize readiness in one shell indicator/popover with core availability and authorized operator probes; remove duplicate page-level readiness panels.
- Add stable `data-action-id` values and inventory entries for every shell action.
- Redirect `/team`, `/tools`, `/curation`, and `/usage` to `/admin?tab=...`; redirect `/profile` to the supported Account destination.
- Remove production `/review-fixtures` and `/unavailable/[gap]`. Move useful hostile-text/accessibility assertions to real-route or component tests.
- Delete `ReadinessPanel` only if reference search proves it is unmounted after shell integration.

Acceptance tests:

- Navigation at 390px, 768px, 1024px, and 1280px is keyboard-operable with correct focus return and no page overflow.
- Admin visibility matches role, while forged member/viewer API mutations still receive server denial.
- Old bookmarks redirect deterministically; removed test/gap routes return production 404.
- No internal `window.location.assign`, dead nav item, duplicate readiness UI, or unmapped shell action remains.
- Shell visual and WCAG AA checks pass.


## Copied visual specification

### Application shell component specification

#### `AppShell`

- Desktop grid columns are `232px minmax(0, 1fr)`; collapsed mode is `72px minmax(0, 1fr)`.
- Nav and topbar are white with border separators.
- Main area uses canvas background and owns vertical scrolling.
- Skip link is visually hidden until focused, then appears at top-left as a Primary-style link.
- No footer is needed.

#### Brand block

- Height 56px, 16px horizontal padding.
- 28px square accent mark with existing spark icon and 8px radius.
- “Smart RAG” 14px/20px weight 600; “Company knowledge” 12px muted.
- Collapsed nav shows mark only with tooltip.

#### `AppNav`

- Exact primary order: Ask, Documents, Tables, Graph.
- Admin is separated by a 16px gap and shown only for owner/admin.
- Row is 40px high, 8px horizontal margin, 8px radius, 12px horizontal inner padding.
- Icon 18px, label 14px weight 500, gap 10px.
- Active: accent-muted background, accent text, and a 3px accent bar inset at left.
- Hover: surface-hover. No hover movement.
- Collapsed: centered icons, labels visually hidden, tooltips enabled.
- Mobile sheet uses full labels and no collapsed mode.

#### `ConsoleTopbar`

- Sticky 56px white bar with bottom border.
- Left: mobile menu button when needed, then one page title.
- Right order: readiness control, command control, Account control.
- Do not repeat logo in the topbar when desktop nav is visible.
- At 390px, hide command control first; keep readiness and Account.

#### `ReadinessIndicator`

- It is a button because it opens a real popover.
- Labels: “Checking,” “Ready,” “Degraded,” or “Unavailable.”
- Use corresponding neutral/success/warning/danger pill styling.
- Popover width 320px. Show “Question answering,” “Keyword search,” and “Graph search” only when real readiness fields authorize those labels.
- Primary blocking copy: “Question answering is temporarily unavailable. Try again when the service is ready.”
- Never expose DSNs, provider names not authorized for the caller, stack traces, or probe credentials.

#### `AccountMenu`

- Trigger is a 36px IconButton containing a generated two-letter initial avatar; no remote avatar.
- Menu shows email, role badge, upload capability text, Account details, and Sign out.
- No MFA field, profile editor, locale editor, or company settings.
- Sign out is separated as a quiet-danger menu item.

#### `CommandMenu`

- Dialog width 560px.
- Search input at top; results show supported routes only.
- Each result has icon, label, and optional short description.
- Keyboard: Ctrl/Cmd+K opens, arrows move, Enter navigates, Escape closes.
- Do not include actions that submit mutations.

#### `PageHeader`

- Desktop: title/description left, one primary action right.
- Mobile: stacked, action full width only when it is the page’s main task.
- Title uses Page title style; description uses secondary body, max width 720px.
- Bottom margin 24px.

## Acceptance checks

390/768/1024/1280 navigation works. Admin visibility is convenience only. Old bookmarks redirect. Removed gap routes 404.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a redirect would hide a still-required contract; keep the destination honest.

## Required evidence

Append `P08-14` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
