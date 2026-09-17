---
phase: 6
packet: 63
status: pending
title: "Exclude source-selector false refusals and require a measured, revalidated correction."
requirement_ids: [P06-63]
---

# Packet 63 — Exclude source-selector false refusals and require a measured, revalidated correction.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-hybrid-retrieval`](../../../../../.cursor/skills/implement-hybrid-retrieval/SKILL.md),
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).

Do not load frontend skills.

## Preconditions

- P06-62 accounting/profile work is recorded. Branch is
  `fix/general-rag-retrieval-accuracy`.
- Inspect `coverage_score.py`, query-routing `correction.py`, and the
  agent correction node before editing.

## Allowed outputs

- `packages/core/src/smart_rag_core/retrieval/coverage_score.py`
- `packages/core/src/smart_rag_core/query_routing/correction.py`
- `apps/agents/src/smart_rag_agents/query/nodes/correction.py`
- Coverage and correction unit tests
- Docs already describing coverage calibration
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- Changing the 0.65 coverage threshold unless labeled development
  evidence in this packet justifies a new frozen profile.
- Identical cached retries.
- Sample-PDF gold phrases as required terms.
- Company-to-Web or company-to-general fallback.
- Starting Packet 64 live qualification.

## Ordered actions

1. Exclude source-selector text from answer-evidence term
   requirements so naming a document cannot force a coverage refusal.
2. Use the same retrieval normalization for coverage term matching
   that candidate generation uses.
3. Forbid an identical cached retry. The one allowed correction must
   use a measured alternate query or profile.
4. Recompute coverage after correction before answer generation.
5. Keep the 0.65 threshold unless this packet’s labeled development
   evidence justifies a new frozen coverage profile.
6. Test source-selector exclusion, identical-retry rejection,
   alternate-query retry, and post-correction coverage recompute.

## Acceptance checks

- Coverage ignores source-selector tokens that were stripped from the
  ranking query.
- An identical retry is rejected or skipped with a recorded reason.
- A permitted retry uses a different query or profile and recomputes
  coverage.
- Threshold remains 0.65 unless a new frozen digest is recorded.
- Company insufficient evidence still never falls back to Web or
  general knowledge.

## Negative tests

- Treating the document title as a required answer fact fails.
- Applying correction twice fails.
- Retrying the exact cached ranking query fails.
- Lowering the threshold without labeled evidence fails.

## Stop routes

- Stop if correction cannot distinguish a material alternate from the
  cached query.
- Stop if coverage changes would require sample-PDF gold terms.
- Do not open holdout.

## Required evidence

- Packet file under `docs/development/phase-06/` plus index append.
- Commands:

  ```powershell
  uv run python -m pytest tests/unit/test_coverage_score.py tests/unit/test_query_correction.py -q
  uv run python scripts/check.py --tier docs
  git diff --check
  ```
