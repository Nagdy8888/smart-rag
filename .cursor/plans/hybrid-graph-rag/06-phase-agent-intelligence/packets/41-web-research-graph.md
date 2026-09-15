---
phase: 6
packet: 41
status: complete
title: "Implement bounded iterative Web research graph, synthesis, verification, and fail-closed routes."
requirement_ids: [P06-41]
---

# Packet 41 — Implement bounded iterative Web research graph, synthesis, verification, and fail-closed routes.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md),
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md).

Do not load frontend skills.

## Preconditions

- P06-38 gateway DTOs and P06-39 persistence RPCs exist.
- Inspect `web_scope` stub, verifier, persist, progress, crawl proxy,
  and answer prompts.

## Allowed outputs

- `packages/core/src/smart_rag_core/web_research/` planner, bounds, prompt
  isolation, URL policy glue, and synthesis helpers
- Agent `nodes/web_scope.py` replacing the stub, plus critique/answer
  prompts, deps/runtime/progress wiring
- Search → critique → optional 1–2 follow-up searches (combined cap 12)
  → batched contents → optional crawl-proxy fallback for Exa-failed URLs
- Persist `web_sources` before synthesis. Empty company/table citations.
  `answer_origin=web`. Verify then persist `web_citations`
- Tests: `tests/unit/test_web_research_graph.py` and additive verifier/
  persist/progress tests
- Docs: QUERY_ROUTING, ANSWER_VERIFICATION, SSE progress, packet evidence

## Forbidden outputs

- Company retrieval, LightRAG, BM25, tables, or uncited general fallback
  on the Web path
- Sending company passages, memory, IDs, JWTs, or signed URLs to Exa
- Direct `httpx` from API/agent to result URLs
- Draft `token_delta` before verification
- SSE excerpts, bodies, keys, or full query text
- More than two rounds, six sources, five external ops, or 50s deadline
- Optional-tool catalog `web_search`

## Ordered actions

1. Inject Exa and crawl-proxy ports. Never construct them inside nodes.
2. Query text sent to Exa is rewritten user text only. Strip emails,
   UUIDs, JWTs, and signed-URL patterns.
3. Bound search formulations to three; candidates to twelve per round.
4. Persist operations through P06-39 RPCs. Ambiguous ops fail closed.
5. Treat fetched text as prompt-injection. Unique source-id delimiters.
   Model may cite only persisted `web_source_id`s.
6. Verifier uses Web excerpt store, not company chunks. Span must be a
   substring of the stored excerpt.
7. Progress keys: `web_search` → “Searching…”, `web_read` → “Reading…”,
   `verify_answer` → “Verifying…”.
8. Empty/unsafe/insufficient evidence returns
   `web_evidence_insufficient` or `web_content_unavailable`.

## Acceptance checks

- Two-round happy path persists ≤6 sources and ≤12 citations.
- Third round is never attempted.
- Disabled Web and quota/auth/timeout map to typed codes.
- Ambiguous operation does not retry.
- Verifier rejects invented source ids and non-contained spans.
- Company citation list on a Web answer is empty.
- Cancellation closes the HTTP client and does not leak the key.

## Negative tests

- Prompt containing a company passage is never sent to Exa.
- Crawl-proxy is not called for a URL that was not an Exa candidate.
- SSE custom payloads omit query, URL bodies, and excerpts.

## Stop routes

- Stop if verification cannot bind a citation to a persisted excerpt.
- Stop if crawl-proxy fallback would fetch a non-candidate URL.
- Stop if hold-until-verify would be broken.

## Required evidence

- Bound counters, operation states, verifier cases, progress keys, and
  frontend-contract handoff to P06-42.
