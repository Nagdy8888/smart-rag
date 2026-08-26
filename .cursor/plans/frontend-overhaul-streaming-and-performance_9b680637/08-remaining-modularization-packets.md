# Candidate Remaining Frontend Modularization Packets

Status: **candidate, non-canonical**

MOD-01 through MOD-06 refactor the stream-critical god files into focused
owners while retaining their public entry files as thin barrels/facades. This
file covers the remaining production source over 300 physical lines. Execute
one ID per model run and preserve behavior before adding features to that owner.

## Verified inventory outside MOD-01–06

```text
589 physical lines  components/tables/analysis-plan.tsx
541                 components/documents/document-library.tsx
499                 components/admin/curation-panel.tsx
493                 components/auth/auth-screens.tsx
504                 lib/table-plan.ts
340                 components/graph/graph-explorer.tsx
342                 components/documents/document-detail.tsx
343                 components/documents/import-source-sheet.tsx
315                 lib/admin-bodies.ts
921                 components/ui/ui.module.css
533                 components/chat/chat.module.css
495                 components/admin/admin.module.css
453                 components/ui/app-shell.module.css
```

All relative inventory paths are under `apps/frontend/src/`.

## MOD-07 — Split pure table-plan logic

**Add under `apps/frontend/src/lib/table-plan/`**

- `draft.ts`: draft types/constants and user-safe copy;
- `validate.ts`: column/SQL/path/value validation;
- `compile.ts`: `compileTablePlanDraft` and request construction;
- `results.ts`: result-column/export guards.

Keep `apps/frontend/src/lib/table-plan.ts` as an explicit ≤100-line barrel.
Move code verbatim first, then update internal imports. No SQL-like input may
become accepted by extraction.

**Tests**

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/lib/table-plan.test.ts src/components/tables/tables-app.test.tsx src/lib/api.test.ts
pnpm --filter smart-rag-frontend typecheck
```

## MOD-08 — Split AnalysisPlan presentation

**Objective:** reduce
`apps/frontend/src/components/tables/analysis-plan.tsx` to ≤200 lines.

**Add under
`apps/frontend/src/components/tables/analysis-plan/`**

- `predicate-row.tsx`;
- `columns-section.tsx`;
- `filters-section.tsx`;
- `aggregations-section.tsx`;
- `group-sort-section.tsx`;
- `comparison-section.tsx`.

Use full `apps/frontend/src/` prefixes during implementation. Child components
receive typed draft values and callbacks only; they do not fetch or compile the
plan. Keep `patchDraft` and Analyze submission in the parent.

**Tests:** existing table tests plus keyboard labels for add/remove/reorder
controls. Every new component ≤220 lines.

## MOD-09 — Extract document-library controller

**Add**

- `apps/frontend/src/components/documents/hooks/use-document-library.ts`;
- `apps/frontend/src/components/documents/document-delete-sheet.tsx`;
- focused hook tests.

Move queries, cursor pagination, reserve→upload→finalize, crawl, retry, delete,
abort/latest-wins, and scoped invalidation into the hook. The page composes
list, import sheet, inspector, and delete confirmation.

**Hard boundaries**

- hook ≤280; page ≤300;
- no upload/crawl security claim moves client-side;
- paid/idempotent mutation headers remain unchanged;
- stale conversation/document selection cannot receive old results.

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/components/documents/document-library.test.tsx src/components/core-rag-surfaces.test.tsx
```

## MOD-10 — Split curation ownership

**Add**

- `apps/frontend/src/components/admin/glossary-panel.tsx`;
- `apps/frontend/src/components/admin/entity-rules-panel.tsx`;
- `apps/frontend/src/components/admin/hooks/use-curation-mutations.ts`.

Keep `curation-panel.tsx` as a ≤150-line tab shell. Preserve all seven mutation
contracts, stale-row conflict UI, permission gates, and scoped invalidations.
Panels ≤280; hook ≤250.

**Tests:** `apps/frontend/src/components/administration-surfaces.test.tsx`,
including 403, concurrency conflict, retry, approve/revoke, and rollback.

## MOD-11 — One auth screen per file

**Add under `apps/frontend/src/components/auth/`**

- `auth-banners.tsx`;
- `sign-in-form.tsx`;
- `sign-up-form.tsx`;
- `forgot-password-form.tsx`;
- `reset-password-form.tsx`;
- `invitation-accept-form.tsx`.

Make `auth-screens.tsx` an exports-only barrel. Keep each form ≤150 lines.
Preserve PKCE, invitation acceptance, safe failure copy, no-secret logging, and
Supabase client ownership.

Expand `auth-screens.test.tsx` beyond sign-in/sign-up to forgot, reset,
invitation, environment-missing, and handshake failures.

## MOD-12 — Split UI controls and data-display CSS

**Objective:** peel coherent selectors from
`apps/frontend/src/components/ui/ui.module.css` without visual change.

**Add under `apps/frontend/src/components/ui/styles/`**

- `controls.module.css`: button/input/select/form controls;
- `data-display.module.css`: tables, pills, empty/error/status surfaces.

Update only owning components in this packet. Do not copy a selector into both
old and new modules. Update geometry/design-token tests to read the new owners.
Each CSS module ≤280 physical lines.

## MOD-13 — Split overlay CSS and primitives

