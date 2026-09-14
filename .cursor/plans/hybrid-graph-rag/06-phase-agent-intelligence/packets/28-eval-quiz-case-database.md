---
phase: 6
packet: 28
status: complete
title: "Implement hosted quiz-case schema, gold rows, and app_api RPCs."
requirement_ids: [P06-28]
---

# Packet 28 — Implement hosted quiz-case schema, gold rows, and app_api RPCs.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-supabase-security`](../../../../../.cursor/skills/implement-supabase-security/SKILL.md),
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md),
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

Do not load frontend, exam-runner, or FastAPI router skills.

## Preconditions

- P06-27 is accepted. Existing P06-10 is accepted. Canonical sequence is
  P06-27, then Packet 10, then this packet. This packet does not execute
  Hybrid retrieval, but it must not run before Packet 10 acceptance.
- Inspect current migrations, roles, `validate_caller_context`,
  `caller_can_read_document`, audit insert, RLS/grant patterns, and the local
  destructive fixture. Never edit an already-applied migration.

## Allowed outputs

- One forward migration for `app.eval_quiz_cases`,
  `app.eval_quiz_gold_chunks`, constraints, indexes, RLS, grants, audit,
  retention, and case RPCs.
- Migration policy allowlist and generated Phase 10 migration-hash artifacts.
- Database contract/privilege tests.
- Schema, data-dictionary, and security documentation for these tables.

## Forbidden outputs

- FastAPI routes, frontend files, exam tables, Compose default changes, or
  operator/service-role DSN usage from FastAPI.
- Direct table DML grants to `app_api`, `authenticated`, `anon`, or
  `PUBLIC`.
- Holdout split, table, or token acceptance.
- Auto-import from `.private-eval/`.
- Logging questions, answers, facts, excerpts, JWTs, or gold UUID lists.

## Ordered actions

1. Inspect the latest migration timestamp, PostgreSQL version, and
   established function-owner/RLS pattern. Choose a new sortable filename.
2. Add `app.eval_quiz_cases` and `app.eval_quiz_gold_chunks` exactly as
   [ADR-hosted-webapp-evaluation-workspace.md](../../../../../docs/adr/ADR-hosted-webapp-evaluation-workspace.md)
   and the P06-27 brief require: 60-case cap, 365-day expiry, row_version CAS,
   idempotency, split immutability, development/qualification only.
3. Normalize gold as 0–3 ordinal rows. Locator snapshots are server-derived
   from canonical chunks. Client never supplies trusted document/version/page
   metadata.
4. Add `app_api` SECURITY DEFINER RPCs with fixed `search_path` for create,
   list summaries, get detail, patch, replace gold, approve, reject, delete,
   status counts, and expired-row purge.
5. Create must load the question through the inspected caller-owned
   query-run message function. Do not accept browser question text as source
   provenance.
6. Enforce capacity under a singleton `company_settings` row lock or advisory
   lock. Concurrent creates must not produce case 61.
7. Approve validates non-empty expected answer, allowed class, source
   family, one to three current gold chunks, one document/version, ACL, and
   split-family isolation. Zero gold is allowed for drafts only.
8. Content-free append-only audit events on every mutation.
9. Add RLS/privilege/IDOR/holdout/capacity tests at the real database
   boundary. Refresh migration hashes through the repository generator.
10. Apply the reviewed migration to the intended hosted project only through
    the approved Supabase MCP/protected path. Verify presence without printing
    DSNs or private rows.

## Acceptance checks

- Reset/reapply and `check_migrations.py` / packet2 hash succeed.
- `app_api` cannot INSERT/UPDATE/DELETE the new tables directly.
- PUBLIC/anon/authenticated cannot execute the new functions.
- Owner/admin positive CRUD works through RPCs.
- Member/viewer, forged role, stale authorization, and disabled user are
  denied.
- Foreign run/citation and inaccessible document are indistinguishable 404s
  at the SQL boundary.
- Concurrent create cannot exceed 60. Idempotency collision is rejected.
- Holdout token is rejected. Source family cannot cross open splits.

## Negative tests

- Fourth, duplicate, cross-version, cross-document, and stale gold denied.
- Content/gold edit resets approval, reviewer, and reviewed_at.
- Expired purge is bounded and content-free.
- Same idempotency key with a different payload is rejected.

## Stop routes

- Stop if hosted apply would print or embed privileged credentials.
- Stop if `app_api` cannot perform the flow without direct table DML.
- Do not invent a company_id column or multi-tenant identifier.

## Required evidence

- Append migration name, hash artifact, hosted apply/verify without secrets,
  privilege negatives, `holdout_opened=false`, and P06-29 handoff.
