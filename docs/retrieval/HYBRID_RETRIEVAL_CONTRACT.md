---
title: Hybrid retrieval contract
owner: engineering-lead
status: draft
last-reviewed: 2026-08-15
audience: engineering, reviewers
phase_packet: Phase 4 Packets 2-8
---

# Hybrid retrieval contract

Single source for versioned Hybrid channel profiles. Packet 2 freezes dense,
BM25, term, HNSW, and authorization foundations. Packet 3 freezes
``hybrid_default_v1`` as the only query-profile retrieval ID. Packet 4 freezes
RRF, channel weights, the 205 pre-fusion union, UTC temporal policies, coverage
signals, and the versioned cache-key/recheck interface. Packet 5 freezes the
top-20 OpenAI rerank contract, skip policy, MMR/quotas, and parent expansion.
Packet 6 freezes per-class ``coverage_score`` thresholds at ``0.65`` in the
hashed artifact ``retrieval/frozen/hybrid_default_v1.json``. Packet 8 froze
those values as the winning profile and recorded a holdout **no-go**. Holdout is never
used for tuning. Unequal RRF weights and a different ``rrf_k`` were **not**
selected.

Related: [ARABIC_NORMALIZATION.md](./ARABIC_NORMALIZATION.md) ·
[BM25_PROJECTION_CONTRACT.md](./BM25_PROJECTION_CONTRACT.md) ·
[HYBRID_TUNING.md](./HYBRID_TUNING.md) ·
[PROHIBITED_V1_METHODS.md](./PROHIBITED_V1_METHODS.md) ·
[STRUCTURED_TABLE.md](./STRUCTURED_TABLE.md) ·
[QUALITY_TARGETS.md](../QUALITY_TARGETS.md) ·
[IDENTITY_PROPAGATION.md](../security/IDENTITY_PROPAGATION.md) ·
[COVERAGE_CALIBRATION.md](../evaluation/COVERAGE_CALIBRATION.md) ·
[COVERAGE_QUALIFICATION.md](../evaluation/COVERAGE_QUALIFICATION.md) ·
[RERANK_COUNTERFACTUAL.md](../evaluation/RERANK_COUNTERFACTUAL.md) ·
[PHASE4_FREEZE.md](../evaluation/PHASE4_FREEZE.md) ·
[PHASE4_ABLATIONS.md](../evaluation/PHASE4_ABLATIONS.md) ·
[PHASE4_HOLDOUT.md](../evaluation/PHASE4_HOLDOUT.md) ·
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
| Fallback `dense_unavailable` | reason | Packet 9 | enum | named | Packet 9 | Dense channel timeout/error | retrieval | same | Live retrieve |
| Fallback `term_unavailable` | reason | Packet 9 | enum | named | Packet 9 | Term channel timeout/error | retrieval | same | Live retrieve |
| Fallback `auth_context_invalid` | reason | Packet 9 | enum | named | Packet 9 | Missing/forged/stale caller | retrieval | same | Live retrieve |
| Fallback `retrieval_empty` | reason | Packet 9 | enum | named | Packet 9 | All channels empty after recheck | retrieval | same | Live retrieve |
| Fallback `retrieval_timeout` | reason | Packet 9 | enum | named | Packet 9 | Retrieval slice exhausted | retrieval | same | Live retrieve |
| Fallback `weak_evidence` | reason | Plan exact bound | enum | exact refused when count > 10k | Packet 2 | No unbounded seq scan | retrieval | same | Envelope change |
| Evidence unit cap | units | Plan Packet 9 | 1–12 | **12** hard max (target 8–12) | `FINAL_EVIDENCE_MAX` | Context selector | retrieval | 12 | Packet 9 |
| Query embed accounting | calls | Global QT-MC | 1 batched | original ∪ ≤3 variants | Packet 9 | Counts toward Hybrid 7 | retrieval | 1 | Live retrieve |
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
| RRF `k` | dimensionless | Plan Packet 4 | 60 | **60** | `hybrid_default_v1` | No ranked-ID evidence to retune | retrieval | 60 | Future sealed holdout after live ranked-ID repair |
| Channel weights dense/BM25/term | weight | Equal until measured | >0 allow-listed | **1.0 / 1.0 / 1.0** | `hybrid_default_v1` | Unequal weights not selected | retrieval | 1.0 | Future ranked-ID ablation |
| Variant credit | rule | Plan | max, never sum | **max per ID** | unit tests | Order/duplicate invariant | retrieval | max | Packet 6 |
| Pre-fusion unique IDs | IDs / query | Plan | 1–205 | **205** | unit overflow | Truncate after fused sort | retrieval | 205 | Packet 6 depths |
| Metadata product | multiplier | Plan | `[1.0, 1.15]` | **clamp 1.15** | unit clamp | ACL/current-version are hard filters | retrieval | 1.15 | Packet 6 |
| Hybrid deadline | seconds | Global contract | ≤25 | **25** | `HYBRID_DEADLINE_SECONDS` | Parallel channels cancel; timeout ≠ empty | retrieval | 25 | Latency miss |
| Retrieval slice | seconds | Packet 9 / statement timeout 8000ms | < Hybrid 25s | **8.0** | `RETRIEVAL_SLICE_SECONDS` | Channels + rerank share this slice; QT-LAT-001 first-evidence | retrieval | 8.0 | Latency miss |
| `recent` window | days | Plan UTC | positive | **90** provisional | QT-TZ-001 | Unknown dates excluded | retrieval | 90 | Packet 6 |
| Temporal intents | enum | Plan / QT-TZ-001 | `none` `latest` `current` `recent` `as_of` | **UTC only** | temporal unit tests | Naive/Hijri timestamps rejected | retrieval | UTC | Signed company TZ |
| Coverage signals | enum | Plan Packet 4 | listed enums | **signals plus numeric score** | unit fixtures | Full-summary refused when headings missing | retrieval | same | Live ranked-ID coverage |
| Cache key | SHA-256 | Plan Packet 4 | versioned material | **IDs/ranks only** | `hybrid_cache_key` | Must recheck before evidence; Valkey TTL not selected | retrieval | same | Valkey store still interface-only |
| BM25 degradation | reason | Plan | `bm25_unavailable` / version / timeout | **visible dense+term** | assemble tests | Never labeled three-channel Hybrid | retrieval | same | Circuit breaker |

