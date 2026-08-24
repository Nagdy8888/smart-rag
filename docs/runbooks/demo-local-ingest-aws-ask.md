---
title: Demo local ingest and AWS ask later
owner: engineering-lead
status: draft
last-reviewed: 2026-08-20
audience: engineering, ops
---

# Demo: laptop ingest, hosted Supabase, AWS ask later

**EC2 is not ready now.** Do not SSH, SSM, or `compose up` on AWS until the
operator says the instance is up. This is a demo procedure, not a
production-ready claim.

Canonical decision:
[ADR-demo-local-ingest-aws-ask.md](../adr/ADR-demo-local-ingest-aws-ask.md).
Related: [LANGSMITH_TRACING.md](../development/LANGSMITH_TRACING.md) ·
[ADR-lightrag-async-embed-batched-sources.md](../adr/ADR-lightrag-async-embed-batched-sources.md) ·
[CONFIGURATION.md](../development/CONFIGURATION.md) ·
[bm25-rebuild.md](./bm25-rebuild.md) ·
[MANAGED_STAGING.md](../deployment/MANAGED_STAGING.md) ·
[STAGING_COMPOSE.md](../deployment/STAGING_COMPOSE.md) ·
[07-bm25-projection.md](../architecture/07-bm25-projection.md)

```mermaid
flowchart LR
  subgraph phaseA [PhaseA_no_EC2]
    ingest["Laptop worker"]
    api["Laptop API"]
    pdb["Laptop ParadeDB"]
  end
  sb["Hosted Supabase"]
  ingest --> sb
  ingest --> pdb
  api --> sb
  api --> pdb
  subgraph phaseB [PhaseB_instance_up]
    edge["t3micro-edge"]
    awsPdb["EC2 ParadeDB"]
  end
  sb -->|"authorized_current reproject"| awsPdb
  edge --> sb
```

## Demo corpus

Source dump `docs/datasets/MovieSummaries/plot_summaries.txt` is ~42k lines.
**Do not ingest it whole.** Each slice is **one `.txt` file** (one upload).

| File | Source lines | Eligibility | Pipelines |
| --- | --- | --- | --- |
| `plot_summaries.graph-200.txt` | 1–200 | company-visible, mark `graph_eligible` after promote | Hybrid + Graph |
| `plot_summaries.hybrid-800.txt` | 201–1000 (800 plots) | leave `graph_eligible=false` | Hybrid only |

Together: 1000 Hybrid plots, 200 Graph plots. Graph indexes the whole
version, so the 800-line file must never be graph-eligible. Slice files:
[DEMO_SLICES.md](../datasets/MovieSummaries/DEMO_SLICES.md). Regenerate
slices with:

```powershell
uv run python scripts/ops/cut_plot_summary_demo_slices.py
```

Ingest the 800-line file first or either order. Approximate OpenAI cost for
both uploads is about **$0.10–$0.30** (`text-embedding-3-large` plus
`gpt-4o-mini` extract on 200 plots, gleaning 0).

## Phase A — laptop ingest and ask

### Prerequisites

- Copy [`.env.hosted-ingest.example`](../../.env.hosted-ingest.example) to
  gitignored `.env.compose`. Fill hosted `SUPABASE_URL`, `app_runtime` DSNs
  (`API_SUPABASE_DB_URL`, `WORKER_SUPABASE_DB_URL`), live `OPENAI_API_KEY`,
  and LangSmith key. `APP_ENV=local`. `MOCK_MODEL_MODE=false`.
  `LANGSMITH_TRACING=true`. **Do not** set
  `SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED=true`.
- Runtime DSNs must be **`app_runtime`**, never `postgres`.
- FastAPI still forbids HS256. If login fails, fix hosted asymmetric keys.
- Laptop RAM for ClamAV + parser + worker. That cost stays off AWS.
- Local ParadeDB is the BM25 engine. Hosted Postgres has no `pg_search`.
  Do not copy that volume to AWS later.

### Two terminals (required)

