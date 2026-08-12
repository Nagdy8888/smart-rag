---
title: ADR — Private service TLS (ParadeDB / Valkey)
adr_id: ADR-private-service-tls
status: accepted
owner: engineering-lead
last-reviewed: 2026-08-12
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

## Consequences

- Local Compose is simpler and still private-by-default.
- Packet 3 must not publish ParadeDB/Valkey ports.
- Phase 10 staging topology cannot inherit TLS omission silently.
