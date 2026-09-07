---
title: Ingestion operational limits
owner: engineering-lead
status: draft
last-reviewed: 2026-09-07
audience: engineering, ops
---

# Ingestion operational limits

Single source of truth for Phase 3 durable job, worker, admission, and graph-handoff bounds. Values fixed by [QUALITY_TARGETS.md](../QUALITY_TARGETS.md) or the global contract require ADR approval to change. Unspecified defaults are conservative placeholders with explicit review triggers.

Related: [JOB_STATE_MACHINE.md](./JOB_STATE_MACHINE.md) · [SCAN_BEFORE_INDEX.md](./SCAN_BEFORE_INDEX.md) · [PARSER_SANDBOX.md](./PARSER_SANDBOX.md) · [Phase 3 evidence](../development/phase-03-ingestion-evidence.md) · [MAPPING.md](../graph/MAPPING.md) · [06-database-workload-isolation.md](../architecture/06-database-workload-isolation.md) · [ADR-lightrag-async-embed-batched-sources.md](../adr/ADR-lightrag-async-embed-batched-sources.md)

## Limit registry

| Limit | Unit | Default | Hard max | Source / benchmark | Owner | Failure route | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Job lease duration | seconds | 300 | 3600 | Plan Packet 2; 5× heartbeat interval | worker | Reclaim after expiry; graph writes denied | Heartbeat renewals fail >1% under longest qualified node |
| Heartbeat interval | seconds | 60 | 900 | Plan Packet 2; ≤ lease/5 | worker | Lease expires; job reclaims | p95 node runtime exceeds 4× heartbeat |
| Lease reclaim grace | seconds | 0 | 60 | Measured: reclaim on `lease_expires_at < now()` | worker | Competing worker claims expired row | Duplicate side effects without ledger dedupe |
| Worker poll interval | seconds | 5 | 60 | Measured local dev idle CPU | worker | Slower dequeue only | Pending p95 wait >15m at envelope |
| Worker concurrency | jobs | 2 | 8 | Plan Packet 2; provisional single-host | worker | Poll/claim bounded | CPU/memory saturation on launch hardware |
| Pending ingestion cap | jobs | 100 | 100 | Plan Packet 2 backpressure | admission | `JobAdmissionError` on enqueue | Sustained cap hits >1h/day |
| Graph index handoff pause | pending `index` jobs | 50 | 50 | Plan Packet 2 graph-handoff pause | admission/claim | Block new `index` claims; allow remove/ACL/rebuild | Pending handoffs >50 for >30m |
| Maintenance user-load pause | CPU/IO/memory percent | 70 | 70 | Global contracts; QT-LAT-001 p95 | HNSW/LightRAG rebuild/BM25 subset rebuild | Skip maintenance; rebuild jobs fail transient `maintenance_paused` | Live 8-doc Packet 4 stayed at 3.06% CPU; fixture-proven only |
| Max job attempts | count | 8 | 8 | Phase 2 schema default | worker | Dead-letter after exhaustion | >5% jobs exhaust attempts |
| Retry backoff base | seconds | 30 | 300 | Measured conservative | worker | `next_attempt_at` scheduling | Retry storm under outage |
| Retry backoff ceiling | seconds | 3600 | 86400 | Measured conservative | worker | Caps delay before reclaim | Oldest pending retry >24h |
| Retry jitter | fraction | 0.25 | 0.5 | Measured anti-thundering-herd | worker | Randomized delay | Synchronized retry spikes |
| Daily ingestion budget | USD/day | 20 | 20 | QT-COST-002 | admission | `JobAdmissionError` budget | Owner sign-off in QUALITY_TARGETS |
| Per-job budget reservation TTL | minutes | 120 | 480 | Measured reserve-once pattern | admission | Reservation expires; true-up on complete/fail | Reservation leak >0.1%/day |
| Estimated job size default | bytes | 0 | — | Unknown until scan (Packet 3) | enqueue | Ordering tie-break only | Size estimates diverge >2× from measured |
| Estimated job size hard cap | bytes | 536870912 | 536870912 | 512 MiB conservative | admission | Reject enqueue | Owner approves larger uploads |
| Dead-letter replay idempotency | policy | new `idempotency_key` suffix | — | Plan Packet 2 traceability | dead-letter | Preserves original DL row | Replay duplicates without audit link |
| Ledger operation dedupe | key | `(job_table, job_id, operation_key)` UNIQUE | — | Plan Packet 2 | graph/worker | Second write is no-op | Duplicate ledger rows |
| Checkpointer retention | days | 30 | 30 | Data dictionary / Phase 2 | ops | GC job (later) | Undeleted runs exceed policy |
| Checkpointer runtime wiring | policy | PostgresSaver on schema `langgraph` | — | `langgraph-checkpoint-postgres==3.1.2` for `langgraph==1.2.11` | agents/worker | `thread_id=job_id`; no runtime `setup()` | Library migrations beyond seeded 0–9 |

