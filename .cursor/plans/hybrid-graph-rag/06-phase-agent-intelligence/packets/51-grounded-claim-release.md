---
phase: 6
packet: 51
status: complete
title: "Version answer/verifier prompts, release only supported atomic claims, and remove all-fusion citation backfill with MCP regressions."
requirement_ids: [P06-51]
---

# Packet 51 — Version answer/verifier prompts, release only supported atomic claims, and remove all-fusion citation backfill with MCP regressions.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).

Do not load frontend or migration skills.

## Preconditions

- P06-50 is recorded. Branch is `fix/rag-reliability-and-citations`.
- Q3 released “Method Call Protocol” without a supporting atomic link.
- `answer_v2.md` already exists for PDF paragraph citations. This
  packet adds `answer_v3.md` and `verifier_v2.md`. Never edit v1 or
  `answer_v2.md`.
- `ensure_fusion_source_citations` must not remain on any live verify
  or persist path. Inspect `citations.py` and `verify.py` first.

## Allowed outputs

- New immutable `apps/agents/src/smart_rag_agents/prompts/answer_v3.md`
- New immutable `apps/agents/src/smart_rag_agents/prompts/verifier_v2.md`
- Prompt registry, changelog, `versions.py`, loaders, and gateway
  contract tests
- `packages/core/src/smart_rag_core/query_answer/` modules that own
  verification, sanitization, citations, and company rendering
- `apps/agents/src/smart_rag_agents/query/nodes/verify.py`
- `apps/agents/src/smart_rag_agents/query/gateway/answer.py`
- Tests listed below and packet evidence
- `docs/agent/ANSWER_VERIFICATION.md`

## Forbidden outputs

- Editing `answer_v1.md`, `answer_v2.md`, or `verifier_v1.md`.
- Guessing SHA-256 hashes.
- Copying free-form `answer_text` into the released company prose.
- All-fusion citation backfill.
- Applying the company renderer to general, user-text, deterministic
  chat, or Web.
- SQL, OpenAPI, or frontend changes.
- A second model call beyond existing ceilings.

## Ordered actions

1. Add immutable `answer_v3.md` and `verifier_v2.md`. Require every
   material factual sentence to correspond to one emitted atomic link;
   forbid acronym expansions unless a supplied source spells them out;
   keep the PDF paragraph mapping contract from `answer_v2`.
2. Pin versions/hashes from LF-normalized file bytes.
3. Add `render_verified_company_answer`. Sort surviving links by
   `(priority, link_id)`. Render each unique surviving claim once.
   Append `composed_conclusion.text` only when the complete chain
   survived.
4. Build citations only from surviving links, with `atomic_link_id`.
   Deduplicate `(source, atomic_link_id)` while preserving order.
5. Add narrow exact-value guards for acronym-definition forms and for
   quoted/numeric/date/code literals on `fact` links. Do not require
   ordinary paraphrases to be substrings.
6. Remove live all-fusion backfill. If no supported material link
   remains, emit the canonical company refusal and no citations.
7. Keep PDF fail-closed paragraph mapping. A released paragraph still
   needs surviving links and contained spans.

## Acceptance checks

- Source says `Model Context Protocol`; free prose says `Method Call
  Protocol` while links omit the expansion: terminal cannot be
  `verified` and released text cannot contain the wrong expansion.
- A wrong expansion inside a cited link is rejected even when a mock
  verifier says supported; the correct expansion passes.
- Released company prose contains only surviving links; a valid
  composed inference still passes.
- No all-fusion backfill. One supported link produces one citation.
  Unsupported/dropped links produce none. `atomic_link_id` persists.
- v3/v2 hashes match file SHA-256. One-call/six-link cap remains.
- General answers are unchanged and receive no company citations.

## Negative tests

- Changing the expected wrong text instead of blocking it fails.
- Trusting a mock verifier that marks any cited ID supported fails.
- Leaving an unsupported sentence beside otherwise-valid links fails.
- Editing `answer_v2.md` fails.

## Stop routes

- Stop if satisfying the request requires another model call.
- Stop if PDF paragraph/exact-span fail-closed behavior would be
  removed.
- Do not start Packet 52 SSE mapping work.

## Required evidence

- Prompt hashes, MCP regressions, citation persist, ruff, pyright.
- Commands:

  ```powershell
  uv run python -m pytest tests/unit/test_answer_verifier.py tests/unit/test_answer_verifier_integration.py tests/unit/test_answer_citations_persist.py tests/unit/test_verifier_gateway.py tests/unit/test_general_chat_generate.py tests/unit/test_answer_paragraph_citations.py -q
  uv run ruff check packages/core/src/smart_rag_core/query_answer packages/core/src/smart_rag_core/gateways apps/agents/src/smart_rag_agents/query tests/unit/test_answer_verifier.py
  uv run pyright packages/core/src/smart_rag_core/query_answer packages/core/src/smart_rag_core/gateways apps/agents/src/smart_rag_agents/query
  git diff --check
  ```

- Commit `fix(rag): release only verifier-supported claims`.
