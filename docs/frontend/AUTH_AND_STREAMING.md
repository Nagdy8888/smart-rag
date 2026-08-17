---
title: Auth and streaming frontend
owner: engineering-lead
status: draft
last-reviewed: 2026-08-17
audience: engineering, frontend, security
packet: P08-02
---

# Auth and streaming (Phase 8 packet 2)

SSR Auth, MFA/invitation surfaces, min-client handshake, and Bearer SSE UX.
Stitch frames are a **template, not a layout**. These routes exist because
Auth/FastAPI contracts exist, not because Stitch numbered them.

Related: [API_UI_MAPPING.md](./API_UI_MAPPING.md) ·
[THIN_DEVELOPER_UI.md](./THIN_DEVELOPER_UI.md) ·
[CORE_RAG_SURFACES.md](./CORE_RAG_SURFACES.md) ·
[ADMINISTRATION.md](./ADMINISTRATION.md) ·
[STITCH_REVIEW.md](./STITCH_REVIEW.md) ·
[SSE.md](../api/SSE.md) ·
[AUTH_RATE_LIMIT_OWNERSHIP.md](../security/AUTH_RATE_LIMIT_OWNERSHIP.md) ·
[phase-08 evidence](../development/phase-08-frontend-integration-evidence.md) ·
[docs index](../README.md)

## Routes

Canonical sign-in is `/login`. Unauthenticated `/` redirects there as a
convenience. FastAPI still authorizes every Bearer call.

| Path | Contract | Notes |
| --- | --- | --- |
| `/login` | `signInWithPassword` | Generic "Sign in failed". Google disabled (GAP-07-04) |
| `/signup` | `signUp` | Invitation still required for FastAPI membership |
| `/forgot-password` | `resetPasswordForEmail` | Check-inbox copy; does not reveal existence |
| `/auth/callback` | PKCE `exchangeCodeForSession` | Replay → "Sign-in could not be completed" |
| `/auth/reset` | `updateUser({ password })` | After recovery `next=/auth/reset` |
| `/mfa/enroll` | `mfa.enroll` TOTP | QR `<img>` only for data-URL `qr_code` |
| `/mfa/challenge` | `mfa.challenge` / `verify` | MFA-required banner + Sign out |
| `/invitations/accept` | `POST /invitations/accept` `{ token }` | Email from JWT, not the form |
| `/unavailable/GAP-07-07` | none | Honest Unavailable; no recovery HTTP |
| `/unavailable/GAP-07-08` | none | Honest Unavailable; no bootstrap HTTP |
| `/` | Auto chat | Packet 3. No route POST field. See [CORE_RAG_SURFACES.md](./CORE_RAG_SURFACES.md) |

Team admin create/offboard, tools, curation, usage, and profile are
packet 4 native routes. See [ADMINISTRATION.md](./ADMINISTRATION.md).
Documents, graph, and tables are packet 3 native routes.

## SSR cookie flow

`@supabase/ssr` **0.7.0** and Next.js **16.3.0** `src/proxy.ts` (not
`middleware.ts`). Only `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY`. PKCE is forced on `createServerClient`.

```mermaid
sequenceDiagram
  participant Browser
  participant Proxy as NextProxy
  participant Auth as SupabaseAuth
  participant Page as AppRouter
  participant API as FastAPI
  Browser->>Proxy: "document request"
  Proxy->>Auth: "getClaims cookie refresh"
  Auth-->>Proxy: "updated cookies"
  alt no session and not a public Auth path
    Proxy-->>Browser: "redirect /login"
  else session present
    Proxy-->>Page: "render with cookies"
    Page->>Auth: "getSession onAuthStateChange"
    Auth-->>Page: "access_token"
    Page->>API: "Authorization Bearer"
  end
  Browser->>Page: "/auth/callback?code"
  Page->>Auth: "exchangeCodeForSession"
  alt code consumed or missing
    Page-->>Browser: "redirect /login?error=callback"
  else success
    Page-->>Browser: "redirect next path"
  end
```

Missing cookies are not the security boundary. Optimistic redirects can be
wrong; FastAPI returns 401/403.

## Auth vs FastAPI throttle ownership

| Surface | Owner | UI claim |
| --- | --- | --- |
| Email/password, reset, MFA enroll/challenge | Supabase Auth | Must **not** say FastAPI throttles login (GAP-07-20) |
| Invitation accept | FastAPI `AUTH_ADJACENT` | Sanitized `detail` codes |
| Chat POST / upload reserve | FastAPI handshake + limiter | 426/402/429/503 banners |

## MFA vs GAP-07-07

TOTP enroll/challenge are Auth-direct. FastAPI 403 `MFA required` shows the
banner, Sign out, and links to `/mfa/challenge` and `/mfa/enroll`. Upload 403
uses the same banner and never fakes TOTP success.

Lost-factor recovery, admin session revoke UI, and recovery codes are
**Unavailable GAP-07-07** because `mfa_recovery.py` has no router. Owner
bootstrap is **Unavailable GAP-07-08**.

## Handshake before spend

`GET /api/meta` publishes `min_client_version` and `sse_schema_version`.
The composer compares `CLIENT_VERSION` (`0.1.0`) before
`startMessageStream`. Below minimum: banner
"This client is below min_client_version. Update before asking a question."
and Send stays disabled. Unreachable meta fails closed for **new** paid POST.
Resume GET does **not** re-handshake ([SSE.md](../api/SSE.md)). A newer
`sse_schema_version` continues; unknown events are ignored.

Server 426 remains. UI shows sanitized `detail` codes for 426/402/429/503,
never stack traces.

## Reconnect and idempotency

`startOrResumeMessageStream` POSTs only when `runId` is null or the run is
terminal. An in-flight run reconnects with GET `/runs/{id}/events?after=`
and omits `X-Client-Version`. The same `Idempotency-Key` is reused if POST
must retry; the server reuses the run. Sequences are monotonic: duplicate
or older `id` values are ignored. One terminal freezes later token deltas.
Cancel posts `/runs/{id}/cancel`. Heartbeats increment diagnostics.

## Frame 01/03 and gap decisions

Frame 01 sign-in chrome is **not** a product route. Native `/login` covers
email/password, disabled Google, and readiness pills. Frame 03 owner-setup
wizard is **not** shipped (GAP-07-08). Invitation accept fills team entry.

## Failure modes

| Case | UI |
| --- | --- |
| Provider Auth error | "Sign in failed" |
| Callback replay | "Sign-in could not be completed" |
| `session_revoked` | Banner + sign out |
| Client below min | Handshake banner; no paid POST |
| Meta down | Fail closed for new paid POST |
| 402 `budget_exhausted` | Budget banner |
| 429 `rate_limited` / `concurrency_limit` | Rate banner + Retry-After |
| 503 `limiter_unavailable` | Fail-closed banner |
| Unknown SSE | Logged; stream continues |

## Verification

```text
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend exec next typegen
pnpm --filter smart-rag-frontend exec tsc --noEmit
pnpm --filter smart-rag-frontend test
pnpm --filter smart-rag-frontend build
```

From `apps/frontend`: `pnpm exec playwright test`

Docs: `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json`
