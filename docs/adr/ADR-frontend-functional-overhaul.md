---
title: ADR — Frontend functional overhaul
adr_id: ADR-frontend-functional-overhaul
status: accepted
owner: engineering-lead
last-reviewed: 2026-08-24
approver: "user (Cursor chat; no legal name provided)"
approval_date: "2026-08-24"
audience: frontend, backend, security, reviewers
---

# ADR: Frontend functional overhaul

## Status

`accepted` — 2026-08-24. The user approved repairing the broken production
chat path, replacing over-expanded console IA with Ask / Documents / Tables /
Graph / Admin / Account, wiring only existing Auth/API/SSE contracts, and
completely removing MFA/TOTP/AAL2 from every application environment.

## Context

Phase 8 packets 1–6 shipped a contract-mapped console, but live chat could
complete with an empty answer: LangGraph checkpoint settings fall back to a
Supabase transaction-pooler DSN, Compose does not inject
`LANGGRAPH_CHECKPOINT_URL` / `LIGHTRAG_DB_URL`, and the production SSE
executor consumes `stream_mode="updates"` without emitting verified answer
text. Several screens also expose controls with no backend owner.

The user asked for a functional overhaul, not more placeholders. After an
explicit security warning, the user also selected complete MFA removal.

## Decision (accepted)

1. Execute the overhaul as additive Phase 8 packets P08-07 through P08-23 on
   `feat/frontend-functional-overhaul`. Do not uncheck completed packets 1–6.
2. Repair query runtime connectivity and the Phase 6-owned executor so admitted
   runs persist input, deliver a non-empty **verified final** answer through
   existing `token_delta` compatibility events, terminate once, and settle
   reservations. Do not fake token streaming or emit unverified drafts.
3. Remove unsupported, permanently disabled, placeholder, duplicate, or
   misleading UI instead of inventing APIs.
4. Replace navigation with Ask, Documents, Tables, Graph, role-gated Admin,
   and Account. Keep the existing light Precision Workspace font family, but
   implement the exact visual contract in
   [00-visual-contract.md](../../.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration/00-visual-contract.md).
5. Remove MFA, TOTP enrollment/challenge/recovery, and AAL2 authorization
   requirements from frontend, backend, database policy surface, local
   configuration, tests, and maintained documentation. Packets P08-11 and
   P08-12 are one ordered feature-branch transaction and must not merge
   independently.
6. Preserve compensating controls that are not MFA: verified JWTs, revoked or
   disabled sessions, live role and authorization-version checks, RLS,
   server-side owner/admin enforcement, rate limits, destructive
   confirmations, generic errors, audit events, and IDOR-safe 404 behavior.
7. Do not add APIs for profile editing, budgets, audit export, source
   preview/download, member directory, owner bootstrap, company settings, or
   manual Hybrid/Combined route selection.
8. Merge to `main` only through a reviewed pull request after deterministic
   gates and the bounded live verification packet pass or are explicitly
   blocked.

## Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| Keep MFA and only hide the UI | User selected complete removal after the privileged-upload warning |
| Replace MFA with a recent-password second step in this change | Requires a separately approved contract |
| Switch LangGraph to `stream_mode="messages"` for live tokens | Would expose unverified drafts and redesign the Phase 6 gateway/verifier |
| Invent missing APIs for dead buttons | Violates existing-contract-only scope |
| Uncheck historical Phase 8 packets | Violates plan-source rules |

## Consequences

- This is a deliberate security reduction. Privileged upload and offboarding
  will run at ordinary authenticated assurance after P08-11/P08-12.
- Applied migrations stay immutable; AAL2 removal is additive.
- Supabase Auth may retain dormant provider fields; they must not authorize.
- Chat UX measures **verified answer availability**, not provider
  time-to-first-token.
- Rollback is `git revert` of the feature-branch commits plus restoring MFA
  routes/policies only via new additive migrations if the user reverses the
  security decision.

## Rollback

Do not force-push `main`. Revert the merge commit. Recreate MFA/AAL2 only
with new additive SQL and a new ADR; never edit applied migrations.
