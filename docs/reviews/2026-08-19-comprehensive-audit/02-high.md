---
title: Comprehensive audit high findings
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: engineering, security, operations, frontend, client-approver
---

# High findings

## AUD-H-001: Auth-lifecycle tables have grants without RLS

`20260813120000_auth_jwks_invitations_v1.sql:15-40,289-291` creates
`app.revoked_sessions` and `app.mfa_recovery_requests` and grants `app_api`
access without enabling or forcing RLS. A compromised or mistakenly exposed
`app_api` SQL path can enumerate revocation or MFA-recovery data.

Revoke direct table access in favor of narrow RPCs, or add deny-by-default
`ENABLE` and `FORCE ROW LEVEL SECURITY` policies. Prove own-subject and
cross-subject behavior under each runtime role.

## AUD-H-002: Broad `app_api` reads bypass ACL intent

Policies in `20260812135916_roles_rls_identity_v1.sql`,
`20260814103200_finalize_uploading_status_grants_v1.sql`, and
`20260814130000_hybrid_retrieval_v1.sql` include `USING (true)` or only
`deleted_at IS NULL` on profiles, versions, chunks, tables, terms, and aliases.
Application RPCs perform ACL checks, but a future direct query or SQL-injection
path can bypass that discipline.

Prefer RPC-only access and revoke table `SELECT`. Where direct reads are
required, bind trusted caller context and enforce document ACL in RLS. Add
negative direct-select contracts.

## AUD-H-003: RLS is enabled but not forced on core tables

`20260812135115_indexes_rls_grants_v1.sql:70-75` enables RLS without forcing it
on several ingestion, invitation, ledger, and glossary tables. Table owners and
superusers can bypass policies, which increases the impact of role ownership or
connection-string mistakes.

Force RLS on every tenant-sensitive table and assert owner/runtime-role
separation from `pg_class`, `pg_roles`, and live connection identity.

## AUD-H-004: Parallel retrieval can exceed the one-replica connection proof

`hybrid_run.py:509-512,837-859` runs retrieval channels in parallel while
`query_graph_runtime.py:158-163,438-444` opens role-specific database work.
The documented pool budget covers one API, one worker, and five query runs.
Replica or channel growth can multiply connections beyond the managed pooler
budget.

Load test with real channel fan-out and `pg_stat_activity` grouped by role.
Introduce bounded pools or a shared channel semaphore before increasing
replicas or concurrency.

## AUD-H-005: Lease loss does not cancel in-flight expensive work

`apps/worker/src/smart_rag_worker/lifecycle.py:496-512,801-803` detects a lost
lease before completion, but parse and embedding work already in progress can
continue until a node boundary. A reclaimed job can duplicate provider spend
or projection work before idempotency resolves the conflict.

Propagate a cooperative cancellation token through parse, chunk, embed, and
graph loops. Test lease expiry during each expensive stage and assert no
duplicate external charge or canonical write.

## AUD-H-006: Graph throughput has process-wide serialization points

`packages/core/src/smart_rag_core/jobs/graph_writer.py:57-77` uses one writer
lease and advisory lock. `query_graph_runtime.py:321-327` also serializes
LightRAG budget binding behind a process-wide lock. Backlog and latency can grow
linearly under concurrent graph ingestion/query work.

Measure queue age and documents per hour at increasing corpus sizes. Remove
process-global mutable adapter state before approving horizontal scale, or
record a deliberate single-writer capacity envelope.

## AUD-H-007: Deployment automation does not prove completion and readiness

`.github/workflows/staging-deploy.yml:40-56` issues an SSM command but does not
prove polling to terminal success, digest verification, `/health/ready`, SSE
health, or rollback. CI can report success before the instance has failed.

Wait on `GetCommandInvocation`, fail on any non-success status, verify candidate
digests, run readiness and smoke checks, and automatically restore the previous
known-good color on failure.

## AUD-H-008: Restore, alert delivery, and secret rotation are unproven

