---
name: hybrid-graph-rag-phase-10-managed-staging
phase: 10
status: pending
depends_on: [1, 2, 3, 4, 5, 6, 7, 8, 9]
split_source: true
source_plan: ../hybrid-graph-rag_ab5281ef.plan.md
global_contract: ./00-global-contracts.md
phase_shared_contract: ./10-phase-managed-staging/00-shared-contracts.md
evidence_path: docs/development/phase-10-managed-staging-evidence.md
---

# Phase 10: Managed staging

## Mandatory model loading contract

1. Read [`00-global-contracts.md`](./00-global-contracts.md) first, then read this file completely.
2. Read the Phase 10 [`00-shared-contracts.md`](./10-phase-managed-staging/00-shared-contracts.md) completely.
3. Select exactly one next unchecked linked packet below and read it completely. Do not load or implement sibling packets.
4. Read only the additional shared/release contracts explicitly linked by that packet.
5. Treat the wrapper, phase shared contract, selected packet, and its linked shared/release contracts as the only implementation scope for this model run. Phase 11 may clarify promotion inputs but does not authorize production access or promotion.
6. Inspect the current repository, schemas, migrations, tests, IaC, and pinned dependency/provider versions named by the selected packet before editing. This plan describes targets, not proof that a file, API, managed feature, or provider behavior exists.
7. Load `.cursor/skills/implement-plan-phase/SKILL.md` and the relevant workspace skills listed below before implementation.
8. Quote the selected packet title, requirement ID, and concrete acceptance checks before editing. Implement the smallest complete packet.
9. Verify unstable external APIs and provider contracts against current primary documentation and add contract tests or policy assertions. Never guess a library method, schema, environment variable, command, managed feature, or provider behavior.
10. Add positive, failure, authorization, idempotency, bounded-resource, fallback, topology, and rollback tests whenever applicable.
11. Run repository-defined format, lint, strict type, test, build, migration, IaC, integration, and deployment-verification commands relevant to changed files. Inspect rather than invent those commands.
12. Use only synthetic or redacted staging data. Update documentation and `docs/development/phase-10-managed-staging-evidence.md` in the same change. Do not leave placeholders, fake success paths, swallowed errors, disabled security, or `TODO` core behavior.
13. Record proof in the exit record. If security, data semantics, cost, topology, or acceptance criteria must change, stop and obtain approval through an ADR or plan update.

## Prerequisites

[Phase 1: Foundation](./01-phase-foundation.md), [Phase 2: Identity and data](./02-phase-identity-data.md), [Phase 3: Ingestion](./03-phase-ingestion.md), [Phase 4: Hybrid RAG](./04-phase-hybrid-rag.md), [Phase 5: GraphRAG](./05-phase-graphrag.md), [Phase 6: Agent intelligence](./06-phase-agent-intelligence.md), [Phase 7: Stitch specification](./07-phase-stitch-specification.md), [Phase 8: Frontend integration](./08-phase-frontend-integration.md), [Phase 9: Local release candidate](./09-phase-local-release-candidate.md)

## Relevant workspace skills

- [`.cursor/skills/verify-release-gates/SKILL.md`](../../../.cursor/skills/verify-release-gates/SKILL.md)
- [`.cursor/skills/implement-supabase-security/SKILL.md`](../../../.cursor/skills/implement-supabase-security/SKILL.md)

## Scope lock

**In scope:** Isolated synthetic-data managed staging with production topology, protected migrations, real CDN/WAF/egress/streaming, rotations, audit anchors, alarms, restore, rebuild, and rollback proof.

**Out of scope:** Production corpus, production user access, final DNS cutover, and irreversible production promotion.

The scope lock controls implementation sequencing; it does not weaken any security, authorization, durability, budget, grounding, bounded-work, or documentation invariant in the global contract.

## Ordered work packets

Complete these in order. A checked box requires committed implementation evidence in the phase exit record, not only code presence.

1. [x] [Provision isolated managed Supabase, SES sandbox, CloudFront/WAF, EC2 blue/green services plus digest-pinned private ParadeDB, private Valkey/proxy networks, and Vercel staging from reviewed IaC.](./10-phase-managed-staging/packets/01-provision-isolated-managed-staging.md)
2. [ ] [Implement GitHub OIDC, protected immutable expand/contract migrations, short-lived credential retrieval, environment separation, and secrets custody.](./10-phase-managed-staging/packets/02-implement-protected-migrations-and-secrets.md)
3. [ ] [Prove direct-origin rejection, provider/crawl/parser egress boundaries, private ports, WAF controls, and 90-second streaming timeout configuration.](./10-phase-managed-staging/packets/03-prove-origin-egress-and-timeouts.md)
4. [ ] [Exercise asymmetric JWKS rollover, dual origin-secret rotation, real 50-second CDN SSE heartbeat/disconnect/resume, ParadeDB outage/version mismatch/rebuild, and Valkey degraded modes.](./10-phase-managed-staging/packets/04-exercise-rotations-streaming-and-degradation.md)
5. [ ] [Exercise staging KMS/S3 Object Lock audit anchors, OpenAI/AWS/Supabase billing and operational alarm routing, SES/OAuth/Storage, managed pooling, load, and database pressure.](./10-phase-managed-staging/packets/05-exercise-anchors-alerts-and-managed-load.md)
6. [ ] [Perform and record database-plus-Storage restore/reconciliation followed by clean BM25 projection rebuild, instance rebuild, old-slot/new-schema and frontend/API deploy-skew behavior, failed deployment, forward-fix migration boundary, and application rollback.](./10-phase-managed-staging/packets/06-prove-restore-rebuild-skew-and-rollback.md)
7. [ ] [Run the complete release suite and an independent external security assessment with synthetic/redacted data and no long-lived CI or runtime bootstrap credential.](./10-phase-managed-staging/packets/07-run-release-suite-and-external-assessment.md)

