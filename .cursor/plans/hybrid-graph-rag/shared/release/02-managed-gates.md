---
name: hybrid-graph-rag-managed-gates
status: active
applies_to: phases-09-and-10
source_phase: ../../10-phase-managed-staging.md
---

# Managed release gates

## Phase ownership

Phase 9 records, but does not claim or simulate, the following managed blockers:

- managed Supabase pooling plus database and Storage restore reconciliation and JWKS rollover;
- production EC2 ParadeDB private network, volume, resource limits, and clean rebuild;
- GitHub OIDC plus protected environment-approved expand/contract migrations using SSM and Secrets Manager;
- CloudFront/WAF/Caddy production topology and direct-origin rejection;
- independent Vercel/API deploy skew and the real 50-second CDN stream with asserted 90-second timeouts;
- AWS KMS/S3 Object Lock anchors;
- provider egress controls;
- origin-secret dual rotation;
- an external security assessment;
- AWS/Supabase billing alarms and staging alert delivery; and
- IaC/policy checks for long-lived secrets, migration approval, private ports, ParadeDB/Valkey limits, and workload/availability triggers.

Phase 10 consumes the exact Phase 9 images and local reports, implements and proves these managed extensions with synthetic or redacted staging data, and reruns the shared security/evaluation gates against staging without weakening or silently replacing Phase 9 evidence. This contract is read only when linked by a Phase 9 or Phase 10 packet. The [global contracts](../../00-global-contracts.md), [Phase 9 shared contract](../../09-phase-local-release-candidate/00-shared-contracts.md), and [Phase 10 shared contract](../../10-phase-managed-staging/00-shared-contracts.md) preserve the phase boundaries.

## Protected migration and credential custody

- Managed migration and deployment workflows use GitHub OIDC to assume a repository- and environment-scoped short-lived AWS role.
- Workflows store no AWS access key and no database or bootstrap credential.
- Production DDL is a protected GitHub Environment action requiring designated approval, immutable migration artifact/hash review, and branch/tag restrictions.
- The OIDC role may invoke only the named SSM migration document and deployment targets.
- The one-shot migration job retrieves the environment-specific database credential from Secrets Manager through its instance or task role, redacts output, destroys the process environment on exit, and records migration hash, operator, and result.
- Separate staging and production credentials rotate at least every 90 days and immediately after suspected exposure.
- Migration artifacts obey the signed expand/contract ADR.
- Expansion remains backward-compatible with the draining old API slot; backfill and code promotion occur before a destructive contract migration in a later release.
- Static policy rejects same-release drop, narrow, enum, RLS, and function incompatibilities.
- Schema rollback is a reviewed forward fix unless the migration has a qualified reversible pre-data boundary.

## Managed hard CI tiers

GitHub Actions use hard gates with no `|| true` fallbacks, tiered so developers are not pushed to bypass a monolithic pipeline:

- Per PR: Python/Node format, lint, strict types, unit/component tests, generated OpenAPI contract, migration static checks, secret/dependency scans, and production frontend build.
- Merge queue/main: migration reset/reapply, RLS/security integration, local Supabase/pgvector/ParadeDB BM25/LightRAG/Valkey integration, parser sandbox, Docker builds/health, and targeted Playwright smoke tests.
- Nightly: full Playwright, retrieval/routing/injection evaluation with frozen fixtures, dependency/Trivy scans, backup/restart tests, and cost-capped opt-in live-model evaluation.
- Release/staging: load/deadline/connection-pool tests, complete security/evaluation suite, restore drill, IaC validation, and no skipped required tests.
- Every integration job fails if zero matching tests execute.

## Managed launch-blocking acceptance gates

Every item below is launch-blocking and must be evidenced in `docs/development/phase-10-managed-staging-evidence.md`. A missing, skipped, empty, flaky, or unavailable mandatory test is failed, not passed.

### Authorization, identity, and graph isolation

- Viewers cannot mutate data or administer tools.
- Disabled users and refresh sessions are revoked.
- Users cannot read another user's private conversations or runs.
- ACL-restricted documents are rejected from LightRAG.
- Restricted graph, entity, or relation text never appears in Combined or inspection.

