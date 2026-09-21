---
name: hybrid-graph-rag-phase-06-agent-intelligence
phase: 6
status: pending
split_source: true
depends_on: [1, 2, 3, 4, 5]
source_plan: ../hybrid-graph-rag_ab5281ef.plan.md
global_contract: ./00-global-contracts.md
---

# Phase 6: Agent intelligence

## Mandatory model loading contract

1. Read [`00-global-contracts.md`](./00-global-contracts.md) first, then this wrapper, then [`00-shared-contracts.md`](./06-phase-agent-intelligence/00-shared-contracts.md), then exactly one linked packet below.
2. Treat that four-file set as the only implementation scope for the active Phase 6 packet. Do not load or implement another Phase 6 packet in the same model run; later-phase files may clarify an interface but do not authorize later-phase implementation.
3. Inspect the current repository, schemas, migrations, tests, and pinned dependency versions before editing. This plan describes targets, not proof that a file or API already exists.
4. Load the relevant workspace skill files listed below before implementation.
5. Before the active work packet, quote its linked checkbox label, state the requirement and concrete acceptance checks, and implement the smallest complete packet.
6. Verify unstable external APIs against current primary documentation and add contract tests. Never guess a library method, schema, environment variable, command, or provider behavior.
7. Add positive, failure, authorization, idempotency, bounded-resource, and fallback tests whenever applicable.
8. Run repository-defined format, lint, strict type, test, build, migration, and integration commands relevant to changed files. Phase 1 must define these commands; later phases must inspect rather than invent them.
9. Update documentation in the same change. Do not leave placeholders, fake success paths, swallowed errors, disabled security, or `TODO` core behavior.
10. Record proof in [`docs/development/phase-06-agent-intelligence-evidence.md`](../../../docs/development/phase-06-agent-intelligence-evidence.md). If security, data semantics, cost, or acceptance criteria must change, stop and obtain approval through an ADR/plan update.

## Prerequisites

[Phase 1: Foundation](./01-phase-foundation.md), [Phase 2: Identity and data](./02-phase-identity-data.md), [Phase 3: Ingestion](./03-phase-ingestion.md), [Phase 4: Hybrid RAG](./04-phase-hybrid-rag.md), [Phase 5: GraphRAG](./05-phase-graphrag.md)

## Relevant workspace skills

- [`.cursor/skills/implement-query-agent/SKILL.md`](../../../.cursor/skills/implement-query-agent/SKILL.md)
- [`.cursor/skills/implement-api-security/SKILL.md`](../../../.cursor/skills/implement-api-security/SKILL.md)
- [`.cursor/skills/implement-observability-evals/SKILL.md`](../../../.cursor/skills/implement-observability-evals/SKILL.md)
- [`.cursor/skills/implement-rag-frontend/SKILL.md`](../../../.cursor/skills/implement-rag-frontend/SKILL.md)

## Scope lock

**In scope:** Query LangGraph, deterministic route composition, grounding and verification, progressive optional tools, FastAPI/SSE, durable budgets, rate-limit degradation, observability, conversation privacy, and the thin developer UI.

**Out of scope:** Stitch production design, complete production frontend, release-candidate qualification, and managed deployment.

The scope lock controls implementation sequencing; it does not weaken any security, authorization, durability, budget, grounding, bounded-work, or documentation invariant in the global contract.

## Ordered work packets

Complete these in order. A checked box requires committed implementation evidence in the phase exit record, not only code presence.

1. [x] [Implement authenticated, idempotent run admission with server-derived database authorization, deadlines, recursion/model/tool ceilings, durable reservations, read-access auditing, and authorized runtime context.](./06-phase-agent-intelligence/packets/01-admission-budgets.md)
2. [x] [Implement memory rewrite, extended typed profiling, the complete deterministic route/limitation matrix, one global correction, and bounded parallel branches.](./06-phase-agent-intelligence/packets/02-profiling-routing.md)
3. [x] [Implement resolved-path Combined fusion and ablation, deterministic table composition, canonical answer evidence, inference-link citations, and layered verification.](./06-phase-agent-intelligence/packets/03-combined-fusion.md)
4. [x] [Implement the optional-tool registry/disclosure contract while keeping core retrieval and verification outside catalog discovery.](./06-phase-agent-intelligence/packets/04-optional-tools.md)
5. [x] [Implement thin FastAPI routers/services, Supabase-Auth/FastAPI rate ownership, authorization-safe retrieval caching, endpoint-specific authorization, CPU offload, and prompt/data isolation.](./06-phase-agent-intelligence/packets/05-fastapi-security.md)
6. [x] [Implement versioned additive API/SSE contracts, compatibility handshake, resumable fetch SSE with persisted sequence IDs, heartbeats, cancellation, reconnect, sanitized errors, and deadline/partial events.](./06-phase-agent-intelligence/packets/06-sse-compatibility-resume.md)
7. [x] [Implement Supabase checkpoints/store memory, idempotency/run-event GC, full governance enforcement, trace redaction, prompt versions, usage accounting, feedback, and immediate conversation deletion.](./06-phase-agent-intelligence/packets/07-memory-governance-evaluation.md)
8. [x] [Ship the thin authenticated developer UI and prove route, fallback, injection, idempotency, budget, outage, event-loop, and privacy gates.](./06-phase-agent-intelligence/packets/08-thin-developer-ui.md)

