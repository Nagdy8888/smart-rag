---
name: implement-observability-evals
description: Implements LangSmith tracing, prompt/version governance, redaction, usage accounting, feedback, labeled datasets, retrieval evaluations, and quality gates. Use for observability, prompts, metrics, evaluations, or tuning.
---

# Implement Observability and Evaluations

Read the global targets, the active phase wrapper/shared contract, exactly one selected packet, and only its linked evaluation/release contracts, plus `DATASET_SPEC.md` when it exists. Do not load sibling packets or reconstruct requirements from legacy section numbers.

Before sending company content to OpenAI, create and obtain owner/client sign-off on `docs/security/OPENAI_DATA_GOVERNANCE.md`. Enforce uploader category/authority attestation, local deterministic sensitive-pattern checks, owner/admin review, and `external_processing_allowed`; prohibited/unknown/contradictory content stays quarantined. Document detector limits and never claim content is excluded from training without tying it to contracted API settings.

## Trace contract

- Use explicit stable run/node names and carry request, run, user-safe, conversation, document-version, route, and job correlation IDs.
- Record model/prompt versions, latency, token/cost usage, reserve-once/true-up state, retries, fallbacks, per-channel ranks/filters, BM25 image/index/normalization version/projection lag/scanned/rechecked/degradation, mapping/survival, selected evidence IDs, and verifier results.
- Do not send raw files, unrestricted passages, secrets, JWTs, email addresses, signed URLs, or sensitive metadata to LangSmith.
- Apply redaction before export and test it with canary secrets/PII.
- Keep production tracing sampling configurable; retain local structured logs for unsampled operational metadata.

## Evaluation discipline

1. Version datasets, schemas, prompt/model/config, and code commit with every run.
2. Keep embedding qualification, tuning/development, immutable launch holdout, and post-launch regression sets distinct; never tune/select few-shots on holdout or report regressions as unbiased holdout.
3. Include chunk/cleaning fixtures, query-profile field labels, byte-identical Arabic Supabase-projection/core/ParadeDB normalization, seeded aliases/codes, query types, selective BM25/HNSW filters, stale BM25 ACL/current rows, BM25 query-syntax injection/outage/version mismatch, temporal/insufficient/contradictory cases, graph mappings, entity collisions, injections, deletion/ACL, tables, and version switchovers required by the plan.
4. Score structure/chunking, query-profile fields, candidate generation, fusion, reranking, coverage/refusal, routing/tools, retrieval, and answer quality as separate stages.
5. Compare each complex method against its simpler baseline:
   - Hybrid vs dense-only, BM25-only, exact-term-only, and dense+term BM25-outage degradation;
   - always-rerank top 20 vs conditional reranking with skipped-case counterfactuals;
   - Combined fusion vs naive union;
   - graph route vs Hybrid fallback;
   - progressive disclosure vs full schemas.
6. Tune BM25 field boosts/query forms, candidate depths, `rrf_k`/weights, rerank pool/triggers, MMR/context, and coverage thresholds per query class on development data; freeze before final holdout. Measure projection lag, index size/RAM, top-75 p95, and clean rebuild separately from answer quality.
7. Report latency/cost/answer-rate/refusal with quality; reject gains that violate signed-off budgets or hide unsupported confident answers.
8. Require SME adjudication for ambiguous labels and capture disagreement rather than forcing a fabricated gold answer.

Run feedback/alias/profile-failure curation weekly through pilot and the first eight production weeks, then monthly after volume stabilizes.

Never claim an evaluation passed from a handful of examples or a subjective answer review.