Raw channel scores never mix. Equal fused scores break ties by effective date,
published date, then canonical ID. Equally authoritative current contradictions
emit `conflict` with both IDs.

## Frozen Packet 5 values

Accuracy-first: rerank every non-trivial knowledge query with at least two
authorized candidates. Skip only a trivial exact identifier/quoted-phrase
lookup with complete terms/filters and two independent channel signals.
Numeric score gaps never skip. Support is a ranking feature, not a
probability. Live OpenAI is unused while `MOCK_MODEL_MODE=true`.

```mermaid
flowchart TD
  fused["Authorized fused IDs"] --> pool["Top-20 pool, max 5 per document"]
  pool --> skip{"Trivial exact and two channels?"}
  skip -->|yes| mmrSkip["MMR plus quotas. No model call"]
  skip -->|no| oneCall["One Responses json_schema call. max_retries=0. No tools"]
  oneCall --> valid{"Set-equality and ranks valid?"}
  valid -->|no| rrf["Keep fused RRF order. Typed fallback"]
  valid -->|yes| mmr["MMR plus document/section quotas"]
  mmrSkip --> parents["Recheck parents. Adjacent from authorized pool"]
  rrf --> parents
  mmr --> parents
  parents --> trim["Cap 12 units / 3500 tokens. Canonical raw_text only"]
```

Counterfactuals: [RERANK_COUNTERFACTUAL.md](../evaluation/RERANK_COUNTERFACTUAL.md).

