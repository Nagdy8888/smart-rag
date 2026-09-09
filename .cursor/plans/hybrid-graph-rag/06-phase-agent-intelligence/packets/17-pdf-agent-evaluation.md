---
phase: 6
packet: 17
status: pending
title: "Qualify PDF Hybrid agent answers on development and qualification without reusing the synthetic judge."
requirement_ids: [P06-17]
---

# Packet 17 — Qualify PDF Hybrid agent answers on development and qualification without reusing the synthetic judge.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md)
and [`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

## Preconditions

- Phase 6 Packet 9 is accepted. Packet 10 has bound production rerank and the
  authorized source-scope resolver.
- Phase 4 Packet 16 has frozen `hybrid_long_document_v1` and recorded
  qualification with `holdout_opened=false`.
- Phase 3 Packet 9 named provider-matrix approval is on file, or this packet
  records an explicit blocked external-judge/trace gate.
- Do not weaken [`scripts/eval_query_agent_langsmith.py`](../../../../../scripts/eval_query_agent_langsmith.py)
  or reuse [`eval_judge_v1.md`](../../../../../apps/agents/src/smart_rag_agents/prompts/eval_judge_v1.md).

## Allowed outputs

- [`scripts/eval_pdf_agent.py`](../../../../../scripts/eval_pdf_agent.py)
- A new versioned real-content judge prompt under
  [`apps/agents/src/smart_rag_agents/prompts/`](../../../../../apps/agents/src/smart_rag_agents/prompts/)
- Private-eval schema/loaders that never print source text
- Tests under `tests/unit/` and `tests/contract/` using synthetic fixtures only
- Evidence in
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)

## Forbidden outputs

- Editing `eval_judge_v1.md`
- Opening private holdout labels
- Counting dense+term outage as full Hybrid
- Committing private questions, answers, glossary values, or excerpts
- Graph retrieve or LightRAG calls for this graph-ineligible PDF

## Ordered actions

1. Add `eval_pdf_agent.py` gated on the verified provider matrix and
   `LANGSMITH_EXPORT_IO=false`.
2. Add a new judge prompt. Deterministic scorers own route/profile, selected
   evidence recall, citation precision/completeness, locators, forbidden IDs,
   refusal, and budget/deadline bounds.
3. One bounded structured judge call per case after governance; invalid or
   timeout output is `unscored`, never a pass.
4. Run development, then freeze prompt hashes, then qualification once.
5. Require non-trivial Hybrid cases to report
   `retrieval_profile_id=hybrid_long_document_v1`, `rerank_call_count=1`,
   `rerank_fallback=none`, `bm25_fallback=none`.

## Acceptance checks

- Citation correctness ≥98%, completeness ≥90%, faithfulness ≥90%,
  routing ≥90%, zero ACL leaks, signed refusal/latency/cost/model-call
  limits.
- Deterministic and judge metrics reported separately.
- Commands, hashes, and `holdout_opened=false` recorded.

## Negative tests

- Synthetic judge reuse, mock/identity satisfying live rerank, holdout
  load, BM25 snippet citations, or graph spans for this PDF fail the packet.

## Stop routes

- Stop if qualification misses a signed gate. Return to development with a
  new candidate. Do not open holdout or weaken thresholds.
- If policy blocks bounded real-content judge input, run local deterministic
  evaluation and mark the external judge/trace gate blocked.

## Required evidence

- Append to the Phase 6 evidence file: prompt hashes, per-class aggregates
  without private text, fallback counts, commands/exit codes, rollback
  (new prompt version; never edit a failed hash), and P06-18 handoff.
