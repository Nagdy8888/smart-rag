---
name: implement-supabase-security
description: Implements Supabase schemas, RLS, Auth, Storage, database roles, queues, budgets, and migrations for this RAG platform. Use for any Supabase, PostgreSQL, pgvector, Auth, Storage, ACL, or migration work.
---

# Implement Supabase Safely

Read the active phase wrapper/shared contract and exactly one selected packet. Load the Phase 2 identity/data or Phase 3 ingestion contract only when the packet explicitly consumes it, and load only the linked managed release contract for Phase 10. Do not load sibling packets or infer requirements from legacy section numbers.

## Required order

1. Inspect current migrations, generated types, local Supabase config, roles, policies, functions, and tests.
2. Verify the local and managed-target PostgreSQL/pgvector extension versions and confirm the plan's `pg_search` extension runs only in private ParadeDB, never managed Supabase.
3. Add one forward migration with schema-qualified objects and explicit grants/revokes.
4. Enable RLS and write policies before exposing a table/view/function.
5. Regenerate types and update repositories/contracts.
6. Add migration reset/reapply plus role/ACL negative tests.

## Non-negotiable data rules

- Runtime API, checkpointer, worker, LightRAG, audit, and migration roles have separate minimal grants.
- Never put `service_role` in runtime API/worker/frontend code.
- User-facing uploads use JWT + Storage RLS; worker Storage access is bucket/path restricted.
- Conversations/runs are creator-private unless the explicit audit policy grants access.
- `documents.current_version_id` is the single visibility pointer.
- Only current company-visible documents may be graph-eligible.
- ACL downgrade/deletion invalidates graph mappings, increments BM25 visibility generation, and writes the projection update/delete job atomically.
- ACL expansion requires authorized admin approval for a new graph-index job; it never auto-enables graph indexing.
- Query admission reserves the route maximum once against company/user budgets; model calls consume only the run-local reservation, and completion/crash reaping true-up actual usage without relocking shared budget rows per call. Ingestion reserves per job/batch.
- Queue claiming uses `SKIP LOCKED`, lease owner/expiry, heartbeat, attempts, and reclaim.
- API/RPC traffic may use transaction pooling. LangGraph checkpointers and LightRAG use session mode or direct connections; prove the total pool budget remains below 70% of the selected Supabase tier limit.
- Apply role-specific statement/lock/idle-transaction timeouts and bounded `work_mem`; maintenance HNSW/graph work pauses under foreground load. Any read replica is candidate-generation only and every selected ID is revalidated on the primary for current-version/ACL visibility.
- Auth uses PKCE, asymmetric signing keys/JWKS with tested `kid` rollover and no production HS256 fallback, owner/admin plus upload-capable-member MFA, single-use 24-hour invitations, server-controlled roles, and refresh-session revocation on disable or privileged/upload-role downgrade.
- Browser-direct email/password/OAuth/reset/MFA limits belong to configured Supabase Auth controls. The atomic private Postgres degraded counters and fail-closed rule apply only to FastAPI-mediated sensitive/cost-bearing operations that FastAPI actually receives.

## Retrieval and projection checks

- Managed Supabase stores canonical chunks, vectors, exact/trigram terms, versioned normalized BM25 projection text, durable `bm25_index_jobs`, active BM25 index/normalization versions, and final authorization state. It does not install `pg_search`.
- The private ParadeDB service has separate bootstrap/writer/read-only roles. Its derived projection is keyed by canonical chunk/version IDs; every returned ID is batch-rechecked through the security-invoker Supabase RPC before fusion/evidence.
- Arabic applies the same schema-qualified immutable versioned normalizer to canonical projection text and byte-identical core/ParadeDB query forms, preserves raw citation text, and ships conformance/idempotence fixtures.
- HNSW requires pgvector 0.8+, iterative scans, allow-listed `ef_search`, and bounded exact fallback.
- Apply authorization/current-version predicates in the security-invoker RPC.
- Set statement, row, and path limits server-side.

## Proof required

Run clean migration reset, RLS matrix tests, privilege tests, Arabic Supabase-projection/core/ParadeDB normalization parity, BM25 outbox/version/current-pointer atomicity, stale BM25 candidate rejection, seeded alias/code search, JWKS rollover, FastAPI-limit fallback, reserve/true-up contention, audit-chain mutation, conversation cascade deletion, primary replica revalidation, queue crash-reclaim, current-version flip, graph-eligibility isolation, and selective-filter ANN tests. Never report the migration safe based only on successful SQL execution.
