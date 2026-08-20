---
title: LangSmith tracing for model and embedding calls
owner: engineering-lead
status: draft
last-reviewed: 2026-08-20
audience: engineering, operators, security
---

# LangSmith tracing for model and embedding calls

Every application OpenAI call goes through `ModelGateway`, `EmbeddingGateway`,
`traced_embeddings_create`, or `traced_embeddings_create_async`. Those
boundaries emit a LangSmith span when `LANGSMITH_TRACING=true`. Tracing is
**off by default**, including mock-model mode. This is gateway-level tracing,
not the Phase 6 production query-graph feedback loop.

Related: [CONFIGURATION.md](./CONFIGURATION.md) ·
[LANGGRAPH_STUDIO.md](./LANGGRAPH_STUDIO.md) ·
[demo-local-ingest-aws-ask.md](../runbooks/demo-local-ingest-aws-ask.md) ·
[SUBPROCESSOR_GOVERNANCE.md](../security/SUBPROCESSOR_GOVERNANCE.md) ·
[OPENAI_DATA_GOVERNANCE.md](../security/OPENAI_DATA_GOVERNANCE.md) ·
[docs index](../README.md)

## Data that is exported

Exported fields are limited to:

- Stable run names (`model.generate`, `model.query_profile`, `model.rerank`,
  `embedding.embed`, `openai.responses.rerank`, `openai.embeddings`)
- Operation, model id, prompt version, prompt SHA-256, candidate/excerpt
  counts, character counts
- SHA-256 prefixes of query/prompt/excerpt/input text (16 hex chars)
- Token usage, provider request id, mode, ranking count
- LightRAG extract `input_tokens`, `cached_input_tokens`, `output_tokens`,
  `total_tokens`, and `estimated_cost_usd`. The estimate uses the pinned
  standard API list price and is not a replacement for the OpenAI invoice.
- Live `openai.embeddings` spans attach LangSmith-recognized
  `usage_metadata` with input/total tokens and the pinned estimated USD cost.
  Usage metadata remains visible and aggregatable while raw span I/O stays
  hidden.
- Correlation ids (`request_id`, `run_id`, `job_id`) when bound
- Embedding `timeout_seconds` (numeric bound only; never input text)
- Ingest parent names (`ingestion.scan`, `ingestion.parse`,
  `ingestion.index`, `ingestion.graph`) with hashed document/version ids

Never exported: raw prompts, user queries, canonical excerpts, embedding
vectors, API keys, JWTs, emails, signed URLs, file bytes, or plot text.

`LANGSMITH_HIDE_INPUTS` and `LANGSMITH_HIDE_OUTPUTS` are forced `true` at
startup so `wrap_openai` child spans cannot send Responses `input` /
`instructions` bodies. Application `process_inputs` / `process_outputs`
hooks are the first control; hide flags are the second.

## Runtime flow

```mermaid
flowchart LR
  settings["SharedSettings"] --> configure["apply_langsmith_sdk_flags"]
  configure --> hide["HideInputsAndOutputs"]
  gateway["ModelOrEmbeddingGateway"] --> span["traceableRedactedSpan"]
  span --> openaiCall["traced_openai_client"]
  openaiCall --> openai["OpenAI"]
  span --> langsmith["LangSmith"]
  hide --> langsmith
```

```mermaid
sequenceDiagram
  participant Caller
  participant Gateway
  participant LangSmith
  participant OpenAI
  Caller->>Gateway: generate or embed
  Gateway->>LangSmith: redacted span start
  Gateway->>OpenAI: Responses or embeddings
  OpenAI-->>Gateway: usage plus payload
  Gateway->>LangSmith: redacted span end
  Gateway-->>Caller: typed response
```

## Enablement

1. Set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in the ignored env
   file. Startup fails if tracing is true without a key.
2. Optional: `LANGSMITH_PROJECT` (default `smart-rag`) and
   `LANGSMITH_ENDPOINT` for a non-default API URL.
3. Local default is still `MOCK_MODEL_MODE=true` (zero OpenAI cost). The
   operator may set `MOCK_MODEL_MODE=false` in gitignored `.env` and
   `.env.compose` to use a live OpenAI key **without org-matrix verification**.
   That is a local unsigned waiver (`APP_ENV=local` only). Compose interpolates
   `${MOCK_MODEL_MODE:-true}` and passes `OPENAI_API_KEY` into api/worker.
4. Org rows in
   [SUBPROCESSOR_GOVERNANCE.md](../security/SUBPROCESSOR_GOVERNANCE.md) and
   [OPENAI_DATA_GOVERNANCE.md](../security/OPENAI_DATA_GOVERNANCE.md) stay
   `unverified` until a console/DPA review. Do not set
   `SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED=true` to fake that review.
   Staging/production still require it. Do not ingest real company files into
   a hosted environment on this waiver.