Packets P06-09 through P06-72 are additive after the completed historical packets. Do not uncheck packets 1–8. P06-14 is a Phase 6/Phase 8 co-owned UI amendment and must not renumber active P08-22/P08-23. P06-16 is the co-owned custom-progress and paced-reveal contract. P06-17 and P06-18 are the 2026-09-09 private-PDF agent evaluation and holdout overlay; they do not start until Packet 9 is accepted and Packet 10 includes the production rerank/scope contract. Packets P06-19 through P06-26 are the 2026-09-10 local PDF evaluation workspace overlay. Packets P06-27 through P06-36 are the 2026-09-10 hosted webapp evaluation amendment. Packets P06-37 through P06-43 are the 2026-09-10 advanced web research overlay. Packets P06-44 through P06-48 are the 2026-09-15 PDF paragraph-citation overlay. Packets P06-49 through P06-57 are the 2026-09-16 live RAG failure remediation overlay. Packets P06-58 through P06-64 are the 2026-09-17 general Hybrid retrieval accuracy overlay. Packets P06-65 through P06-72 are the 2026-09-21 honest RAG accuracy repair overlay. Integrity requires contiguous packet numbers, so Web packets follow P06-36, citation packets follow P06-43, live-failure packets follow P06-48, retrieval-accuracy packets follow P06-57, and honest-accuracy packets follow P06-64. After P06-41, execute P06-44 through P06-48, then resume P06-42, P06-43, then P06-49 through P06-57, then P06-58 through P06-64, then P06-65 through P06-72, then leftover P06-17. Do not reuse P06-27 through P06-64 for honest-accuracy work. Do not mark P06-17, P06-18, or Phase 6 complete in this overlay. Do not check P06-62, P06-63, or P06-64 until live evidence proves their remaining items.

