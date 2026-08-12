---
name: hybrid-graph-rag-production-promotion-delta
status: active
applies_to: phase-11
source_phase: ../../11-phase-production.md
---

# Production promotion delta

## Exact-artifact ownership

Phase 10 staging evidence for rotations, restore, rebuild, streaming, egress, deployment skew, alarms, external assessment, and rollback is a mandatory prerequisite and is not recreated with production data. Phase 11 promotes the exact qualified artifacts and configuration through protected procedures, applies only production-safe environment deltas, performs production-safe verification, and stops on topology or contract drift instead of redesigning infrastructure during release.

The exact qualified set includes application and infrastructure images, the ParadeDB digest and `pg_search`/BM25 schema/index/normalization versions, migration artifacts and hashes, configuration profile and schema, Supabase plan/features and connection modes, regions, CloudFront/WAF/Caddy timeout and origin controls, Vercel/API compatibility contract, deployment documents, and rollback inputs.

This contract is read only with the [Phase 11 shared contract](../../11-phase-production/00-shared-contracts.md) and a packet that links it. The [staging topology](./03-staging-topology.md), [managed gates](./02-managed-gates.md), and [global contracts](../../00-global-contracts.md) remain mandatory.

## Allowed production-safe deltas

Only reviewed environment-specific values may differ from the Phase 10-qualified staging set:

- production Supabase, SES, AWS, Vercel, DNS, TLS, CloudFront, WAF, ECR, SSM, and Secrets Manager resource identifiers;
- production regions only when they exactly match the regions qualified in staging;
- production domains, redirect allowlists, CORS entries, CSP endpoints, and publishable Supabase values;
- production secrets, certificates, signing keys, origin-header values, SMTP credentials, and least-privilege role bindings;
- signed production capacity, budget, retention, backup/PITR, alarm thresholds, and owner routes that remain within the qualified sizing and contract envelope; and
- the approved expand-compatible production migration artifact and recorded operator/change window.

No production-safe delta may change an image digest, dependency or engine pin, database/BM25 schema or index semantics, retrieval behavior, security boundary, provider feature assumption, timeout contract, release acceptance criterion, or supported envelope without returning to Phase 10 qualification and any required ADR/client approval.

## Production infrastructure contract

Infrastructure remains under `infra/ec2/` with deployment documentation under `docs/deployment/`.

- EC2 is rebuildable with encrypted EBS, IMDSv2 enforced, a least-privilege instance role, Systems Manager instead of public SSH, automated bootstrap or user data, and security groups accepting origin traffic only from CloudFront origin-facing ranges plus controlled operations access.
- CloudFront and AWS WAF protect the API.
- Caddy validates the secret origin header, applies slow-client, connection, header, body, and time limits, disables SSE buffering, and proxies only FastAPI.
- IaC preserves and drift-checks the Phase 6 90-second FastAPI/SSE timeout contract.
- ParadeDB and both Valkey services remain Docker-network-only with separate named reader, writer, and ACL users as applicable, explicit memory policies, and hard container memory limits.
- ParadeDB and LightRAG expose no public port.

## Production egress

- Host firewall, `DOCKER-USER`, or equivalent rules deny direct container egress except through named paths.
- API and agents use the staging-qualified allow-listed provider-egress path.
- Only the crawl proxy may reach arbitrary public HTTP(S), and it cannot reach private, link-local, or metadata ranges.
- ParadeDB, parser, and OCR networks have no route to the internet, provider proxy, Valkey, or host metadata.
- Egress-deny logs and proxy decisions remain monitored.
- Any single-host exception requires the Phase 10 accepted-risk ADR and compensating monitoring; absent that approval, production is blocked.

## Protected migrations and blue/green deployment

- Production migration artifacts follow the Phase 10-qualified expand/contract policy.
- The draining old API image remains compatible with the expanded schema.
- Destructive contraction waits for a later approved release.
- Production rollback uses the qualified application rollback and forward-fix migration boundary.
- API slots deploy blue/green: start and health-check the inactive slot, drain old streams, switch Caddy upstream, and then stop the old slot.
- A failed health check leaves the old slot active.
- Accepted same-host failure and deployment limitations remain documented against the four-hour RTO.
- Images were built and scanned in CI, pushed to ECR, and are deployed through SSM with immutable tags.
- GitHub OIDC may invoke only environment-scoped SSM deployment or migration documents.
- The EC2 role retrieves runtime or migration secrets just in time.
- Production migration requires protected approval.

