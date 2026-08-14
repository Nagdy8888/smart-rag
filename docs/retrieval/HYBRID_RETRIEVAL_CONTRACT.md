---
title: Hybrid retrieval contract
owner: engineering-lead
status: draft
last-reviewed: 2026-08-14
audience: engineering, reviewers
phase_packet: Phase 4 Packets 2-4
---

# Hybrid retrieval contract

Single source for versioned Hybrid channel profiles. Packet 2 freezes dense,
BM25, term, HNSW, and authorization foundations. Packet 3 freezes
``hybrid_default_v1`` as the only query-profile retrieval ID. Packet 4 freezes
RRF, channel weights, the 205 pre-fusion union, UTC temporal policies, coverage
signals, and the versioned cache-key/recheck interface. Rerank, MMR, and
calibrated coverage/refusal thresholds remain **not selected** until Packets
5-6 measure them on development/qualification data. Holdout is never used for
tuning.

Related: [ARABIC_NORMALIZATION.md](./ARABIC_NORMALIZATION.md) ·
[BM25_PROJECTION_CONTRACT.md](./BM25_PROJECTION_CONTRACT.md) ·
[QUALITY_TARGETS.md](../QUALITY_TARGETS.md) ·
[IDENTITY_PROPAGATION.md](../security/IDENTITY_PROPAGATION.md) ·
[phase-04 evidence](../development/phase-04-hybrid-rag-evidence.md)

## Protocol

```mermaid
sequenceDiagram
  participant API as FastAPI
  participant JWKS as Supabase JWKS
  participant Txn as Postgres transaction
  participant RPC as security-invoker RPC
  participant PDB as ParadeDB reader

  API->>JWKS: Verify JWT
  JWKS-->>API: sub plus session
  API->>API: Load CallerContext from profile
  API->>Txn: BEGIN SET LOCAL ROLE app_api
  API->>Txn: SET LOCAL hnsw and timeout
  alt Dense or term
    Txn->>RPC: retrieve_dense_candidates or retrieve_term_candidates
    Note over RPC: validate_caller_context plus ACL before rank and limit
  else BM25
    API->>PDB: typed field operators ID only
    PDB-->>API: up to 300 chunk IDs
    Txn->>RPC: recheck_retrieval_candidates
  end
  Txn-->>API: authorized IDs
  API->>API: max-across-variant RRF then weighted channels
  API->>API: UTC temporal policy plus coverage signals
  API->>Txn: COMMIT or ROLLBACK
```

Direct/pooled SQL does not inherit JWT identity. Caller IDs passed into RPCs
are **server-derived** and rechecked against live `profiles` and
`authorization_version`. PostgREST/anon/authenticated/`service_role` are not
granted retrieval EXECUTE.

## Frozen Packet 2 values

Every row records unit, source/baseline, allowed range, selected value,
dataset/config version, metric evidence, owner, rollback, and review trigger.

