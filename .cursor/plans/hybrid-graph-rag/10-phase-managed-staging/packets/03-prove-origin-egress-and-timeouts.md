---
phase: 10
packet: 3
status: pending
title: "Prove direct-origin rejection, provider/crawl/parser egress boundaries, private ports, WAF controls, and 90-second streaming timeout configuration."
requirement_ids: [P10-03]
---

# Packet 3 — Prove direct-origin rejection, provider/crawl/parser egress boundaries, private ports, WAF controls, and 90-second streaming timeout configuration.

Required contracts: [phase shared](../00-shared-contracts.md), [managed gates](../../shared/release/02-managed-gates.md), and [staging topology](../../shared/release/03-staging-topology.md).

## Preconditions

- P10-01/02 pass; reviewed CDN/WAF/Caddy/network/egress IaC, 90-second contract, allowlists, and monitored denial fixtures are deployed.

## Allowed outputs

- Ingress/WAF/origin/timeout/port/egress IaC/runtime assertions, denial logs, narrow reviewed fixes, and evidence.

## Forbidden outputs

- Direct origin/public private ports/SSH/unrestricted egress; parser/OCR/ParadeDB internet/metadata; crawl private-IP bypass; sub-90-second/buffered SSE; unapproved exception.

## Ordered actions

1. Assert CloudFront/WAF/Caddy/origin-header/security-group policy and direct-origin denial.
2. Assert WAF/Caddy size/rate/bot/connection/header/body/slow-client controls and no SSE buffering.
3. Assert CloudFront/Caddy read/keep-alive ≥90 seconds in drift tests.
4. Scan public/cross-network/private service and metadata reachability.
5. Exercise provider allowlist and crawl DNS/private/link-local/metadata/redirect/peer-IP policy.
6. Verify denial/proxy logs and accepted-risk ADR if unavoidable.

## Acceptance checks

- **P10-03-A:** Valid CDN succeeds; direct/missing/wrong-secret origin fails. Evidence: request matrix. Failure: blocker.
- **P10-03-B:** Private/metadata/management ports unreachable. Evidence: scan. Failure: stop.
- **P10-03-C:** Provider/crawl/parser/ParadeDB egress boundaries hold. Evidence: matrix/logs. Failure: stop/approved ADR only.
- **P10-03-D:** WAF/Caddy controls and ≥90-second assertions pass. Evidence: IaC/runtime/drift. Failure: block streaming.
- **P10-03-E:** Denial telemetry reaches monitoring. Evidence: synthetic alert. Failure: repair.

## Negative tests

- Direct IP/hostname secrets, port scans, arbitrary provider/public destination, private/rebind/redirect crawl targets, reduced timeout/buffering, WAF/Caddy limit excess.

## Stop routes

- Stop on origin, port, egress, metadata, crawl, logging, timeout, or unapproved-exception failure; rerun topology packets after material change.

## Required evidence

Append P10-03 to `docs/development/phase-10-managed-staging-evidence.md`: topology/IaC identity, origin/WAF/Caddy/timeout assertions, scans, egress matrix/logs, alert, ADR, negatives, failures/repairs.