9. [x] [Canonical amendment for general-chat strict-split, ADR, and packets P06-10 through P06-15.](./06-phase-agent-intelligence/packets/09-canonical-general-chat-amendment.md)
10. [x] [Implement typed knowledge-scope classification, the live profile gateway, and deterministic route compilation.](./06-phase-agent-intelligence/packets/10-knowledge-scope-routing.md)
11. [x] [Drain successful LangGraph streams and classify expected cancellation without hiding real trace errors.](./06-phase-agent-intelligence/packets/11-sse-stream-lifecycle-tracing.md)
12. [x] [Implement bounded, budgeted general and user-text model answers without weakening document grounding.](./06-phase-agent-intelligence/packets/12-general-chat-execution.md)
13. [x] [Add authenticated query_studio_live with per-run resources and normal ACL, admission, and budget controls.](./06-phase-agent-intelligence/packets/13-authenticated-studio-live.md)
14. [x] [Add answer-origin, clarification, and citation-safe behavior to the main chat UI.](./06-phase-agent-intelligence/packets/14-chat-origin-ux.md)
15. [x] [Run all deterministic and live gates, inspect LangSmith traces, and update evidence and runbooks.](./06-phase-agent-intelligence/packets/15-integrated-verification.md)
16. [x] [Add LangGraph custom SSE progress and paced verified-answer presentation contract.](./06-phase-agent-intelligence/packets/16-sse-custom-progress.md)
17. [ ] [Qualify PDF Hybrid agent answers on development and qualification without reusing the synthetic judge.](./06-phase-agent-intelligence/packets/17-pdf-agent-evaluation.md)
18. [ ] [Execute one immutable private-PDF holdout and close with redacted evidence.](./06-phase-agent-intelligence/packets/18-pdf-holdout-close.md)
19. [x] [Authorize the local-only PDF evaluation workspace overlay, ADR, and packets P06-20 through P06-26.](./06-phase-agent-intelligence/packets/19-local-pdf-evaluation-overlay.md)
20. [x] [Implement the local private-file evaluation store and source-bound draft generation.](./06-phase-agent-intelligence/packets/20-pdf-eval-workspace-store.md)
21. [x] [Implement the local-only owner/admin PDF evaluation API and passage lookup.](./06-phase-agent-intelligence/packets/21-pdf-eval-workspace-api.md)
22. [x] [Add the Admin Evaluation workspace for review, approval, and AI comparison.](./06-phase-agent-intelligence/packets/22-pdf-eval-workspace-ui.md)
23. [x] [Implement conservative PDF heading extraction for structure-aware chunking.](./06-phase-agent-intelligence/packets/23-pdf-heading-extraction.md)
24. [x] [Add ranked-ID channel diagnostics and local evaluation baseline tooling.](./06-phase-agent-intelligence/packets/24-pdf-eval-channel-diagnostics.md)
25. [x] [Repair measured Hybrid candidate and rerank failures without opening holdout.](./06-phase-agent-intelligence/packets/25-pdf-eval-retrieval-repair.md)
26. [x] [Wire ACL-safe retrieval caching and record Combined plus holdout gates.](./06-phase-agent-intelligence/packets/26-retrieval-cache-and-holdout-gates.md)
27. [x] [Authorize the hosted-evaluation workspace amendment, ADR, and packets P06-28 through P06-36.](./06-phase-agent-intelligence/packets/27-hosted-webapp-evaluation-amendment.md)
28. [x] [Implement hosted quiz-case schema, gold rows, and app_api RPCs.](./06-phase-agent-intelligence/packets/28-eval-quiz-case-database.md)
29. [x] [Replace the HTTP file store with a typed DB-backed case API.](./06-phase-agent-intelligence/packets/29-eval-quiz-case-api.md)
30. [x] [Add durable exam-run, result, report, and hidden-conversation database contracts.](./06-phase-agent-intelligence/packets/30-eval-exam-database.md)
31. [x] [Implement the restart-safe production-corpus Hybrid exam runner.](./06-phase-agent-intelligence/packets/31-eval-exam-runner.md)
32. [x] [Expose exam start, poll, cancel, latest report, and missed-case APIs.](./06-phase-agent-intelligence/packets/32-eval-exam-api.md)
33. [x] [Add owner/admin Save to quiz beside existing thumbs feedback.](./06-phase-agent-intelligence/packets/33-ask-quiz-capture.md)
34. [x] [Implement Admin case review, gold picker, stale repair, and draft regeneration.](./06-phase-agent-intelligence/packets/34-admin-eval-curation.md)
35. [x] [Implement the Admin Recall@10 scoreboard, exam progress, and qualification confirmation.](./06-phase-agent-intelligence/packets/35-admin-exam-board.md)
36. [x] [Run integrated verification, reconcile docs, and write the close evidence.](./06-phase-agent-intelligence/packets/36-hosted-eval-verification.md)
37. [x] [Authorize advanced web research overlay, ADR, and packets P06-38 through P06-43.](./06-phase-agent-intelligence/packets/37-advanced-web-research-amendment.md)
38. [x] [Implement bounded Exa REST gateway, configuration, and controlled provider egress.](./06-phase-agent-intelligence/packets/38-exa-rest-gateway-controlled-egress.md)
39. [x] [Add durable run-scoped web evidence, URL citations, and merged source_kind listing.](./06-phase-agent-intelligence/packets/39-run-web-evidence.md)
40. [x] [Implement four-mode admission, Auto default, exactly-one-source routing, and Web envelope.](./06-phase-agent-intelligence/packets/40-four-mode-admission-routing.md)
41. [x] [Implement bounded iterative Web research graph, synthesis, verification, and fail-closed routes.](./06-phase-agent-intelligence/packets/41-web-research-graph.md)
42. [x] [Implement four-option Ask dropdown, Web origin, progress, citations, and resume.](./06-phase-agent-intelligence/packets/42-four-mode-ask-ux.md)
43. [x] [Verify integrated Web gates, then resume P06-17.](./06-phase-agent-intelligence/packets/43-web-research-gates.md)
44. [x] [Authorize PDF paragraph-citation overlay, ADR, and packets P06-45 through P06-48.](./06-phase-agent-intelligence/packets/44-pdf-paragraph-citations-amendment.md)
45. [ ] [Implement structured paragraph mappings, exact spans, and fail-closed verification.](./06-phase-agent-intelligence/packets/45-pdf-paragraph-grounding.md)
46. [ ] [Persist ACL-safe PDF citation traces, page repair, and conversation history.](./06-phase-agent-intelligence/packets/46-pdf-citation-persistence.md)
47. [ ] [Render book title, PDF viewer page, and exact excerpt beside each answer paragraph.](./06-phase-agent-intelligence/packets/47-inline-pdf-citation-ui.md)
48. [ ] [Prove PDF citation accuracy across regression, authorization, history, and UI gates.](./06-phase-agent-intelligence/packets/48-pdf-citation-gates.md)
49. [x] [Authorize live RAG failure remediation overlay, ADR, and packets P06-50 through P06-57.](./06-phase-agent-intelligence/packets/49-live-rag-failure-remediation-amendment.md)
50. [x] [Implement deterministic evidence fitting, exact duplicate suppression, typed overflow handling, and answer/deadline reserves with Q15 regressions.](./06-phase-agent-intelligence/packets/50-bound-answer-context.md)
51. [x] [Version answer/verifier prompts, release only supported atomic claims, and remove all-fusion citation backfill with MCP regressions.](./06-phase-agent-intelligence/packets/51-grounded-claim-release.md)
52. [x] [Map insufficient evidence/refusal/deadline to one truthful partial outcome and unify visible/accessibility copy.](./06-phase-agent-intelligence/packets/52-graceful-terminals.md)
53. [x] [Add additive transcript-v2 run metadata and ACL-safe bounded citation-detail contracts.](./06-phase-agent-intelligence/packets/53-run-linked-transcript.md)
54. [x] [Restore per-turn citations and feedback after reload and add accessible conversation deletion confirmation.](./06-phase-agent-intelligence/packets/54-restore-frontend-state.md)
55. [x] [Add bounded transient reconnect behavior, stale SSE connection retirement, and honest query-runtime readiness.](./06-phase-agent-intelligence/packets/55-postgres-readiness.md)
56. [x] [Use the approved local host-worker parser topology and prove sequential Exa runs without cross-loop cleanup errors.](./06-phase-agent-intelligence/packets/56-worker-async-lifecycle.md)
57. [x] [Run full deterministic/live/browser gates and existing P06-17 development/qualification without opening holdout.](./06-phase-agent-intelligence/packets/57-integrated-qualification.md)
58. [x] [Authorize general Hybrid retrieval accuracy overlay, ADR, and packets P06-59 through P06-64.](./06-phase-agent-intelligence/packets/58-hybrid-retrieval-accuracy-amendment.md)
59. [x] [Create a tested, private-safe dual-metric and stage-attribution retrieval baseline.](./06-phase-agent-intelligence/packets/59-dual-metric-stage-baseline.md)
60. [x] [Implement authorized source resolution, ranking-query title stripping, and post-ACL duplicate collapse.](./06-phase-agent-intelligence/packets/60-source-aware-ranking.md)
61. [x] [Repair term and BM25 candidate generation and selectively enrich indexed search terms.](./06-phase-agent-intelligence/packets/61-term-bm25-candidate-repair.md)
62. [ ] [Repair retrieve-time durable call accounting and qualify a measured immutable long-document profile.](./06-phase-agent-intelligence/packets/62-rerank-accounting-long-document.md)
63. [ ] [Exclude source-selector false refusals and require a measured, revalidated correction.](./06-phase-agent-intelligence/packets/63-coverage-correction-semantics.md)
64. [ ] [Qualify disjoint retrieval classes, rerun the company-document regression, and publish redacted evidence.](./06-phase-agent-intelligence/packets/64-live-qualification-evidence.md)
65. [x] [Authorize the detailed honest accuracy overlay, ADR, and packets P06-66 through P06-72.](./06-phase-agent-intelligence/packets/65-honest-rag-accuracy-amendment.md)
66. [x] [Deploy the reviewed seven-argument term RPC and prove live term_unavailable is gone.](./06-phase-agent-intelligence/packets/66-term-rpc-live.md)
67. [x] [Add owner/admin document title rename and reindex one canonical copy.](./06-phase-agent-intelligence/packets/67-canonical-document-title.md)
68. [x] [Persist ID-only Hybrid branch diagnostics and de-hardcode promotion inputs.](./06-phase-agent-intelligence/packets/68-stage-diagnostics.md)
69. [ ] [Seal private aliases, isolation-slice gold, and the frozen 30-question acceptance sample.](./06-phase-agent-intelligence/packets/69-seal-private-gold.md)
70. [ ] [Run the four-arm isolation experiment and name the owning failure stage.](./06-phase-agent-intelligence/packets/70-stage-isolation.md)
71. [ ] [Implement one bounded repair for the proven dominant stage.](./06-phase-agent-intelligence/packets/71-proven-stage-repair.md)
72. [ ] [Qualify live accuracy, publish redacted evidence, and leave leftover P06-17 open.](./06-phase-agent-intelligence/packets/72-live-qualification.md)

