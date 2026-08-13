---
title: Ingestion operational limits
owner: engineering-lead
status: draft
last-reviewed: 2026-08-13
audience: engineering, ops
---

# Ingestion operational limits

Single source of truth for Phase 3 durable job, worker, admission, and graph-handoff bounds. Values fixed by [QUALITY_TARGETS.md](../QUALITY_TARGETS.md) or the global contract require ADR approval to change. Unspecified defaults are conservative placeholders with explicit review triggers.

Related: [JOB_STATE_MACHINE.md](./JOB_STATE_MACHINE.md) · [Phase 3 evidence](../development/phase-03-ingestion-evidence.md)

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
| Checkpointer runtime wiring | policy | no checkpointer on probe graph | — | `langgraph-checkpoint-postgres` not pinned | agents | compile-only probe; no runtime migrate | Pin + bootstrap path approved |

## ClamAV / scan bounds (Packet 3)

| Limit | Unit | Default | Hard max | Source / benchmark | Owner | Failure route | Review trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Scan max bytes | bytes | 104857600 | 104857600 | 100 MiB conservative | worker | `over_limit`; remain quarantined | Owner approves larger uploads |
| Scan timeout | seconds | 120 | 300 | Measured local dev | worker | `unscannable`; retry transient | p95 scan > timeout |
| Signature max age | hours | 24 | 24 | Global contract QT-RET-002 | worker | `stale_signature`; block promotion | Signatures stale >1h in prod |
| Scan max recursion | levels | 16 | 32 | ClamAV default guidance | worker | `over_limit` | Archive bomb fixtures fail open |
| Scan max files | count | 10000 | 10000 | ClamAV default guidance | worker | `over_limit` | Nested archive fixtures |
| Scan max embedded PE | count | 40 | 40 | ClamAV default guidance | worker | `over_limit` | — |
| Archive max expansion ratio | ratio | 250 | 250 | Plan Packet 3 | worker | `over_limit` | Zip bomb fixtures |
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
| Admin notification kinds | policy | byte_spike, quarantine_accumulation, repeated_scan_failure | — | Phase 2 seeds | worker/api | durable row + Inbucket locally | Missing alert on anomaly fixture |
| Metadata governance policy version | text | `2026-08-13` | — | Packet 1 sign-off | worker | deny promotion | Policy drift without sign-off |

## Priority ordering

Claim ordering is deterministic: `critical` → `high` → `normal` → `low`, then `created_at ASC`, then `estimated_size_bytes ASC`. Deletion/ACL/security cleanup jobs must enqueue at `critical` or `high` (Packet 7+).

## Graph-handoff pause

When `COUNT(*) FROM app.lightrag_index_jobs WHERE status = 'pending' AND operation = 'index'` exceeds **50**, `app.claim_lightrag_index_job` skips new `index` operations while still claiming `remove`, `graph_acl_remove`, and `rebuild`.

## Budget admission

Daily ingestion spend uses durable `app.budget_reservations` with `reservation_kind = 'ingestion_daily'`. Enqueue reserves an estimated USD amount against `app.company_settings.daily_ingestion_budget_usd` (default from QT-COST-002). Completion/failure true-ups adjust committed/released amounts without bypassing the daily cap.

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

Crawl proxy image: built from `infra/crawl-proxy` (Python 3.11 slim + `brotli==1.1.0`). Only `crawl-proxy` joins the non-internal `egress` Compose network; API/worker/parser remain on `private` without public routes.

Primary references: [RFC 9309 robots](https://www.rfc-editor.org/rfc/rfc9309.html), [Python urllib.robotparser](https://docs.python.org/3/library/urllib.robotparser.html), [httpx redirects](https://www.python-httpx.org/compatibility/#redirects) (disabled; manual hop revalidation), [ipaddress](https://docs.python.org/3/library/ipaddress.html).

## Verification commands

```bash
uv run pytest tests/unit/test_crawl_policy.py tests/unit/test_crawl_proxy.py -q
uv run pytest tests/contract/test_crawl_ssrf.py tests/contract/test_compose_topology.py -q
```

When local Supabase is running, apply migrations and run the SKIP LOCKED contract test:

```bash
pnpm exec supabase db reset --yes
uv run pytest tests/contract/test_job_leases.py -q
```
