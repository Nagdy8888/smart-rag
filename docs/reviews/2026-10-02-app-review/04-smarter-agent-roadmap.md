---
title: Making the app smarter — modification roadmap
owner: engineering-lead
status: draft
last-reviewed: 2026-10-02
audience: eng, product, client-approver
---

# Making the app smarter — modification roadmap

Companion to [03-agent-brain-review.md](./03-agent-brain-review.md). Every item below
respects the plan's invariants: canonical Supabase evidence, ACL re-validation,
bounded budgets, typed refusals, and the ≤3 model calls per run envelope unless
explicitly noted and priced.

## Priority order (impact × effort)

| # | Change | Impact | Effort | Preserves grounding |
| --- | --- | --- | --- | --- |
| S1 | General extractive-answer mode (replace eval salvages) | High | M | Yes — spans come from canonical passages |
| S2 | Iterative multi-hop decomposition (bounded) | High | L-M | Yes — links cite every hop |
| S3 | Trust the model profile over regex signals | High | S | Yes — routing matrix unchanged |
| S4 | Post-turn conversation summarization | Med | S | Yes — memory is untrusted context |
| S5 | Related-question suggestions in Ask | Med | S | Yes — suggestions are retrieved, not generated claims |
| S6 | Semantic result cache for repeat asks | Med | M | Yes — cached rows re-check ACL |
| S7 | Query expansion with SME aliases at retrieval time | Med | S | Yes — expansion only feeds retrieval |
| S8 | Structured-table text-to-SQL for numeric asks | High | M-L | Yes — table provenance contract exists |
| S9 | Online eval loop with user feedback | Med | M | n/a (observability) |
| S10 | Arabic semantic retrieval upgrade | Med | M | Yes |
| S11 | One bounded verify→regenerate pass (drop unsupported claims only) | Med-High | M | Yes — the regenerated answer still passes deterministic checks + the ≤6-link verifier |

## S1 — General extractive-answer mode (replaces per-question scaffolding)

Today, literal/lookup questions are rescued by ~11 corpus-specific salvage
functions plus retrieval promotions plus prompt rules
(`generate_grounded.py:613-1015`, `rerank.py:428-668`, `answer_v4.md:33-45`). A
general mechanism covers the same cases without hard-coding:

1. The profile already detects literal-anchor asks (`rerank.py:807`,
   `literal_anchor_ask`, `_NUMBER_LITERAL`/`_HYPHEN_TOKEN` extractors in
   `generate_grounded.py:42-44`).
2. For that class, compute the best matching span in the top-ranked authorized
   passage(s) — the scoring helpers already exist (`_passage_query_overlap`,
   `_bounded_match_span`, `_best_evidence_match`, `generate_grounded.py:1528-1649`).
3. Emit the span verbatim as the first claim with its citation; pass the rest of
   the answer to the model as usual.

This is a generalization of `salvage_refused_literal_claims` (removed in G1a), which already did
query-anchored extraction for distinctive literals — it just only runs after a
refusal. Running the equivalent **before** generation, for literal-shaped asks,
removes the need for most per-question code. Roll out behind a flag, measure on
the holdout + the 100-question baseline, then deprecate the eval-specific list.

## S2 — Iterative multi-hop decomposition

The plan can carry up to three subquestions, but branches execute in one batch
(`query_routing/branches.py:execute_branches`); there is no "use hop-1's answer to
seed hop-2" step. Add a bounded loop in `company_scope`:

- Only for profiles classified `inference`/multi-hop with relationship signals.
- Hop N+1's retrieval seeds = entity IDs extracted from hop N's top passages
  (the graph adapter already returns typed entities — `retrieval/lightrag_structured.py`).
- Hard cap: existing branch budget + the single correction slot; no extra model
  calls — the answer stage still runs once.
- Every emitted `inference_link` keeps 1-2 citations as today; the composed
  conclusion is labeled inference (already enforced by `answer_v4.md:74-78`).

This attacks the weakest scorecard row (multi-hop ★★) within the current cost
envelope, because entity extraction from passages is deterministic.

## S3 — Trust the model profile over regex signals

`classify_knowledge_scope` (`knowledge_scope.py:354-470`) lets deterministic
regexes override the structured model payload, and `_needs_model`
(`preparation.py:91-128`) often skips the call entirely. Two safe inversions:

- When a profile payload exists with confidence ≥ threshold, use it unless a
  **company** signal fired (security-relevant direction stays regex-first).
- Widen `_needs_model` triggers: ambiguous scope, prior-turn topic switch, or
  non-greeting interrogatives all justify the single call.