## Phase sequence requirement

<!-- markdownlint-disable-next-line MD029 -->
10. Managed staging: provision isolated managed Supabase/SES sandbox, private EC2 ParadeDB, CloudFront/WAF, EC2 and Vercel with production topology; prove OIDC/protected migrations, BM25 private access/rebuild/fallback, JWKS and origin-secret rotation, egress isolation, real-CDN slow streaming, alerts, restore, and rollback using synthetic data.

## Stop conditions

Stop this phase and report the blocker instead of improvising when:

- a prerequisite phase or required sign-off is incomplete;
- the actual repository contradicts the plan and the difference changes security, data, cost, or acceptance semantics;
- a required dependency contract cannot be verified from its pinned version and primary documentation;
- an authorization, idempotency, deadline, budget, provenance, or fallback test cannot exercise the real boundary;
- a required integration is unavailable and only a fake or skipped test would pass;
- any launch-blocking check fails after bounded repair attempts.

## Required exit record

Create or update `docs/development/phase-10-managed-staging-evidence.md` with:

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

The detailed Phase 10 requirements are redistributed into these normative single-source contracts:

- [Phase 10 shared contracts](./10-phase-managed-staging/00-shared-contracts.md)
- [Managed release gates](./shared/release/02-managed-gates.md)
- [Managed staging topology](./shared/release/03-staging-topology.md)
- [Release sizing envelope](./shared/release/05-sizing-envelope.md)

## Phase deliver, review, and done gate

<!-- markdownlint-disable-next-line MD036 -->
**Phase 10 — Managed staging**

- Deliver: isolated managed Supabase/SES sandbox, asymmetric signing keys, CloudFront/WAF with asserted 90-second origin timeouts, EC2 blue/green slots plus private digest-pinned ParadeDB, split Valkey/proxy networks, Vercel preview/staging, OIDC/protected expand-contract migration path, Secrets Manager credentials, synthetic corpus, staging KMS/S3 Object Lock audit anchors/export, API/frontend skew evidence, BM25 projection/rebuild/fallback evidence, OpenAI/AWS/Supabase alert routing, origin/JWKS rotation, database-plus-Storage restore/reconciliation followed by BM25 rebuild, rollback evidence, and an external security assessment report.
- Review: managed pooling/Auth key rollover/email/Storage/CDN behavior, ParadeDB private roles/network/digest/resources/index/rebuild/degradation, latency/connection budgets, WAF/origin/egress restrictions, slow SSE and version skew, Valkey outage, migration compatibility/approval/custody, audit-chain/KMS/S3 anchor verification, operational/billing alarms, database/Storage reconciliation, external-assessment remediation, and instance rebuild.
- Done when: the complete release suite passes against isolated production-equivalent topology using only synthetic/redacted data; managed Supabase plan/features, session/transaction pooling, OAuth/email/Storage, asymmetric signing keys, JWKS cache/unknown-`kid`, and standby→active→retired rollover are proven without HS256 fallback or auth outage; pinned ParadeDB starts with no public/egress path, separate reader/writer credentials and hard resources, serves only typed bounded BM25 queries, batch-rechecks candidates in Supabase, rejects stale ACL/deletion evidence, and visibly degrades to dense+term during kill/version mismatch; GitHub OIDC assumes only the environment-scoped role and a protected approved immutable expand migration runs through the named SSM/Secrets Manager path with no long-lived CI/database/bootstrap credential or runtime extension-create access; the old API slot remains healthy against the expanded schema and destructive contract work is deferred; independent Vercel/API deployment orders satisfy the version handshake and additive SSE/OpenAPI policy; CloudFront/WAF/Caddy assert the linked 90-second timeout contract, direct-origin requests fail, private ports and unapproved provider/crawl/parser/ParadeDB egress are unreachable, and the real 50-second SSE heartbeat/disconnect/resume test passes; split Valkey outage/recovery and blue/green drain/rollback pass; dual origin-secret rotation and rollback pass; audit-chain mutation/fork/missing-anchor tests pass against staging KMS/S3 Object Lock; synthetic BM25 plus operational and OpenAI/AWS/Supabase billing alarms reach named routes; managed database plus every Storage-bucket restore/reconciliation, clean derived BM25 rebuild/parity, instance rebuild, failed deployment behavior, and application rollback are proven; and the independent assessment has zero open Critical/High findings with accepted residual risk documented before Phase 11.
