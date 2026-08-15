---
title: Phase 5 GraphRAG evidence
owner: engineering-lead
status: pending
last-reviewed: 2026-08-15
audience: engineering, reviewers
phase: 5
---

# Phase 5 — GraphRAG evidence

Canonical packet evidence and exit record for
[Phase 5](../../.cursor/plans/hybrid-graph-rag/05-phase-graphrag.md).
Packet 1 creates this file; later packets append. Phase status remains
`pending`. Holdout stays sealed. Packets 2–8 are not started.

Related: [LIGHTRAG_CONTRACT.md](../graph/LIGHTRAG_CONTRACT.md) ·
[ADR-lightrag-identical-content-collapse.md](../adr/ADR-lightrag-identical-content-collapse.md) ·
[TOOL_VERSIONS.md](./TOOL_VERSIONS.md) ·
[CONFIGURATION.md](./CONFIGURATION.md) ·
[ADR index](../adr/README.md) ·
[docs index](../README.md)

## Prerequisites

| Prerequisite | Evidence |
| --- | --- |
| Phase 1 complete/accepted | [phase-01-foundation-evidence.md](./phase-01-foundation-evidence.md) status `accepted` |
| Phase 2 complete/accepted | [phase-02-identity-data-evidence.md](./phase-02-identity-data-evidence.md) status `accepted` |
| Phase 3 complete/accepted | [phase-03-ingestion-evidence.md](./phase-03-ingestion-evidence.md) status `accepted` |
| Phase 4 engineering-close | [ADR-phase4-engineering-close.md](../adr/ADR-phase4-engineering-close.md) continues toward GraphRAG; holdout sealed |
| User mandate | Implement Phase 5 / continue through GraphRAG (Cursor chat 2026-08-15) |

## Packet 1 — immutable LightRAG pin and complete contract qualification

### Quoted requirement

> Pin and contract-test the exact LightRAG version, storage/schema behavior,
> structured identifier/source semantics, and precomputed-keyword bypass.

### Acceptance checks restated

- Exact artifact/hash/source and required public APIs qualify against real
  PostgreSQL; PGTable needs no AGE.
- Schema/bootstrap, workspace, pool/finalization, ID/source/duplicate,
  callback, structured query, status, cancellation, deletion, and bounds tests
  pass without parsing prose or relying on undocumented fields.
- Both keyword lists produce zero keyword-extraction and answer-generation
  calls; remaining calls pass through the shared gateway.
- Identical-content sources remain independently attributable/deletable, or
  GraphRAG is disabled pending an approved disable ADR.

### Negative tests restated

Hash/version mismatch, missing class/API, hidden callback, runtime-prose
parser, source-token ambiguity/truncation, duplicate-source collapse, schema
warning/drift, unbounded provider retry, unsupported deletion result, or
main-only behavior fails qualification.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `packages/core/pyproject.toml` | Direct pins `lightrag-hku==1.5.6`, `asyncpg==0.31.0`, `pgvector==0.5.0` |
| `uv.lock` | Wheel SHA-256 `81b8aa8b09c11e446f94b53dbbef8d6becd900a7a44685fca95ff59cf5c8e457`; sdist `1c5afb96db5cd9f0b13b7d8d93ce1daf5a51bf7e2f74fe5ce4fe3eb9be03e77f` |
| `.venv/Lib/site-packages/lightrag/` | Installed 1.5.6 source: `aquery_data`, enqueue content-hash dedup, `ClientManager`, `POSTGRES_WORKSPACE` override, keyword bypass |
| `packages/core/src/smart_rag_core/retrieval/graph.py` | Protocols and pin constants; no `lightrag` import |
| `packages/core/src/smart_rag_core/retrieval/lightrag_pin.py` | Lock hash + required class verification |
| `packages/core/src/smart_rag_core/retrieval/lightrag_callbacks.py` | Counted gateway callbacks |
| `packages/core/src/smart_rag_core/retrieval/lightrag_structured.py` | `aquery_data` Pydantic models |
| `packages/core/src/smart_rag_core/retrieval/lightrag_qualification.py` | Disposable-schema harness |
| `tests/fixtures/lightrag/aquery_data_success_envelope.json` | Redacted success field names from the pin docstring |
| `packages/core/src/smart_rag_core/ingestion/embeddings/policy.py` | 1024-dim embedding pin |

### Primary documentation sources (2026-08-15)

- PyPI 1.5.6: <https://pypi.org/project/lightrag-hku/1.5.6/>
- GitHub commit `b33c6b0812cddf39206e48a9810112e51f025274`: <https://github.com/HKUDS/LightRAG/tree/b33c6b0812cddf39206e48a9810112e51f025274>
- ProgramingWithCore.md: <https://github.com/HKUDS/LightRAG/blob/b33c6b0812cddf39206e48a9810112e51f025274/docs/ProgramingWithCore.md>
- Installed `lightrag/lightrag.py` `aquery_data` docstring (success field names)
- Installed `lightrag/pipeline.py` content-hash / filename duplicate records
- Installed `lightrag/kg/postgres_impl.py` `ClientManager` / `POSTGRES_*`
- Installed `lightrag/kg/pgtable_impl.py` AGE-free DDL