IaC defines alarms, SNS, KMS, audit anchors, and Secrets Manager resources, but
repository evidence still marks live delivery, rotation, PITR restore, and
timed recovery as blocked or not run. Declared resources do not prove an
operable incident response.

Run synthetic alarms with acknowledgement, populate and rotate secrets through
the intended identity path, and perform a timed Supabase plus derived-store
recovery drill.

## AUD-H-009: Contract tests can silently skip when infrastructure is absent

About 42 contract files contain infrastructure-dependent `pytest.skip` paths.
A nominally green contract tier can omit Postgres, ClamAV, crawl-proxy, or other
critical boundaries without failing the job.

Create required-stack CI jobs and fail when the expected marker count is zero
or unexpected skips occur. Keep optional local behavior separate from release
proof.

## AUD-H-010: Security-sensitive god files expand review blast radius

The current tree includes large modules such as:

- `apps/frontend/src/lib/api.ts` at about 1,918 lines;
- `lightrag_adapter.py` at about 1,464 lines;
- `hybrid_run.py` at about 1,429 lines;
- query `pipeline.py` at about 1,143 lines;
- backend `sse_stream.py` and worker `lifecycle.py` at about 910 lines each.

Twenty-six Python files exceed 800 lines. Split by stable responsibility after
release gates are green, using behavior-neutral commits and contract parity.
Add enforceable complexity and file-size budgets.

## AUD-H-011: The mobile sign-in task is buried under diagnostics

At 390-by-844, the login document was 2,413 pixels high and the form began near
1,961 pixels. Full protected navigation, readiness status, outage copy, and an
848-pixel reviewed fixture appeared first. This is a severe task-priority
failure and exposes engineering language such as gap identifiers to end users.

Render a focused public auth shell. Move readiness and hostile-text fixtures to
an authenticated diagnostics/story route, collapse navigation for signed-out
users, and put the form in the first viewport.

## AUD-H-012: Production CSP still permits inline scripts

`apps/frontend/next.config.ts:8-13,98-102` deliberately returns
`script-src 'self' 'unsafe-inline'` in production. React escapes normal text and
the hostile-text tests are positive controls, but any future injection sink has
weaker browser containment.

Move to nonce-based CSP in `proxy.ts`, keep production free of
`unsafe-eval`, and test emitted headers on the deployed Next.js response.

## AUD-H-013: Missing Supabase public configuration fails open at the UI shell

`apps/frontend/src/proxy.ts:34-40` returns `NextResponse.next()` when the public
Supabase URL or anon key is missing. Protected console routes and administration
forms can render without a session check. FastAPI remains authoritative and
should deny data operations, but production configuration failure exposes the
console shell and creates inconsistent auth behavior.

Fail closed to a dedicated configuration-error route, make the production build
or startup reject missing public Auth variables, and test every protected route
with both variables absent.

## AUD-H-014: SSE and async failures can become silent unhandled rejections

`chat-app.tsx:289-323` handles reconnect 404 but passes other non-OK responses to
the SSE consumer. Both send and reconnect rethrow non-abort errors from async
event handlers. This can leave stale running state and an unhandled promise
without a user-visible recovery path. The app also has no route-level
`error.tsx` for render failures.

Classify every non-OK reconnect response before SSE parsing, convert transport
exceptions into bounded failure state, and add route-level error boundaries for
render errors. Test 401, 403, 429, 500, malformed SSE, and connection loss.

## AUD-H-015: Missing API origin silently defaults production clients to localhost

`apps/frontend/src/lib/env.ts:10-12` defaults
`NEXT_PUBLIC_API_BASE_URL` to `http://127.0.0.1:8000`. In a production browser
that address is the end user's machine, and the CSP may also block it. A missing
build variable therefore produces a misleading broken deployment rather than a
clear configuration failure.

Allow the localhost default only in development. Fail the production build or
render a blocking configuration error when the API origin is absent or invalid.