| Tunable | Unit | Source / baseline | Allowed range | Selected | Dataset / config | Evidence | Owner | Rollback | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Rerank pool | IDs | Plan | 2–20 | **20** | `hybrid_default_v1` | `build_rerank_pool` | retrieval | 20 | Packet 6 |
| Max passages per document in pool | IDs | Plan | 1–5 | **5** | unit quota test | Duplicates cannot crowd the pool | retrieval | 5 | Packet 6 |
| Rerank model | model id | OpenAI Responses structured output | allow-listed | **`gpt-4o-mini`** | `openai==2.26.0` | Mock identity in CI; live unverified | retrieval | `gpt-4o-mini` | Packet 6 live bake-off |
| Rerank prompt | version | Packet 5 | `rerank_v1` | **`rerank_v1`** | SHA-256 `4767049107cfe6e8591c84d3b1d202393dfd2564383e6c5bfa0bd5fece8f1925` | Changelog | retrieval | `rerank_v1` | Prompt edit |
| SDK retries | count | Plan one-operation | 0 | **0** | OpenAI client `max_retries=0` | Timeout/429 fall back to RRF | retrieval | 0 | SDK bump |
| Excerpt bound | chars / passage | Input bound | 1–400 | **400** | `RERANK_EXCERPT_CHARS` | Canonical `raw_text` only | retrieval | 400 | Token miss |
| MMR lambda | mix | Plan | (0, 1] | **0.7** provisional | Jaccard on `arabic_norm_v1` | Unit diversity test | retrieval | 0.7 | Packet 6 |
| Document / section quota | passages | Plan | ≥1 | **2 / 2** | unit quota | Stable ID tie-break | retrieval | 2 | Packet 6 |
| Final evidence | units / tokens | Plan ~8–12 | ≤12 / ≤3500 | **12 / 3500** | trim after parents | Recheck after expansion | retrieval | 12 / 3500 | Packet 6 |
| Skip policy | rule | Plan | trivial exact only | **two-channel exact/quote** | counterfactual script | No score-gap skip; Packet 6 did not retune | retrieval | same | Live always-rerank |

`app.fetch_authorized_chunk_context` still raises `context_batch_exceeds_limit`
above 75 IDs **per RPC**. The Python loader batches fused Hybrid IDs
(dense 100 + BM25 75 + term 30) into sequential 75-ID calls. Parallel
dense, term, and BM25-recheck channels each open a dedicated Supabase
connection from the full Postgres URL; they must not share one `psycopg`
connection (`Connection.info.dsn` omits the password).

## Frozen Packet 6 values

Runtime loads only ``hybrid_default_v1``. Unknown ids, including the documented
rollback id ``hybrid_packet5_v1``, fail closed. Mutating the JSON after the
pinned SHA-256 is a runtime error.

```text
coverage_score = min(
  required_term_entity_coverage,
  subquestion_coverage,
  min(1, distinct_evidence_count / profile_minimum),
  support_confidence
)
```

Simple queries use subquestion coverage 1 and profile minimum 1. Relationship
needs two units. Broad synthesis needs three. Multi-part needs one unit per
subquestion. ``support_confidence`` is rerank support when rerank ran, else
``1.0`` for exact or two-channel winners, else ``0.60``. It is not a
probability. Weak coverage is the development baseline ``<0.65``. False
supported answers carry loss weight 2; unnecessary refusals carry weight 1.

```mermaid
flowchart TD
  signals["Packet 4 coverage signals"] --> score["coverage_score min formula"]
  score --> threshold["Frozen per-class 0.65"]
  threshold --> decision{"score below threshold?"}
  decision -->|yes and signal none or full| weak["WEAK_EVIDENCE refuse"]
  decision -->|yes keep media negation conflict scoped BM25| keep["Keep signal. Refuse if refusal class"]
  decision -->|no| answer["ANSWER when no refusal signal"]
```

| Tunable | Unit | Source / baseline | Allowed range | Selected | Dataset / config | Evidence | Owner | Rollback | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Coverage threshold (all classes) | score | Development baseline 0.65 | 0.50–0.90 | **0.65** | `hybrid_default_v1` SHA-256 `def45b691e64707d07d3c7ea47f45eb1b23b5d2d2546c37a19a514f316c5940c` | [COVERAGE_CALIBRATION.md](../evaluation/COVERAGE_CALIBRATION.md) | retrieval | 0.65 | Independently sealed holdout (not opened in Packet 8) |
| False-supported loss weight | weight | Plan | >0 | **2** | occupancy eval | Qualification confirm | retrieval | 2 | Label revision |
| Unnecessary-refusal loss weight | weight | Plan | >0 | **1** | occupancy eval | Qualification confirm | retrieval | 1 | Label revision |
| Profile id | id | Packet 3 | allow-listed | **`hybrid_default_v1`** | hashed JSON | Unknown id fails closed | retrieval | `hybrid_packet5_v1` docs-only | Hash mismatch |

