---
title: Managed Auth TOTP residue
owner: engineering-lead
status: accepted
last-reviewed: 2026-09-07
audience: operations, security
packet: P08-12
---

# Managed Auth TOTP residue

Application authorization is single-factor after P08-11 and P08-12. Hosted
Auth should keep new TOTP enrollment/verification off in the Auth dashboard.
This runbook covers hosted Supabase projects that may still hold dormant
factors.

Never `DELETE FROM auth.mfa_factors` (or any other `auth` schema SQL). Mutating
GoTrue internals that way is unsupported and can strand sessions.

## Prerequisites

- Project owner or Auth admin access to the hosted Supabase project.
- Service-role key used only from a trusted operator host, never from the
  browser or frontend env.
- A change window. Deleting a **verified** factor signs the user out of every
  active session ([Auth Admin deleteFactor](https://supabase.com/docs/reference/javascript/auth-admin-mfa-deletefactor)).
- Hosted Auth MFA TOTP already disabled in the dashboard.

Restart Auth from the hosted dashboard after changing MFA settings.
Do not reset the database.

## Dry run (required first)

1. Confirm Dashboard **Authentication → Multi-factor authentication** (or the
   current Auth MFA settings page) can disable TOTP enrollment and
   verification. Equivalent self-hosted env flags from current Auth docs are
   `MFA_TOTP_ENROLL_ENABLED=false` and `MFA_TOTP_VERIFY_ENABLED=false`.
2. Enumerate residue **per known user id** with the documented Auth Admin API
   only:

```js
const { data, error } = await supabase.auth.admin.mfa.listFactors({
  userId: "<user-uuid>",
});
```

   There is no documented project-wide “list every factor” API. Do not SQL-scan
   `auth.mfa_factors`. If you cannot list factors for a user, skip deletion and
   record that user as dormant residue.
3. Write down factor ids, `factor_type`, and `status` (`verified` vs
   `unverified`). Do not delete yet.

## Unenroll (only after dry-run review)

For each listed factor you choose to remove:

```js
await supabase.auth.admin.mfa.deleteFactor({
  userId: "<user-uuid>",
  id: "<factor-uuid>",
});
```

End-user `supabase.auth.mfa.unenroll({ factorId })` requires an AAL2 session and
is not used here: the product no longer has a challenge/enroll UI.

If `listFactors` / `deleteFactor` is unavailable on the project's Auth version,
**leave residue dormant**. Disable enrollment/verification in Dashboard and stop.

## Verification

- Dashboard (or config) shows TOTP enroll/verify disabled.
- Browser has no `/mfa/enroll` or `/mfa/challenge` route.
- Sign-in, sign-up, reset/callback, invitation accept, and sign-out succeed
  without a TOTP challenge.
- `GET /me` does not authorize on `mfa_enrolled` (deprecated, always false).
- Upload and admin mutations succeed or fail on role/`upload_enabled`/quota,
  never on AAL2.

## Rollback

Re-enable TOTP enrollment/verification only with a new approved packet and a
new additive Auth configuration change. Do not reintroduce `/mfa/*` UI from
git history without restoring backend AAL2 gates (also removed in P08-11).

## Honest residue limits

- Factors that cannot be listed through Auth Admin remain in GoTrue until the
  provider provides a documented inventory API.
- Unverified leftover factors expire according to provider policy; they are not
  deleted with SQL.
- Google OAuth stays omitted while `[auth.external.google] enabled=false`.
  Do not ship a disabled Google button.