| Tunable | Unit | Source / baseline | Allowed range | Selected | Dataset / config | Evidence | Owner | Rollback | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dense candidate cap | IDs / query | Plan Packet 2 / skill | 1–100 | **100** | `phase4-dataset-v1` (not ingested) | SQL `LEAST(..., 100)` plus fixture clamp | retrieval | 100 | Packet 4 fusion |
| BM25 scan cap | IDs | Plan: 300 over 3 pages | 1–300 | **300** one top-N (no keyset) | `bm25_v1` | Typed queries; keyset not qualified on pg_search 0.25.2 | retrieval | 300 | If pin qualifies stable cursors |
| BM25 authorized survivors | IDs | Plan | 1–75 | **75** | `bm25_v1` | Recheck `LIMIT 75` | retrieval | 75 | Packet 4 |
| Term candidate cap | IDs | Plan | 1–30 | **30** | identifier-rules-v1 | SQL clamp | retrieval | 30 | Packet 6 calibration |
| Exact fallback row cap | authorized rows | Plan | ≤10,000 | **10,000** | `app.retrieval_exact_row_cap()` | Hard count, not planner estimate | retrieval | 10,000 | Envelope change |
| `hnsw.iterative_scan` | enum | pgvector 0.8 default `off` | `off` / `relaxed_order` / `strict_order` | **strict_order** | pgvector 0.8.0 local | Does **not** make HNSW exact | retrieval | `strict_order` | pgvector major bump |
| `hnsw.ef_search` low/medium/high | integer | pgvector default **40** | 4–1000 | **40 / 80 / 120** | seeded fixture | Fixture ANN IDs matched exact top-5 | retrieval | 40 | Packet 6 on development set |
| `hnsw.max_scan_tuples` | tuples (approx) | pgvector default 20,000 | ≥1 | **8000 / 16000 / 20000** | seeded fixture | Approximate visit bound, not a hard cap | retrieval | 20000 | Underfill vs exact oracle |
| `hnsw.scan_mem_multiplier` | × `work_mem` | pgvector default 1 | 1–1000 | **2** | pgvector 0.8 docs | Scales `work_mem` only | retrieval | 1 | Memory pressure |
| Retrieval `work_mem` | bytes | `app_api` role 8MB | bounded | **32MB** SET LOCAL | role timeouts Packet 2 | Transaction-local | retrieval | 8MB | Pool OOM |
| Statement timeout | ms | Hybrid p95 2s first evidence; `app_api` 15s | < 15s role default | **8000** | QT-LAT-001 | SET LOCAL | retrieval | 8000 | Latency miss |
| Trigram threshold | similarity | pg_trgm default 0.3 | 0–1 | **0.3** | pg_trgm | SET LOCAL `pg_trgm.similarity_threshold` | retrieval | 0.3 | Packet 6 |
| Vector opclass | — | ADR embedding | cosine | **`vector_cosine_ops` 1024** | ADR-embedding-model-dimension | HNSW index | retrieval | cosine | New embedding ADR |
| Arabic normalizer | version | Phase 2 | `arabic_norm_v1` only | **arabic_norm_v1** | parity fixtures | Byte-identical core/SQL/ParadeDB | retrieval | none | Second normalizer forbidden |
| BM25 tokenizer | — | Phase 2 pin | unicode_words, no stemmer | **`pdb.unicode_words`** | pg_search 0.25.2 | No English stemmer on Arabic | retrieval | unicode_words | Ablation packet |
| BM25 field order | priority | Plan | title > heading/alias > body | **title, heading, alias, body** | `bm25_v1` | Separate parameterized field queries | retrieval | same | Packet 4 boosts |
| BM25 operators | enum | ParadeDB match/phrase | `\|\|\|` `&&&` `###` | typed only; **no `pdb.parse`** | contract tests | Injection text stays a bound parameter | retrieval | typed | Pin change |
| Fallback `bm25_unavailable` | reason | Plan | enum | recorded, dense+term continue | Packet 2 | ParadeDB error or missing index | retrieval | same | Packet 4 coverage |
| Fallback `weak_evidence` | reason | Plan exact bound | enum | exact refused when count > 10k | Packet 2 | No unbounded seq scan | retrieval | same | Envelope change |
| Retrieval profile ID | enum | Plan Packet 3 | allow-listed IDs | **`hybrid_default_v1`** | `query_profile_v1` | LLM cannot set weights, depths, SQL, or timeouts | retrieval | `hybrid_default_v1` | New allow-listed ID |

## Frozen Packet 4 values

Packet 4 does not calibrate on holdout. Equal channel weights and the 90-day
`recent` window are plan-safe defaults until Packet 6 measures development
then qualification.

```mermaid
flowchart TD
  variants["At most 3 variants per channel"]
  denseCap["Dense cap 100"]
  bm25Cap["Authorized BM25 cap 75 after recheck"]
  termCap["Term cap 30"]
  maxRrf["Max RRF contribution per ID across variants"]
  weighted["Weighted channel sum rrf_k 60"]
  union["Unique IDs cap 205"]
  temporal["UTC latest current recent as_of"]
  coverage["Coverage conflict media negation"]

  variants --> denseCap
  variants --> bm25Cap
  variants --> termCap
  denseCap --> maxRrf
  bm25Cap --> maxRrf
  termCap --> maxRrf
  maxRrf --> weighted
  weighted --> union
  union --> temporal
  temporal --> coverage
```

