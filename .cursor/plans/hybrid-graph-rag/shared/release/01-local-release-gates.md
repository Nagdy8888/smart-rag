---
name: hybrid-graph-rag-local-release-gates
status: active
applies_to: phase-09
source_phase: ../../09-phase-local-release-candidate.md
---

# Local release gates

## Ownership boundary

Phase 9 applies every gate below against the exact local images and the local Supabase, ParadeDB, Valkey, and proxy stack. Requirements explicitly needing managed Supabase behavior, GitHub OIDC/SSM/Secrets Manager, production environment protection, CloudFront/WAF/Caddy staging topology, real-CDN streaming, AWS KMS/S3 Object Lock, direct-origin checks, or managed restore belong to the [managed gates](./02-managed-gates.md). Phase 9 records those requirements as open Phase 10 blockers; it does not provision cloud resources, mark them skipped, fake their evidence, or require cloud proof after every locally applicable gate passes.

This contract is read only with the [Phase 9 shared contract](../../09-phase-local-release-candidate/00-shared-contracts.md) and a Phase 9 packet that links it. The [global contracts](../../00-global-contracts.md) remain authoritative.

## Hard CI tiers

GitHub Actions use hard gates with no `|| true` fallbacks, tiered so developers are not pushed to bypass a monolithic pipeline. Phase 9 validates only workflows and controls executable without managed cloud resources:

- Per PR: Python/Node format, lint, strict types, unit/component tests, generated OpenAPI contract, migration static checks, secret/dependency scans, and production frontend build.
- Merge queue/main: migration reset/reapply, RLS/security integration, local Supabase/pgvector/ParadeDB BM25/LightRAG/Valkey integration, parser sandbox, Docker builds/health, and targeted Playwright smoke tests.
- Nightly: full Playwright, retrieval/routing/injection evaluation with frozen fixtures, dependency/Trivy scans, backup/restart tests, and cost-capped opt-in live-model evaluation.
- Local release candidate: load/deadline/connection-pool tests, complete local security/evaluation suite, local Supabase restore drill, exact image builds, and no skipped locally required tests.
- Every integration job fails if zero matching tests execute.

## Local launch-blocking acceptance gates

Each item is launch-blocking. Its evidence belongs in `docs/development/phase-09-local-release-candidate-evidence.md`; a failure stops the active packet under its stated stop route rather than being skipped or converted to fake success.

### Identity, authorization, and graph isolation

- Viewers cannot mutate data or administer tools; disabled users and refresh sessions are revoked; users cannot read another user's private conversations/runs.
- Typed server-derived RPC identity returns zero rows for missing, forged, disabled, or stale caller context under transaction pooling.
- The explicit company-visible/restricted ACL model, grant authority, viewer read-only grants, and default visibility pass negative tests.
- ACL-restricted documents are rejected from LightRAG, and restricted graph/entity/relation text never appears in Combined or inspection.

### Local asymmetric Auth and mutation controls

- Local Supabase uses asymmetric signing keys.
- JWKS cache and unknown-`kid` behavior plus local standby → active → retired rollover fixtures preserve valid sessions, reject revoked or unknown keys, and prove no FastAPI HS256 secret fallback exists.
- Owner/admin and upload-capable member MFA, upload-permission downgrade, URL-source approval, corpus-write provenance, and anomaly alerts are exercised.
- Managed rollover proof remains a Phase 10 gate.

### Ingestion, replay, quotas, and structure

- Re-ingestion, retry, restart, lease reclaim, BM25 projection replay, and graph-index replay create no duplicate canonical chunks, duplicate active BM25 projection rows, or duplicate active LightRAG versions.
- Shared-workspace graph indexing never exceeds concurrency one.
- Per-user/company upload quotas, actual-size enforcement, signed-upload expiry, and never-finalized quarantine cleanup reject or purge abuse and audit it.
- Chunk fixtures meet the Section 1 size/structure gate, flag figure/chart-only regions, remove only declared boilerplate, reconstruct parents, preserve original citation coordinates, and suppress exact/fuzzy duplicates without losing provenance.