5. Laptop **ingest** demo (Phase A): set `LANGSMITH_TRACING=true` on the
   **worker** (not the EC2 API). After a plot-slice upload, open project
   `LANGSMITH_PROJECT` and filter `ingestion.index` / `embedding.embed`.
   The 200-line graph file must also show `ingestion.graph` and
   `model.lightrag_llm`. After a canonical-passage Graph-200 rebuild, run
   `uv run python scripts/ops/report_demo_langsmith_usage.py` (or use the
   totals printed by `rebuild_demo_graph_canonical_passages.py`). The
   2026-08-20 bounded attempt recorded one `ingestion.graph` trace
   (179,216 tokens, estimated USD 0.04261959) with 40 successful
   `model.lightrag_llm` spans; Graph Ready did not flip
   (`vendor_status_failed`). Procedure:
   [demo-local-ingest-aws-ask.md](../runbooks/demo-local-ingest-aws-ask.md).

## Failure modes

| Condition | Behavior |
| --- | --- |
| Tracing off (default) | No LangSmith export. Model calls still go through the gateway. |
| Tracing on, missing key | Settings validation fails at process start. |
| LangSmith unreachable | SDK records a local tracing error; the OpenAI call is not retried for tracing. **unverified** live network failure until a key is used. |
| `wrap_openai` child span | I/O hidden by forced env flags; parent span has hashes/counts only. |
| Direct `OpenAI()` in packages/apps/scripts | Unit AST test fails. Use `traced_openai_client`. |

`block_openai_network` still denies only `api.openai.com`. It does not block
`api.smith.langchain.com`.

## Bounded query-agent evaluation

`scripts/eval_query_agent_langsmith.py` syncs a versioned **development-only**
LangSmith dataset and runs `Client.evaluate` against the admitted production
query graph in-process. It is an evaluation tool. It does not retune Hybrid,
open holdout, or claim Combined +10pp.

Parent run name: `query.agent.eval`. Exported fields are case id, hashed
user/conversation ids, routes, versions, counts, latency, and cost.
Never exported: raw query, answer, passages, prompts, email, JWT, DSN, or
keys. Dataset example `outputs` may retain synthetic query/answer because
`redaction_class=synthetic`.

```mermaid
sequenceDiagram
  participant CLI as eval_query_agent_langsmith
  participant LS as LangSmith
  participant Graph as AdmittedQueryGraph
  CLI->>CLI: select development cases
  CLI->>LS: sync versioned dataset
  loop each case max_concurrency 1
    CLI->>Graph: admit invoke persist settle
    Graph->>LS: query.agent.eval parent
  end
  CLI->>LS: deterministic evaluators
  CLI->>CLI: local JSON summary
```

Hard bounds: development split only, `HoldoutAccess.denied()`, ≤20 cases,
`max_concurrency=1`, one repetition, max USD 2.00, at most one judge call
per case, mock default. Different `--limit` values produce different
dataset names (selected-set manifest hash). Remote metadata drift fails
closed.

```powershell
uv run python scripts/eval_query_agent_langsmith.py --dry-run --limit 3
uv run python -m pytest tests/unit/test_agent_eval.py tests/unit/test_langsmith_agent_runner.py tests/unit/test_query_agent_eval_trace.py -q
```

Live mock/live-agent runs need `LANGSMITH_TRACING=true`, a key, a project,
local Supabase, an active synthetic member, and ingested synthetic corpus.
`--llm-judge` requires `--live-agent`. ParadeDB absence fails unless
`--allow-bm25-degraded`.

## Verification

```powershell
uv run pytest tests/unit/test_langsmith_tracing.py tests/unit/test_ingest_trace.py tests/unit/test_query_agent_eval_trace.py tests/unit/test_openai_rerank.py tests/unit/test_openai_lightrag.py tests/unit/test_model_gateway.py tests/unit/test_settings.py -q
uv run ruff check packages/core/src/smart_rag_core/observability packages/core/src/smart_rag_core/gateways/openai_rerank.py packages/core/src/smart_rag_core/gateways/openai_lightrag.py packages/core/src/smart_rag_core/gateways/model.py packages/core/src/smart_rag_core/gateways/embedding.py packages/core/src/smart_rag_core/settings/base.py tests/unit/test_langsmith_tracing.py tests/unit/test_ingest_trace.py tests/unit/test_openai_lightrag.py
```


Live LangSmith project visibility is **unverified** until
`LANGSMITH_TRACING=true` is used with a real key.

## Rollback

Set `LANGSMITH_TRACING=false` (the default) and restart API/worker. No
database migration is involved.
