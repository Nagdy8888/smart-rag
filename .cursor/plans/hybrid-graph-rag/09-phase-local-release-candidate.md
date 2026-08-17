---
name: hybrid-graph-rag-phase-09-local-release-candidate
phase: 9
status: pending
depends_on: [1, 2, 3, 4, 5, 6, 7, 8]
split_source: true
source_plan: ../hybrid-graph-rag_ab5281ef.plan.md
global_contract: ./00-global-contracts.md
phase_shared_contract: ./09-phase-local-release-candidate/00-shared-contracts.md
evidence_path: docs/development/phase-09-local-release-candidate-evidence.md
---

# Phase 9: Local release candidate

## Mandatory model loading contract

1. Read [`00-global-contracts.md`](./00-global-contracts.md) first, then read this file completely.
2. Read the Phase 9 [`00-shared-contracts.md`](./09-phase-local-release-candidate/00-shared-contracts.md) completely.
3. Select exactly one next unchecked linked packet below and read it completely. Do not load or implement sibling packets.
4. Read only the additional shared/release contracts explicitly linked by that packet.
5. Treat the wrapper, phase shared contract, selected packet, and its linked shared/release contracts as the only implementation scope for this model run. Later phases may clarify an interface but do not authorize managed implementation.
6. Inspect the current repository, schemas, migrations, tests, and pinned dependency versions named by the selected packet before editing. This plan describes targets, not proof that a file or API already exists.
7. Load `.cursor/skills/implement-plan-phase/SKILL.md` and the relevant workspace skills listed below before implementation.
8. Quote the selected packet title, requirement ID, and concrete acceptance checks before editing. Implement the smallest complete packet.
9. Verify unstable external APIs against current primary documentation and add contract tests. Never guess a library method, schema, environment variable, command, or provider behavior.
10. Add positive, failure, authorization, idempotency, bounded-resource, and fallback tests whenever applicable.
11. Run repository-defined format, lint, strict type, test, build, migration, and integration commands relevant to changed files. Inspect rather than invent those commands.
12. Update documentation and `docs/development/phase-09-local-release-candidate-evidence.md` in the same change. Do not leave placeholders, fake success paths, swallowed errors, disabled security, or `TODO` core behavior.
13. Record proof in the exit record. If security, data semantics, cost, or acceptance criteria must change, stop and obtain approval through an ADR or plan update.

## Prerequisites

[Phase 1: Foundation](./01-phase-foundation.md), [Phase 2: Identity and data](./02-phase-identity-data.md), [Phase 3: Ingestion](./03-phase-ingestion.md), [Phase 4: Hybrid RAG](./04-phase-hybrid-rag.md), [Phase 5: GraphRAG](./05-phase-graphrag.md), [Phase 6: Agent intelligence](./06-phase-agent-intelligence.md), [Phase 7: Stitch specification](./07-phase-stitch-specification.md), [Phase 8: Frontend integration](./08-phase-frontend-integration.md)

## Relevant workspace skills

- [`.cursor/skills/verify-release-gates/SKILL.md`](../../../.cursor/skills/verify-release-gates/SKILL.md)

## Scope lock

**In scope:** Local immutable-image release qualification, full non-AWS security/evaluation/load gates, contention and degradation tests, restart/resume, backup/restore, and no-go review.

**Out of scope:** Provisioning AWS, Vercel production, managed staging resources, KMS/S3 anchors, CloudFront/WAF, or production data services.

The scope lock controls implementation sequencing; it does not weaken any security, authorization, durability, budget, grounding, bounded-work, or documentation invariant in the global contract.

## Ordered work packets

Complete these in order. A checked box requires committed implementation evidence in the phase exit record, not only code presence.

1. [x] [Build the exact candidate images and seed only the approved local evaluation corpus through all readiness states.](./09-phase-local-release-candidate/packets/01-build-exact-candidate-images.md)
2. [ ] [Run all applicable hard CI, expand/contract migration compatibility, identity/RLS/BM25/cache/read-audit, graph isolation, injection, parsing, deletion, idempotency/GC, API/SSE compatibility, and redaction gates with no skipped required tests.](./09-phase-local-release-candidate/packets/02-run-applicable-hard-ci-and-security-gates.md)
3. [x] [Measure Hybrid/Combined/table/inspection quality, BM25 projection/query/recheck/rebuild behavior, p50/p95/deadlines, model calls/cost, graph survival, writer throughput, and onboarding ETA.](./09-phase-local-release-candidate/packets/03-measure-quality-latency-and-throughput.md)
4. [ ] [Run foreground-plus-maintenance Supabase/HNSW/ParadeDB/graph load, connection caps, budget-lock contention, CPU offload, and five-stream event-loop tests.](./09-phase-local-release-candidate/packets/04-run-contention-and-five-stream-load.md)
5. [x] [Kill, deny, fill, and restart worker/ParadeDB/Valkey/services to prove reclaim, degraded retrieval/rate behavior, heartbeat/reconnect, and safe recovery.](./09-phase-local-release-candidate/packets/05-prove-failure-degradation-and-recovery.md)
6. [ ] [Run local egress enforcement, dependency/image scans, Supabase database plus all Storage-bucket restore/reconciliation including LightRAG, clean ParadeDB projection rebuild, and instance-equivalent sizing evidence.](./09-phase-local-release-candidate/packets/06-run-egress-scans-restore-and-sizing.md)
7. [ ] [Resolve blockers or explicitly reduce/resign supported limits; leave managed-topology gates clearly open for Phase 10.](./09-phase-local-release-candidate/packets/07-resolve-blockers-and-handoff-managed-gates.md)