### Deletion, ACL downgrade, and derived-state cleanup

- Deletion or ACL downgrade excludes sources atomically, increments BM25 visibility generation, and prevents stale projection evidence through mandatory Supabase recheck.
- BM25 purge plus targeted graph cleanup verifies within 24 hours.
- Native merged summaries are never exposed.
- Dirty changes are batched into a clean graph rebuild within seven days.
- Graph service is quarantined or degraded whenever resolver or cleanup verification fails.

### Resume, idempotency, and durable budgets

- Killing the worker mid-run resumes safely from checkpoints.
- Every OpenAI call and embedding, including LightRAG internals, summaries, and verifier, is durably budgeted and traced.
- Reserve-once/true-up, concurrent child calls, cancellation, and crash reaping cannot overspend.
- Shared budget-row lock wait meets its signed gate.
- No direct SDK bypass exists.

### Rate-limit ownership and Valkey degradation

- Rate limits work across multiple API workers while ParadeDB, the LightRAG schema, and both Valkey instances remain private.
- Killing, restarting, ACL-denying, or filling Valkey proves auth-sensitive limits fall back or fail closed, cost-bearing mutations fail closed, low-risk degraded reads alert, and recovery does not double-admit.
- Direct Supabase Auth operations use configured provider rate/captcha controls.
- FastAPI counters and degraded buckets cover only FastAPI-mediated operations.

### Routing, grounding, and composed answers

- Direct factual fixtures route to Hybrid.
- Current relationship/multi-hop fixtures route to Combined.
- Explicit historical relationship fixtures route to Hybrid with the temporal limitation.
- Full-document summaries require complete section coverage or scoped refusal.
- Negation and media-dependent fixtures clarify, prove, or refuse safely.
- Weak misroutes escalate once.
- Structured calculations are deterministic and cited.
- Graph-only is inspection.
- Composed inferences cite every atomic link.
- Combined degrades safely.
- Broad/global and comparison fixtures follow the full matrix.
- Mixed prose/calculation requests compose branches.
- Global summaries only steer Hybrid.
- Second-stage fusion must beat naive union or be removed.

### Hybrid, BM25, reranking, and temporal behavior

- Filtered HNSW retains recall under selective ACL/date/tag filters with the bounded 100-candidate dense profile.
- ParadeDB BM25 uses the pinned Unicode tokenizer, typed field/phrase/boolean query, bounded 75-survivor/300-scan contract, and batched authoritative Supabase recheck.
- Arabic projection/query normalization is byte-identical and improves the labeled BM25 baseline without changing citation text.
- Seeded codes and aliases meet their gates.
- Variant fusion does not sum generic matches.
- Killing or version-mismatching ParadeDB visibly degrades to dense plus term with zero unauthorized or stale evidence.
- Query-profile fields including negation, document, media, and historical signals meet signed per-field targets before route/ranking attribution.
- Temporal questions use the signed UTC/company-timezone anchor and select authoritative recent/as-of sources.
- The accuracy-first OpenAI policy reranks non-trivial queries, validates top-20 output, never triggers from raw RRF score gaps, and never falls through to a local model.
- The skipped-case counterfactual report justifies every tightened trigger or pool reduction.
- Coverage thresholds are frozen per query class from development precision/answer-rate/refusal curves.
- Insufficient, contradictory, incomplete, and ACL-filtered cases refuse or return verified partial rather than exploiting a threshold chosen on the final holdout.

### Graph readiness and bounded resolution

- `Graph Ready` requires thresholded precomputed chunk/relation-to-canonical mappings and signed per-language Arabic/mixed coverage.
- Query-time resolution performs bounded joins with no N-per-statement searches.
- New-version pointer flips expose exactly one version.
- Profile keywords prevent duplicate LightRAG query extraction.
- Authorized ACL graph-blindness notices appear only for users entitled to know the restricted sources exist.

### Query replay, compatibility, and streaming

