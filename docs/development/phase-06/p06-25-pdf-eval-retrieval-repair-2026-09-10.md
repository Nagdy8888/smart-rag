# P06-25 — PDF eval retrieval repair (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Rerank schema-invalid JSON maps to `OpenAIRerankError("rerank_schema_invalid")`
and RRF fallback. `max_retries=0` is unchanged. No new candidate profile digest.
`FROZEN_LONG_DOCUMENT_PROFILE_SHA256` remains empty.
`hybrid_default_v1` bytes were not edited. Holdout was not opened.

Requirement: do not retune from the 2/24 ungrounded baseline. Freeze remains
denied without live development and qualification live-rerank reports.

Files:

- [`packages/core/src/smart_rag_core/gateways/openai_rerank.py`](../../../packages/core/src/smart_rag_core/gateways/openai_rerank.py) (existing mapping, contract-tested)
- [`tests/unit/test_openai_rerank.py`](../../../tests/unit/test_openai_rerank.py) (`test_invalid_json_maps_to_schema_invalid`)
- [`tests/unit/test_hybrid_rerank.py`](../../../tests/unit/test_hybrid_rerank.py) (`test_invalid_json_schema_falls_back_to_rrf`)
- [`docs/evaluation/PDF_HYBRID_EVALUATION.md`](../../evaluation/PDF_HYBRID_EVALUATION.md)

Verification:

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_openai_rerank.py tests/unit/test_hybrid_rerank.py::test_invalid_json_schema_falls_back_to_rrf -q` | 0 |
| `FROZEN_LONG_DOCUMENT_PROFILE_SHA256` | `""` |
| `runtime_allow_listed` | false unless live gates pass (denied) |

Proven: invalid JSON is a typed fallback, not an untyped success. Identity
rerank still cannot freeze.

Unverified: live grounded channel histograms; any fusion/quota repair that
would need a new immutable candidate digest.

Rollback: leave freeze pin empty; keep RRF fallback.

Handoff: Packet 26 wires ACL-safe retrieval cache and records Combined plus
holdout as still-unverified live gates.
