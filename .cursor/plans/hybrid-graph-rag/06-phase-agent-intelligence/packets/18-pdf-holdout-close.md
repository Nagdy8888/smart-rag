---
phase: 6
packet: 18
status: pending
title: "Execute one immutable private-PDF holdout and close with redacted evidence."
requirement_ids: [P06-18]
---

# Packet 18 — Execute one immutable private-PDF holdout and close with redacted evidence.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md)
and [`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).

## Preconditions

- Named human/SME seal of the private dataset; provider-matrix approval;
  frozen code/profile/chunk/index/glossary/prompt/model hashes;
  development and qualification gates from Packets 16 (Phase 4) and 17
  passed; Supabase/ParadeDB healthy; graph disabled for this version.
- No uncommitted runtime changes except the user-owned
  `eval_judge_v1.md` change, which is excluded from this PDF eval hash.

## Allowed outputs

- Authorized one-time holdout loader records (actor, purpose, manifest hash,
  run ID, git SHA, `holdout_opened=true`)
- [`docs/evaluation/PDF_HYBRID_EVALUATION.md`](../../../../../docs/evaluation/PDF_HYBRID_EVALUATION.md)
  with aggregates only
- Evidence append in
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)

## Forbidden outputs

- Private questions, answers, glossary terms, or excerpts in Git
- Second holdout run after a miss
- Tuning on the opened holdout
- Claiming generalization beyond this PDF and this sealed distribution

## Ordered actions

1. Reviewer supplies holdout through the authorized loader. Record
   `holdout_opened=true` and one-way run ID.
2. Run retrieval and agent metrics from overlay Packets 14–15 exactly once
   on the frozen production query path.
3. Inspect terminal and LangSmith traces by case/run ID. Require real rerank
   spans for eligible cases, hidden I/O, no unauthorized evidence, and no
   `ingestion.graph`, `retrieval.graph`, or LightRAG model span.
4. Publish the redacted evaluation document. Any BM25 outage, rerank
   fallback, stale index, missing label, or incomplete result is a recorded
   failure/degraded slice, not a rerun excuse.

## Acceptance checks

- Every gap in the overlay gap-to-packet list has code plus
  positive/negative/live evidence, or an honest blocked/no-go record.
- Passing statement is: qualified on this PDF and this human-sealed query
  distribution. User acceptance of the report is required.

## Negative tests

- Holdout reuse for tuning, invented Recall from occupancy, graph traces for
  this version, or exported source I/O fail the packet.

## Stop routes

- Any signed gate miss records `no_go`. Repairs use development/qualification
  only and a later launch claim requires a newly collected sealed holdout.

## Required evidence

- Redacted evaluation document, run IDs, hashes, fallback counts,
  commands/exit codes, rollback (do not reopen this holdout), and user
  acceptance request.
