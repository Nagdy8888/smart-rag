---
title: ADR — Private service TLS (ParadeDB / Valkey)
adr_id: ADR-private-service-tls
status: accepted
owner: engineering-lead
last-reviewed: 2026-08-18
approver: "user (Cursor chat; continuing Phase 1–5 mandate)"
approval_date: "2026-08-12"
---

# ADR: Private service TLS for ParadeDB and Valkey

## Status

`accepted` for **local same-host Docker** with TLS omitted. Staging/production must revisit.

## Threat model (local)

- Attacker on the developer workstation or compromised container on the same Docker user-defined network.
- Not in scope for local: remote internet attackers reaching ParadeDB/Valkey (no host ports published).

## Decision (local development)

**Omit TLS** between backend/worker and ParadeDB/Valkey on the private Compose network when all of the following compensating controls hold:

1. No public/host ports for ParadeDB, Valkey limits, Valkey cache, or crawl proxy.
2. Distinct strong credentials per Valkey instance; ParadeDB roles separated (bootstrap/writer/reader intent).
3. Services attached only to an internal Docker network.
4. Credential rotation owner: engineering-lead; local secrets only in ignored `.env`.
5. Application never treats Valkey as durable authority.

## Staging / production revisit trigger

Re-open this ADR and require TLS (or equivalent private-link encryption) before managed staging when any of:

- Services span hosts or leave a single trusted private network;
- Compliance requires encryption-in-transit for datastore/cache;
- A host port or shared network path becomes unavoidable.

## Phase 10 Packet 1 record (2026-08-18)

Staging IaC under `infra/ec2/` keeps ParadeDB and both Valkey instances on a
**single-host private Docker network** (`private`, `internal: true`) with **no
host ports**, distinct credentials, and hard `mem_limit` values. Those are the
same compensating controls as local Compose. **TLS is still omitted** on that
private network pending Packet 3 egress proof. This packet does not silently
claim TLS is enabled. Revisit again if staging spans hosts, publishes a host
port, or Packet 3 cannot prove the private boundary.

## Phase 10 Packet 3 record (2026-08-18)

Packet 3 asserts deny-by-default provider egress, parser `network_mode: none`,
ParadeDB on internal `private` only, and unpublished private ports in
committed Compose/Caddy. **TLS is still omitted** on that single-host private
Docker network. No new accepted-risk ADR is filed. Live port/metadata scan
remains Blocked, so this record is IaC proof only.

## Consequences

- Local Compose is simpler and still private-by-default.
- Packet 3 must not publish ParadeDB/Valkey ports.
- Phase 10 staging topology cannot inherit TLS omission silently.
