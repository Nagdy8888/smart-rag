---
title: ADR — ParadeDB edition and availability
adr_id: ADR-paradedb-edition-availability
status: accepted
owner: engineering-lead
last-reviewed: 2026-08-12
approver: "user (Cursor chat; continuing Phase 1–5 mandate)"
approval_date: "2026-08-12"
---

# ADR: ParadeDB edition and availability

## Status

`accepted` for local Phase 1 development topology.

## Context

Managed Supabase does not expose `pg_search`. V1 requires a private ParadeDB/`pg_search` service for rebuildable BM25 candidates only. Canonical text, ACL, and final evidence remain in Supabase.

Alternatives considered:

1. **ParadeDB Community image (`paradedb/paradedb`)** — public Docker Hub image with `pg_search`, suitable for local/private EC2.
2. **ParadeDB Enterprise** — commercial features/support; not required for v1 BM25 projection.
3. **In-process BM25 (rank_bm25 / Lucene)** — rejected; plan requires ParadeDB/`pg_search` qualification.
4. **Managed Supabase only** — impossible; extension unavailable.

## Decision

Use the **ParadeDB Community** runnable image `paradedb/paradedb` pinned by **immutable digest**, PostgreSQL 17 line (`pg17` tag family), for local Docker and later private EC2. No public host port. Least-privilege bootstrap/writer/reader roles. Application BM25 projection DDL remains Phase 2/4-owned.

Pinned local reference (resolved 2026-08-12 from Docker Hub manifest API):

- Image: `paradedb/paradedb:pg17@sha256:dca046b8a0ddd070c368d5254cbb7f596b3b7bc67bc2efa7c0fbe881087883bb`

Health must verify `pg_search` is available (`SELECT 1 FROM pg_extension WHERE extname = 'pg_search'` after init), not TCP alone.

## Consequences

- Licensing/availability: Community image for v1; Enterprise revisit only if Community cannot meet BM25 qualification gates.
- Derived index is destroyable/rebuildable from Supabase.
- Staging/production must re-verify digest and license terms before promotion.
