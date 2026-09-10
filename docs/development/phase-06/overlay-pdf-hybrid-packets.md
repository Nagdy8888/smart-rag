---
title: Overlay PDF Hybrid packets (P13, P15, P16)
owner: engineering-lead
status: draft
last-reviewed: 2026-09-10
audience: engineering, reviewers
---

# Overlay PDF Hybrid packets

Additive evidence for overlay Packets 13, 15, and 16. Historical Phase 6
Packet 9 remains the next unchecked historical packet. This file does not
mark Phase 6 complete.

Related: [PDF_HYBRID_EVALUATION.md](../../evaluation/PDF_HYBRID_EVALUATION.md) ·
[hybrid-pdf-accuracy-remediation.md](../hybrid-pdf-accuracy-remediation.md) ·
[ADR-hybrid-long-document-profile.md](../../adr/ADR-hybrid-long-document-profile.md) ·
[phase-06 index](../phase-06-agent-intelligence-evidence.md) ·
[docs index](../../README.md)

```mermaid
flowchart LR
  scope["Server source scope"] --> rerank["rerank_v1 one call"]
  rerank --> default["hybrid_default_v1"]
  default --> blocked["tune no_go; freeze denied"]
```

## Packet 13 — production rerank and source scope

### Proven

- `ProcessHybridRetriever` binds `model_gateway` and `rerank_v1`.
- Runtime `load_frozen_profile` is `hybrid_default_v1` only.
- Textual `requested_sources` resolve to a hard version filter only at
  confidence ≥ 0.80 and exact-one authorized current title/filename match.
- Ambiguous and unauthorized names stay unscoped. Missing IDs do not leak.
- `authorized_chunk_loader(caller)` is forwarded on process and run-scoped Hybrid.

### Not proven

- Live OpenAI rerank `rerank_call_count=1` on every eligible PDF case.
  2026-09-10 live development: 7/24 ones, 18 `rerank_timeout`, 3
  `rerank_schema_invalid`. Mock/identity output cannot satisfy the
  live-rerank gate.

## Packet 15 — PDF agent eval

### Proven

- `scripts/eval_pdf_agent.py` uses `eval_pdf_judge_v1` and does not reuse
  `eval_judge_v1.md`.
- Deterministic citation/ACL scorers treat invalid judge output as `unscored`.
- Command exits `2` until matrix, freeze, and human seal exist.

### Blocked

- Development/qualification agent metrics on this PDF. Frozen
  `hybrid_long_document_v1` remains runtime-denied.

## Packet 16 — holdout close

### Blocked

- Named SME open-once. `scripts/eval_pdf_holdout.py` never materializes
  holdout rows while the long-document profile is denied.
- `holdout_opened=false`.
- No-go: an opened holdout is never reused for tuning.

## Verification

```text
uv run python scripts/draft_pdf_eval_dataset.py
uv run python scripts/eval_pdf_hybrid.py --probe-gold
uv run python scripts/eval_pdf_hybrid.py --probe-grounding
uv run python scripts/eval_pdf_hybrid.py --split development --live
uv run python scripts/eval_pdf_agent.py --split development
uv run python scripts/eval_pdf_holdout.py --labels .private-eval/holdout/labels.json
```

Recorded 2026-09-10:

| Command | Exit | Output tokens |
| --- | --- | --- |
| `eval_pdf_hybrid.py --probe-gold` | 0 | 28 cases; gold∩representatives 28/28; 1 ID/case; `holdout_opened=false` |
| `eval_pdf_hybrid.py --probe-grounding` | 0 | 24 scored; 2 grounded; 4 refusals; `holdout_opened=false` |
| `eval_pdf_hybrid.py --split development --live` | 0 | `gates_pass=false`; Recall@10 0.0417; fused occupancy 0.0417; locator 0.0357; p95 3236 ms; eligible rerank 7/24; digest `d9e1547…` |
| `eval_pdf_hybrid.py --split development --live --rerank identity` | 0 | Recall@10 0.0417; `gold_in_fused_any` 0.0417; `live_rerank=false`; cannot freeze |
| `eval_pdf_hybrid.py --fault paradedb` | 0 | `bm25_fallback=retrieval_timeout`; `dense_term_degraded=true`; `full_hybrid=false` |
| `eval_pdf_hybrid.py --freeze` | 2 | `blocked=qualification_and_gates_required_before_freeze` |
| `eval_pdf_hybrid.py --split holdout` | 2 | `blocked=holdout_sealed`; `holdout_opened=false` |
| `eval_pdf_agent.py --split development` | 2 | `blocked=live_agent_eval_required`; `eval_judge_v1_reused=false` |
| `eval_pdf_holdout.py` | 2 | `blocked=holdout_sealed`; `holdout_opened=false` |
