---
phase: 10
packet: 1
status: complete
title: "Provision isolated managed Supabase, SES sandbox, CloudFront/WAF, EC2 blue/green services plus digest-pinned private ParadeDB, private Valkey/proxy networks, and Vercel staging from reviewed IaC."
requirement_ids: [P10-01]
---

# Packet 1 — Provision isolated managed Supabase, SES sandbox, CloudFront/WAF, EC2 blue/green services plus digest-pinned private ParadeDB, private Valkey/proxy networks, and Vercel staging from reviewed IaC.

Required contracts: [phase shared](../00-shared-contracts.md), [managed gates](../../shared/release/02-managed-gates.md), and [staging topology](../../shared/release/03-staging-topology.md).

## Preconditions

- Accepted exact Phase 9 artifacts/limits/handoff; reviewed IaC, intended production plan/features/regions/topology; verified provider docs; isolated staging accounts.

## Allowed outputs

- Production-equivalent isolated staging resources, synthetic/redacted seed, topology inventory, and Phase 10 evidence.

## Forbidden outputs

- Production data/users/DNS/email/promotion; public private services/SSH; IMDSv1; mutable images; unencrypted state; long-lived credentials; unapproved substitutes.

## Ordered actions

1. Verify Phase 9 manifest and intended plan/features/regions.
2. Provision managed Supabase/Auth/Storage/pooling/backup and SES sandbox.
3. Provision CloudFront/WAF, encrypted IMDSv2 EC2/SSM/ECR/security groups.
4. Start blue/green API, worker, exact private ParadeDB, split Valkey, restricted proxies/Caddy.
5. Configure Vercel with public values only; verify limits, health, ports, credentials, no production connectivity.
6. Seed only synthetic/redacted corpus and freeze topology.

## Acceptance checks

- **P10-01-A:** Intended managed plan/features/regions and exact Phase 9 artifacts match. Evidence: inventory. Failure: stop drift.
- **P10-01-B:** EC2 is rebuildable/encrypted/IMDSv2/SSM-only with controlled ingress. Evidence: IaC/runtime assertions. Failure: blocker.
- **P10-01-C:** ParadeDB/Valkey/LightRAG/private services have hard limits/credentials/no public path. Evidence: network scan. Failure: stop.
- **P10-01-D:** Vercel/SES separation exposes no secret. Evidence: environment scan. Failure: rotate/remove.
- **P10-01-E:** Only synthetic/redacted data exists. Evidence: manifest. Failure: purge/incident.

## Negative tests

- Attempt SSH/IMDSv1/direct origin/private ports/metadata, mutable digest, production connection, secret exposure, and non-redacted seed.

## Stop routes

- Stop on artifact/provider/region/topology/private-boundary/credential/encryption/data-isolation failure; approve/requalify any material change.

## Required evidence

Append P10-01 to `docs/development/phase-10-managed-staging-evidence.md`: Phase 9 identities, IaC hash, plan/features/regions, digests, topology/ports, EC2 assertions, Vercel/SES separation, synthetic manifest, health, negatives, repairs, frozen identity.