- Idempotent query retries create one paid run.
- Idempotency-key/run-event garbage collection preserves replay boundaries.
- Additive OpenAPI/SSE contracts, minimum-client handshake, and unknown-event tolerance pass.
- SSE resumes after an event sequence.
- Heartbeats survive the local Caddy/reverse-proxy path.
- Every run terminates within its step and deadline ceiling.
- A five-run Composite load proves event-loop lag and heartbeat-jitter gates while CPU-heavy stages use bounded offload.
- A deliberately slow local stream proves heartbeat, disconnect, and resume through local Caddy.
- Real managed-CDN and timeout-IaC proof remains a Phase 10 gate.

### Injection, malware, governance, and egress

- Prompt, BM25-query, graph injection, and entity-name XSS fixtures cannot change instructions, execute unrestricted ParadeDB SQL/query syntax, forge source IDs, invoke tools, or execute markup.
- Malware tests distinguish the frozen CI database from production freshness, reject stale or incompatible signatures, persist scan versions, and re-scan before promotion.
- Parser-sandbox fixtures fail closed.
- Data-governance fixtures prove missing, prohibited, or unknown attestations or detected sensitive patterns never reach OpenAI, LangSmith, or another covered external flow.
- Approved cases are auditable under the signed provider packet.
- URL crawling cannot bypass admin approval or the dedicated egress proxy.
- Network tests prove parser, API, and agent containers cannot use unrestricted egress.

### Privacy, read audit, cache, and audit-chain integrity

- Conversation deletion immediately denies reads/resume and removes messages, runs, events, citations, checkpoints, store summaries, and private feedback while preserving only content-free audit/aggregate records.
- Restricted evidence, preview, and downloads produce append-only read-access events without passage text.
- Populated retrieval-cache and stale-BM25-projection fixtures followed by deletion or ACL downgrade yield zero stale evidence after mandatory Supabase recheck.
- Local audit-chain tests detect row change, removal, reorder, fork, and missing or invalid anchors through the Phase 6 exporter test adapter.
- Managed immutable-anchor proof remains a Phase 10 gate.

### Embedding, memory, traces, and compatibility windows

- The embedding ADR proves small-1536 versus large-1536 and at least one reduced-large dimension on a disjoint Arabic/mixed qualification slice.
- The selected model, dimension, and index type match the schema and gateway.
- Representative index-memory extrapolation fits the approved tier and envelope.
- Maintenance queries pause under user-load thresholds.
- Any read-replica candidate is rejected unless primary ACL/current-version revalidation succeeds.
- With the production configuration profile loaded locally, emitted LangSmith traces provably omit or redact configured payload fields and raw source text.
- CI fails on skipped integration controls, broken migrations, types, frontend build, or container build.
- Expand/contract static checks reject destructive same-release migrations.
- An old API image serves authenticated read/chat/upload smoke traffic against the post-expansion local schema during a bounded drain simulation.

### Local database and Storage restore

- The local restore drill covers application schemas, canonical chunks, BM25 outbox/index-version state, mappings, private LightRAG tables, `documents-quarantine`, `documents-originals`, `web-snapshots`, and `table-artifacts`.
- Reconciliation quarantines orphaned objects, marks missing or hash-mismatched references unavailable, excludes them from retrieval and graph, and raises an admin notification.
- The ParadeDB volume is then destroyed and rebuilt only from restored authorized current Supabase data.
- Sampled BM25 candidate parity and recovery duration are measured.
- ParadeDB files are not canonical backup inputs.

## Failure routes

- A failed authorization, stale-evidence, deletion, budget, grounding, restore, or egress gate is a local launch blocker and cannot be averaged away.
- A missing, skipped, empty, flaky, or unavailable locally mandatory test is a failed gate.
- A gate that genuinely requires managed infrastructure is recorded, with owner and expected evidence, in the Phase 9 evidence document and handed to Phase 10; it does not fail an otherwise complete Phase 9 local proof.
- A numeric quality, latency, capacity, or cost miss follows the decision route in the [sizing envelope](./05-sizing-envelope.md): repair, resize/isolate, or reduce and re-sign the supported envelope before staging.
