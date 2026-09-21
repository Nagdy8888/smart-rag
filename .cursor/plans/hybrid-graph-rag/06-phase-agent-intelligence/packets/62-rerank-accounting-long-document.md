---
phase: 6
packet: 62
status: pending
title: "Repair retrieve-time durable call accounting and qualify a measured immutable long-document profile."
requirement_ids: [P06-62]
---

# Packet 62 — Repair retrieve-time durable call accounting and qualify a measured immutable long-document profile.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-hybrid-retrieval`](../../../../../.cursor/skills/implement-hybrid-retrieval/SKILL.md),
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).

Do not load frontend skills.

## Preconditions

- P06-61 candidate repair is recorded. Branch is
  `fix/general-rag-retrieval-accuracy`.
- Inspect `QueryRetrieveBudget` construction, Hybrid embed/rerank
  accounting, `hybrid_long_document_v1.json`, and
  [`ADR-hybrid-long-document-profile.md`](../../../../../docs/adr/ADR-hybrid-long-document-profile.md)
  before editing.
- Do not pin the failed `hybrid_long_document_v1.json` digest.

## Allowed outputs

- Retrieve-budget wiring that passes the run database connection
- Durable embedding/rerank/verifier usage rows
- Time reservation for reranking inside the existing retrieval and
  deadline envelope
- A new immutable long-document profile JSON with a new digest when
  development ablations justify it
- Query-aware excerpt, pool, quota, and MMR values only from
  development ablations
- Tests for missing-connection failure, durable usage, rerank
  timeout fallback, and profile immutability
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- Pinning `hybrid_long_document_v1.json` without a measured digest.
- Mutating frozen `hybrid_default_v1` bytes in place.
- Raising `MODEL_INPUT_MAX_CHARS` or the product deadline.
- Spending the answer-stage reserve on retrieval.
- Sample-PDF-specific profile keys.
- Starting Packet 63 coverage/correction coding.

## Ordered actions

1. Pass the run database connection into retrieve-time accounting so
   embedding and rerank calls persist to `llm_usage`.
2. Fail closed or record an explicit accounting error when the
   connection is omitted on a counted retrieve path; do not silently
   skip durable writes.
3. Reserve time for reranking inside the existing retrieval slice and
   overall deadline. If the reserve cannot be met, skip rerank with a
   recorded RRF fallback rather than overflowing the answer reserve.
4. Qualify a new immutable long-document profile from development
   ablations. Enable it only for exact-one authorized version scope
   above the existing representative-count gate.
5. Tune query-aware excerpts, pool, quota, and MMR only from those
   ablations. Do not copy sample-PDF page numbers into the profile.
6. Add tests that counted retrieve calls write usage rows and that the
   new profile file is immutable by digest.

## Acceptance checks

- Retrieve embedding and rerank calls appear in durable usage when a
  connection is supplied.
- Missing connection on counted retrieve is tested and does not fake
  success.
- Rerank either completes inside the reserved envelope or falls back
  to RRF with a recorded reason.
- The new long-document profile has a non-empty SHA-256 and is not
  the failed prior digest unless measurement proves that file.
- `hybrid_default_v1` bytes are unchanged.

## Negative tests

- Enabling the unfrozen prior long-document file without a digest
  fails.
- Using the answer-stage eight-second reserve for retrieval fails.
- Profile JSON containing sample-PDF identifiers fails.

## Stop routes

- Stop if ablations cannot justify a new profile; leave long-document
  runtime denied and record the blocker.
- Stop if durable accounting requires a schema that changes security
  semantics without an ADR.
- Do not open holdout to tune pool/quota values.

## Required evidence

- Packet file under `docs/development/phase-06/` plus index append.
- Commands:

  ```powershell
  uv run python -m pytest tests/unit/test_retrieve_budget_accounting.py tests/unit/test_long_document_profile.py -q
  uv run python scripts/check.py --tier docs
  git diff --check
  ```
