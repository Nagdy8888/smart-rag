---
phase: 6
packet: 72
status: pending
title: "Qualify live accuracy, publish redacted evidence, and leave leftover P06-17 open."
requirement_ids: [P06-72]
---

# Packet 72 — Qualify live accuracy, publish redacted evidence, and leave leftover P06-17 open.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`verify-release-gates`](../../../../../.cursor/skills/verify-release-gates/SKILL.md).

This packet records gates. It does not add a special-case fixture to
hide a failed owning packet.

## Preconditions

- P06-71 slice ablation is positive. Branch is
  `fix/honest-rag-accuracy`.
- P06-68 measured fields are wired. Unknown required fields block
  promotion.
- Private gold and credentials stay gitignored.

## Allowed outputs

- Evidence docs, evaluation docs, and wrapper checkboxes 62–72 from
  live evidence only
- Updates to
  [`COMPANY_DOCUMENTS_RAG_100.md`](../../../../../docs/evaluation/COMPANY_DOCUMENTS_RAG_100.md),
  [`PDF_HYBRID_EVALUATION.md`](../../../../../docs/evaluation/PDF_HYBRID_EVALUATION.md),
  [`DUAL_METRIC_SCORING.md`](../../../../../docs/evaluation/DUAL_METRIC_SCORING.md),
  and P06-61/62/63/64 evidence
- Redacted hashes, commands, rollback, and an explicit unverified
  generalization claim when disjoint real documents are unavailable

## Forbidden outputs

- Opening P06-18 or setting `holdout_opened=true`
- Checking P06-62, P06-63, or P06-64 from unit tests or merged code
- Weakening citation, faithfulness, ACL, latency, or cost gates
- Marking P06-17, P06-18, or Phase 6 complete
- Embedding sample-PDF gold in production code
- Pasting passwords, DSNs, unrestricted PDF text, or raw excerpts
- Touching the user's uncommitted `README.md` or `docs/assets/`
- `--no-verify`, force-push, or `gh pr merge --admin`

## Ordered actions

1. Run all 100 questions with fresh conversations and P06-68 measured
   fields. Report separately: strict phrase, grounded fact with alias
   count, blinded semantic support, first-failure histogram,
   deadlines, errors, ACL leaks, citations, latency, cost,
   `unknown_required_fields` (must be 0), effective-route histogram.
2. Interim gate: grounded `>= 90%`, zero deadlines. Promotion:
   grounded `>= 95%`, zero deadlines, zero ACL leaks, explicit BM25
   degradation, measured rerank accounting, zero unknown fields,
   strict reported separately.
3. Two disjoint real PDFs are required for a generalization claim; if
   not supplied, record `generalization_unverified`. Holdout stays
   sealed.
4. Update evaluation docs and P06-61/62/63/64 evidence. Check
   P06-62/63/64 only if their live items are now proven.
5. Leave leftover P06-17 open. Do not open P06-18.

## Acceptance checks

- Dual-metric report includes strict phrase, grounded fact, deadlines,
  and measured stage buckets.
- `unknown_required_fields = 0`.
- ACL leaks remain zero.
- BM25 outage remains an explicit degradation.
- Generalization is claimed only with two disjoint real PDFs.
- P06-17, P06-18, and Phase 6 remain incomplete.
- Wrapper checkboxes 62–64 change only from live evidence.

## Negative tests

- Promoting on strict score alone fails.
- Promoting with unknown required fields fails.
- Checking P06-62/63/64 from unit tests fails.
- Opening holdout to chase the 95% gate fails.

## Stop routes

- Stop if live Ask cannot run without embedding credentials in git.
- Stop if a gate fails and the owning packet is not reopened.
- Do not delete the feature branch in this packet; git delivery is
  after P06-72 evidence.

## Required evidence

Create
[`p06-72-live-qualification-2026-09-21.md`](../../../../../docs/development/phase-06/p06-72-live-qualification-2026-09-21.md)
and append to the Phase 6 evidence index: redacted counts, stage
histogram, promotion decision, `holdout_opened=false`, commands/exits.

Commands:

```powershell
uv run python scripts/check.py --tier fast
uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py
git diff --check
```