Channel depths, rerank skip, MMR, and quotas were **not** retuned. Packet 5
counterfactuals remain the recall evidence for those values. Occupancy
calibration is not a live ranked-ID ablation.

## Frozen Packet 7 structured-table values

Ordinary cell/text lookup stays Hybrid. Calculation binds
`structured_table_query` when the profile has `table_intent` and a calculation
hint. See [STRUCTURED_TABLE.md](./STRUCTURED_TABLE.md).

| Tunable | Unit | Source / baseline | Allowed range | Selected | Dataset / config | Evidence | Owner | Rollback | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Statement deadline | seconds | Plan Packet 7 | >0 | **3.0** | DuckDB 1.2.1 subprocess | Unit timeout terminate-then-kill | retrieval | 3.0 | Labeled-table p95 still unverified |
| Kill grace | seconds | Plan Packet 7 | >0 | **0.5** | same | Unit FakeProc | retrieval | 0.5 | Hang incidents |
| DuckDB memory_limit | bytes label | Adversarial bound | allow-listed | **64MB** | pin 1.2.1 | Connect config | retrieval | 64MB | Host RAM change |
| Temp directory size | bytes label | Adversarial bound | allow-listed | **32MB** | pin 1.2.1 | Connect config | retrieval | 32MB | Spill incidents |
| Threads | count | Plan | 1 | **1** | pin 1.2.1 | Connect config | retrieval | 1 | Never raise in v1 |
| Output rows | rows | Plan | 1–1000 | **1000** hard; plan default 100 | Packet 7 | Over-limit fails closed | retrieval | 1000 | Wide-sheet abuse |
| Output bytes | bytes | Plan | 1–1048576 | **1048576** | Packet 7 | Worker JSON cap | retrieval | 1048576 | Wide-sheet abuse |
| Scanned rows LIMIT | rows | Plan | 1–100000 | **100000** | Packet 7 | Compiler LIMIT | retrieval | 100000 | Envelope change |
| Timezone | IANA | Plan UTC | UTC | **UTC** | Packet 7 | `SET TimeZone='UTC'` | retrieval | UTC | Signed company TZ |

## Not selected (Packet 8 freeze)

Packet 8 recorded a **no-go**. See [PHASE4_FREEZE.md](../evaluation/PHASE4_FREEZE.md)
and [PHASE4_HOLDOUT.md](../evaluation/PHASE4_HOLDOUT.md). Winning profile remains
`hybrid_default_v1`. Cache TTLs and unequal RRF weights stay unselected.

| Tunable | Owner packet | Status |
| --- | --- | --- |
| Cache TTLs / Valkey store | 8 | still interface only; IDs/ranks plus mandatory recheck |
| Unequal RRF channel weights | 8 | not selected; no ranked-ID evidence |
| Live Hybrid Recall@10 / citation percents | 8 | Packet 8 unverified; Packet 9 measured Phase-4-owned open-split Recall@K (holdout sealed) |

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
uv run pytest tests/unit/test_hybrid_retrieval_foundations.py tests/unit/test_hybrid_fusion.py tests/unit/test_hybrid_rerank.py tests/unit/test_hybrid_coverage.py tests/unit/test_phase4_dataset.py tests/unit/test_structured_table.py tests/unit/test_phase4_freeze.py tests/contract/test_hybrid_retrieval.py tests/contract/test_hybrid_fusion.py tests/contract/test_hybrid_rerank.py tests/contract/test_structured_table.py -q
uv run python scripts/eval_coverage_calibration.py
uv run python scripts/eval_coverage_qualification.py
uv run python scripts/eval_rerank_counterfactual.py
uv run python scripts/eval_phase4_freeze.py
uv run python scripts/ci/check_migrations.py
```

## Rollback

Drop forward via later expand/contract migrations
`20260814130000_hybrid_retrieval_v1.sql`,
`20260814140000_hybrid_rerank_context_v1.sql`, and
`20260814150000_structured_table_v1.sql`. ParadeDB index rebuild is derived
(`infra/paradedb/migrations/20260814130000_bm25_search_index.sql`).
