---
phase: 6
packet: 25
status: complete
title: "Repair measured Hybrid candidate and rerank failures without opening holdout."
requirement_ids: [P06-25]
---

# Packet 25 — Repair measured Hybrid candidate and rerank failures without opening holdout.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-hybrid-retrieval`](../../../../../.cursor/skills/implement-hybrid-retrieval/SKILL.md).

## Preconditions

- Packet 24 diagnostics exist. Do not retune from the 2026-09-10 2/24
  ungrounded baseline. If live grounded labels are unavailable, implement
  only proven rerank schema/timeout contract repairs and record the freeze
  blocker.

## Allowed outputs

- Additive rerank schema/timeout tests and prompt/request bound fixes that
  preserve `max_retries=0` and RRF fallback
- A new immutable candidate profile JSON with a new digest when fusion or
  quota repair is evidenced
- Docs recording rejected versus new candidate digests
- Qualification freeze of `hybrid_long_document_v1` only when both live
  reports pass

## Forbidden outputs

- Editing `hybrid_default_v1` bytes.
- Rewriting a rejected candidate digest in place.
- Tuning against holdout.
- Raising the Hybrid 25s deadline.
- Local rerankers.

## Ordered actions

1. Fix `rerank_schema_invalid` against pinned OpenAI 2.26.0 structured
   output with a contract test.
2. If live grounded evidence exists, choose the repair from channel
   diagnostics: parser/query/source-scope for total miss; new candidate
   profile for fusion loss; rerank request/slice only when first-evidence
   and 25s still pass.
3. Preserve top-20 rerank, canonical excerpts, 12 evidence units, and
   authorization bounds.
4. Do not pin `FROZEN_LONG_DOCUMENT_PROFILE_SHA256` without passing
   development and qualification live-rerank reports.

## Acceptance checks

- Schema-invalid rerank falls back to RRF and is tested.
- Timeout remains a typed fallback.
- Freeze remains denied without live gates.

## Negative tests

- Invalid JSON schema from the model does not raise an untyped success.
- Identity rerank still cannot freeze.

## Stop routes

- If labels remain ungrounded, stop freeze and record the operator reseal
  and live eval blocker.
- Do not guess unequal RRF weights.

## Required evidence

- Append rerank tests, any new candidate digest, and freeze status
  (`runtime_allow_listed=false` unless live gates pass).