## Approved planned deviation: general-chat strict split

User approval on 2026-08-25; 2026-08-26 remediation accepted 2026-09-10: add a strict dual-mode assistant to the production Ask path and a separate live LangSmith Studio graph. General questions may use OpenAI world knowledge. Company/document questions remain citation-required RAG. Genuine mixed scope returns clarification. Failed or low-confidence profile inference records typed degradation and may return an honest general answer that explicitly says company documents were not searched. Never fall back from insufficient company evidence to world knowledge.

- Recorded in [`docs/adr/ADR-general-chat-strict-split.md`](../../../docs/adr/ADR-general-chat-strict-split.md).
- Preserve `query_studio` as the deterministic, unbound, no-cost graph. Live retrieval uses only `query_studio_live` with a real developer JWT.
- No service-role key or synthetic live identity is permitted.
- The production query path may spend one counted `profile` call under existing caps. Pure greetings/small talk are profile-model classified and general-model answered, normally consuming one profile plus one answer call.
- Keep existing scope values and route families. Deterministic company signals override model output; a server-derived degradation reason never authorizes evidence.
- After plan compilation, validated plans select explicit company, general, mixed, or fail-closed nodes. Direct paths skip retrieval/correction/fusion/table/tool/verifier-model work and still receive deterministic verification.
- P06-10 remains the first historical coding packet after the P06-09 markdown amendment. User-approved 2026-09-10 overlay packets P06-19 through P06-26 run before Packet 10. After P06-26, execute P06-27, then Packet 10, then P06-28 through P06-36, then P06-11.