## Secrets and frontend boundary

- Secrets live in AWS Secrets Manager or SSM Parameter Store.
- Secrets never appear in committed `.env` files, long-lived GitHub secrets, command output, or frontend variables.
- Vercel receives only the API URL, Supabase URL, and publishable key.
- Vercel production and preview environments remain separated.
- Supabase redirect allowlists, backend CORS entries, CSP, and no secret or service-role exposure are verified before access opens.

## Backup, reconciliation, and derived rebuild

- Supabase backup/PITR and Storage recovery levels are documented for the selected production plan.
- Production backup-health checks cover application schemas, canonical chunks, BM25 outbox/index-version state, source mappings, private LightRAG tables, every durable Storage bucket, and database/Storage reconciliation for missing, mismatched, or orphaned objects.
- ParadeDB is rebuilt only from reconciled authorized current Supabase data.
- The instance-rebuild runbook recreates EC2 services from IaC, images, and secrets; starts empty ParadeDB; rebuilds its projection from Supabase; and verifies API, worker, ParadeDB, and Valkey health without treating host data as canonical.
- Encrypted EBS stores the working BM25 index.
- Snapshots may shorten recovery but are never the authority or sole rebuild path.
- The selected Supabase backup tier must meet the approved 24-hour RPO or the target is revised before launch.

## Production monitoring and provider configuration

CloudWatch host and container alarms preserve coverage for disk, memory, CPU, restarts, API readiness, event-loop lag, heartbeat jitter, rate-limit degradation, ParadeDB health/index size/RAM/query latency/projection lag/rebuild/fallback, Valkey memory/rejections, egress denials, queue backlog and graph ETA, LightRAG indexing/query health, error rate, latency, OpenAI spend, aggregate AWS budget/data-transfer/EBS spend, audit-anchor gaps, and SES bounces.

Supabase monitoring and billing alerts preserve coverage for database CPU, IO, cache, replica lag, connections, compute/storage/egress thresholds, slow queries, and backup health. `docs/runbooks/alert-routing.md` assigns each operational and billing alarm an owner, severity, notification route, acknowledgement target, escalation, and linked response. Phase 11 verifies real production routes.

Supabase production setup includes RLS/advisor review, custom domain and redirects as needed, Storage limits, pooled/direct connection choices, and SES SMTP credentials.

## Origin-secret lifecycle

The staging-qualified `docs/runbooks/origin-secret-rotation.md` remains normative:

- rotate the random CloudFront origin-header name and value at least every 90 days and after exposure;
- generate and store the pending value;
- make Caddy accept old and new;
- add and switch the CloudFront custom header;
- wait for distribution deployment;
- verify CDN success and direct-origin rejection;
- remove the old CloudFront header;
- remove old Caddy acceptance after a maximum 15-minute overlap;
- keep at least one valid value during abort or rollback; and
- audit every rotation.

## Production-safe verification and failure routes

Evidence belongs in `docs/development/phase-11-production-evidence.md`.

- Verify exact hashes and digests before migration or deployment. Any mismatch stops promotion and returns the artifact to Phase 10.
- Run only bounded, non-destructive, production-safe smoke, security, redaction, compatibility, private-network, BM25 projection/recheck/fallback, backup-health, audit-anchor, and alert-route checks.
- Do not seed the staging synthetic suite into production, run destructive restore or full failover drills against production data, repeat penetration testing against unapproved live scope, or recreate staging proof with private corpus.
- A changed security, data, cost, topology, sizing, or acceptance contract requires the relevant ADR or plan approval and staging requalification.
- A failed protected migration, inactive-slot health check, old-slot/new-schema check, rollback boundary, direct-origin or egress check, stale-evidence recheck, alarm route, backup consistency check, or redaction check blocks user access.