After MOD-12, add `apps/frontend/src/components/ui/styles/overlays.module.css`
for sheet, confirm dialog, command menu, menu, popover, and drawer. Keep focus
behavior changes in UX-04, not this move-only packet.

Run primitive, geometry, and visual tests. End with no remaining
`ui.module.css` concern over 300 physical lines.

## MOD-14 — Split admin request builders

**Add under `apps/frontend/src/lib/admin-bodies/`**

- `invitations-tools.ts`;
- `glossary.ts`;
- `entity-rules.ts`.

Keep `admin-bodies.ts` as a ≤100-line barrel. Preserve extra-forbid request
shapes and concurrency fields. Expand `admin-bodies.test.ts` for every builder.

## MOD-15 — Split chat CSS by extracted owner

After MOD-06 and FEP presentation ownership stabilize, split:

- `apps/frontend/src/components/chat/chat-rail.module.css`;
- `apps/frontend/src/components/chat/chat-transcript.module.css`;
- `apps/frontend/src/components/chat/chat-composer.module.css`;
- focused progress/reveal styles beside their components.

No selector duplication, geometry change, or snapshot update is permitted in
the move-only packet. Each module ≤280 physical lines.

## MOD-16 — Split graph explorer controller

**Add**

- `apps/frontend/src/components/graph/hooks/use-graph-explorer.ts`;
- small results/inspector components when needed.

Move search, chip selection, inspect mutation, and stale-result guards into the
hook. Keep list/canvas selection on one callback and preserve the 12-chip
bound. `graph-explorer.tsx` exits ≤220 lines.

Run `graph-explorer.test.tsx` and `core-rag-surfaces.test.tsx`.

## MOD-17 — Split document detail and import tabs

**Add**

- `apps/frontend/src/components/documents/hooks/use-document-detail.ts`;
- `apps/frontend/src/components/documents/document-delete-sheet.tsx` reuse from
  MOD-09;
- `apps/frontend/src/components/documents/import-file-tab.tsx`;
- `apps/frontend/src/components/documents/import-website-tab.tsx`.

Keep visibility-aware polling, 404 title non-leakage, handshake gate,
attestation, and controlled form state unchanged. Add a direct
`import-source-sheet.test.tsx`; do not rely only on the library integration.

## MOD-18 — Shared auth/query/idempotency owners

**Dependencies:** MOD-02 through MOD-05. Run before MOD-09 and MOD-10 so their
new hooks use the shared owners.

**Add**

- `apps/frontend/src/lib/idempotency.ts`;
- `apps/frontend/src/lib/auth/use-api-auth.ts`;
- `apps/frontend/src/lib/hooks/use-current-user.ts`;
- focused tests for all three.

Move the three identical `crypto.randomUUID()` helpers from Chat, Documents, and
Curation into documented `newIdempotencyKey()`. Preserve one key across a
retry; never generate a new key inside a retry attempt.

`useApiAuth()` derives `{accessToken}` from the existing `useSession()` context
and memoizes by token. It does not create a Supabase client or refresh tokens.

`useCurrentUser()` owns the session-scoped `/me` TanStack query and exposes
explicit pending/error/data fields. Replace duplicate `/me` queries only after
query-key and role behavior tests characterize them. Server `/me` remains the
role authority.

**Tests:** stable object identity for unchanged token, null signed-out auth,
subject-scoped `/me` cache, revoked-session failure, one `/me` request for
multiple consumers, and idempotency-key reuse across retry.

## MOD-19 — Split shell and admin CSS owners

**Dependencies:** UX-01 for stable shell markup and MOD-10 for stable curation
components.

Split:

- `apps/frontend/src/components/ui/app-shell.module.css` into shell layout,
  navigation, and topbar modules owned by their importing components;
- `apps/frontend/src/components/admin/admin.module.css` into admin shell,
  tables/forms, and curation panel modules.

Each CSS module is ≤280 physical lines. Move selectors without visual changes;
do not duplicate selectors or mix responsive fixes into the move. Update
geometry, shell, administration, 390px, and desktop visual tests.

## Explicit dependency order

Execute one ID per run:

1. MOD-07, then MOD-08.
2. MOD-18, then MOD-09 and MOD-10.
3. MOD-09 must pass before MOD-17.
4. MOD-10 must pass before MOD-14 and MOD-19.
5. MOD-11 may run after MOD-18.
6. MOD-12 must pass before MOD-13.
7. MOD-16 must pass before UX-05 changes graph behavior.
8. MOD-15 is blocked until MOD-06 and FEP-04 pass.
9. MOD-19 is blocked until UX-01 and MOD-10 pass.

Independent IDs still run in separate model runs.

## Final architecture gate

Extend `apps/frontend/src/lib/architecture-budget.test.ts` to scan all
production `.ts`, `.tsx`, and concern-owned CSS:

- no production TS/TSX file over 300 physical lines;
- no concern-owned CSS module over 300 physical lines;
- compatibility barrels ≤100;
- allow-list only generated/vendor files with a documented reason;
- no line-count compliance through minified formatting or removed docs.

Run focused owner tests after each split. After the last MOD packet, run lint,
typecheck, and Vitest; the full build/Playwright release gate remains VER-01.
Record every before→after count in evidence.
