---
phase: 6
packet: 7
status: complete
title: "Implement Supabase checkpoints/store memory, idempotency/run-event GC, full governance enforcement, trace redaction, prompt versions, usage accounting, feedback, and immediate conversation deletion."
requirement_ids: [P06-07]
---

# Packet 7 — Implement Supabase checkpoints/store memory, idempotency/run-event GC, full governance enforcement, trace redaction, prompt versions, usage accounting, feedback, and immediate conversation deletion.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

## Preconditions

- Packets 1–6 are accepted; durable runs/reservations/usage/events, ownership, route/fusion/tool/API/SSE metrics, and deletion-denial hooks are available.
- Phase 3 has owner/client-signed [`OPENAI_DATA_GOVERNANCE.md`](../../../../../docs/security/OPENAI_DATA_GOVERNANCE.md) and [`SUBPROCESSOR_GOVERNANCE.md`](../../../../../docs/security/SUBPROCESSOR_GOVERNANCE.md). Missing, prohibited, unknown, or contradictory decisions block this packet.
- Phase 4 provides approved [`DATASET_SPEC.md`](../../../../../docs/evaluation/DATASET_SPEC.md), frozen split IDs/labels/baselines, and immutable holdout controls. Phase 6 consumes them and adds outcomes to existing case IDs; it does not recreate/relabel data or retune Phase 4 thresholds.

## Allowed outputs

- Supabase LangGraph checkpoint/store memory, retention/reapers, prompt versions/changelogs, redacted traces, governance enforcement, usage/feedback flows, CI/nightly/online evaluation additions, immediate conversation deletion, docs/tests/evidence.
- Additive schemas/jobs/configuration only when required for accepted checkpoint, retention, deletion, prompt, trace, feedback, or evaluation contracts.

## Forbidden outputs

- Raw files/full source duplication in checkpoints/store, unauthorized resume/history, automatic rewriting of old conversations after source deletion, process-only retention, reaper deletion of active/retryable keys, or coupling idempotency GC to budget reconciliation.
- Raw private documents, BM25 projection text, secrets, or unsigned external flows in LangSmith/Vercel/providers; governance claims beyond signed settings; holdout tuning/contamination; unbounded real-model evaluation; or ordinary retention delaying explicit conversation deletion.

## Ordered actions

1. Use Supabase-backed LangGraph checkpointing with `thread_id=conversation_id` and verify run/conversation ownership on every checkpoint, resume, and history path, except explicit owner/admin audited access.
2. Use LangGraph store only for compact conversation summaries and user preferences, never source-document copies. Summary generation is a budgeted gateway call. Past conversations remain point-in-time records; deleted-source citations are marked unavailable rather than rewriting history, and retention/offboarding governs undeleted conversations.
3. Implement a dedicated idempotent reaper: completed-run idempotency keys expire after the signed default seven days and completed events after 30 days. Keep it separate from budget reconciliation, never delete active/retryable keys, preserve one-paid-run behavior at expiry boundaries, and let explicit conversation deletion purge its keys/events immediately.
4. Centralize prompts under [`apps/agents/src/smart_rag_agents/prompts/`](../../../../../apps/agents/src/smart_rag_agents/prompts/) with immutable version IDs, changelogs, and approved environment promotion.
5. Trace every graph run with run name, hashed user identifier, run ID, requested/effective/corrected route, model/prompt versions, disclosed tools, per-channel candidate counts, BM25 index/version/lag/recheck/fallback, latency, tokens, cache, and cost. Redact production payloads and make private-content sampling explicit/configurable.
6. Enforce signed governance for answer, verification, summary, LangSmith, Supabase persistence, Vercel-visible metadata, and every other external flow. Do not recreate the governance packet or infer provider behavior.
7. Confirm the frozen dataset covers answer/source truth, acceptable variants, atomic links, expected refusal/route/profile, language, temporal intent, codes/entities/aliases, filters, ACL actors, and exact, alias, typo, factual, Arabic/mixed, selective-filter, temporal, multi-part/comparison, relationship, multi-hop, synthesis, table, refusal, graph mapping/version, ACL-negative, rewrite/profile, and injection cases.
8. Add CI/nightly evaluations, attached to existing case IDs, for:
   - Chunking/cleaning: retained-content coverage after declared boilerplate removal, heading/reading order, intact table/list units, token distribution, overlap, parent reconstruction, citation coordinates, exact/fuzzy duplicate precision/recall, and naive fixed-size ablation.
   - Query profile: per-field exact match/precision/recall/F1 for language/configuration, type, temporal intent/date, codes/numbers, entities/aliases, filters, relationship/table signals, and decomposition; attribute retrieval failure to the first failing stage.
   - Retrieval: per-channel/fused Recall@K, MRR/nDCG, raw/normalized Arabic BM25 and ta-marbuta ablation, English/mixed BM25, code/alias/typo accuracy, selective-filter BM25/HNSW recall/candidate sufficiency, projection/recheck/outage, temporal/ACL, graph entity/path recall, and complete route matrix.
   - Ablations: Phase 2 small/large/reduced embeddings; dense-only; BM25-only; populated trigram-only; dense+term without BM25; summed/max variant RRF; static/query-aware RRF; metadata/freshness multipliers; always/conditional rerank, pool sizes, skipped-case counterfactuals; parent expansion; class MMR; rewrites; global steering; naive Combined union; resolved-path fusion.
   - Per-profile accuracy, citation quality, p50/p95/deadline, graph survival/partial readiness, OpenAI token/cost including LightRAG internal/indexing calls, and fallback; promote complexity only for justified measured gain.
   - Answer faithfulness, atomic-link/composed-inference support, deterministic table correctness, citation correctness/completeness, insufficient-evidence refusal, role enforcement, and run ownership.
   - Original/rewrite fidelity, Hybrid→Combined correction precision/recall, profile keyword pass-through with zero hidden LightRAG keyword calls, statement/chunk→passage mapping precision/coverage, do-not-merge rules, atomic version switchover, graph-eligibility isolation, deleted-source suppression, and query idempotency/reconnect.
   - Injection: PDF/HTML/OCR instructions, citation forgery, tool inducement, adversarial entity/relation names, graph-extraction poisoning, and frontend XSS.
   - Tool discovery precision/success, unnecessary disclosure, and token reduction.
   - Malware/quarantine, parser escape/resource, SSRF redirect/DNS rebinding, OCR/parser, and re-ingestion/deletion idempotency.
   - Review routes: historical relationship → Hybrid + `temporal_graph_limitation`; whole-document coverage pass/refusal; negation clarification/proof/refusal; media limitation; authorized ACL-blindness with zero unauthorized disclosure.
   - Cache leak after delete/restrict with zero stale evidence; idempotency/event reaper retention and no duplicate paid run at expiry.
   - Additive OpenAPI/SSE evolution, unknown-event tolerance, and minimum-client handshake before paid work.
