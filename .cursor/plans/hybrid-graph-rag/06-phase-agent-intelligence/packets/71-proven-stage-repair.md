---
phase: 6
packet: 71
status: complete
title: "Implement one bounded repair for the proven dominant stage."
requirement_ids: [P06-71]
---

# Packet 71 — Implement one bounded repair for the proven dominant stage.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills are selected from the P06-70 gate. Load only the one
matching skill: `implement-hybrid-retrieval`,
`implement-query-agent`, or `implement-observability-evals`. Do not
load the others.

## Preconditions

- P06-70 named exactly one decision-gate branch. Branch is
  `fix/honest-rag-accuracy`.
- The 12-question slice still has approved gold.
- Quote the gate result before editing.

## Allowed outputs

- Only the modules that the proven stage owns
- One stage-specific regression test file
- Docs for that stage
- A rerun of the 12-question slice (all four arms)
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- Touching any other stage, prompt, profile, or threshold
- Mutating frozen `hybrid_default_v1` bytes in place
- Raising `MODEL_INPUT_MAX_CHARS`
- Opening holdout
- Running all 100 questions before a positive slice result
- Embedding sample-PDF literals in production files

## Ordered actions

1. Quote the P06-70 gate result and the owning stage.
2. Implement the smallest change for that stage.
3. Add a stage-specific regression and an ablation proving the stage
   metric moves without ACL, citation, deadline, latency, or cost
   regression.
4. Rerun the 12-question slice (Arms A, A-prime, B, and C).
5. Stop if the slice does not improve on the owning stage's metric.

## Acceptance checks

- The slice improves on the owning stage's metric.
- ACL leaks remain zero. Citations remain canonical.
- Deadline, latency, and cost ceilings do not regress.
- No other stage was edited.

## Negative tests

- A no-change slice result rejects the hypothesis.
- Editing a second stage in this packet fails.
- Running the 100-question set before a positive slice result fails.

## Stop routes

- Stop if the slice does not improve.
- Stop if the repair would require a second stage, a new frozen
  profile, or a coverage-threshold change without a new digest.
- Do not start Packet 72 until the slice ablation is positive.

## Required evidence

Create
[`p06-71-proven-stage-repair-2026-09-21.md`](../../../../../docs/development/phase-06/p06-71-proven-stage-repair-2026-09-21.md)
and append to the Phase 6 evidence index: quoted gate, files changed,
before/after slice metric, ACL/citation/deadline/latency/cost, rollback.

Commands:

```powershell
uv run python scripts/check.py --tier docs
git diff --check
```

Narrow tests are chosen after the gate names the stage. Record the
exact pytest invocation in evidence.
