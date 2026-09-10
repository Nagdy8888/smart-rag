# P06-26 — Retrieval cache and holdout gates (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

`RetrievalCacheStore` is injected into `HybridRetriever` / `ProcessHybridRetriever`
from `app_state.valkey_cache_client`. Cache stores IDs/ranks only after a
successful fused ranking with fallback `NONE`. Hits recheck current
version/deletion/ACL before evidence assembly. Partial survivors invalidate.
Outage is a miss. Private PDF stays `graph_ineligible`. `eval_pdf_holdout.py`
was not run.

Requirement: Combined +10pp and holdout remain operator/live gates.

Files:

- Additive `retrieval_cache` on Hybrid retrieve and process bindings
- [`tests/unit/test_hybrid_retrieval_cache.py`](../../../tests/unit/test_hybrid_retrieval_cache.py)
- [`tests/unit/test_query_graph_runtime.py`](../../../tests/unit/test_query_graph_runtime.py) (`test_process_bindings_inject_retrieval_cache_from_app_state`)
- [`docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md`](../../retrieval/HYBRID_RETRIEVAL_CONTRACT.md)
- [`docs/evaluation/PDF_HYBRID_EVALUATION.md`](../../evaluation/PDF_HYBRID_EVALUATION.md)

Verification:

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_hybrid_retrieval_cache.py tests/unit/test_query_graph_runtime.py::test_process_bindings_inject_retrieval_cache_from_app_state -q` | 0 |
| `qt_eval_009_status()` | `unverified` |
| `holdout_opened` | `false` |

Proven: identical-query hit can skip embed; ACL downgrade / partial recheck
misses; Valkey timeout is a miss; process bindings inject the cache from app
state.

Unverified: Combined +10pp on a disjoint graph-eligible live set. Holdout
execution stays Packet 18 / named operator.

Rollback: omit `retrieval_cache` from process bindings; cache remains unused.

Handoff: overlay P06-19–P06-26 is evidenced. Resume historical **Packet 10**
(typed knowledge-scope routing). Do not freeze `hybrid_long_document_v1`
or open holdout from this overlay.
