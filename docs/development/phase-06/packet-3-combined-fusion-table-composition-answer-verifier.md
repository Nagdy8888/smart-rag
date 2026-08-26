# Packet 3 — Combined fusion, table composition, answer, verifier

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

## Quoted requirement

> Implement resolved-path Combined fusion and ablation, deterministic table
> composition, canonical answer evidence, inference-link citations, and
> layered verification.

## Acceptance checks restated

- Resolved paths contribute only authorized current canonical passages;
  table outputs identify exact deterministic source cells/ranges; graph
  prose/BM25 snippets never reach answer evidence.
- Formulas, `0.25` hop penalty, `1.20` edge-support multiplier cap, RRF
  denominator `60`, graph weight `0.50`, agreement cap `1.10`, and 40%
  graph-discovered-only cap are exact, deterministic, and fixture-tested.
- Fusion beats naive union on answer/path success and citation
  completeness within gates **or is removed** in favor of documented union.
- On disjoint relationship/multi-hop evaluation, Combined answer path
  improves success by ≥10 percentage points over Hybrid alone while
  preserving citation correctness/completeness, faithfulness, cost
  ceilings; first token ≤10s and completion ≤35s p95 **if measurable**.
- One answer call and at most one small verifier call covering ≤6 material
  links; unsupported links omitted/refused, not softened.

## Inspected schema / APIs

| Item | Found |
| --- | --- |
| Latest migration | `20260816180000_query_memory_routing_v1.sql` (no Packet 3 SQL) |
| `app.citations.provenance` | jsonb already present; expand-only payload, no new column |
| `GRAPH_SURVIVAL_FALLBACK_THRESHOLD` | `0.50` in `retrieval/graph.py` |
| `FINAL_EVIDENCE_MAX` / `DOCUMENT_QUOTA` | `12` / `2` from Phase 4 Hybrid |
| `RRF_K` | `60` |
| Usage kinds `answer` / `verifier` | already in `query_admission.ceilings` |
| Pinned OpenAI | `openai==2.26.0`; Responses `json_schema`, `store=False`, `max_retries=0` |
| Prompt hashes | LF-normalized SHA-256 of `answer_v1.md` / `verifier_v1.md` |

## Fusion vs union decision

Selected algorithm: **`resolved_path_fusion`**.

Development/qualification fixtures (synthetic authorized IDs, holdout
sealed):

| Case | Hybrid success | Union success | Fusion success |
| --- | --- | --- | --- |
| refund-period | true | true | true |
| project-atlas-product | false | false | true |
| atlas-to-supplier-multihop | false | false | true |

| Metric | Value |
| --- | --- |
| Hybrid success rate | `1/3` |
| Union success rate | `1/3` |
| Fusion success rate | `1` |
| Fusion citation completeness | `1` |
| Union citation completeness | `1/3` |
| Combined minus Hybrid (synthetic pp) | `66.67` |
| `fusion_beats_union` | true |
| Live QT-EVAL-009 +10pp | **unverified** |
| First token ≤10s / completion ≤35s p95 | **unverified** |

Fusion beat naive union because gold relationship/multi-hop chunks sat at
Hybrid ranks 15–20 (outside the frozen 12-unit cap) and resolved graph
support promoted them via Combined RRF plus the `1.10` agreement
multiplier. Union kept Hybrid-first order and dropped those gold IDs.
This synthetic gain is **not** QT-EVAL-009. It does not use CoverageSlice
floors, Phase 4 identity-rerank percents, or holdout labels.

Config hash is `6fadc2a7b98e47cc00c09590d8a6d196e2554fe3eb971052d058e08d0128164f`
(`fusion_config_hash(resolved_path_fusion)`). Tests assert it matches
`SELECTED_FUSION_ALGORITHM`.

## Representative contracts

