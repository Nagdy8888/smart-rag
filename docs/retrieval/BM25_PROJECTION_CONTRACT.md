---
title: BM25 projection contract
owner: engineering-lead
status: draft
last-reviewed: 2026-09-09
audience: engineering
---

# BM25 projection contract

Private ParadeDB/`pg_search` holds a **rebuildable** lexical projection keyed by canonical chunk/version IDs. Supabase remains authoritative for text, ACL, current-version, and final evidence. BM25 returns candidate IDs/ranks only; every candidate is batch-rechecked in Supabase before evidence assembly.

## Assumptions (unmeasured)

Full-envelope index size, RAM, p95 top-75 latency, write throughput, outbox lag, and clean rebuild duration are **assumptions** until Phase 4/9 qualification (see [QUALITY_TARGETS.md](../QUALITY_TARGETS.md) QT-BM25-*).

## Topology

See [ADR-paradedb-edition-availability.md](../adr/ADR-paradedb-edition-availability.md) and Compose private service (no host port).

## Outage

ParadeDB failure → Hybrid visibly degrades to dense + exact/trigram term search
(`bm25_unavailable`). See [HYBRID_RETRIEVAL_CONTRACT.md](./HYBRID_RETRIEVAL_CONTRACT.md).

Packet 2 creates `bm25_chunks_search_idx` with `pdb.unicode_words` over
title/heading/alias/body plus filter fields `language`, `acl_scope_id`,
`is_current`, and `visibility_generation`. Queries return `chunk_id` only.

`version_id` is stored on the projection and indexed with a btree
(`bm25_chunks_version_id_idx`) but is **not** a `pg_search` filter column.
On the pinned ParadeDB image, mixing `version_id` with `pdb.score` in the
same `WHERE` raises `XX000` unsupported query shape. Variant BM25 therefore
loads current-version ids with that btree, then scopes the scored scan with
`chunk_id = ANY(...)` on the BM25 key field. Hybrid still rechecks every id
on canonical Supabase.

[docs index](../README.md)
