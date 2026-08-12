---
name: hybrid-graph-rag-phase-11-production
phase: 11
status: pending
depends_on: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
split_source: true
source_plan: ../hybrid-graph-rag_ab5281ef.plan.md
global_contract: ./00-global-contracts.md
phase_shared_contract: ./11-phase-production/00-shared-contracts.md
evidence_path: docs/development/phase-11-production-evidence.md
---

# Phase 11: Production

## Mandatory model loading contract

1. Read [`00-global-contracts.md`](./00-global-contracts.md) first, then read this file completely.
2. Read the Phase 11 [`00-shared-contracts.md`](./11-phase-production/00-shared-contracts.md) completely.
3. Select exactly one next unchecked linked packet below and read it completely. Do not load or implement sibling packets.
4. Read only the additional shared/release contracts explicitly linked by that packet.
5. Treat the wrapper, phase shared contract, selected packet, and its linked shared/release contracts as the only implementation scope for this model run. Promote exact Phase 10-qualified artifacts and apply only documented production-safe deltas.
6. Inspect the current repository, schemas, migrations, tests, IaC, qualified artifact records, and pinned dependency/provider versions named by the selected packet before editing or promotion. This plan describes targets, not proof that an artifact, file, API, or provider behavior exists.
7. Load `.cursor/skills/implement-plan-phase/SKILL.md` and the relevant workspace skills listed below before implementation.
8. Quote the selected packet title, requirement ID, and concrete acceptance checks before editing. Implement the smallest complete packet.
9. Verify unstable external APIs and provider contracts against current primary documentation and add contract tests or policy assertions. Never guess a library method, schema, environment variable, command, artifact identity, or provider behavior.
10. Add positive, failure, authorization, idempotency, bounded-resource, fallback, topology-drift, and rollback tests whenever applicable.
11. Run repository-defined format, lint, strict type, test, build, migration, IaC, integration, and production-safe verification commands relevant to changed files. Inspect rather than invent those commands.
12. Update documentation and `docs/development/phase-11-production-evidence.md` in the same change. Do not leave placeholders, fake success paths, swallowed errors, disabled security, or `TODO` core behavior.
13. Record proof in the exit record. If security, data semantics, cost, topology, artifact identity, or acceptance criteria must change, stop, return to staging qualification as required, and obtain approval through an ADR or plan update.

## Prerequisites

[Phase 1: Foundation](./01-phase-foundation.md), [Phase 2: Identity and data](./02-phase-identity-data.md), [Phase 3: Ingestion](./03-phase-ingestion.md), [Phase 4: Hybrid RAG](./04-phase-hybrid-rag.md), [Phase 5: GraphRAG](./05-phase-graphrag.md), [Phase 6: Agent intelligence](./06-phase-agent-intelligence.md), [Phase 7: Stitch specification](./07-phase-stitch-specification.md), [Phase 8: Frontend integration](./08-phase-frontend-integration.md), [Phase 9: Local release candidate](./09-phase-local-release-candidate.md), [Phase 10: Managed staging](./10-phase-managed-staging.md)

## Relevant workspace skills

- [`.cursor/skills/verify-release-gates/SKILL.md`](../../../.cursor/skills/verify-release-gates/SKILL.md)

## Scope lock

**In scope:** Approved production promotion, final configuration and security verification, smoke/rollback tests, operational documentation, ownership, and handoff.

**Out of scope:** Unapproved architecture changes, expanded scale claims, new retrieval methods, or relaxed acceptance/security/cost criteria.

The scope lock controls implementation sequencing; it does not weaken any security, authorization, durability, budget, grounding, bounded-work, or documentation invariant in the global contract.

## Ordered work packets

Complete these in order. A checked box requires committed implementation evidence in the phase exit record, not only code presence.

1. [ ] [Reconfirm the full provider/subprocessor governance packet, signed targets, capacity/cost limits, expand/contract migration artifact, API/client compatibility, external-assessment recency, change window, owners, and rollback go/no-go.](./11-phase-production/packets/01-reconfirm-production-go-no-go.md)
2. [ ] [Provision/configure production Supabase, private digest-pinned ParadeDB, SES, CloudFront/WAF, EC2/SSM/ECR, Vercel, DNS/TLS, secrets, backups, and monitoring from qualified artifacts.](./11-phase-production/packets/02-configure-production-from-qualified-artifacts.md)
3. [ ] [Run protected migrations and health-gated immutable deployment; verify CORS, redirects, origin restrictions, egress, Auth, budgets, rates, BM25 projection/recheck/fallback, and private services.](./11-phase-production/packets/03-deploy-and-verify-production-controls.md)
4. [ ] [Run production-safe smoke, security, redaction, API handshake, BM25 projection/query/degradation, audit-anchor/export, OpenAI/AWS/Supabase alert delivery, database/Storage consistency, backup-health, and rollback tests before user access.](./11-phase-production/packets/04-run-production-safe-release-tests.md)
5. [ ] [Publish the complete documentation index, ADRs, API/config/provider records, retention policy, and all required operational runbooks.](./11-phase-production/packets/05-publish-documentation-and-runbooks.md)
6. [ ] [Hand off named ownership, escalation, RTO/RPO/growth triggers, graph pin/exit procedure, quarterly qualification work, and tested Hybrid-only disable path.](./11-phase-production/packets/06-hand-off-operational-ownership.md)

