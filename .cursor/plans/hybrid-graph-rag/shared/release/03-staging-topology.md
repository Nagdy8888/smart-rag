---
name: hybrid-graph-rag-staging-topology
status: active
applies_to: phase-10
source_phase: ../../10-phase-managed-staging.md
---

# Managed staging topology

## Staging purpose and data boundary

Do not provision or depend on AWS during feature development. Only after the local release candidate passes, deploy a short-lived isolated staging environment using the same managed Supabase plan and features, Supavisor endpoints, SES sandbox and custom SMTP path, CloudFront/WAF, EC2 images, Vercel configuration, and regions intended for production.

Seed only synthetic or redacted fixtures. Run the release suite, pooling/load tests, OAuth/email/Storage/CDN latency, backup/restore, BM25 projection rebuild and fallback, and rollback in staging before opening production. Production corpus and production user access are forbidden.

This contract is read only with the [Phase 10 shared contract](../../10-phase-managed-staging/00-shared-contracts.md) and a packet that links it. The [managed gates](./02-managed-gates.md) define the proof, and the [global contracts](../../00-global-contracts.md) remain authoritative.

## Infrastructure location and immutable promotion inputs

Create infrastructure under `infra/ec2/` and deployment documentation under `docs/deployment/`.

- Images build in CI, are scanned, are pushed to ECR, and deploy through SSM with immutable tags and a rollback procedure.
- GitHub OIDC may invoke only environment-scoped SSM deployment and migration documents.
- The EC2 role retrieves runtime or migration secrets just in time.
- Production migration requires the protected approval defined by the managed gate.
- Secrets live in AWS Secrets Manager or SSM Parameter Store, never in committed `.env` files, long-lived GitHub secrets, command output, or frontend variables.
- Vercel receives only the API URL, Supabase URL, and publishable key.

## EC2, ingress, and private services

- EC2 is rebuildable from reviewed IaC, encrypted EBS, immutable images, and secrets.
- IMDSv2 is enforced.
- The instance uses a least-privilege role and Systems Manager instead of public SSH.
- Automated bootstrap or user data recreates services.
- Security groups accept origin traffic only from CloudFront origin-facing ranges plus controlled operations access.
- CloudFront and AWS WAF protect the API.
- Caddy validates the secret origin header, applies slow-client, connection, header, body, and time limits, disables SSE buffering, and proxies only FastAPI.
- IaC sets CloudFront origin read/keep-alive and Caddy timeouts to the Phase 6 90-second FastAPI/SSE contract and asserts them in drift checks.
- ParadeDB and both Valkey services are Docker-network-only with separate named reader, writer, and ACL users as applicable, explicit memory policies, and hard container memory limits.
- ParadeDB and LightRAG expose no public port.

## Egress isolation

- Host firewall, `DOCKER-USER`, or an equivalent enforcement point denies direct container egress except through named paths.
- API and agents use an allow-listed provider-egress path.
- Only the crawl proxy may reach arbitrary public HTTP(S), and it cannot reach private, link-local, or metadata ranges.
- ParadeDB, parser, and OCR networks have no route to the internet, provider proxy, Valkey, or host metadata.
- Egress-deny logs and proxy decisions are monitored.
- Any unavoidable single-host exception requires a Phase 10 accepted-risk ADR before launch; without approved compensating monitoring, production is blocked.

## Blue/green and version-skew behavior

- Deploy API slots blue/green on the host.
- Start and health-check the inactive slot, drain old streams, switch the Caddy upstream, and only then stop the old slot.
- A failed health check leaves the old slot active.
- Accepted same-host failure and deployment limitations are documented against the four-hour RTO.
- Blue/green deploys consume only expand-compatible migrations while the old slot can receive traffic.
- Staging deliberately runs the old image against the expanded schema through the drain window.
- Vercel and API are then deployed in both orders to prove the documented version handshake and additive SSE/OpenAPI compatibility.

