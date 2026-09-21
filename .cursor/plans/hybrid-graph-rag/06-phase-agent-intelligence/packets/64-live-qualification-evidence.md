---
phase: 6
packet: 64
status: pending
title: "Qualify disjoint retrieval classes, rerun the company-document regression, and publish redacted evidence."
requirement_ids: [P06-64]
---

# Packet 64 — Qualify disjoint retrieval classes, rerun the company-document regression, and publish redacted evidence.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`verify-release-gates`](../../../../../.cursor/skills/verify-release-gates/SKILL.md),
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

This packet records gates. It does not add a special-case fixture to
hide a failed owning packet.

## Preconditions

- Packets P06-59 through P06-63 are recorded with green commits.
- Branch is `fix/general-rag-retrieval-accuracy`.
- Private label/ID paths remain gitignored. `git status --short` shows
  none of them before qualification.

## Allowed outputs

- Phase 6 evidence files for P06-58 through P06-64
- Updates to
  [`PDF_HYBRID_EVALUATION.md`](../../../../../docs/evaluation/PDF_HYBRID_EVALUATION.md)
  and
  [`COMPANY_DOCUMENTS_RAG_100.md`](../../../../../docs/evaluation/COMPANY_DOCUMENTS_RAG_100.md)
- Redacted hashes, commands, rollback, and an explicit unverified
  generalization claim when disjoint real documents are unavailable
- Wrapper checkbox for this packet only after every scenario passes
- Repair commits only by returning to the owning packet listed below

## Forbidden outputs

- Opening P06-18 or setting `holdout_opened=true`.
- Weakening citation/faithfulness/routing/ACL/latency/cost thresholds.
- Marking P06-17, P06-18, or Phase 6 complete.
- Embedding sample-PDF gold in production code to pass the
  regression.
- Pasting passwords, DSNs, unrestricted PDF text, or raw excerpts.
- `--no-verify`, force-push, or `gh pr merge --admin`.

## Ordered actions

1. Run synthetic, unit, contract, and metamorphic suites for packets
   59–63.
2. Run a live retrieval-only development evaluation with stage
   attribution.
3. Run one disjoint qualification set covering short and long PDFs,
   one-document and multi-document corpora, duplicate files, exact
   identifiers/acronyms, paraphrases, lists, headings, ambiguous
   source names, OCR/layout limitations, Arabic/mixed text, negation,
   stale versions, ACL denial, and BM25 outage. If sufficient disjoint
   real documents are unavailable, mark generalization unverified.
4. Rerun the 100-question Ask regression with a fresh conversation per
   question and the dual-metric scorer.
5. Promote only if ACL leaks remain zero, corpus
   expansion/duplicates do not regress source recall, BM25
   degradation is explicit, rerank/accounting gates pass, signed
   latency/cost limits hold, sample grounded fact correctness is at
   least 95%, strict score is reported separately, product-deadline
   failures are zero on the sample, and remaining misses are
   attributed by stage.
6. If a gate fails, stop and reopen the owning packet: P06-59 scorer,
   P06-60 source ranking, P06-61 candidates, P06-62 accounting/profile,
   P06-63 coverage/correction.
7. Publish redacted evidence, then leftover P06-17 remains open.

## Acceptance checks

- Dual-metric report includes strict phrase, grounded required-fact
  coverage, deadline failures, and stage buckets.
- Grounded required-fact correctness is at least 95% on the sample
  with zero product-deadline failures.
- ACL leaks remain zero. Unauthorized documents never enter results.
- BM25 outage remains an explicit degradation, not silent success.
- Generalization is claimed only with disjoint evidence; otherwise
  marked unverified.
- P06-17, P06-18, and Phase 6 remain incomplete.

## Negative tests

- Promoting on strict score alone without fact coverage fails.
- Hardcoding sample-PDF answers to pass the regression fails.
- Opening holdout to chase the 95% gate fails.
- Claiming generalization without disjoint documents fails.

## Stop routes

- Stop if live Ask cannot run without embedding credentials in git.
- Stop if a gate fails and the owning packet is not reopened.
- Do not delete the feature branch in this packet; git delivery is
  after P06-64 evidence.

## Required evidence

- Packet file under `docs/development/phase-06/` plus index append.
- Commands:

  ```powershell
  uv run python scripts/check.py --tier fast
  uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py
  git diff --check
  ```