| Tunable | Unit | Source / baseline | Allowed range | Selected | Dataset / config | Evidence | Owner | Rollback | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RRF `k` | dimensionless | Plan Packet 4 | 60 only until Packet 6 | **60** | `phase4-dataset-v1` | Unit `1/(60+rank)`; other `k` raises | retrieval | 60 | Packet 6 ablation |
| Channel weights dense/BM25/term | weight | Equal until measured | >0 allow-listed | **1.0 / 1.0 / 1.0** | `hybrid_default_v1` | Weighted sum after max-across-variants | retrieval | 1.0 | Packet 6 |
| Variant credit | rule | Plan | max, never sum | **max per ID** | unit tests | Order/duplicate invariant | retrieval | max | Packet 6 |
| Pre-fusion unique IDs | IDs / query | Plan | 1–205 | **205** | unit overflow | Truncate after fused sort | retrieval | 205 | Packet 6 depths |
| Metadata product | multiplier | Plan | `[1.0, 1.15]` | **clamp 1.15** | unit clamp | ACL/current-version are hard filters | retrieval | 1.15 | Packet 6 |
| Hybrid deadline | seconds | Global contract | ≤25 | **25** | `HYBRID_DEADLINE_SECONDS` | Parallel channels cancel; timeout ≠ empty | retrieval | 25 | Latency miss |
| `recent` window | days | Plan UTC | positive | **90** provisional | QT-TZ-001 | Unknown dates excluded | retrieval | 90 | Packet 6 |
| Temporal intents | enum | Plan / QT-TZ-001 | `none` `latest` `current` `recent` `as_of` | **UTC only** | temporal unit tests | Naive/Hijri timestamps rejected | retrieval | UTC | Signed company TZ |
| Coverage signals | enum | Plan Packet 4 | listed enums | **signals, not thresholds** | unit fixtures | Full-summary refused when headings missing | retrieval | same | Packet 6 thresholds |
| Cache key | SHA-256 | Plan Packet 4 | versioned material | **IDs/ranks only** | `hybrid_cache_key` | Must recheck before evidence; no Valkey yet | retrieval | same | Packet 6 TTL |
| BM25 degradation | reason | Plan | `bm25_unavailable` / version / timeout | **visible dense+term** | assemble tests | Never labeled three-channel Hybrid | retrieval | same | Circuit breaker |

Raw channel scores never mix. Equal fused scores break ties by effective date,
published date, then canonical ID. Equally authoritative current contradictions
emit `conflict` with both IDs.

## Not selected (later packets)

| Tunable | Owner packet | Status |
| --- | --- | --- |
| OpenAI rerank pool / model / schema | 5 | not applied |
| MMR / quotas / parent expansion | 5 | not applied |
| Coverage / refusal numeric thresholds | 6 | not applied |
| Cache TTLs / Valkey store | 6 | interface only |

## Authorization negatives

Zero rows for missing, forged, disabled, stale `authorization_version`,
cross-scope (member vs restricted without ACL), stale current-version,
soft-deleted chunks, `service_role` EXECUTE, and PostgREST/anon RPC calls.
Table-owner (superuser) connections still run `validate_caller_context` inside
the invoker function; NULL caller IDs return no rows.

## Citations

Dense/term/BM25 adapters return **canonical chunk IDs** only. Citation display
must read `document_chunks.raw_text`. BM25 `body_search` and
`search_normalized` are search forms and must not be shown as evidence.

## Verification

```powershell
uv run pytest tests/unit/test_hybrid_retrieval_foundations.py tests/unit/test_hybrid_fusion.py tests/contract/test_hybrid_retrieval.py tests/contract/test_hybrid_fusion.py -q
uv run python scripts/ci/check_migrations.py
```

## Rollback

Drop forward migration `20260814130000_hybrid_retrieval_v1.sql` via a later
expand/contract migration. ParadeDB index rebuild is derived
(`infra/paradedb/migrations/20260814130000_bm25_search_index.sql`).
