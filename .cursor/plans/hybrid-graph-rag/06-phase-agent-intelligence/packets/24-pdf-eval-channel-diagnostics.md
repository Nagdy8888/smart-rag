---
phase: 6
packet: 24
status: complete
title: "Add ranked-ID channel diagnostics and local evaluation baseline tooling."
requirement_ids: [P06-24]
---

# Packet 24 — Add ranked-ID channel diagnostics and local evaluation baseline tooling.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-hybrid-retrieval`](../../../../../.cursor/skills/implement-hybrid-retrieval/SKILL.md)
and [`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

## Preconditions

- Packet 20–23 contracts exist. Human seal and live ingest remain operator
  gates.

## Allowed outputs

- Additive optional fields or evaluation-only diagnostics on Hybrid results
  for authorized per-channel IDs after Supabase recheck
- `scripts/eval_pdf_hybrid.py` / `pdf_eval_runtime.py` count-only histograms
  that separate candidate miss, fusion loss, rerank/MMR drop, and
  selected-but-wrong-answer
- Unit tests with synthetic IDs only
- Docs updates that never include private questions

## Forbidden outputs

- Opening holdout.
- Exposing BM25 snippets or unauthorized pre-recheck IDs.
- Tuning RRF or rewriting rejected profile JSON.
- Claiming Recall@10 from ungrounded labels.

## Ordered actions

1. Inspect `HybridRunResult` and add optional authorized channel ID tuples
   if missing.
2. Score each labeled case into: absent from all channels; present in a
   channel but absent from fused IDs; fused but dropped by rerank/MMR/quota;
   selected; timeout/schema fallback.
3. Keep CLI probes `--probe-gold` and `--probe-grounding`.
4. Document that live development/qualification runs and human reseal are
   required before Packet 25 may retune.

## Acceptance checks

- Unit tests map synthetic ranked/fused/channel IDs to the four loss stages.
- Reports remain count/ID-hash only.
- `holdout_opened=false` on development tooling.

## Negative tests

- A BM25 snippet must not appear in diagnostics.
- Holdout split via CLI still returns `blocked=holdout_sealed`.

## Stop routes

- Stop live evaluation if labels are not grounded. Record the operator
  reseal blocker instead of substituting mock gold.

## Required evidence

- Append unit command/exit and the live-operator blocker list for reseal.
