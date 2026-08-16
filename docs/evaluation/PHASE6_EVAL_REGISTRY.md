---
title: Phase 6 evaluation registry
owner: engineering-lead
status: draft
last-reviewed: 2026-08-16
audience: engineering, reviewers
---

# Phase 6 evaluation registry

Packet 7 maps every listed evaluation category to **existing** Phase 4/5/6
tests and docs. It does not recreate datasets, retune Phase 4 thresholds, or
open the launch holdout. QT-EVAL-009 Combined +10pp on live mapping remains
`unverified`.

Related: [DATASET_SPEC.md](./DATASET_SPEC.md) ·
[PHASE4_HOLDOUT.md](./PHASE4_HOLDOUT.md) ·
[PHASE4_FREEZE.md](./PHASE4_FREEZE.md) ·
[MEMORY_DELETION.md](../agent/MEMORY_DELETION.md) ·
[QUALITY_TARGETS.md](../QUALITY_TARGETS.md)

## Invariants

- `HoldoutAccess.denied()` in CI and nightly. No holdout labels for tuning.
- Online eval mock-mode default is true. Sample ≤ 20 cases. Cost ≤ USD 2.00.
  Unlimited real OpenAI jobs fail closed.
- Versioned evaluation is required before router/prompt/profile/normalizer/
  chunking/threshold release. Few-shots may use only approved redacted
  profile failures that stay disjoint from holdout.
- Curation: weekly during the pilot and first eight production weeks, then
  monthly. Post-launch regression sets are not the immutable holdout.

## Category map

Canonical table: `packages/core/src/smart_rag_core/evaluation/phase6_registry.py`.
CI: `uv run python scripts/ci/check_phase6_eval_registry.py` (unit tier).

| Category | Command owner | Status |
| --- | --- | --- |
| Chunking/cleaning | `tests/unit/test_chunking_service.py`, `test_chunking_dedup.py` | mapped |
| Query profile fields | `test_query_profile.py`, `test_phase6_querytype_map.py` | mapped |
| Retrieval | Hybrid retrieval/fusion/rerank unit + contract | mapped |
| Ablations | Combined fusion vs naive union; Hybrid fusion | mapped |
| Citation/faithfulness | Answer verifier + structured table | mapped |
| Injection | Parser governance, profile, FastAPI JSON escape, BM25 syntax | mapped |
| Tools | Optional-tools mapping vs discovery | mapped |
| Malware/SSRF | ClamAV, crawl proxy/policy, parser sandbox | mapped |
| Historical relationship → Hybrid + `temporal_graph_limitation` | Routing matrix + graph retriever | mapped |
| Whole-document coverage 1.0 | Hybrid coverage + routing | mapped |
| Negation | Routing matrix | mapped |
| Media limitation | Routing + coverage | mapped |
| ACL-blindness | Routing, coverage, ranked-id leak fixture | mapped |
| Cache leak after delete/restrict | Retrieval cache + recheck | mapped |
| Reaper 7/30-day + one-paid-run | `test_query_memory_reaper.py` | mapped |
| SSE handshake / unknown events | SSE protocol/resume/heartbeat | mapped |
| Holdout isolation | Phase 4 freeze/materialize | mapped |
| Bounded online eval | `test_phase6_eval_registry.py` | mapped |
| QT-EVAL-009 Combined +10pp live | Synthetic fusion fixture only | **unverified** |
| Rewrite/correction/mapping/idempotency | Correction, admit, graph mapping | mapped |
| Conversation deletion | HTTP 204/404 + lingering-ID search | mapped |
| LangSmith redaction + 24h retry | Tracing unit + reaper contract | mapped |
| Governance external flows | External processing + tracing | mapped |

Frontend XSS encoding of entity/relation/crawl content is packet 8 UI. This
registry covers API JSON escaping and parser/HTML injection.

## Nightly

`.github/workflows/nightly.yml` already runs the unit job, which executes
`scripts/ci/check_phase6_eval_registry.py` via `scripts/check.py --tier unit`.
Live retrieval evals and unbounded OpenAI remain future nightly work.

## Verification

```text
uv run python scripts/ci/check_phase6_eval_registry.py
uv run python -m pytest tests/unit/test_phase6_eval_registry.py -q
```
