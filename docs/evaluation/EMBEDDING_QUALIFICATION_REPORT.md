---
title: Embedding qualification report
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering, reviewers
---

# Embedding qualification report (`embedding-qual-v1`)

Frozen slice: [`tests/fixtures/embedding_qualification/slice_v1.json`](../../tests/fixtures/embedding_qualification/slice_v1.json)  
Raw metrics: [`embedding_qualification_raw.json`](./embedding_qualification_raw.json)  
ADR: [`ADR-embedding-model-dimension.md`](../adr/ADR-embedding-model-dimension.md)

**Holdout policy:** this slice is for model/dimension selection only. Do not tune launch holdout on it.

## Environment

| Pin | Value |
| --- | --- |
| Date | 2026-08-12 |
| OpenAI | live Embeddings API |
| Candidates | small@1536; large@1536; large@1024 |
| Docs / queries | 33 / 22 (≥20 Arabic/mixed documents) |

## Results (Recall@10 / MRR / nDCG@10)

| Candidate | ar | mixed | en | all | tokens | latency_ms | est. USD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| small@1536 | 1.00 / 0.917 / 0.938 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 1.00 / 0.970 / 0.977 | 1487 | 3054 | ~0.000030 |
| large@1536 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 0.983 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 0.993 | 1487 | 1712 | ~0.000193 |
| **large@1024** | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 0.981 | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 0.992 | 1487 | 1591 | ~0.000193 |

All returned vectors were finite at the requested dimension (no silent model substitution).

## Selection

**Winner:** `text-embedding-3-large` @ **1024**, storage `vector`, cosine distance — see ADR for RAM gate.

## Reproduction

```powershell
$env:MOCK_MODEL_MODE='false'
# OPENAI_API_KEY required
uv run python scripts/embedding_qualification_bakeoff.py
uv run pytest tests/contract/test_embedding_dimensions.py -q
```
