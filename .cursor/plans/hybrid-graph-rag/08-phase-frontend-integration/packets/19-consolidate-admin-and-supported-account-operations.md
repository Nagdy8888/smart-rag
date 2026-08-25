---
phase: 8
packet: 19
status: complete
title: "Consolidate Admin and supported Account operations"
requirement_ids: [P08-19]
---

# Packet 19 — Consolidate Admin and supported Account operations

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-12 single-factor Auth and P08-14 Account menu exist. Move retained admin code once.

## Allowed outputs

/admin tabs team/tools/curation/usage, real mutations only, removal of bootstrap/budget/audit/profile-editor UI.

## Forbidden outputs

MFA copy. Member directory. Owner bootstrap. Budget policy UI. Duplicate account pages.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-19 — Consolidate Admin and supported Account operations

Purpose: replace four top-level management routes and dead settings panels with one compact role-aware admin workspace after the final single-factor model is in place.

Primary files:

- current `team-app.tsx`, `tools-app.tsx`, `curation-app.tsx`, `usage-app.tsx`, and `profile-app.tsx`
- new `/admin` route/container and small tab components; move retained code exactly once and delete old implementations
- API clients/types for existing entity-rule and tool-query actions
- redirects, tests, docs, and inventory.

Implementation:

- Create `/admin` tabs `team`, `tools`, `curation`, and `usage`; tabs update URL state and support keyboard navigation.
- Team keeps invitation creation/link and offboarding by known user ID. Remove member-directory and owner-bootstrap panels. Offboarding uses ordinary authenticated owner/admin authorization.
- Tools uses `GET /tools?q=`, real enable/disable, and permission mutations. Remove tool seeding from ordinary product UI.
- Curation wires existing entity-rule PATCH with `row_version` conflict handling and suggestions POST, plus existing import/approve/rollback/upsert/approve/revoke.
- Usage shows only real caller/company totals and real degraded/rate-limit states. Remove budget policy and audit-history UI.
- Account remains the P08-14 shell menu with supported `/me` fields and Sign out. Remove old profile editor, locale editor, company settings, and duplicate account pages.
- Owner/admin visibility is convenience only; direct APIs retain role/capability, 403, and IDOR-safe 404 enforcement.

Acceptance tests:

- Owner/admin can execute every retained mutation without MFA; member/viewer cannot see Admin and forged requests fail.
- Stale entity-rule `row_version` yields recoverable 409; tool search URL-encodes `q`.
- No bootstrap, budget, audit, profile editor, company settings, member directory, placeholder, gap, or permanent-disabled control renders.
- Keyboard, screen-reader, mobile, and mixed-direction email/error copy checks pass.


## Copied visual specification

### Auth component and page specification

#### `AuthLayout`

- Full viewport canvas with centered content.
- Brand above card with 32px bottom gap.
- Auth card: width 420px, white, 12px radius, border, shadow-1, 32px padding desktop and 24px mobile.
- No split-screen marketing panel, stock art, gradient, testimonial, or decorative background.

#### `AuthCard`

- Title, one-sentence helper, form, then text links.
- Form fields separated by 16px.
- Primary submit is full width, 44px high.
- Secondary navigation is plain text link beneath with 16px top margin.
- Inline error banner sits above fields and receives focus after failure.

Exact pages:

- Sign in title: “Sign in to Smart RAG.” Helper: “Use your company account to access private knowledge.”
- Sign up title: “Create your account.” Helper: “Your account still needs a valid company invitation.”
- Forgot title: “Reset your password.” Helper: “We’ll send a reset link to your email.”
- Reset title: “Choose a new password.”
- Invitation title: “Accept invitation.” Helper: “Sign in with the email address that received this invitation.”
- Callback page shows Spinner plus “Completing sign in…” and a safe timeout error with “Return to sign in.”
- No Google button, MFA/TOTP page, recovery page, owner-bootstrap page, or unavailable-gap page.
### Admin component specification

#### Admin frame

- PageHeader title “Admin.”
- Description: “Manage access, tools, retrieval curation, and usage.”
- Horizontal Tabs: Team & access, Tools, Curation, Usage.
- Tab content is one column with maximum width 1120px.
- Member/viewer never see this route in nav; direct page visit renders a safe permission ErrorState after real server confirmation.

#### Team & access

- First Card “Invite user”: email Input, role Select, upload access Checkbox, Primary “Send invitation.”
- Success shows invitation ID and expiry only; never token.
- Second Card “Offboard user”: danger section, user ID Input, consequence copy, quiet-danger “Review offboarding,” then ConfirmDialog.
- No member directory, avatars, owner-bootstrap wizard, MFA/AAL2 copy, or fake invitation list.

#### Tools

- Toolbar: SearchInput and count.
- Tool cards are compact 2-column desktop/1-column mobile.
- Card: name, version, description, enabled StatusPill, permission Select for owner/admin, and real Enable/Disable AsyncButton.
- Full manifest fields open in Drawer through “View details.”
- No tool seeding form in ordinary UI.

#### Curation

- Two Tabs inside content: Glossary and Entity rules.
- Glossary: import form, result/status, then real Approve/Rollback actions.
- Entity rules: DataTable with canonical type, aliases, status, row version, overflow actions Edit/Approve/Revoke.
- “Suggest rule” Secondary action opens Dialog backed by the real suggestions endpoint.
- Edit uses real PATCH and shows conflict banner on stale row version with “Reload rule.”
- No bulk action without an existing endpoint.

#### Usage

- Two metric cards maximum in one row: “Your usage” and owner/admin “Company usage.”
- Each card shows tokens and USD from the real response, using 24px numeric value and 13px label.
- Below: real readiness/rate degradation StatusBanner.
- No charts without time-series data. No budget editor, hard-cap slider, audit panel, forecast, fake trend, or progress bar.

## Acceptance checks

Owner/admin mutations work without MFA. Member/viewer Admin is hidden and APIs still deny. Stale row_version is recoverable 409.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if an admin mutation contract is missing; omit the control rather than faking success.

## Required evidence

Append `P08-19` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
