---
title: Comprehensive audit executive verdict
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: product, engineering, security, operations, client-approver
---

# Executive verdict

## Decision

**NO-GO for production.**

Smart RAG is production-minded in architecture but remains a local release
candidate with partial managed-staging evidence. The main problem is not the
absence of thoughtful controls. It is that release evidence is red or missing
at the exact boundaries that decide whether those controls work together.

## Why approval is blocked

Four conditions independently block release:

1. **The intended hosted Supabase state is unknown.** The database available to
   the audit belongs to another application and was excluded. Local SQL cannot
   prove migration completeness, drift, advisor state, backups, or live RLS.
2. **Automated release gates are red.** Current runs produced 200 Pyright
   errors, 7 unit failures, 9 contract failures, 10 unformatted Python files,
   Ruff findings, and documentation failures.
3. **Managed deployment is partial.** Repository evidence does not prove the
   complete API, worker, ClamAV, parser-sandbox, migration, alert, restore,
   rollback, and external-assessment path.
4. **Scale claims exceed proof.** The strongest signed evidence remains a
   one-host envelope with 8 Hybrid versions, 16 chunks, 15 graph documents,
   and 5 concurrent query runs. Twenty-five-user load, live first-token p95,
   multi-replica connection budgets, and timed disaster recovery are unproven.

## Risk concentration

The highest source-level security risks are in database role design:

- `app.revoked_sessions` and `app.mfa_recovery_requests` have grants but no RLS;
- several canonical tables retain permissive `app_api` read policies;
- several tenant-sensitive tables enable RLS without forcing it;
- the migration surface is large: 59 files declare 86 tables, roughly 170
  function definitions/replacements, and 100 indexes.

The highest runtime and scalability risks are:

- connection fan-out from parallel Hybrid retrieval on a budget proven only
  for one API and one worker;
- lease loss not cooperatively cancelling in-flight parse/embed work;
- serialized graph indexing and process-local runtime state;
- no managed full-stack soak, restore drill, or alert-delivery proof.

The highest frontend and UX risk observed live is straightforward: on a
390-by-844 login page, the sign-in form begins about 1,961 pixels below the top,
after full application navigation, readiness diagnostics, outage copy, and an
848-pixel hostile-text fixture. This makes the primary task require substantial
scrolling and exposes internal implementation language to end users.

The late frontend pass also confirmed production configuration and runtime
gaps: missing Supabase variables let the protected Next.js shell render, a
missing API origin defaults to the browser's localhost, and reconnect errors
other than 404 can reach the SSE parser without classification. FastAPI still
protects data, but the frontend must fail closed and expose recoverable errors.

## What is strong

The audit verified substantial positive engineering:

- asymmetric JWT verification with restricted algorithms and authenticated
  role enforcement;
- test-identity and mock-mode restrictions in hosted environments;
- server-authoritative authorization with caller authorization versions;
- ACL rechecks after derived retrieval;
- parameterized SQL at the inspected backend call sites;
- durable job claims using leases and `FOR UPDATE SKIP LOCKED`;
- parser sandboxing with no network, read-only root, and dropped capabilities;
- crawl URL normalization, private-address blocking, DNS pinning, and proxy
  egress;
- SSE ownership checks, replay semantics, and sanitized error events;
- fail-closed external-processing governance and malware scanning;
- pinned GitHub Actions and non-root container patterns;
- clean frontend typecheck, ESLint, and 171 passing Vitest tests;
- passing Python and Node dependency audits at the configured policy levels.

These strengths materially reduce risk. They do not replace missing integration
and live-environment proof.

## Recommended decision path

Do not start broad refactoring first. Close release safety in this order:

1. connect only the intended Smart RAG Supabase project and prove the full
   migration/RLS/advisor/backup state;
2. restore green type, unit, contract, lint, format, and documentation gates;
3. add and verify the RLS/grant hardening migration;
4. run the complete managed stack, including malware scanning and workers;
5. prove deployment waiting, health gates, rollback, alert delivery, and
   timed restore;
6. run signed load and latency tests at the intended envelope;
7. perform behavior-neutral god-file splits and external penetration testing.

The detailed sequence and exit checks are in the
[remediation plan](./90-remediation-plan.md).