## ClamAV / scan bounds (Packet 3)

| Limit | Unit | Default | Hard max | Source / benchmark | Owner | Failure route | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Scan max bytes | bytes | 104857600 | 104857600 | 100 MiB conservative | worker | `over_limit`; remain quarantined | Owner approves larger uploads |
| Scan timeout | seconds | 120 | 300 | Measured local dev | worker | `unscannable`; retry transient | p95 scan > timeout |
| Signature max age | hours | 24 | 24 | Global contract QT-RET-002 | worker | `stale_signature`; block promotion | Signatures stale >1h in prod |
| Scan max recursion | levels | 16 | 32 | ClamAV default guidance | worker | `over_limit` | Archive bomb fixtures fail open |
| Scan max files | count | 10000 | 10000 | ClamAV default guidance | worker | `over_limit` | Nested archive fixtures |
| Scan max embedded PE | count | 40 | 40 | ClamAV default guidance | worker | `over_limit` | — |
| Archive max expansion ratio | ratio | 250 | 250 | Plan Packet 3/8; parser ZIP inspect + stream cap + ClamAV | parser/scan | `over_limit` / failed parse, zero elements | Zip bomb fixtures |
| Scan concurrent streams | count | 2 | 4 | Worker concurrency /2 | worker | queue/backpressure | CPU saturation |
| Signature reload memory | MiB | 512 | 1024 | ClamAV docs + local measure | ops | fail closed until reload completes | OOM during freshclam |
| Quarantine TTL | hours | 24 | 168 | QT-RET-002 | cleanup | Storage API delete + quota release | Owner via company_settings |
| Promotion copy timeout | seconds | 300 | 600 | Measured Storage copy | worker | saga retry; admin alert | Large object promotion lag |
| Promotion verify timeout | seconds | 120 | 300 | Measured hash verify | worker | remain quarantined | Hash mismatch alerts |
| Orphan cleanup batch | rows | 100 | 1000 | Phase 2 RPC cap | worker | next poll cycle | Backlog >24h |

ClamAV engine image pin (local Compose): `clamav/clamav:stable@sha256:78810772a92b4a9168115bc6b2e0ffd702640893b9577f8c3d0432762d2655c4` (GPL-2.0; upstream Cisco Talos ClamAV).

## Promotion / cleanup bounds (Packet 3)

| Limit | Unit | Default | Hard max | Source / benchmark | Owner | Failure route | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Promotion saga idempotency | key | `{operation_key}:promotion` | — | Plan Packet 3 | worker | resume from ledger step | Duplicate destination objects |
| Authoritative object reference | policy | one destination path post-DB-switch | — | Plan Packet 3 | worker | reconciler; no parse success | Orphan accepted object detected |
| Admin notification kinds | policy | byte_spike, quarantine_accumulation, repeated_scan_failure | — | Phase 2 seeds | worker/api | durable row + optional operator SMTP | Missing alert on anomaly fixture |
| Metadata governance policy version | text | `2026-08-13` | — | Packet 1 sign-off | worker | deny promotion | Policy drift without sign-off |

