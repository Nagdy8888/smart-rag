---
title: Phase 2 identity/data evidence
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering, reviewers
---

# Phase 2 — identity and data evidence

Canonical packet evidence. Packet 1 creates this file; later packets append.

## Packet 1 — capability and embedding qualification

### Requirement

Prove local + managed pgvector 0.8+/iterative-scan, pinned ParadeDB/`pg_search` BM25 contracts, byte-identical `arabic_norm_v1`, and live embedding bake-off; freeze disjoint qualification slice; accept embedding ADR.

### Versions recorded

| Component | Value |
| --- | --- |
| Supabase CLI | 2.113.0 (`npx`) |
| Local Supabase Postgres | 15.8 / pgvector **0.8.0** |
| Managed project | `smart-rag` / `qsjivtwtmlmtksufqjik` / `eu-central-1` / Postgres 17.6 / pgvector **0.8.2** |
| ParadeDB | digest `sha256:dca046b8a0ddd070c368d5254cbb7f596b3b7bc67bc2efa7c0fbe881087883bb` / PG 17.10 / `pg_search` 0.25.2 / vector 0.8.4 |
| OpenAI candidates | `text-embedding-3-small`@1536; `text-embedding-3-large`@1536; `text-embedding-3-large`@1024 |

Managed target is the **new** Smart RAG project (not the previous Reel project).

### Artifacts

- Migration: `supabase/migrations/20260812131227_pgvector_gate_and_arabic_norm_v1.sql`
- Core: `packages/core/src/smart_rag_core/text/arabic_normalize.py`
- ParadeDB SQL: `infra/paradedb/sql/arabic_norm_v1.sql`
- Fixtures: `tests/fixtures/arabic_normalization/`, `tests/fixtures/embedding_qualification/`
- Contracts: `tests/contract/test_{arabic_normalization_parity,pgvector_capabilities,paradedb_bm25,embedding_dimensions}.py`
- Bake-off: `scripts/embedding_qualification_bakeoff.py` → `docs/evaluation/embedding_qualification_raw.json`
- Docs: Arabic normalization, BM25 projection `07`, embedding ADR + report

### Commands and results

```text
npx supabase db reset --yes
→ Applied 20260812131227_pgvector_gate_and_arabic_norm_v1.sql (local vector 0.8.0)

Managed MCP apply_migration pgvector_gate_and_arabic_norm_v1
→ normalize('مَدْرَسَة')='مدرسه'; assert_pgvector_capabilities()='0.8.2'; iterative_scan ok

uv run pytest tests/contract/test_arabic_normalization_parity.py \
             tests/contract/test_pgvector_capabilities.py \
             tests/contract/test_paradedb_bm25.py \
             tests/contract/test_embedding_dimensions.py -q
→ passed (managed DB URL test skipped — no direct pooled password in env; MCP SQL proved managed gate)

MOCK_MODEL_MODE=false uv run python scripts/embedding_qualification_bakeoff.py
→ Wrote embedding_qualification_raw.json; winner large@1024 per ADR
```

### Acceptance mapping

| Check | Evidence |
| --- | --- |
| Local pgvector 0.8+ + iterative-scan + selective filter | Local migration gate + `test_pgvector_capabilities` |
| Managed pgvector 0.8+ + iterative-scan | MCP SQL on `qsjivtwtmlmtksufqjik` |
| Arabic byte-identical SQL/core/ParadeDB | `test_arabic_normalization_parity` (0 failures) |
| ParadeDB BM25 contracts | `test_paradedb_bm25` |
| Live three-candidate bake-off | raw JSON + report |
| ADR pins live API ids/dims | ADR accepted large@1024 |
| No bulk ingest / no pg_search on Supabase | Migration scope limited |

### Unverified / follow-ups

- Managed selective-filter HNSW via direct `psycopg` DSN (password not stored in repo `.env`); MCP proved GUC + normalize.
- Full-envelope RAM: ADR requires ≥16 GB usable DB RAM or `halfvec` before bulk embed.
- Packet checkbox remains unchecked until user **accept**.

### Next packet

Packet 2 — expand/contract-safe authoritative schema (after Packet 1 accept).