### Managed asymmetric Auth

- Local and managed Supabase use asymmetric signing keys.
- JWKS cache and unknown-`kid` behavior plus standby → active → retired rollover preserve valid sessions, reject revoked or unknown keys, and prove no FastAPI HS256 secret fallback exists.
- Owner/admin and upload-capable member MFA, upload-permission downgrade, URL-source approval, corpus-write provenance, and anomaly alerts are exercised.

### Replay, deletion, budgets, and rate limits

- Re-ingestion, retry, restart, lease reclaim, BM25 projection replay, and graph-index replay create no duplicate canonical chunks, duplicate active BM25 rows, or duplicate active LightRAG versions.
- Shared-workspace graph indexing never exceeds concurrency one.
- Chunk fixtures meet the Section 1 size/structure gate, remove only declared boilerplate, reconstruct parents, preserve original citation coordinates, and suppress exact/fuzzy duplicates without losing provenance.
- Deletion or ACL downgrade excludes sources atomically, increments BM25 visibility generation, prevents stale BM25 evidence through Supabase recheck, verifies BM25 purge plus targeted graph cleanup within 24 hours, never exposes native merged summaries, batches a clean graph rebuild within seven days, and quarantines or degrades graph service whenever resolver or cleanup verification fails.
- Killing the worker mid-run resumes safely from checkpoints.
- Every OpenAI call and embedding, including LightRAG internals, summaries, and verifier, is durably budgeted and traced.
- Reserve-once/true-up, concurrent child calls, cancellation, and crash reaping cannot overspend; shared budget-row lock wait meets its gate; no direct SDK bypass exists.
- Rate limits work across multiple API workers while ParadeDB, the LightRAG schema, and both Valkey instances remain private.
- Killing, restarting, ACL-denying, or filling Valkey proves auth-sensitive limits fall back or fail closed, cost-bearing mutations fail closed, low-risk degraded reads alert, and recovery does not double-admit.

### Routing, grounding, and retrieval

- Direct factual fixtures route to Hybrid.
- Relationship or multi-hop fixtures route to Combined.
- Weak misroutes escalate once.
- Structured calculations are deterministic and cited.
- Graph-only is inspection.
- Composed inferences cite every atomic link.
- Combined degrades safely.
- Broad/global and comparison fixtures follow the full matrix.
- Mixed prose/calculation requests compose branches.
- Global summaries only steer Hybrid.
- Second-stage fusion must beat naive union or be removed.
- Filtered HNSW retains recall under selective ACL/date/tag filters with the bounded 100-candidate dense profile.
- Private ParadeDB BM25 uses the pinned digest and version, Unicode tokenizer, typed field/phrase/boolean query, bounded 75-survivor/300-scan contract, and batched authoritative Supabase recheck.
- Arabic projection/query normalization is byte-identical and improves the labeled BM25 baseline without changing citation text.
- Seeded codes and aliases meet their gates.
- Variant fusion does not sum generic matches.
- Killed or version-mismatched ParadeDB visibly degrades to dense plus term with zero unauthorized or stale evidence.
- Query-profile fields meet signed per-field targets before route/ranking attribution.
- Temporal questions select authoritative recent or as-of sources.
- The accuracy-first OpenAI policy reranks non-trivial queries, validates top-20 output, never triggers from raw RRF score gaps, and never falls through to a local model.
- Its skipped-case counterfactual report justifies every tightened trigger or pool reduction.
- Coverage thresholds are frozen per query class from development precision/answer-rate/refusal curves.
- Insufficient, contradictory, incomplete, and ACL-filtered cases refuse or return verified partial rather than exploiting a threshold chosen on the final holdout.

### Graph readiness, replay, and streaming

- `Graph Ready` requires thresholded precomputed chunk/relation-to-canonical mappings.
- Query-time resolution performs bounded joins with no N-per-statement searches.
- New-version pointer flips expose exactly one version.
- Profile keywords prevent duplicate LightRAG query extraction.
- Idempotent query retries create one paid run.
- SSE resumes after an event sequence.
- Heartbeats survive the CDN/Caddy path.
- Every run terminates within its step and deadline ceiling.
- A five-run Composite load proves event-loop lag and heartbeat-jitter gates while CPU-heavy stages use bounded offload.
- The 50-second staging stream passes through CloudFront with asserted 90-second read/keep-alive settings, heartbeats, disconnect, and resume.