| Contract | Result |
| --- | --- |
| Refund-period fact | Hybrid evidence only |
| Project Atlas product relationships | Combined with resolved canonical support |
| Atlas-to-Supplier multi-hop | Combined inference citations; conclusion need not be verbatim |
| LightRAG timeout | `requested_route=combined`, `effective_route=hybrid`, `graph_timeout` |
| Numeric comparison | Deterministic table ranges; prose math fails closed |
| Unsupported link | Removed/refused, chain dropped |

## Negative tests

Unmapped/stale/deleted/unauthorized path, missing edge support, native
prose, BM25 snippet, graph-only answer, hidden keyword call, hidden
LightRAG `answer_generate`, model fusion weight, agreement multiplier
above `1.10`, graph-only share above 40%, table arithmetic from prose,
seventh verifier link, verifier loop, second answer generation, unsupported
chain, conclusion-verbatim not required, LightRAG timeout mislabeled
Combined, and holdout-tuned configuration all fail closed.

## Graph wiring

`apply_correction` → `fuse_evidence` → `compose_tables` →
`generate_answer` → `verify_answer` → END.

Unbound Hybrid `INV-SR-1001` invoke: empty evidence, one refused/partial
answer payload, `answer_call_count=0`, `verifier_call_count=0`,
`keyword_extract_count=0`, `catalog_llm_call_count=0`. Compile constructs
no sockets or OpenAI.

## Commands and results

Recorded on Windows PowerShell. DSN passwords are not logged.

| Command | Exit |
| --- | --- |
| `uv run ruff format` on changed Python paths | 0 |
| `uv run ruff check` on changed Python paths | 0 |
| `uv run python -m pyright` on changed Python paths | 0 errors |
| `uv run python -m pytest tests/unit/test_combined_fusion.py tests/unit/test_answer_verifier.py tests/contract/test_langgraph_config.py tests/unit/test_package_imports.py tests/contract/test_import_boundaries.py` | 0; **48 passed**, 5 warnings (SwigPy worker import), 0 failed |
| `uv run python scripts/ci/check_migrations.py` | 0 (48 reviewed files; no Packet 3 SQL) |

## Deviations

- No new SQL migration. Fusion scores and inference flags live in existing
  `app.citations.provenance` jsonb.
- Live Combined vs Hybrid +10pp on labeled relationship/multi-hop cases
  with live mapping/extraction was **not** measured. Residual gate for
  phase exit.
- Latency p95 (first token ≤10s, completion ≤35s) was **not** measured.
- Naive union was **not** shipped; resolved-path fusion beat union on the
  measurable development fixtures above.
- SSE, optional tool catalog, and UI are out of scope (packets 4–8).
- Persist-to-Postgres citation insert is implemented but not live-database
  tested in this packet.

## Rollback

Forward-fix: skip `fuse_evidence` / answer / verifier nodes and stop
writing fusion keys into `app.citations.provenance`. No DROP. No new
migration to revert.

## Packet 4 handoff

- Optional tool registry and progressive disclosure. Core Hybrid,
  LightRAG, StructuredTable, citation, answer, and verifier tools stay
  **outside** the catalog.
- Packet 3 already binds those core tools directly on the query graph.
- Discovery remains at most one round and three optional manifests.
- Unselected optional schemas must never enter prompts.
- SSE, reconnect, heartbeats, and UI remain later packets.
- Keep `keyword_extract_count=0` and `catalog_llm_call_count=0` on the
  core path. A catalog LLM is only for optional discovery after
  role/feature filtering.
- Auto admit should still reserve `composite` so Combined and
  Hybrid→Combined escalation fit the envelope.

## Unverified (packet 3)

- QT-EVAL-009 live Combined vs Hybrid +10pp on labeled
  relationship/multi-hop cases with live mapping/extraction.
- Combined first-token ≤10s and completion ≤35s p95.
- Live OpenAI answer/verifier Responses calls (mock mode only).
- Live `app.citations` insert against Postgres.
- Hosted Auth throttling (carried from packet 1).