## Phase sequence requirement

<!-- markdownlint-disable-next-line MD029 -->
9. Local release candidate: run the full Docker stack through load/eval/security tests including Supabase/ParadeDB/Valkey/CPU contention, BM25 projection/rebuild/outage behavior, graph-onboarding ETA, observability, Supabase database plus Storage restore/reconciliation including LightRAG followed by derived BM25 rebuild, backward-compatible migration/API deploy-window simulations, restart/resume tests, no-go review, and dependency/image audits without using AWS.

## Stop conditions

Stop this phase and report the blocker instead of improvising when:

- a prerequisite phase or required sign-off is incomplete;
- the actual repository contradicts the plan and the difference changes security, data, cost, or acceptance semantics;
- a required dependency contract cannot be verified from its pinned version and primary documentation;
- an authorization, idempotency, deadline, budget, provenance, or fallback test cannot exercise the real boundary;
- a required integration is unavailable and only a fake or skipped test would pass;
- any launch-blocking check fails after bounded repair attempts.

## Required exit record

Create or update `docs/development/phase-09-local-release-candidate-evidence.md` with:

- plan requirement and work-packet number;
- files, migrations, APIs, environment variables, and documentation changed;
- exact verification commands discovered from the repository;
- test/build/lint/type/migration results and relevant measured metrics;
- authorization, failure, idempotency, fallback, and bounded-resource evidence;
- unverified external assumptions or unavailable managed-environment checks;
- deviations, ADR approval, and rollback notes;
- explicit handoff inputs and open blockers for the next phase.

Do not set `status: complete` until every `Done when` item below is proven.

## Canonical detailed requirements

The detailed Phase 9 requirements are redistributed into these normative single-source contracts:

- [Phase 9 shared contracts](./09-phase-local-release-candidate/00-shared-contracts.md)
- [Local release gates](./shared/release/01-local-release-gates.md)
- [Managed-gate ownership and handoff](./shared/release/02-managed-gates.md)
- [Release sizing envelope](./shared/release/05-sizing-envelope.md)

## Phase deliver, review, and done gate

<!-- markdownlint-disable-next-line MD036 -->
**Phase 9 — Local release candidate**

- Deliver: seeded evaluation corpus, routing/quality/limitation report, ParadeDB BM25 projection/query/recheck/outage/rebuild report, foreground-plus-maintenance load report, budget-lock/event-loop/Valkey/cache degradation report, graph writer throughput/ETA, identity/ACL/read-audit/security/egress report, migration/API compatibility evidence, dependency/image scans, restart/resume/GC proof, Supabase database-plus-all-Storage restore/reconciliation proof covering private LightRAG tables plus clean derived BM25 rebuild, and resolved local blockers plus explicit managed handoff.
- Review: actual Supabase CPU/IO/cache/HNSW memory, ParadeDB index/RAM/latency/lag/rebuild/private-role and fallback evidence, cache/BM25 ACL recheck, replica/split need, EC2/ParadeDB/Valkey/CPU-pool resources, graph onboarding duration/per-language coverage, measured limits, migration/API compatibility window, availability triggers, Storage/database reconciliation, and backup retention.
- Done when: the exact immutable candidate images start and pass the full local Docker release suite; the approved seeded corpus produces published routing/retrieval/answer/citation/refusal/limitation/Combined-gain, per-channel BM25 quality, latency/deadline, token/cost, graph-survival/per-language mapping, and writer-throughput/ETA reports; foreground-plus-ParadeDB-rebuild/HNSW/graph-maintenance load proves Supabase and derived-search connection/CPU/IO/cache/memory and 70% pause/isolation behavior; ParadeDB private roles, typed query safety, projection replay/versioning, batched Supabase recheck, stale ACL/deletion rejection, 75-survivor/300-scan bounds, clean rebuild parity, and dense+term outage degradation pass; reserve-once lock wait, five-stream event-loop/heartbeat, bounded CPU offload, OCR, EC2-equivalent, Valkey/cache OOM/outage/recovery, and local egress measurements meet or explicitly reduce signed limits; expand/contract lint, migration reset/reapply, old-slot-on-new-schema and additive API/SSE compatibility, worker/service kill/restart/resume, idempotency/GC, identity/ACL/cache/read-audit, deletion/cleanup, injection/XSS, upload quota/quarantine, malware/parser/crawl, full governance packet, redaction, rate ownership/degradation, dependency/image scans, and local Supabase database plus all Storage-bucket restore/reconciliation including private LightRAG tables followed by derived BM25 rebuild pass with no skipped required tests; every local blocker is resolved and every external assessment/billing/managed-topology item is documented as an explicit Phase 10 handoff; and the supported envelope is proven, resized, isolated, or reduced with client sign-off before staging.
