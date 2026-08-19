---
title: Low production-readiness findings
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: engineering
reviewed_commit: 09a102a
---

# Low findings

Hygiene and polish. Do not use these to delay a real staging stand-up.

Related: [medium](./03-medium.md) · [what is excellent](./92-what-is-excellent.md)

## PRD-L-001 — Root metadata calls the UI a production console

- **Location:** `apps/frontend/src/app/layout.tsx:6-9`
- **Evidence:** Description: "Production Auto chat, documents, graph..."
- **Impact:** Browser tab and SEO-ish copy over-claim. Matches PRD-C-006 integrity issue at the edge.
- **Remediation:** "Smart RAG console (release candidate)" until Phase 11.

## PRD-L-002 — FastAPI title/version still `0.1.0`

- **Location:** `apps/backend/src/smart_rag_api/main.py:175-176`
- **Impact:** Harmless; handshake uses settings `API_VERSION`. Keep them in sync.

## PRD-L-003 — CSP `style-src 'unsafe-inline'`

- **Location:** `apps/frontend/next.config.ts:27`
- **Impact:** Common with CSS modules; residual CSS injection. Hostile text is React-escaped.
- **Remediation:** Prefer hashed styles when Next allows; not a blocker.

## PRD-L-004 — Graph SVG uses `currentColor` circles without edges

- **Location:** `graph-explorer.tsx` (see M-006)
- **Impact:** Accessibility: `role="img"` with a generic label. List pane carries the real information.

## PRD-L-005 — Many docs index rows remain `draft`

- **Location:** `docs/README.md`
- **Impact:** Reviewers cannot tell verified vs aspirational from the index alone.
- **Remediation:** Flip architecture/security docs that have tests to `verified` with last-reviewed dates.

## PRD-L-006 — `X-Test-AAL` not in CORS (test-only)

- Duplicate of M-005. Kept so test engineers see it in Low if they only skim.

## PRD-L-007 — Default mock fixture id is `phase-1-foundation-v1`

- **Location:** `packages/core/src/smart_rag_core/settings/base.py:146-153`
- **Impact:** Easy to think answers are Phase 6 quality while fixtures are Phase 1.
- **Remediation:** Fail ready if fixture id does not match the frozen Hybrid/answer prompt versions.

## PRD-L-008 — Plan index todos lag wrappers (Phase 6–8 pending in index)

- **Location:** `.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md:20-27`
- **Impact:** Humans reading only the index underestimate how much UI/agent code exists, and overestimate production readiness.
- **Remediation:** Sync todos when exit records land (C-007).

## PRD-L-009 — JWKS verifier does not pin JWT `role` to `authenticated`

- **Location:** `packages/core/src/smart_rag_core/security/jwks.py`
- **Evidence:** Checks `alg`, `kid`, `aud`, `iss`, `exp`, `sub`. Never reads `role`. HS256 rejection already blocks classic `service_role` HS256 JWTs.
- **Impact:** Residual if a future ES256 `service_role` token shares `aud=authenticated`.
- **Remediation:** Require `role == "authenticated"`; reject `service_role` / `anon`.

## PRD-L-010 — Ingestion status router is not thin

- **Location:** `apps/backend/src/smart_rag_api/routers/ingestion_status.py`; `.cursor/rules/05-monorepo-boundaries.mdc`; `.cursor/rules/10-python-quality.mdc`
- **Evidence:** GET and retry open `psycopg.connect`, `SET ROLE app_api`, and call repositories from the router. This is also the IDOR surface (C-010).
- **Impact:** Persistence and authorization live at the HTTP edge. The next status field will be added here instead of an ACL RPC.
- **Remediation:** After C-010, the router should only call an injected service. Keep SQL in repositories/RPCs.

## PRD-L-011 — Cookie flags rely on `@supabase/ssr` defaults

- **Location:** frontend Auth session helper (library defaults; this repo does not set `httpOnly` / `SameSite` explicitly)
- **Impact:** Residual if a future custom cookie writer drops `Secure`/`SameSite`. Not a live bypass found in this pass.
- **Remediation:** Pin cookie options in the session factory; Playwright assert `Secure` + `SameSite=Lax` or `Strict` on HTTPS.

## PRD-L-012 — `profiles_update_self_non_role` only freezes `role`

- **Location:** `supabase/migrations/20260812135916_roles_rls_identity_v1.sql:480-492`
- **Evidence:** WITH CHECK compares `role` only. `authenticated` currently has schema/table revokes on `app`, so PostgREST cannot hit this now.
- **Impact:** A future GRANT on `app.profiles` would let users set `upload_enabled=true` via PostgREST (MFA still enforced in FastAPI).
- **Remediation:** WITH CHECK also freezes `upload_enabled`, `mfa_enrolled`, and `disabled_at`.

## PRD-L-013 — `retrievers_unbound` has no user-facing limitation copy

- **Location:** `packages/core/src/smart_rag_core/query_routing/constants.py:45`; `apps/frontend/src/lib/limitations.ts:6-39`
- **Evidence:** Fallback reason `retrievers_unbound` exists. `LIMITATION_COPY` has no entry; unknown codes fall through to generic copy.
- **Impact:** After C-009, users will not see an honest “retrieval was not attached” message. Operators debugging chat will not distinguish unbound from empty Hybrid.
- **Remediation:** Add locked copy; treat unbound as `verified_partial` (H-029), never silent generic.