## Priority ordering

Claim ordering is deterministic: `critical` → `high` → `normal` → `low`, then `created_at ASC`, then `estimated_size_bytes ASC`. Deletion/ACL/security cleanup jobs must enqueue at `critical` or `high` (Packet 7+).

## Graph-handoff pause

When `COUNT(*) FROM app.lightrag_index_jobs WHERE status = 'pending' AND operation = 'index'` exceeds **50**, `app.claim_lightrag_index_job` skips new `index` operations while still claiming `remove`, `graph_acl_remove`, and `rebuild`.

## Maintenance user-load pause

HNSW `REINDEX`, LightRAG `rebuild`, and Packet 4 BM25 subset rebuild call
`MaintenancePauseController` before starting work. The trigger is **70%**
database CPU, IO, or memory, or Hybrid first-evidence p95 above QT-LAT-001
(2000 ms). Missing or invalid telemetry is fail-closed on those gated
paths. Fixture tests prove the 70% fire. Live Packet 4 8-doc CPU peaked at
3.06% and remains **Blocked**. Do not claim QT-CAP-001/002 from that subset.
See [06-database-workload-isolation.md](../architecture/06-database-workload-isolation.md).

## Budget admission

Daily ingestion spend uses durable `app.budget_reservations` with `reservation_kind = 'ingestion_daily'`. Enqueue reserves an estimated USD amount against `app.company_settings.daily_ingestion_budget_usd` (default from QT-COST-002). Completion/failure true-ups adjust committed/released amounts without bypassing the daily cap.

Graph mutations use separate kinds: `graph_index` (daily cap `daily_graph_index_budget_usd`, default 20) and `graph_maintenance` (monthly cap `monthly_graph_maintenance_budget_usd`, default 800). Normal graph index must not consume the maintenance reserve or `ingestion_daily`. See [WORKSPACE_LIFECYCLE.md](../graph/WORKSPACE_LIFECYCLE.md).

## Crawl bounds (Packet 4)

| Limit | Unit | Default | Hard max | Source / benchmark | Owner | Failure route | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Allowed schemes | policy | http, https | http, https | Plan Packet 4 | worker | `policy_denied` | New scheme request |
| Allowed ports | ports | 80, 443 | 80, 443 | Plan Packet 4 | worker | `policy_denied` | Owner approves alt port |
| Max URL length | chars | 2048 | 2048 | Conservative | worker | `invalid_url` | Crawl fixture exceeds |
| Max redirects | hops | 5 | 5 | Plan Packet 4 | worker | `limit_exceeded` | Redirect chain fixtures |
| Max depth | levels | 2 | 5 | Approval + hard cap | worker | stop enqueue/deeper links | Owner approves depth |
| Max pages | pages | 50 | 200 | Approval + hard cap | worker | stop crawl | Owner approves pages |
| Max wire bytes / page | bytes | 2097152 | 2097152 | 2 MiB measured | proxy | `wire_bytes_exceeded` | Large page fixtures |
| Max decoded bytes / page | bytes | 5242880 | 5242880 | 5 MiB measured | proxy | `decoded_bytes_exceeded` | Compression fixtures |
| Max decompression ratio | ratio | 50 | 50 | Plan Packet 4 | proxy | `decompression_ratio_exceeded` | Zip/gzip bomb fixtures |
| Max wire bytes / crawl | bytes | 52428800 | 52428800 | 50 MiB measured | worker | `limit_exceeded` | Site-wide crawl |
| Max decoded bytes / crawl | bytes | 104857600 | 104857600 | 100 MiB measured | worker | `limit_exceeded` | Site-wide crawl |
| DNS timeout | seconds | 5 | 5 | Measured local | worker | `dns_failure` | Resolver latency |
| Connect timeout | seconds | 10 | 10 | Measured local | proxy | `read_timeout` | Slow origins |
| Read timeout | seconds | 30 | 30 | Measured local | proxy | `read_timeout` | Large pages |
| Total crawl timeout | seconds | 300 | 300 | Plan Packet 4 | worker | `limit_exceeded` | Long crawls |
| Concurrent fetches | count | 2 | 2 | Worker concurrency /2 | worker | queue | CPU saturation |
| Robots.txt max bytes | bytes | 524288 | 524288 | RFC 9309 guidance | worker | `robots_denied` | Large robots files |
| Robots fetch timeout | seconds | 15 | 15 | Measured | worker | `robots_denied` | Slow robots hosts |
| Max header block | bytes | 32768 | 32768 | Measured | proxy | fail closed | Header abuse |
| Allowed content types | MIME | html/plain/xhtml | same | Plan Packet 4 | worker | skip/fail page | New MIME request |
| Crawl policy version | text | `crawl_v1` | — | Packet 4 sign-off | worker | deny crawl | Policy drift |
| Egress path | policy | crawl-proxy only | — | ADR deny-by-default | infra | block job | Direct egress probe |