## Phase sequence requirement

<!-- markdownlint-disable-next-line MD029 -->
11. Production: promote immutable images/configuration including private BM25, provision production data services and email, verify DNS/TLS/CORS/redirects/alarms/budgets, smoke test, test rollback, and hand off.

## Stop conditions

Stop this phase and report the blocker instead of improvising when:

- a prerequisite phase or required sign-off is incomplete;
- the actual repository contradicts the plan and the difference changes security, data, cost, or acceptance semantics;
- a required dependency contract cannot be verified from its pinned version and primary documentation;
- an authorization, idempotency, deadline, budget, provenance, or fallback test cannot exercise the real boundary;
- a required integration is unavailable and only a fake or skipped test would pass;
- any launch-blocking check fails after bounded repair attempts.

## Required exit record

Create or update `docs/development/phase-11-production-evidence.md` with:

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

The detailed Phase 11 requirements are redistributed into these normative single-source contracts:

- [Phase 11 shared contracts](./11-phase-production/00-shared-contracts.md)
- [Production promotion delta](./shared/release/04-production-promotion-delta.md)
- [Release sizing envelope](./shared/release/05-sizing-envelope.md)
- [Documentation and operational handoff](./shared/release/06-documentation-operational-handoff.md)

## Phase deliver, review, and done gate

<!-- markdownlint-disable-next-line MD036 -->
**Phase 11 — Production**

- Deliver: production managed Supabase/SES, private digest-pinned ParadeDB, CloudFront/WAF, EC2/SSM/ECR, Vercel, DNS/TLS, least-privilege short-lived expand/contract deployment path/secrets, API/client compatibility, closed external-assessment gate, audit chain/anchors/export, BM25 plus operational and OpenAI/AWS/Supabase billing routes, database/Storage backup consistency with derived-index rebuild, smoke tests, rollback, and handoff.
- Review: access, re-confirmed OpenAI/LangSmith/Supabase/Vercel governance settings, BM25 pin/license/private access/projection/lag/rebuild/degradation, target/cost/graph-ETA limits, pen-test recency/residual risks, migration/API compatibility, alarms/owners, RTO/RPO/growth triggers, BM25 and graph pin/exit runbooks, database/Storage reconciliation, retention/deletion, origin/key rotation, and rollback before user access.
- Done when: production promotion uses the exact Phase 10-qualified immutable images/configuration including ParadeDB digest/schema/index versions and protected short-lived expand-compatible migration/deployment path; the external assessment is no older than 90 days or has a completed delta review, with zero open Critical/High findings; DNS/TLS/CORS/redirects, Supabase Auth/Storage/RLS, private typed BM25 access plus mandatory Supabase candidate recheck and dense+term degradation, API/minimum-client handshake, WAF/origin/egress restrictions, private ports, budgets, rate/degraded modes, email, database/Storage backup consistency, and retention configuration pass production-safe smoke/security/redaction checks; observability, on-call routes, audit-chain anchors/export, BM25 health/lag/rebuild/fallback, OpenAI/AWS/Supabase billing, queue/graph ETA, database, Storage consistency, and backup alarms receive and route real signals; the draining old slot works against the expanded schema and health-gated application rollback/forward-fix migration boundaries are tested; `docs/README.md` links the final API/version/config/provider-governance, BM25 architecture/rebuild, ADR, deployment, security, evaluation, retention/deletion, and runbook set; the owner has published the retention/legal-hold policy and named owners for every alert, RTO/RPO, availability, workload-isolation, and growth trigger; the handoff records ParadeDB/`pg_search` and LightRAG pins, BM25 index/normalization version and rebuild/lag limits, graph workspace/current-only temporal limitation/survival/ETA/cost limits, and reserves one to two engineer-days per quarter for dependency/schema qualification and deletion/rebuild/per-language/source-map review; and the documented BM25-outage dense+term path plus graph disable-to-Hybrid-only procedure are executed successfully before user access.
