---
phase: 6
packet: 45
status: pending
title: "Implement structured paragraph mappings, exact spans, and fail-closed verification."
requirement_ids: [P06-45]
---

# Packet 45 — Implement structured paragraph mappings, exact spans, and fail-closed verification.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).

Do not load frontend, FastAPI, or Supabase-migration skills.

## Preconditions

- P06-44 is recorded. Branch is `fix/pdf-paragraph-citations`.
- Requirement IDs: `CIT-PARA-003`, `CIT-SPAN-004`, `CIT-LINK-006`,
  `CIT-VERIFY-007`, `CIT-BOUNDS-012`.
- One answer call and one at-most-six-link verifier call remain the
  ceilings. Do not add a second model call.

## Allowed outputs

- `packages/core/src/smart_rag_core/query_answer/models.py`
- `packages/core/src/smart_rag_core/query_answer/schemas.py`
- `packages/core/src/smart_rag_core/query_answer/generate_grounded.py`
- `packages/core/src/smart_rag_core/query_answer/sanitize.py`
- `packages/core/src/smart_rag_core/query_answer/deterministic.py`
- `packages/core/src/smart_rag_core/query_answer/verifier.py`
- `packages/core/src/smart_rag_core/query_answer/citations.py`
- `packages/core/src/smart_rag_core/query_answer/versions.py`
- `packages/core/src/smart_rag_core/gateways/mock_model.py`
- `apps/agents/src/smart_rag_agents/query/gateway/answer.py`
- `apps/agents/src/smart_rag_agents/query/nodes/verify.py`
- New immutable `apps/agents/src/smart_rag_agents/prompts/answer_v2.md`
- Prompt registry, exports, changelog, and unit tests listed below
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- Database, API, SSE, frontend, or migration changes.
- Editing `answer_v1.md`.
- Changing `general_chat_json_schema()` or Web answer schema.
- A fallback that cites every retrieved fusion passage.
- A second answer or verifier call.

## Ordered actions

1. Add `AnswerParagraph` with contiguous `paragraph_index` `0..5`,
   `text` 1..4000 characters without an embedded `\n\n`, and 1..6
   existing `link_ids`.
2. Add nullable `paragraph_index` on `AnswerCitation` and
   `paragraphs` on `AnswerPayload`.
3. For live company answers, derive `answer_text` as
   `"\n\n".join(paragraph.text for paragraph in paragraphs)`.
4. Add immutable `answer_v2.md`. Require 1–6 paragraphs, at most 6
   links, at most 12 citations, and exact 1–1000 character spans copied
   from supplied canonical records.
5. Update `answer_json_schema()`: required `paragraphs`; required
   nullable `paragraph_index` on citations; `maxItems` 6 on paragraphs
   and atomic links; omit provider-authored `answer_text`.
6. Pin `ANSWER_PROMPT_VERSION` to `answer_v2` and the LF-normalized
   SHA-256 of the new file. Never guess the digest.
7. Implement deterministic company validation: contiguous indices,
   bounds, link/citation/paragraph agreement, fusion membership,
   `citation_span_aligns()`, table ranges, no orphans. Machine reasons
   include `paragraph_index_invalid`, `paragraph_unmapped`,
   `citation_span_required`, `citation_link_mismatch`,
   `citation_paragraph_mismatch`, and `answer_bounds_exceeded`.
8. Update verifier application: drop every paragraph that references an
   unsupported or omitted link, drop its citations, rebuild
   `answer_text`, mark `partial`, or refuse with no original prose if
   nothing survives.
9. Remove `ensure_fusion_source_citations()` from the production verify
   path. A live company answer with no valid paragraph mappings becomes
   `insufficient_evidence` or a citation-free refusal before verified
   tokens.
10. Update the mock gateway so company fixtures emit paragraph objects
    and exact spans copied from supplied source records. Mocks must pass
    the same substring check.

## Acceptance checks

- `answer_v2` is registered, hashed, and schema-tested.
- Two paragraphs map to two different chunks.
- Two citations can attach to one paragraph.
- Missing mapping, null/empty span, span/chunk mismatch, and
  citation/link/paragraph disagreement fail closed.
- Unsupported verifier links remove the owning paragraph and citations.
- All paragraphs removed produces a citation-free refusal.
- Seventh link and thirteenth citation fail bounds.
- General and Web payloads remain unaffected.
- One answer call and one verifier call remain unchanged.

## Negative tests

- `ensure_fusion_source_citations()` on the live verify path fails the
  packet.
- Streaming unsupported prose after its link is removed fails the
  packet.
- Editing `answer_v1.md` or guessing a SHA-256 fails the packet.

## Stop routes

- Stop if satisfying the request requires another model call beyond
  existing ceilings.
- Stop if company answers would stream before paragraph verification.
- Do not start P06-46 SQL, API, or frontend work in this packet.

## Required evidence

- Prompt version/hash, validation cases, verifier-removal cases, ruff,
  pyright, and pytest exits. Handoff: paragraph payload contract for
  P06-46 persistence.