9. Feed explicit feedback to Supabase and LangSmith with separate tags: `chunk/cleaning loss`, `profile field wrong`, `candidate miss`, `wrong rerank`, `bad refusal/overconfident answer`, `missed relationship`, `wrong route`, `wrong calculation`, `bad citation`, and `insufficient graph`.
10. Run owner/admin/SME curation weekly during the pilot and first eight production weeks, then monthly only after failure/alias volume stabilizes. Promote approved aliases promptly and convert confirmed failures to a versioned post-launch regression set without reporting it as the immutable holdout.
11. Require versioned evaluation before router/prompt/profile/normalizer/chunking/threshold release. Mine only approved redacted profile failures for few-shots and keep all splits disjoint. Online evaluation uses a bounded sample and cost ceiling; no job makes unlimited real OpenAI calls.
12. Implement immediate conversation deletion in one Postgres transaction: verify ownership, tombstone, and remove messages, runs, sequenced events, citations/private feedback, checkpoint rows/namespaces, and summaries/preferences scoped only to that conversation. Every read/resume path denies as soon as the tombstone exists.
13. Durably request deletion of sampled LangSmith payloads within 24 hours and retry. Retain only content-free append-only deletion audit evidence and pseudonymized aggregate usage; undeleted-data retention windows do not delay deletion. Integration tests search every application/checkpoint/store table for the conversation ID.
14. Reconcile packet 1 immutable usage with trace/evaluation/feedback handles and company/user usage reporting without exposing private source text or changing budget truth.

## Acceptance checks

- Checkpoint/resume/history is Supabase-durable and ownership-safe; store content is compact memory only, summary calls are budgeted, and deleted-source citations are marked unavailable.
- Seven-day key and 30-day event defaults reap only completed data, preserve active/retryable and expiry-boundary one-paid-run semantics, and remain independent of budget reconciliation.
- Prompts/traces/usage are versioned, costed, redacted, and permitted by signed governance; prohibited or unknown external flows block.
- CI/nightly suites cover every listed category on frozen/disjoint data, preserve holdout isolation, enforce bounded online cost, and include route/fusion/tool/cache/reaper/API/SSE/privacy outcomes.
- Conversation deletion immediately denies reads and leaves no conversation-scoped application/checkpoint/store/private-feedback/event/citation state; LangSmith deletion is durably requested within 24 hours with only content-free audit and pseudonymized aggregate usage retained.
- Feedback tags, weekly-first-eight-weeks/monthly-later curation, alias approval, regression versioning, and release evaluation controls are implemented without contaminating the launch holdout.

## Negative tests

- Foreign resume/history, source document in store, unbudgeted summary, stale checkpoint after tombstone, active/retryable key reaped, seven/30-day boundary duplicate, GC triggering budget true-up, raw private trace/BM25 text/secret, unsigned external destination, prompt without version, holdout label read/tuning, unbounded evaluator, merged feedback tags, unapproved alias/few-shot, deletion partial commit, lingering ID in any table/namespace, read during deletion, LangSmith request not retried, or private deletion audit payload fails.

## Stop routes

- Stop if signed governance or frozen datasets are missing/contradictory, checkpointer/store deletion cannot be transactionally proven, external trace deletion lacks a durable retry path, retention can violate one-paid-run semantics, or evaluation would require holdout leakage/unbounded paid calls.
- Do not recreate governance, relabel data, weaken immediate deletion, or claim provider deletion beyond verified request/acknowledgment evidence.

## Required evidence

- Append to [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md): checkpoint/store schema and ownership traces, memory sizes/summary usage, reaper boundary tables, prompt/version manifests, governance decision mapping, redacted trace captures, frozen split/dataset hashes, CI/nightly/online evaluation reports and call ceilings, feedback/curation schedule, usage reconciliation, transactional deletion searches, 24-hour LangSmith retry evidence, exact commands/exit codes, deviations, rollback, and packet 8 handoff.
