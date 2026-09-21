---
phase: 6
packet: 60
status: complete
title: "Implement authorized source resolution, ranking-query title stripping, and post-ACL duplicate collapse."
requirement_ids: [P06-60]
---

# Packet 60 — Implement authorized source resolution, ranking-query title stripping, and post-ACL duplicate collapse.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-hybrid-retrieval`](../../../../../.cursor/skills/implement-hybrid-retrieval/SKILL.md),
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).

Do not load frontend or FastAPI-router skills.

## Preconditions

- P06-59 baseline scorer exists. Branch is
  `fix/general-rag-retrieval-accuracy`.
- Inspect `preparation.py`, `source_scope.py`,
  `adapters_hybrid.py`, Hybrid fusion/MMR selection, and current
  authorization recheck paths before editing.

## Allowed outputs

- `packages/core/src/smart_rag_core/query_routing/preparation.py`
- `packages/core/src/smart_rag_core/retrieval/source_scope.py`
- `apps/agents/src/smart_rag_agents/query/runtime/adapters_hybrid.py`
- Hybrid result assembly that already owns post-ACL selection
- Unit and metamorphic tests for authorized exact title match,
  ambiguous names, unauthorized names, title stripping, and
  exact-duplicate collapse
- Retrieval docs already describing source scope
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- Automatic document deletion.
- Scoping on unauthorized or ambiguous titles.
- Leaking whether an unauthorized title exists.
- Embedding the sample PDF hash, book title, or gold phrases.
- Changing BM25 RPCs, term extraction, coverage thresholds, or frozen
  default profile bytes.
- Opening holdout or starting Packet 61 term-channel coding.

## Ordered actions

1. Preserve meaningful upload titles through ingest/query display
   paths already owned by document metadata. Do not invent a
   book-specific alias table.
2. Deterministically resolve an explicitly named authorized document
   when exactly one current authorized title matches. Use that
   document/version as the scope selector.
3. Remove the matched title from the ranking query so source-selector
   tokens do not dominate dense/BM25 ranking.
4. Keep ambiguous and unauthorized matches unscoped and
   indistinguishable. Do not return a different error that reveals
   unauthorized existence.
5. After ACL and current-version recheck, collapse exact duplicate
   content so duplicate copies cannot consume document quotas. Do not
   delete documents.
6. Add metamorphic tests: equivalent wording retains the relevant
   source; adding a document title scopes rather than distorts
   ranking; adding irrelevant authorized documents or exact duplicate
   copies does not evict the supporting passage; unauthorized
   documents never enter results.

## Acceptance checks

- Exact authorized title match scopes retrieve to that version.
- The ranking query no longer contains the matched title tokens.
- Ambiguous authorized titles and unauthorized titles remain unscoped
  with indistinguishable client behavior.
- Exact duplicate survivors collapse after ACL/current-version
  recheck; documents remain stored.
- Metamorphic tests pass without sample-PDF literals.

## Negative tests

- Confidence below the existing named-source threshold must not
  scope.
- Title ILIKE against unauthorized documents must not scope.
- Collapsing before ACL recheck fails.
- Deleting a document as the duplicate handler fails.

## Stop routes

- Stop if title resolution would require a benchmark-specific alias.
- Stop if duplicate collapse cannot keep ACL/current-version recheck
  in front of drop.
- Do not freeze a long-document profile in this packet.

## Required evidence

- Packet file under `docs/development/phase-06/` plus index append.
- Commands:

  ```powershell
  uv run python -m pytest tests/unit/test_source_scope.py tests/unit/test_source_aware_ranking.py -q
  uv run python scripts/check.py --tier docs
  git diff --check
  ```