### Files changed (Packet 1)

- `packages/core/src/smart_rag_core/retrieval/graph.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_pin.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_callbacks.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_structured.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_qualification.py`
- `packages/core/src/smart_rag_core/retrieval/__init__.py`
- `packages/core/src/smart_rag_core/gateways/model.py`
- `packages/core/src/smart_rag_core/gateways/__init__.py`
- `tests/unit/test_lightrag_pin.py`
- `tests/contract/test_lightrag_contract.py`
- `tests/fixtures/lightrag/aquery_data_success_envelope.json`
- `docs/graph/LIGHTRAG_CONTRACT.md`
- `docs/development/phase-05-graphrag-evidence.md`
- `docs/development/TOOL_VERSIONS.md`
- `docs/development/CONFIGURATION.md`
- `docs/README.md`
- `docs/adr/README.md`
- `docs/adr/ADR-lightrag-identical-content-collapse.md`
- `docs/development/phase-04-hybrid-rag-evidence.md` (MD012 trailing blank so the docs tier can run)

`packages/core/pyproject.toml` and `uv.lock` already contained the 1.5.6 pin
before this packet's remaining implementation.

### Commands and results

DSN passwords are not logged. Packet 1 Python files type-check clean under
Pyright strict. The full-repo types tier remains red from pre-existing errors
outside this packet.

| Command | Exit |
| --- | --- |
| `uv run python scripts/check.py --tier format` | 0 |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier types` | 1 (612 pre-existing errors; Packet 1 files 0) |
| `uv run python -m pytest tests/unit/test_lightrag_pin.py tests/unit/test_phase3_graph_scope_guard.py tests/unit/test_package_imports.py -q` | 0 |
| `uv run python -m pytest tests/contract/test_lightrag_contract.py -q` | 0 (5 passed against local Supabase Postgres) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

Scoped Packet 1 Pyright (graph, pin, callbacks, structured, qualification,
retrieval `__init__`, gateways, pin/contract tests): 0 errors.

### Negative tests

| Fixture | Result |
| --- | --- |
| Wheel/sdist hash mismatch | `LightRagPinError` |
| AGE class selected | pin compare fails; `PGGraphStorage` is not selected |
| Rendered context parser | `ProseContextRejectedError` |
| Empty / blank / duplicate / 200-cap source IDs | `SourceIdContractError` |
| Unsupported deletion status | `LightRagQualificationError` |
| `aquery_data` failure / `no_results` envelope | `LightRagQueryFailure` |
| Runtime `pipmaster.install` | test monkeypatch raises |
| Apps/backend/worker/agents `lightrag` import | static AST scan |

### Identical-content hard gate

**Failed.** Live `test_ids_sources_duplicates_and_identical_content_gate`
against local Supabase: `apipeline_enqueue_documents` collapsed identical
synthetic text under `duplicate_kind=content_hash` even with distinct IDs and
unique opaque basenames. The second canonical ID had no `LIGHTRAG_DOC_STATUS`
row (`identical_content_status_missing`). GraphRAG is **disabled** by
[ADR-lightrag-identical-content-collapse.md](../adr/ADR-lightrag-identical-content-collapse.md).
The gate was not weakened.

### Deviations

- Qualification sets `cosine_better_than_threshold=-1.0` because mock
  hash vectors have no semantic neighborhood. Not a production Graph setting.
- Harness wraps `pgvector.asyncpg.register_vector` to try `extensions` after
  `public` (local Supabase type location).
- Vendor `created_at` on `aquery_data` entities/relations is an int unix
  timestamp on this pin; models accept `str | int | float`.
- Cancel qualification uses an `asyncio.Event` gate rather than a long sleep
  so vendor LLM workers can be released before `finalize_storages`.
- Packet 2 private-schema migrations are not in this packet.

### Unverified

- `pip-audit` / advisory scan of `lightrag-hku==1.5.6` beyond lock hashes.
- Production Graph deployable settings (intentionally absent).
- Full-repo Pyright (612 pre-existing errors outside Packet 1).

### Rollback

- Remove Packet 1 adapter/qualification modules and tests.
- Revert documentation index links and the disable ADR.
- Do not drop application schemas; Packet 1 uses disposable test schemas only.
- Keep `lightrag-hku==1.5.6` in the lock only if a later packet still needs it.

### Packet 2 handoff

**Packet 2 must not start.** Packet 1 recorded an honest GraphRAG disable:
identical-content independence failed on pin 1.5.6. Hybrid RAG remains
available. Holdout remains sealed. Do not mark Phase 5 complete.
