---
phase: 11
packet: 2
status: pending
title: "Provision/configure production Supabase, private digest-pinned ParadeDB, SES, CloudFront/WAF, EC2/SSM/ECR, Vercel, DNS/TLS, secrets, backups, and monitoring from qualified artifacts."
requirement_ids: [P11-02]
---

# Packet 2 — Provision/configure production Supabase, private digest-pinned ParadeDB, SES, CloudFront/WAF, EC2/SSM/ECR, Vercel, DNS/TLS, secrets, backups, and monitoring from qualified artifacts.

Required contracts: [phase shared](../00-shared-contracts.md), [production delta](../../shared/release/04-production-promotion-delta.md), and [sizing envelope](../../shared/release/05-sizing-envelope.md).

## Preconditions

- P11-01 go; exact qualified IaC/artifacts and approved environment deltas; isolated least-privilege production; DNS/TLS rollback; access closed.

## Allowed outputs

- Production resources/config from exact artifacts; approved environment identifiers/secrets/certs/DNS/backup/budget/alarms; topology/drift evidence.

## Forbidden outputs

- Rebuild/pin/index/topology/scale change; corpus/access; public private services/SSH/IMDSv1/unrestricted egress; long-lived/exposed secrets; unsafe DNS cutover.

## Ordered actions

1. Verify hashes before apply.
2. Configure Supabase/Auth/Storage/backups/pooling/SES and redirects.
3. Configure CloudFront/WAF, encrypted IMDSv2 EC2/SSM/ECR/Caddy/blue-green/worker/proxies/monitoring.
4. Start exact private ParadeDB and split Valkey with credentials/limits.
5. Configure Vercel public values, just-in-time secrets, certificates/origin/DNS, backup/budgets/alarms.
6. Run non-invasive topology/configuration/port/secret/encryption/region/plan/digest/timeout drift checks; keep access closed.

## Acceptance checks

- **P11-02-A:** Exact qualified artifacts/topology with approved deltas only. Evidence: apply/drift manifest. Failure: Phase 10.
- **P11-02-B:** All providers/resources separated and least privilege. Evidence: inventory. Failure: block.
- **P11-02-C:** Private boundaries/encryption/IMDSv2/SSM/egress match staging. Evidence: assertions. Failure: blocker.
- **P11-02-D:** No secret exposure; credentials separate/rotation-ready. Evidence: scans. Failure: revoke/rotate.
- **P11-02-E:** Backup/billing/monitoring/DNS rollback/access hold ready. Evidence: checklist. Failure: no-go.

## Negative tests

- Changed artifact/plan/region/timeout/network; public port/metadata/SSH; secret search; larger topology; early data/access.

## Stop routes

- Stop on drift/delta/private-boundary/egress/secret/encryption/backup/DNS failure; rotate exposure; return material change to Phase 10.

## Required evidence

Append P11-02 to `docs/development/phase-11-production-evidence.md`: hashes/resources/deltas, network/encryption/IMDSv2/SSM, pins/limits, secret scans, provider separation, DNS/TLS rollback, backups/budgets/monitoring, repairs, access hold.
