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
- `tsc` / full frontend suite / plan integrity recorded after this section.

### Rollback

Revert this commit. Restoring TOTP UI without restoring backend AAL2 gates
(P08-11) would be a product lie. Do not SQL-delete factors as a rollback.

### Handoff

P08-11 + P08-12 MFA removal is complete. UI surface packets P08-13+ may start.
Do not merge this branch until remaining Phase 8 remediation packets finish.