## Restore, reconciliation, and instance rebuild

- Supabase backup/PITR and Storage recovery levels are documented for the selected plan.
- Restore drills recover application schemas, canonical chunks, BM25 outbox/index-version state, source mappings, private LightRAG tables, and every durable Storage bucket to a recorded point.
- `docs/runbooks/storage-db-reconciliation.md` detects database references with missing or hash-mismatched objects and object-only orphans, excludes incomplete versions from retrieval and graph, quarantines orphans, emits append-only audit and admin alerts, and defines safe reconciliation and rollback.
- `docs/runbooks/bm25-rebuild.md` recreates the derived projection only from reconciled authorized current Supabase state.
- An instance-rebuild runbook recreates EC2 services from IaC, images, and secrets; starts empty ParadeDB; rebuilds its projection from Supabase; and verifies API, worker, ParadeDB, and Valkey health without treating host data as canonical.
- Encrypted EBS stores the working BM25 index.
- Snapshots may shorten recovery but are never the authority or sole rebuild path.
- The selected Supabase backup tier must meet the approved 24-hour RPO or the target is revised before launch.

## Monitoring, billing, and alert delivery

CloudWatch host and container alarms cover:

- disk, memory, CPU, restarts, and API readiness;
- event-loop lag, heartbeat jitter, and error rate or latency;
- rate-limit degradation and Valkey memory or rejections;
- ParadeDB health, index size, RAM, query latency, projection lag, rebuild, and fallback;
- egress denials;
- queue backlog, graph ETA, and LightRAG indexing/query health;
- OpenAI spend;
- aggregate AWS budget, data-transfer, and EBS spend;
- audit-anchor gaps; and
- SES bounces.

Supabase monitoring and billing alerts cover database CPU, IO, cache, replica lag, connections, compute, storage, egress budget thresholds, slow queries, and backup health.

`docs/runbooks/alert-routing.md` assigns each operational and OpenAI/AWS/Supabase billing alarm an owner, severity, notification route, acknowledgement target, escalation, and linked response. Staging sends synthetic alarms to prove every handoff path.

## Managed Supabase, SES, and Vercel

- Supabase production-equivalent setup includes RLS and advisor review, custom domain and redirects as needed, Storage limits, pooled and direct connection choices, and SES SMTP credentials.
- SES remains sandboxed in staging.
- Vercel has production and preview environment separation, Supabase redirect allowlists, backend CORS entries, CSP, and no secret or service-role exposure.

## Origin-secret dual rotation

Create `docs/runbooks/origin-secret-rotation.md`.

- Rotate the random CloudFront origin header name and value at least every 90 days and after exposure.
- Generate and store the pending value.
- Make Caddy accept old and new.
- Add and switch the CloudFront custom header.
- Wait for distribution deployment.
- Verify CDN success and direct-origin rejection.
- Remove the old CloudFront header.
- Remove old Caddy acceptance after a maximum 15-minute overlap.
- Abort or rollback keeps at least one valid value.
- Every rotation is audited and tested in staging.

## Required proof and failure routes

Evidence belongs in `docs/development/phase-10-managed-staging-evidence.md` and must identify immutable image/configuration/migration hashes, environment and region, managed plan and endpoints, test commands, machine-readable results, restore points, alarm deliveries, and rollback artifacts without secrets or raw private source text.

- Direct-origin reachability, a public private-service port, unrestricted egress, missing credential separation, or a failed 50-second stream under asserted 90-second timeouts blocks staging.
- Topology drift from intended production regions, managed features, images, digests, network boundaries, or deployment order blocks Phase 11 until corrected and requalified.
- A failed restore, clean BM25 rebuild/parity check, instance rebuild, rotation, alarm route, blue/green drain, version-skew test, or rollback is launch-blocking.
- Synthetic/redacted staging data is mandatory. Introducing production corpus or production users stops the phase and invokes security and incident handling.