## Approved planned deviation: local PDF evaluation workspace

User approval on 2026-09-10: after Packet 9, prioritize a local-only owner/admin PDF evaluation workspace, label repair, and evidence-driven retrieval diagnosis before Packet 10 coding. Historical P06-19 through P06-26 remain. Hosted-label custody is superseded by the deviation below.

- Recorded in [`docs/adr/ADR-local-pdf-evaluation-workspace.md`](../../../docs/adr/ADR-local-pdf-evaluation-workspace.md) (superseded for custody and official Recall@10).
- FastAPI uses `app_api` plus server-derived owner/admin identity. Operator and service-role DSNs are forbidden on this path.
- Holdout files remain outside the repository. The workspace never lists, fetches, or opens holdout.
- Automatic drafts may propose extractive questions. A named human must approve. The answering model receives only the question.
- Do not freeze `hybrid_long_document_v1`, retune frozen Hybrid weights, or open holdout until grounded labels and open-split gates pass.

## Approved planned deviation: hosted webapp evaluation workspace

User approval on 2026-09-10: store quiz questions, expected answers, gold metadata, and exam state in the existing hosted Supabase project. Day-to-day evaluation happens in the local/test webapp. The web exam measures production-corpus Hybrid Recall@10 (all required gold chunks in the signed-in examiner's production Hybrid top 10). Ordinary thumbs feedback stays. Holdout and freeze stay out.

- Recorded in [`docs/adr/ADR-hosted-webapp-evaluation-workspace.md`](../../../docs/adr/ADR-hosted-webapp-evaluation-workspace.md).
- Integrity keeps packet numbers contiguous, so hosted packets are P06-27 through P06-36. Execute P06-27, then existing Packet 10, then P06-28 through P06-36, then resume P06-11.
- RLS, `app_api` RPCs, content-free audit, immediate delete, and 365-day retention are mandatory. Browser clients never talk to evaluation tables.
- Staging and production keep `PDF_EVAL_WORKSPACE_ENABLED` false. Packet 29 may default the local Compose flag to true.
- Rollback disables `PDF_EVAL_WORKSPACE_ENABLED`. Do not down-migrate populated hosted tables.

## Approved planned deviation: advanced web research mode

User approval on 2026-09-10: add Ask dropdown Auto, Company documents, General, Web. Auto is the default and chooses exactly one source. Web research uses Exa locally with `WEB_SEARCH_ENABLED`. Staging and production reject the flag.

- Recorded in [`docs/adr/ADR-advanced-web-research.md`](../../../docs/adr/ADR-advanced-web-research.md).
- Integrity keeps packet numbers contiguous, so Web packets are P06-37 through P06-43. Do not reuse P06-27 through P06-36. After P06-43, resume P06-17.
- Web is a deterministic `web_scope` subgraph. Search and page-read are injected ports, not optional catalog tools.
- Never blend company documents and Web. Never fall back from insufficient company evidence to Web.
- Rollback sets `WEB_SEARCH_ENABLED=false`. Do not down-migrate populated Web tables.

## Approved planned deviation: PDF paragraph citations

User approval on 2026-09-15: company-PDF answers cite each factual paragraph with the canonical document title, the 1-based PDF viewer file page (`page_index + 1`), and an ACL-checked exact supporting excerpt of at most 1000 characters. Printed `page_label` stays in locators and must not drive the chat page. General, user-text, deterministic, and Web answers stay unchanged.

- Recorded in [`docs/adr/ADR-pdf-paragraph-citations.md`](../../../docs/adr/ADR-pdf-paragraph-citations.md).
- Integrity keeps packet numbers contiguous after P06-43, so overlay packets are P06-44 through P06-48. Do not reuse P06-37 through P06-43.
- Execute after P06-41, then resume P06-42, P06-43, then P06-17.
- Creator-owned citation GET may return the bounded excerpt only after live run-ownership and chunk ACL/current-version/deletion recheck. SSE stays ID/ordinal metadata.
- Missing, ambiguous, unsupported, or uncontained mappings fail closed. Retrieval is not citation proof. Legacy null-span rows stay unmapped.
- Rollback stops using `answer_v2` and `list_run_citations_v4` in application code. Do not down-migrate populated citation rows. Do not present `page_label` as the PDF viewer page.

## Approved planned deviation: live RAG failure remediation

User approval on 2026-09-16: bound company evidence to the existing model input limit, release only verifier-supported claims, map expected refusals to one truthful partial terminal, add additive transcript run metadata and citation detail, restore Sources/feedback after reload, reconnect stale Postgres sockets, and use the documented local host-worker plus same-loop Exa clients. Do not raise `MODEL_INPUT_MAX_CHARS`. Do not open holdout.

- Recorded in [`docs/adr/ADR-live-rag-failure-remediation.md`](../../../docs/adr/ADR-live-rag-failure-remediation.md).
- Integrity keeps packet numbers contiguous after P06-48, so overlay packets are P06-49 through P06-57. Do not reuse P06-44 through P06-48.
- Execute after P06-48, then P06-58 through P06-64, then P06-65 through P06-72, then leftover P06-17. Do not mark P06-17, P06-18, or Phase 6 complete. Do not open P06-18.
- New company prompt pins are `answer_v3` and `verifier_v2` because `answer_v2` already owns PDF paragraph citations.
- Transcript SQL is `app.list_conversation_messages_v3` because v2 already returns `run_id`. Keep v1 and v2 callable. Company citation-detail excerpt remains 1–1000 characters.
- Company insufficient evidence never falls back to Web or general knowledge.
- Rollback stops using the fit/renderer/v3 transcript/citation-detail/reconnect/host-worker overlay in application code. Do not down-migrate populated rows.

## Approved planned deviation: general Hybrid retrieval accuracy

User approval on 2026-09-17: repair the general Hybrid retrieval path for future company-document questions without embedding the sample PDF, its 100 prompts, or its answers in production logic. Use dual metrics, authorized source resolution, ranking-query title stripping, post-ACL exact-duplicate collapse, term/BM25 candidate repair, retrieve-time accounting, a measured long-document profile, and coverage/correction repair. Keep existing security, grounding, deadline, and cost gates.

- Recorded in [`docs/adr/ADR-hybrid-retrieval-accuracy.md`](../../../docs/adr/ADR-hybrid-retrieval-accuracy.md).
- Integrity keeps packet numbers contiguous after P06-57, so overlay packets are P06-58 through P06-64. Do not reuse P06-49 through P06-57.
- Execute after P06-57, then P06-65 through P06-72, then leftover P06-17. Do not mark P06-17, P06-18, or Phase 6 complete. Do not open P06-18.
- Production code, prompts, profiles, migrations, and tests must contain no sample-PDF hash, book title, question ID, gold phrase, expected answer, page number, or benchmark-specific alias.
- Do not mutate frozen `hybrid_default_v1` bytes in place. Do not pin the failed `hybrid_long_document_v1.json` digest. Do not raise `MODEL_INPUT_MAX_CHARS`. Do not fall back from company documents to Web or general knowledge. Do not delete documents automatically.
- Rollback disables the overlay in application code and restores prior frozen Hybrid pins. Do not down-migrate populated rows. Do not delete live documents as rollback.

## Approved planned deviation: honest RAG accuracy repair

User approval on 2026-09-21: measure the live Hybrid path honestly, deploy the reviewed seven-argument term RPC, add owner/admin document title rename, reindex one canonical copy, persist ID-only diagnostics, human-seal private gold, isolate one owning failure stage, repair only that stage, qualify live Ask, merge only after GitHub jobs are green, then score a frozen 30-question PDF sample. Keep existing security, grounding, deadline, and cost gates.

- Recorded in [`docs/adr/ADR-honest-rag-accuracy.md`](../../../docs/adr/ADR-honest-rag-accuracy.md).
- Integrity keeps packet numbers contiguous after P06-64, so overlay packets are P06-65 through P06-72. Do not reuse P06-58 through P06-64.
- Execute after P06-64, then leftover P06-17. Do not mark P06-17, P06-18, or Phase 6 complete. Do not open P06-18. Do not check P06-62, P06-63, or P06-64 until live evidence proves remaining items.
- Production code, prompts, profiles, migrations, and tests must contain no sample-PDF hash, book title, question ID, gold phrase, expected answer, page number, or benchmark-specific alias.
- Missing required live fields are `unknown` and block promotion. `runs.route_family` is the admission envelope, not the effective retrieve route. Script exit 0 is not accuracy evidence.
- Do not mutate frozen `hybrid_default_v1` bytes in place. Do not pin the failed `hybrid_long_document_v1.json` digest. Do not raise `MODEL_INPUT_MAX_CHARS`. Do not fall back from company documents to Web or general knowledge. Do not delete documents automatically. Do not merge with `gh pr merge --admin`.
- Rollback disables the overlay in application code and restores prior frozen Hybrid pins. Do not down-migrate populated rows. Do not delete live documents as rollback.

## Phase sequence requirement

**Program sequence item 6:** Agent intelligence covers deadline-bounded LangGraph, complete composable route matrix, escalation, deterministic Combined fusion/ablation, inference verification, optional-tool disclosure, memory, resumable streaming, reserve-once durable budgets, Valkey-down rate behavior, bounded CPU offload/event-loop telemetry, conversation deletion, traces, and thin UI.

## Stop conditions

Stop this phase and report the blocker instead of improvising when:

- a prerequisite phase or required sign-off is incomplete;
- the actual repository contradicts the plan and the difference changes security, data, cost, or acceptance semantics;
- a required dependency contract cannot be verified from its pinned version and primary documentation;
- an authorization, idempotency, deadline, budget, provenance, or fallback test cannot exercise the real boundary;
- a required integration is unavailable and only a fake or skipped test would pass;
- any launch-blocking check fails after bounded repair attempts.

## Required exit record

Create or update [`docs/development/phase-06-agent-intelligence-evidence.md`](../../../docs/development/phase-06-agent-intelligence-evidence.md), linked from the repository documentation index, with:

- plan requirement and work-packet number;
- files, migrations, APIs, environment variables, and documentation changed;
- exact verification commands discovered from the repository;
- test/build/lint/type/migration results and relevant measured metrics;
- authorization, failure, idempotency, fallback, and bounded-resource evidence;
- unverified external assumptions or unavailable managed-environment checks;
- deviations, ADR approval, and rollback notes;
- explicit handoff inputs and open blockers for the next phase.

Do not set `status: complete` until every `Done when` item below is proven.

## Canonical detailed requirements

The Phase 6 runtime Hybrid dependency contract and legacy Sections 8–11 are redistributed into the shared contract and eight historical packets. Additive packets P06-09 through P06-15 record the approved general-chat strict-split amendment. Additive packet P06-16 records the co-owned LangGraph custom SSE progress and paced verified-answer presentation contract. Additive packets P06-19 through P06-26 record the 2026-09-10 local PDF evaluation workspace overlay. Additive packets P06-27 through P06-36 record the 2026-09-10 hosted webapp evaluation workspace. Additive packets P06-37 through P06-43 record the 2026-09-10 advanced web research overlay. Additive packets P06-44 through P06-48 record the 2026-09-15 PDF paragraph-citation overlay. Additive packets P06-49 through P06-57 record the 2026-09-16 live RAG failure remediation overlay. Additive packets P06-58 through P06-64 record the 2026-09-17 general Hybrid retrieval accuracy overlay. Additive packets P06-65 through P06-72 record the 2026-09-21 honest RAG accuracy repair overlay. Every linked file remains normative; this wrapper intentionally does not duplicate the former monolithic body. Legacy section numbers remain mapped through the [section map](../hybrid-graph-rag_ab5281ef.plan.md#legacy-section-map).

### Phase 6 runtime Hybrid dependency contract

See [`00-shared-contracts.md`](./06-phase-agent-intelligence/00-shared-contracts.md).

### 8. Query LangGraph and answer contract

See [packet 1](./06-phase-agent-intelligence/packets/01-admission-budgets.md), [packet 2](./06-phase-agent-intelligence/packets/02-profiling-routing.md), [packet 3](./06-phase-agent-intelligence/packets/03-combined-fusion.md), [packet 6](./06-phase-agent-intelligence/packets/06-sse-compatibility-resume.md), and [packet 7](./06-phase-agent-intelligence/packets/07-memory-governance-evaluation.md).

### 8.1 Combined evidence-fusion algorithm

See [packet 3](./06-phase-agent-intelligence/packets/03-combined-fusion.md).

### 9. Progressive tool disclosure and token control

See [packet 4](./06-phase-agent-intelligence/packets/04-optional-tools.md).

### 10. FastAPI contract, streaming, and security

See [packet 1](./06-phase-agent-intelligence/packets/01-admission-budgets.md), [packet 5](./06-phase-agent-intelligence/packets/05-fastapi-security.md), [packet 6](./06-phase-agent-intelligence/packets/06-sse-compatibility-resume.md), [packet 7](./06-phase-agent-intelligence/packets/07-memory-governance-evaluation.md), and [packet 16](./06-phase-agent-intelligence/packets/16-sse-custom-progress.md).

### 11. LangSmith, prompts, cost, and evaluation

See [packet 7](./06-phase-agent-intelligence/packets/07-memory-governance-evaluation.md) and [packet 8](./06-phase-agent-intelligence/packets/08-thin-developer-ui.md).

## Phase deliver, review, and done gate

### Phase 6 — Agent intelligence

- Deliver: deadlines/ceilings, server-derived authorization, frozen ParadeDB BM25 runtime contract/recheck/degradation, rewrite fidelity, extended type-to-composable-plan/limitation matrix, routing correction, resolved-path fusion and naive-union ablation, table composition, inference verifier, memory, deterministic core tools, optional disclosure, additive API/SSE version handshake, resumable SSE, authorization-safe cache, idempotency/event GC, reserve-once/true-up budgets, provider-versus-FastAPI rate ownership, endpoint-specific Valkey-down limits, restricted read auditing, event-loop/CPU-offload controls, immediate conversation deletion, full governance enforcement, defenses, traces, and thin UI.
- Review: every route type and mixed example, BM25 index/version/typed query/authorization recheck/outage, historical relationship, whole-document coverage, negation/media/refusal, ACL graph blindness, escalation, global steering, fusion weights/caps/ablation, inference labels, deadline output, verifier cost, cache invalidation/recheck, API/SSE deploy compatibility, direct Auth versus application rate ownership, injection, reconnect, rate-store outage, budget contention/crashes, reaper boundaries, event-loop/heartbeat jitter, restricted read/deletion coverage, and early feedback.
- Done when: rewrite/profile fidelity and the complete direct, current relationship/multi-hop, historical relationship→Hybrid, broad/global, coverage-proven single-document summary, negation/media scoped-refusal, comparison, structured-table, graph-inspection, no-retrieval, multi-part, and Composite route matrix meet signed routing/correction targets; the local runtime Hybrid contract is enforced without retuning Phase 4, every BM25 candidate is bounded and Supabase-rechecked, and a killed/incompatible ParadeDB visibly degrades to dense+term without stale/unauthorized evidence or BM25 snippets; full-document summaries refuse unless section coverage is `1.0`, negation never asserts an unproved complement, media-only questions show the signed limitation, and ACL graph-blindness is visible only to authorized users; resolved-path fusion beats naive union or is removed; on the disjoint relationship/multi-hop evaluation the complete Combined answer path improves success by at least 10 percentage points over Hybrid alone while meeting global citation correctness/completeness, faithfulness, latency, model-call, tool, and cost ceilings; graph-only remains inspection and every graph lead resolves to authorized canonical evidence; table values and every material atomic inference link are grounded and verified; query retries create one paid run, the idempotency/event reaper preserves replay boundaries, additive API/SSE schema and version handshake pass, SSE sequence resume/heartbeat/cancel work, and every route terminates within deadline/recursion/correction ceilings with safe partial/refusal; retrieval-cache ACL downgrade/deletion tests yield zero stale evidence after Postgres recheck; all profiling, rerank, LightRAG, answer, summary, and verifier calls consume one durable reservation without hot shared-row relocking or overspend; provider-owned Auth controls and FastAPI-owned limits are independently proven, while endpoint-specific application cost/mutation limits survive or fail safely during Valkey loss; restricted evidence/downloads create append-only audit events; five-run event-loop/CPU-offload/heartbeat gates pass locally; prompt/BM25-query/graph/tool/XSS injection fixtures fail; deleted conversations leave no application/checkpoint/store/private-feedback state; traces are versioned, costed, redacted, and permitted by the signed governance packet; optional schemas remain outside unrelated prompts; and the thin developer UI proves authenticated upload/status, streaming/reconnect, BM25/limitation/route diagnostics, citations, and early feedback.
