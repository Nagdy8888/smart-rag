---
title: Overlay PDF Hybrid packets (P13, P15, P16)
owner: engineering-lead
status: draft
last-reviewed: 2026-09-09
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

- Live OpenAI rerank `rerank_call_count=1` with `store=False` on this PDF.
  A dummy retrieve after BM25 repair returned `rerank_timeout` inside the
  8s slice. Mock/identity output cannot satisfy the live-rerank gate.

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
uv run python scripts/eval_pdf_hybrid.py --split development --live
uv run python scripts/eval_pdf_agent.py --split development
uv run python scripts/eval_pdf_holdout.py --labels .private-eval/holdout/labels.json
```

Recorded 2026-09-09:

| Command | Exit | Output tokens |
| --- | --- | --- |
| `eval_pdf_hybrid.py --split development --live` (post-seal) | 0 | `gates_pass=false`; `fallback_histogram={none: 28}`; Recall@10 0.0417; locator 0.0357; p95 10545 ms; eligible rerank 0/24; `holdout_opened=false` |
| `eval_pdf_hybrid.py --split holdout` | 2 | `blocked=holdout_sealed`; `holdout_opened=false` |
| `eval_pdf_agent.py --split development` | 2 | freeze denied; `eval_judge_v1_reused=false` |
| `eval_pdf_holdout.py` | 2 | `blocked=holdout_sealed`; `holdout_opened=false` |