### Injection, governance, egress, and privacy

- Prompt, BM25-query, graph injection, and entity-name XSS fixtures cannot change instructions, execute unrestricted ParadeDB SQL/query syntax, forge source IDs, invoke tools, or execute markup.
- Malware tests distinguish the frozen CI database from production freshness, reject stale or incompatible signatures, persist scan versions, and re-scan before promotion.
- Parser-sandbox fixtures fail closed.
- Data-governance fixtures prove missing, prohibited, or unknown attestations or detected sensitive patterns never reach OpenAI.
- Approved cases are auditable.
- URL crawling cannot bypass admin approval or the dedicated egress proxy.
- Network tests prove parser, API, and agent containers cannot use unrestricted egress.
- Conversation deletion immediately denies reads/resume and removes messages, runs, events, citations, checkpoints, store summaries, and private feedback while preserving only content-free audit/aggregate records.
- Audit-chain tests detect row change, removal, reorder, fork, and missing KMS/S3 anchors.

### Embedding, traces, IaC, and compatibility

- The embedding ADR proves small-1536 versus large-1536 and at least one reduced-large dimension on a disjoint Arabic/mixed qualification slice.
- The selected model, dimension, and index type match the schema and gateway.
- Representative index-memory extrapolation fits the approved tier and envelope.
- Maintenance queries pause under user-load thresholds.
- Any read-replica candidate is rejected unless primary ACL/current-version revalidation succeeds.
- With the production environment profile loaded, emitted LangSmith traces provably omit or redact configured payload fields and raw source text.
- IaC and policy tests reject long-lived GitHub AWS or database secrets, unapproved production migration, mutable, unpinned, or publicly reachable ParadeDB, missing ParadeDB/Valkey credentials or memory limits, direct-origin access, absent origin-secret dual-rotation support, and undocumented workload/availability triggers.
- CI fails on skipped integration controls, broken migrations, types, frontend build, or container build.
- The version handshake and additive OpenAPI/SSE policy survive both deployment orders: new API with the previous frontend and new frontend with the previous API.
- Unsupported clients receive the documented upgrade response before paid work.
- Unknown additive events do not break an active stream.
- A blue/green old API slot serves the qualified smoke suite against the post-expansion schema during drain.
- Destructive contract DDL is absent from that release.

### Managed restore and external assessment

- Managed restore covers all application and private schemas plus `documents-quarantine`, `documents-originals`, `web-snapshots`, and `table-artifacts` at a recorded recovery point.
- Reconciliation quarantines object-only orphans, marks missing or hash-mismatched database references `restore_incomplete`, excludes them from Hybrid and graph, and emits an alert.
- ParadeDB is destroyed and rebuilt only from reconciled authorized current Supabase data.
- Sampled BM25 parity and recovery duration are proven.
- No ParadeDB snapshot is accepted as canonical recovery evidence.
- Before Phase 11, an independent third-party penetration test or external security review covers Auth/JWKS, RLS/ACL/identity propagation, ParadeDB private access/query construction/stale-candidate recheck, signed URL/quarantine abuse, SSRF/egress, prompt/graph injection, direct-origin bypass, rate-limit ownership, and Storage policies.
- Critical and High findings are remediated and independently retested.
- Accepted Medium risk has a dated ADR and owner.

## Failure and handoff routes

- Phase 9 records every managed item above as an explicit blocker with expected Phase 10 evidence; lack of cloud proof is not a Phase 9 failure.
- Phase 10 stops on a missing prerequisite, topology drift, unverified provider contract, fake or skipped integration, unresolved Critical/High assessment finding, or any launch-blocking failure after bounded repair.
- Capacity and managed-resource misses follow the [sizing envelope](./05-sizing-envelope.md).
- Topology, network, restore, rotation, alert, and rollback evidence must satisfy the [staging topology contract](./03-staging-topology.md); an unapproved exception cannot be normalized into the baseline.
