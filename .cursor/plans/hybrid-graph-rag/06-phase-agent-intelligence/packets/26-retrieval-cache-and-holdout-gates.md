---
phase: 6
packet: 26
status: complete
title: "Wire ACL-safe retrieval caching and record Combined plus holdout gates."
requirement_ids: [P06-26]
---

# Packet 26 — Wire ACL-safe retrieval caching and record Combined plus holdout gates.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-hybrid-retrieval`](../../../../../.cursor/skills/implement-hybrid-retrieval/SKILL.md)
and [`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

## Preconditions

- `RetrievalCacheStore` and `tests/contract/test_retrieval_cache.py` exist.
- Combined fusion is already wired. Private PDF stays `graph_ineligible`.
- Holdout remains sealed unless a named operator later runs Packet 18.

## Allowed outputs

- Production retrieve-path injection of `RetrievalCacheStore` into
  `ProcessHybridRetriever` / `HybridRetriever`
- Cache hit recheck before evidence assembly
- Contract/unit tests for identical-query reuse and ACL-downgrade miss
- Docs recording Combined +10pp and holdout as still operator/live gates
  when those datasets are unavailable

## Forbidden outputs

- Caching raw passage text, answers, BM25 snippets, or authorization
  decisions.
- Enabling Graph on the private PDF.
- Opening holdout from the evaluation workspace.
- Claiming Combined +10pp without the disjoint live set.

## Ordered actions

1. Inject the existing cache store through backend query bindings.
2. Key by principal/ACL-scope hash, visibility generation, profile/index
   versions, and normalized query. Store IDs/ranks only.
3. Recheck current-version/deletion/ACL on every hit.
4. Treat cache outage as a miss.
5. Keep Combined verification on a separate graph-eligible set. Record
   `qt_eval_009_status=unverified` until that live run exists.
6. Do not run `eval_pdf_holdout.py` in this packet.

## Acceptance checks

- Second identical query can hit cache. ACL downgrade yields zero stale
  evidence.
- Cache outage does not fail the query.
- Holdout CLI still fail-closed.

## Negative tests

- Deleted or unauthorized IDs in a cache payload are dropped by recheck.
- Graph-ineligible private PDF is unchanged.

## Stop routes

- Stop rather than skip the recheck.
- Do not open holdout to “complete” the overlay.

## Required evidence

- Append cache tests, Combined unverified-or-proven status, and
  `holdout_opened=false`. Handoff back to Packet 10.