Idle polls stay quiet. Start **one** host worker and tee stdout to a log,
then filter that file in two windows:

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
uv run python scripts/ops/run_laptop_ingest_worker.py *>> logs\laptop-ingest-worker.log
```

```powershell
Get-Content -Wait logs\laptop-ingest-worker.log | Select-String '\[hybrid\]'
```

```powershell
Get-Content -Wait logs\laptop-ingest-worker.log | Select-String '\[graph\]'
```

Do not start a second worker, and do not use `docker compose logs worker`
(the Compose worker image cannot run the parser sandbox).

| Prefix | What must appear |
| --- | --- |
| `[hybrid]` | Both uploads: `scan` → `parse` → `embed_batch` → `bm25` → `hybrid_ready` |
| `[graph]` | **Only** the 200-line file: `lightrag_index` → `extract_batch` → `graph_ready` |

The 800-line file must **not** emit `[graph]` extract lines. Empty windows
after an upload fail the demo check. Messages are counts and reason codes
only (no plot text).

### LangSmith (required)

Open project `LANGSMITH_PROJECT` (default `smart-rag`). Filter
`ingestion.index` / `embedding.embed` for both files. The 200-line file must
also show parent `ingestion.graph` and child `model.lightrag_llm` extract
spans. Each successful extract span exposes input/cached/output/total token
counts and `estimated_cost_usd`; LangSmith can aggregate its wrapped OpenAI
child spans at trace level. Live `openai.embeddings` spans attach recognized
input/total-token and estimated-USD usage metadata so Hybrid trace totals are
also visible. USD values are standard-list-price estimates, not the canonical
provider invoice. Hide I/O stays forced. No plot text in traces.

Graph-200 may use the accepted local synthetic mapping override when its
processed vendor graph exceeds the production 200/200 entity/relation
enumeration limits. The durable LightRAG job must carry
`local_demo_mapping_override=true`, `content_class=synthetic`, and
`review_approved=true`; the worker ignores the override outside
`APP_ENV=local`. The fixed local ceilings are 2,000 entities and 1,800
relations (the canonical-passage extract measured 1,779 / 1,531). All
mapping coverage/support and model-call gates remain unchanged.

The original Graph-200 whole-version extract measured **87/95** persisted
chunk maps and **2,832/3,314 (85.46%)** coverage. Rebuilds must index each
current canonical Hybrid passage as its own LightRAG source. Do **not**
ingest `docs/datasets/MovieSummaries/plot_summaries.txt`. Do **not** alter
completed Hybrid-800/Graph-200 Hybrid indexes. If Graph Ready is still
`graph_pending` and `company_default__rebuild` already has **164**
`processed` canonical-passage sources, stop the looping worker and run
**one** mapping-only job (no vendor deletes, no re-extract):

```powershell
uv run python scripts/ops/rebuild_demo_graph_canonical_passages.py --map-only
```

That path requeues job `542628df-2c38-4b15-a180-893d7fd74998` with the
existing 164-source checkpoint, maps the isolated graph, then verifies
Graph Ready on the **active pointer workspace** (expected
`company_default__rebuild` after isolate switch). Leftover maps on retired
`company_default` are not part of the 164-count. It does not auto-requeue
and does not call `run_forever`. On success it prints Graph Ready plus
LangSmith token/USD totals. On failure it prints the first failed
invariant and stops.

A full rebuild without `--map-only` deletes leftover vendor IDs and
re-extracts. Refuse that when 164 isolated sources are already
`processed`. Do **not** use `scripts/ops/retry_demo_graph_mapping.py` for
this corpus: it looks up the whole-version vendor ID and un-quarantines
live `company_default`.

The 2026-08-20 attempt failed closed:
`failed_invariant=version_status:graph_pending`,
`job_last_error=vendor_status_failed`, workspace `quarantined`. LightRAG
aborted at extract 37/164 after an embedding health-check timeout (75s
limit, 131.3s actual). LangSmith project `smart-rag-demo-3` recorded one
`ingestion.graph` trace (179,216 tokens, estimated USD 0.04261959) and 40
successful `model.lightrag_llm` spans. Do not retry in a loop.

The operator-requested 2026-08-20 retry deleted leftover vendor sources,
then failed at the first isolated `ainsert` with
`PipelineNotInitializedError` for `company_default__rebuild:pipeline_status`.
`bind_workspace` now calls in-memory `initialize_pipeline_status` (no DDL)
before insert. After that fix, run **one** bounded rebuild when the operator
asks. Do not loop.

On 2026-08-20 the isolated extract (164 processed sources, 1,779/1,531
objects) reached **Graph Ready** with
`rebuild_demo_graph_canonical_passages.py --map-only`. The active pointer is
`company_default__rebuild`. Do not re-extract. Do not start EC2/Phase B
until the operator says the instance is up.

The long-term fix is in
[ADR-lightrag-async-embed-batched-sources.md](../adr/ADR-lightrag-async-embed-batched-sources.md):
canonical passage sources, `AsyncOpenAI` with a 20s provider timeout, batches
of eight, candidate isolation, 90% / 0.80 gates unchanged. Do **not** raise
the LightRAG watchdog. Do not start another live Graph-200 rebuild unless the
operator explicitly asks.

See
[ADR-canonical-passage-lightrag-sources.md](../adr/ADR-canonical-passage-lightrag-sources.md).

### Ingest order

1. Wire env (hosted `SUPABASE_URL` + `app_runtime` DSNs), then start
   laptop Compose **without** the distroless `worker` service. Publish
   ParadeDB/ClamAV/crawl-proxy with the Packet 8 overlay so the **host**
   worker can reach them and launch `smart-rag-parser-sandbox:local`:

   ```powershell
   uv run python scripts/ops/wire_hosted_ingest_env.py
   uv run python scripts/ops/wire_frontend_hosted_auth.py
   docker compose --env-file .env.compose --profile parser-build build parser-sandbox
   docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --build paradedb valkey-limits valkey-cache clamav crawl-proxy api
   uv run python scripts/ops/run_laptop_ingest_worker.py
   ```

   The host worker copies ``WORKER_SUPABASE_DB_URL`` onto ``LIGHTRAG_DB_URL``
   when that variable is unset, then ``SET ROLE app_lightrag``. Without that,
   hybrid ingest can reach `hybrid_ready` while the 200-line LightRAG job
   stays `pending` forever and LangSmith shows no `ingestion.graph` runs.
   Startup prints `lightrag_db_url_set=true` (never the DSN).

   Do not run `.\scripts\dev.ps1` for this demo (it starts local Docker
   Supabase). Filter logs from the host worker process, not `docker compose logs worker`.
2. Upload `plot_summaries.hybrid-800.txt` through the local UI. Leave
   `graph_eligible` false (upload default). Wait for `[hybrid]` through
   `hybrid_ready` (public status `graph_ineligible`).
3. Upload `plot_summaries.graph-200.txt`. After scan/promote sets
   `current_version_id`, mark eligibility **before** BM25 finalize:

   ```powershell
   $env:OPERATOR_SUPABASE_DB_URL = "<session URL that can SET ROLE postgres>"
   uv run python scripts/ops/mark_demo_graph_eligible.py <document_uuid>
   ```

   Do not point the API/worker DSN at `postgres`.
4. Confirm `[graph]` extract lines and LangSmith `ingestion.graph`.
5. Ask on the **laptop API** (`http://127.0.0.1:8000` or
   `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`). Hybrid uses local
   ParadeDB. Graph reads hosted tables. Do not wait on CloudFront.