Crawl proxy image: built from `infra/crawl-proxy` (trixie builder, distroless
runtime, `brotli==1.1.0`). Only `crawl-proxy` joins the non-internal `egress`
Compose network; API/worker/parser remain on `private` without public routes.

Primary references: [RFC 9309 robots](https://www.rfc-editor.org/rfc/rfc9309.html), [Python urllib.robotparser](https://docs.python.org/3/library/urllib.robotparser.html), [httpx redirects](https://www.python-httpx.org/compatibility/#redirects) (disabled; manual hop revalidation), [ipaddress](https://docs.python.org/3/library/ipaddress.html).

## Parser / OCR bounds (Packet 5)

| Limit | Unit | Default | Hard max | Source / benchmark | Owner | Failure route | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Parser input bytes | bytes | 104857600 | 104857600 | Align scan max | worker | `failed` disposition | Owner approves larger uploads |
| Parser expanded bytes | bytes | 524288000 | 524288000 | Measured zip/archive guard | worker | `failed` disposition | Archive bomb fixtures |
| Parser sandbox memory | MiB | 512 | 1024 | Local Docker Desktop measure | worker | kill + `failed` | OOM in parser container |
| Parser sandbox CPUs | cores | 1.0 | 2.0 | Single-host envelope | worker | throttle/kill | p95 parse > timeout |
| Parser sandbox PIDs | count | 64 | 128 | fork bomb fixtures | worker | kill + `failed` | fork storm fixtures |
| Parser kill timeout | seconds | 120 | 300 | Plan Packet 5 | worker | kill grace 5s | p95 parse > timeout |
| Parser concurrency | jobs | 2 | 2 | Worker concurrency /2 | worker | queue | CPU saturation |
| PDF max pages | pages | 500 | 500 | Plan Packet 5 | parser | `limit_exceeded:pages` | Large PDF fixtures |
| XLSX max sheets | sheets | 50 | 50 | Plan Packet 5 | parser | `limit_exceeded:sheets` | Workbook fixtures |
| CSV/XLSX max rows | rows | 200000 | 200000 | Plan Packet 5 | parser | `limit_exceeded:rows` | Spreadsheet fixtures |
| OCR max pixels | pixels | 50000000 | 50000000 | 200 DPI letter page estimate | parser | skip OCR / `media_only` | Scanned PDF fixtures |
| OCR DPI | dpi | 200 | 300 | Tesseract guidance | parser | downgrade quality | OCR quality review |
| OCR languages | codes | eng+ara | eng+ara | Phase 1 multilingual gate | parser | `media_only`/diagnostic | Language coverage gap |
| OCR min confidence | percent | 30 | 30 | Measured dev fixtures | parser | omit low-conf boxes | OCR recall review |
| Parser config version | text | `parser_v1` | — | Packet 5 sign-off | parser | reject stale replay | Policy drift |
| Cleaning policy version | text | `cleaning_v1` | — | Packet 5 sign-off | parser | reject stale replay | Cleaning rule change |
| Parser network | policy | none | none | ADR parser isolation | infra | block job | Egress probe from parser |
| Parser secrets | policy | none | none | ADR parser isolation | infra | block launch | Secret mount detected |

Parser/OCR library pins (uv workspace `packages/core`):

| Library | Pin | License | Role |
| --- | --- | --- | --- |
| PyMuPDF | 1.25.5 | AGPL-3.0 | PDF text/boxes/scanned render |
| python-docx | 1.1.2 | MIT | DOCX logical structure |
| python-pptx | 1.0.2 | MIT | PPTX slides/shapes/order |
| openpyxl | 3.1.5 | MIT | XLSX typed cells/formulas |
| beautifulsoup4 | 4.13.3 | MIT | HTML DOM + boilerplate |
| lxml | 6.1.0 | BSD | HTML parser backend |
| markdown-it-py | 3.0.0 | MIT | Markdown token paths |
| pytesseract | 0.3.13 | Apache-2.0 | OCR wrapper |
| Pillow | 12.3.0 | HPND | OCR/image buffers |
| pydantic | 2.13.4 | MIT | ParseResult JSON in sandbox runner |
| Tesseract (image) | distro package | Apache-2.0 | OCR engine + eng/ara traineddata |

Parser sandbox image: built from `infra/parser-sandbox` (`smart-rag-parser-sandbox:local`). Compose profile `parser-build` only; service stays on `private` network and is **not** attached to `egress`.

Primary references: [PyMuPDF docs](https://pymupdf.readthedocs.io/), [python-docx](https://python-docx.readthedocs.io/), [python-pptx](https://python-pptx.readthedocs.io/), [openpyxl](https://openpyxl.readthedocs.io/), [Tesseract](https://tesseract-ocr.github.io/).

## Chunking / dedup / table artifact bounds (Packet 6)

| Limit | Unit | Default | Hard max | Source / benchmark | Owner | Failure route | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Chunking policy version | text | `chunking_v1` | — | Packet 6 sign-off | worker | reject stale replay | Policy drift |
| Tokenizer version | text | `cl100k_base_v1` | — | ADR `text-embedding-3-large` sizing | worker | reject stale replay | Embedding model change |
| Dedup policy version | text | `dedup_v1` | — | Packet 6 sign-off | worker | exact-only fallback | Fuzzy gate miss |
| Passage target tokens | tokens | 200–400 | — | CHUNKING_CONTRACT | worker | split/merge | <90% ordinary prose in band |
| Passage overlap | tokens | 50 | 40–60 | CHUNKING_CONTRACT | worker | metric fail | Overlap drift |
| Passage hard cap | tokens | 600 | 600 | CHUNKING_CONTRACT | worker | atomic exception only | Silent split defect |
| Parent cap | tokens | 1500 | 1500 | CHUNKING_CONTRACT | worker | truncate child refs | Parent reconstruction fail |
| Near-dup threshold | ratio | 0.92 | 0.92 | Packet 6 provisional | worker | exact-only fallback | Precision/recall gate |
| Near-dup precision gate | ratio | 0.99 | 0.99 | QT-CHK dedup | worker | exact-only fallback | Fixture regression |
| Near-dup recall gate | ratio | 0.85 | 0.85 | QT-CHK dedup | worker | exact-only fallback | Fixture regression |
| Table schema version | text | `table_parquet_v1` | — | Packet 6 sign-off | worker | reject write | Schema drift |
| Parquet compression | codec | zstd | zstd | Arrow 19 pin | worker | fail closed | Round-trip loss |
| Parquet row group size | rows | 65536 | 65536 | Arrow 19 pin | worker | fail closed | Read latency review |
| Timestamp unit/timezone | policy | `us` / UTC | — | Packet 6 | worker | fail closed | TZ coercion defect |
| DuckDB sandbox | policy | read-only fixture | — | Phase 4 prep | tests | block query | Escape probe |

Arrow / Parquet / tokenizer library pins (uv workspace `packages/core`):

| Library | Pin | License | Role |
| --- | --- | --- | --- |
| tiktoken | 0.9.0 | MIT | Embedding token counting (`cl100k_base`) |
| pyarrow | 19.0.1 | Apache-2.0 | Typed Parquet read/write |
| duckdb | 1.2.1 | MIT | Dev-only sandbox contract tests |

Primary references: [tiktoken](https://github.com/openai/tiktoken), [Apache Arrow Parquet](https://arrow.apache.org/docs/python/parquet.html), [DuckDB read_parquet](https://duckdb.org/docs/data/parquet/overview.html).

## Embedding bounds (Packet 7)

| Limit | Unit | Default | Hard max | Source / benchmark | Owner | Failure route | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Embedding model | id | `text-embedding-3-large` | — | ADR-embedding-model-dimension | gateway | reject batch | Model change without ADR |
| Embedding dimensions | count | 1024 | 1024 | ADR-embedding-model-dimension | gateway | reject batch | Dimension mismatch |
| Contextual policy version | text | `contextual_v1` | — | Packet 7 sign-off | worker | reject stale replay | Policy drift |
| Batch size | inputs/request | 64 | 2048 | OpenAI documented tier + measured dev | gateway | split/reject | Provider 413/limit errors |
| Request timeout | seconds | 120 | 300 | Hybrid ingest only. LightRAG uses 20s below. | gateway | retry once | p95 timeout breaches |
| LightRAG embedding provider timeout | seconds | 20 | 20 | Must stay below LightRAG watchdog (30s). SDK default 600s is forbidden there. | gateway | `embedding_timeout` | Watchdog health-check kill |
| LightRAG embedding watchdog | seconds | 30 | 30 | Vendor `default_embedding_timeout`; do not raise | adapter | vendor force-kill | Health-check 75s misses |
| Gateway retries | count | 2 | 2 | Packet 7 bounded repair | gateway | fail batch | Retry storm |
| Gateway concurrency | workers | 1 | 2 | Worker concurrency /2 | gateway | queue | Provider 429 sustained |
| Ledger idempotency | key | `(version_id, operation_key)` UNIQUE | — | Packet 7 | worker | replay no-op | Duplicate canonical rows |
| Budget reservation | USD/job | 0.05 | 1.00 | QT-COST-002 provisional | admission | `JobAdmissionError` | Budget leak >0.1%/day |

Primary references: [OpenAI embeddings](https://platform.openai.com/docs/guides/embeddings), [ADR-embedding-model-dimension](../adr/ADR-embedding-model-dimension.md).

## BM25 projection bounds (Packet 7)

| Limit | Unit | Default | Hard max | Source / benchmark | Owner | Failure route | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Upsert batch size | rows | 250 | 250 | Measured ParadeDB writer | worker | split batch | Writer timeout/OOM |
| Delete batch size | rows | 500 | 500 | Measured ParadeDB writer | worker | split batch | Long delete tail |
| Verify sample queries | count | 5 | 10 | Packet 7 cross-system gate | worker | remain pre-Hybrid | False Hybrid Ready |
| Verify query limit | rows | 10 | 10 | Packet 7 tie-break check | worker | fail verify | Non-deterministic rank |
| Index schema version | text | `bm25_v1` | — | BM25 projection contract | worker | fail closed | Schema drift |
| Normalization version | text | `arabic_norm_v1` | — | Phase 2 SQL fixture | worker | fail closed | Parity regression |
| Projection lag SLO | minutes p95 | 5 | 5 | QT-BM25-003 | ops | diagnostic only | Sustained lag |
| Deletion cleanup priority | band | `high` | `critical` | Plan Packet 7 | worker | immediate enqueue | Stale candidate leak |

ParadeDB writer credentials: `PARADEDB_URL` on worker only (Compose `paradedb_writer`). Supabase remains authoritative; ParadeDB holds rebuildable projection rows keyed by canonical chunk IDs.

## Graph mapping bounds (Packet 4)

| Limit | Unit | Default | Hard max | Source / benchmark | Owner | Failure route | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Mapping support | ratio | 0.80 | 0.80 | Phase 5 Packet 4 | mapper | object unavailable + repair | Owner sign-off to change |
| Overall mapping coverage | ratio | 0.90 | 0.90 | Phase 5 Packet 4 | mapper | stay `graph_pending` | English-only corpus review |
| Arabic/mixed coverage | ratio | 0.85 | 0.85 | Phase 5 Packet 4 per-language | mapper | `language_gate` repair | Arabic fixture miss |
| Overlap accept | Jaccard | 0.50 | 0.50 | Packet 4 hash/span/overlap | mapper | fall through to Hybrid batch | Near-dup false merge |
| Vendor chunks per document | count | 500 | 500 | Packet 4 budget | mapper | `mapping_budget_chunks` | Large-doc split policy |
| Canonical passage sources per version | count | 500 | 500 | ADR-canonical-passage-lightrag-sources | indexer | `graph_source_too_many_passages` | Corpus larger than Graph-200 |
| Canonical passage source chars | chars | 24000 | 24000 | ADR-canonical-passage-lightrag-sources | indexer | `graph_source_passage_too_large` | Passage exceeds envelope+chunker |
| Graph source insert batch size | sources | 8 | 8 | ADR-lightrag-async-embed-batched-sources | indexer | split remaining batches | Load-test before raising |
| Graph source batch transient attempts | count | 2 | 2 | First try plus cleanup retry | indexer | fail job; no live quarantine when isolated | Retry storm |
| Graph embedding latency alert | milliseconds | 15000 | 15000 | Operator signal; 131.3s Graph-200 miss | worker | admin notification `graph_embedding_latency` | p95 embed > 15s |
| Graph source batch size alert | sources | 8 | 8 | Fires when an insert batch exceeds the signed cap | worker | admin notification `graph_source_batch_size` | Unsigned batch increase |
| Graph source batch poll deadline | seconds | 14400 | 14400 | Graph-200 ~164 extract sources | indexer | `vendor_status_deadline` | Extract p95 exceeds 4h |
| Entities per document | count | 200 | 200 | Packet 4 budget | mapper | `mapping_budget_entities` | Extraction flood |
| Relations per document | count | 200 | 200 | Packet 4 budget | mapper | `mapping_budget_relations` | Extraction flood |
| Hybrid mapping retrieve | calls/doc | 1 | 1 | Packet 4 one-shot | mapper | `mapping_budget_hybrid` | Per-relation retrieve regression |
| Mapping Hybrid candidate cap | IDs | 100 | 100 | Dense candidate cap reuse | mapper | cap then RRF | Channel-cap drift |
| Support rerank | calls/doc | 1 | 1 | Packet 4 OpenAI-only | mapper | `mapping_budget_rerank` | Local-model proposal |
| Support rerank pool | passages | 20 | 20 | Hybrid rerank pool | mapper | skip rerank if &lt; 2 | Pool drift |
| Support rerank deadline | seconds | 8 | 8 | Retrieval slice | mapper | identity ranks support 0.0 | Deadline change |
| Source ids per entity | count | 200 | 200 | Packet 1 `GRAPH_FIELD_SEP` | mapper | truncated unavailable | Silent provenance |
| Source ids per relation | count | 200 | 200 | Packet 1 `GRAPH_FIELD_SEP` | mapper | truncated unavailable | Silent provenance |

The accepted synthetic Graph-200 demo may raise only the entity/relation
enumeration limits to 2,000/1,800. The worker applies that pair only when
`APP_ENV=local` and the durable job payload contains
`local_demo_mapping_override=true`, `content_class=synthetic`, and
`review_approved=true`. Staging, production, and every other job retain the
200/200 bounds. Vendor chunks and model-call limits are unchanged.

Canonical-passage indexing is the Graph Ready path:
[ADR-canonical-passage-lightrag-sources.md](../adr/ADR-canonical-passage-lightrag-sources.md)
and
[ADR-lightrag-async-embed-batched-sources.md](../adr/ADR-lightrag-async-embed-batched-sources.md).
Hybrid/rerank mapping callbacks stay unused on that exact bijection. Repair
jobs are keyed by workspace/object/map_kind/config generation. Repair must
not query Hybrid and must not lower these thresholds. See [MAPPING.md](../graph/MAPPING.md).

## Graph query and inspection bounds (Packet 5)

| Limit | Unit | Default | Hard max | Source / benchmark | Owner | Failure route | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Graph candidates | count | 12 | 12 | Phase 5 Packet 5 | retrieval | clamp then drop | Owner sign-off |
| Graph hops | hops | 3 | 3 | Phase 5 Packet 5 | retrieval | path truncated | Owner sign-off |
| Graph paths | count | 6 | 6 | Phase 5 Packet 5 | retrieval | path truncated | Owner sign-off |
| Global steering topics | count | 3 | 3 | Phase 5 Packet 5 | retrieval | `global_steering_only` | Owner sign-off |
| Query adapter deadline | seconds | 45 | 45 | `GraphQueryBounds` | retrieval | `graph_deadline` | Combined budget |
| Inspection deadline | seconds | 10 | 10 | Phase 5 Packet 5 | API | `graph_deadline` | Owner sign-off |
| Inspection depth | hops | 3 | 3 | Phase 5 Packet 5 | SQL | clamp | Owner sign-off |
| Inspection rows | count | 200 | 200 | Phase 5 Packet 5 | SQL | LIMIT | Owner sign-off |
| Inspection statement_timeout | seconds | 3 | 3 | Phase 5 Packet 5 | SQL | statement timeout | Owner sign-off |
| Mapping support (query) | ratio | 0.80 | 0.80 | Packet 4 threshold | resolver | whole-candidate drop | Owner sign-off |
| Survival fallback | ratio | 0.50 | 0.50 | Phase 5 Packet 5 | retrieval | `graph_survival_below_threshold` | Combined packet |
| Survival rolling window | samples | 20 | 20 | Phase 5 Packet 5 | retrieval | recorded mean only | Combined packet |

Query-time repair uses `map_kind=query_resolve` and never Hybrid. See [RETRIEVAL.md](../graph/RETRIEVAL.md).

## Verification commands

```bash
uv run pytest tests/unit/test_parser_adapters.py tests/unit/test_parser_governance.py tests/unit/test_parser_sandbox.py -q
uv run pytest tests/contract/test_parser_sandbox.py tests/contract/test_compose_topology.py -q
uv run pytest tests/unit/test_chunking_service.py tests/unit/test_chunking_dedup.py tests/unit/test_table_parquet.py tests/contract/test_duckdb_parquet_sandbox.py -q
uv run pytest tests/unit/test_embedding_service.py tests/unit/test_phase3_graph_scope_guard.py tests/unit/test_ingestion_status_openapi.py -q
docker compose --profile parser-build build parser-sandbox
```

When ParadeDB sidecars are running, apply cloud migrations and run integration contracts:

```bash
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --wait clamav paradedb crawl-proxy
docker compose --env-file .env.compose --profile parser-build build parser-sandbox
uv run pytest tests/contract/test_job_leases.py tests/contract/test_hybrid_lifecycle.py tests/contract/test_hybrid_ready_e2e.py tests/contract/test_crawl_proxy_live.py tests/contract/test_clamav_scan.py -q
uv run python scripts/phase3_throughput_benchmark.py --iterations 10
```