Misrouting is the most user-visible "dumb" failure ("it answered from general
knowledge about our own docs" or vice versa). This is mostly configuration of
existing code paths, plus persisted-field sampling to watch drift.

## S4 — Post-turn conversation summarization

Memory load supports a compact store summary (`nodes/memory.py:80-99`), but the
query graph never writes one; follow-ups on long threads quietly lose context.
Add a worker-side job (worker owns job lifecycle per monorepo boundaries) that
summarizes the last K turns after a settled run, writing to the existing
`memory_store` namespace with the same `summary_v1` prompt. Bounded: one summary
job per conversation per N turns, skip when token count is below threshold.

## S5 — Related-question suggestions

`web_research/planner.py:propose_follow_ups` already proposes follow-ups for web
runs. Extend the pattern to company runs: after fusion, generate 2-3 candidate
next questions from the **selected evidence headings** (deterministic templates +
one optional small model call, or zero-call template mode). Suggestions are
rendered as chips that send a new run — they are retrieval aids, not claims, so
grounding is unaffected. This materially improves perceived intelligence and
guides users toward answerable phrasings.

## S6 — Semantic result cache

Repeat/near-repeat questions re-run the full paid pipeline. `hybrid_run/cache_lookup.py`
already has a cache path for hybrid runs — extend it to key on normalized query
and authorization_version and corpus generation, and add embedding-similarity lookup
(cosine ≥ 0.97 with profile-class match) for near-repeats. Cached answers must
re-check ACL/current-version (the batch recheck already exists for BM25 IDs) and
carry a "cached" transparency flag in SSE progress. Saves cost and turns
p95 latency into p50 for the common "ask again" case.

## S7 — Retrieval-time query expansion with SME aliases

The corpus already supports SME-seeded search terms/aliases (hybrid contract).
Wire the profile's `variants` and glossary (`glossary` tables + import flow exist)
into an expansion step: for each variant, one bounded BM25/vector query per the
existing max-per-variant RRF budget (`retrieval/hybrid_run/jobs.py`). No model
call needed; the variants come from the single prep payload. This directly
improves recall on paraphrases — the failure mode the eval salvages were
compensating for.

## S8 — Structured-table text-to-SQL (numeric aggregation)

`StructuredTable` routes exist for numeric aggregation
(`nodes/tables.py`, `tools/`), but natural-language aggregation over larger
corpora is limited to pre-composed tables. Next step: an allow-listed
text-to-SQL planner over registered table schemas with: identifier allow-list,
no DDL/DML, row/time caps, and results returned only as table records with cell
provenance (so the answer contract is unchanged). The disclosure/tooling
framework (`tools/catalog.py`, `disclosure.py`) already models side-effect-free
execution with progress events.

## S9 — Online evaluation loop

`evaluation/online.py` and `evaluation/agent_eval/langsmith.py` exist but the
loop is not continuous. Wire: (a) thumbs feedback from the chat UI into a
`feedback_usage` table (endpoint exists — `services/feedback_usage.py`), (b) a
weekly job that samples verified/partial/refused runs against holdout questions,
(c) route-matrix counters (misclassification rate, refusal rate, verifier skip
rate) into the governance dashboards. This turns every "make it smarter" change
into a measured bet instead of a vibe.

Operator path already available for private gold suites: run
`scripts/run_company_ask.py` then publish dual-metric scores to LangSmith via
`scripts/publish_company_ask_langsmith.py` (or `--langsmith-publish`). See
[COMPANY_ASK_LANGSMITH.md](../../evaluation/COMPANY_ASK_LANGSMITH.md). That
covers offline regression boards; continuous online sampling remains open.

## S10 — Arabic retrieval depth

Arabic normalization parity (`arabic_norm_v1`) is enforced on BM25. Remaining
gaps for smartness: (1) Arabic query expansion using the glossary import path
(`services/glossary_import.py`), (2) Arabic-aware chunk boundary heuristics in
`ingestion/chunking`, (3) bilingual synonym injection into `ll_keywords` for
LightRAG (precomputed per contract — no hidden calls). Measure with a dedicated
Arabic known-answer slice before/after.

## S11 — One bounded verify→regenerate pass

Today `verify_answer` is always terminal (`graph.py:213`; `MAX_ANSWER_CALLS = 1`), so
any unsupported link forces `verified_partial` even when the fix is trivial — drop
the bad claim and keep the rest. Add one conditional edge: when deterministic
checks reject at least one link but others survive, regenerate **once** from the
surviving evidence plus the verifier's failure reasons, then re-run deterministic
checks. Guardrails: one regeneration per run (extra model call from the existing
correction headroom in the envelope), never re-retrieval, and the second pass
must still pass the ≤6-link verifier. This directly reduces the
`verified_partial` rate — the most common "almost right" outcome users see.

## Explicitly rejected ideas

- **Unbounded agent loops / ReAct-style tool chaining** — violates the budget and
  bounded-work plan invariants; the deterministic spine is the product's moat.
- **Local cross-encoder reranker in v1** — plan says v1 has none; revisit only
  with an ablation that beats the current top-20 OpenAI rerank on the holdout.
- **Loose "chat with your docs" free-form answers without citations** — breaks
  the core promise; general scope already covers non-company chat with explicit
  labeling.
- **Auto-enabling graph indexing on ACL expansion** — forbidden by the database
  security contract (admin approval stays manual).

## Sequencing suggestion

1. Weeks 1-2: S3 + S4 (small, high-visible fixes; no new infra).
2. Weeks 2-4: S1 behind a flag with holdout measurement; begin S7.
3. Weeks 4-8: S2 bounded hop loop; S5 suggestions; S6 cache; S11 verify→regenerate.
4. Weeks 8+: S8 text-to-SQL design spike; S9 loop; S10 parity work.