## Phase B — when the instance is ready

Do **not** start worker/ClamAV/parser on `t3.micro`. Use the t3 overlay and
`--profile t3micro-edge` only. In-repo `SmartRagStagingDeploy` now matches
that command. **Do not** `aws ssm send-command` until the operator says the
host is up.

Fill EC2 ParadeDB from hosted Supabase only. RAM-safe one-shot:

1. Stop `t3micro-edge` (API/Caddy/proxies). Keep ParadeDB and Valkey up.
2. Reproject `authorized_current` with the worker image, no ingest stack:

   ```bash
   printf '%s' '{"rebuild_scope":"authorized_current"}' | docker compose \
     -f docker-compose.staging.yml -f docker-compose.t3micro.yml \
     --env-file /opt/smart-rag/.env --profile demo-reproject \
     run --rm -T bm25-reproject
   ```

3. Start `--profile t3micro-edge` again.

Do not publish ParadeDB `5432`. Do not point the laptop worker at AWS
ParadeDB. Do not copy a laptop dump. Do not enable LangSmith on the EC2 API
for ingest (there is no ingest worker there).

## Failure modes

| Symptom | Action |
| --- | --- |
| Empty `[hybrid]` / `[graph]` windows | Tracing/progress not on the laptop worker; restart worker with the hosted-ingest env |
| LangSmith has no `ingestion.*` trees | `LANGSMITH_TRACING` was false on the worker, or mock mode hid live gateway spans |
| `lightrag_llm_openai_not_configured` | Worker is stale. Stop it, update the live adapter, run `uv run python scripts/ops/reset_demo_graph_extract.py`, then start exactly one worker. |
| Graph Ready stays `graph_pending` after extract | Snapshot mismatch or coverage below 90%. Do not retry Hybrid mapping. Do not lower the gate. |
| Rebuild reports `graph_source_snapshot_mismatch` | A canonical passage split or drifted. Stop. Do not lower the 90% gate. |
| Isolated rebuild fails with `PipelineNotInitializedError` / `pipeline_status_uninitialized` | Candidate workspace lacked in-memory `pipeline_status`. Stop. Do not raise the watchdog. Update the adapter, then run **one** rebuild. |
| Rebuild reports `version_status:graph_pending` with `vendor_status_failed` | Prior 164-source `ainsert` was force-killed (75s health-check vs 131.3s embed). Code now batches eight sources with `AsyncOpenAI`. Stop. Do not auto-requeue. Do not raise the watchdog. Operator must request any new live rebuild. |
| Graph extract on the 800-line file | File was marked graph-eligible; do not upload a combined 1000-line eligible file |
| HS256 login failure | Fix hosted JWKS; do not enable HS256 in FastAPI |
| `postgres` DSN on API/worker | Switch to `app_runtime` |
| ParadeDB dump copied to EC2 | Discard; reproject from hosted Supabase |

## Verification

```powershell
uv run pytest tests/unit/test_ingest_progress.py tests/unit/test_ingest_trace.py tests/unit/test_demo_plot_slices.py tests/contract/test_demo_plot_slices.py tests/contract/test_staging_deploy_t3micro.py tests/contract/test_demo_reproject_profile.py tests/unit/test_langsmith_tracing.py tests/unit/test_openai_lightrag.py tests/unit/test_graph_source_batches.py tests/unit/test_graph_index_isolate.py tests/unit/test_embedding_service.py -q
```

Live LangSmith trees and TTY prefixes after a real upload remain **unverified**
until Phase A is run with operator keys.

## Rollback

Set `LANGSMITH_TRACING=false` and `MOCK_MODEL_MODE=true`, restart the laptop
worker, and stop using hosted `SUPABASE_URL` interpolation (Compose falls
back to local GoTrue). Phase B: do not send SSM; leave the instance untouched.
