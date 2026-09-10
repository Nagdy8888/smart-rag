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

Packets P06-09 through P06-26 are additive after the completed historical packets. Do not uncheck packets 1–8. P06-14 is a Phase 6/Phase 8 co-owned UI amendment and must not renumber active P08-22/P08-23. P06-16 is the co-owned custom-progress and paced-reveal contract. P06-17 and P06-18 are the 2026-09-09 private-PDF agent evaluation and holdout overlay; they do not start until Packet 9 is accepted and Packet 10 includes the production rerank/scope contract. Packets P06-19 through P06-26 are the 2026-09-10 local PDF evaluation workspace overlay. Integrity requires contiguous packet numbers, so they follow P06-18. User approval on 2026-09-10: execute P06-19 through P06-26 immediately after Packet 9, then resume Packet 10. Do not start Packet 10 coding until the overlay packets are accepted or an explicit blocker is recorded.

9. [x] [Canonical amendment for general-chat strict-split, ADR, and packets P06-10 through P06-15.](./06-phase-agent-intelligence/packets/09-canonical-general-chat-amendment.md)
10. [ ] [Implement typed knowledge-scope classification, the live profile gateway, and deterministic route compilation.](./06-phase-agent-intelligence/packets/10-knowledge-scope-routing.md)
11. [ ] [Drain successful LangGraph streams and classify expected cancellation without hiding real trace errors.](./06-phase-agent-intelligence/packets/11-sse-stream-lifecycle-tracing.md)
12. [ ] [Implement bounded, budgeted general and user-text model answers without weakening document grounding.](./06-phase-agent-intelligence/packets/12-general-chat-execution.md)
13. [ ] [Add authenticated query_studio_live with per-run resources and normal ACL, admission, and budget controls.](./06-phase-agent-intelligence/packets/13-authenticated-studio-live.md)
14. [ ] [Add answer-origin, clarification, and citation-safe behavior to the main chat UI.](./06-phase-agent-intelligence/packets/14-chat-origin-ux.md)
15. [ ] [Run all deterministic and live gates, inspect LangSmith traces, and update evidence and runbooks.](./06-phase-agent-intelligence/packets/15-integrated-verification.md)
16. [ ] [Add LangGraph custom SSE progress and paced verified-answer presentation contract.](./06-phase-agent-intelligence/packets/16-sse-custom-progress.md)
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

## Approved planned deviation: general-chat strict split

User approval on 2026-08-25; 2026-08-26 remediation accepted 2026-09-10: add a strict dual-mode assistant to the production Ask path and a separate live LangSmith Studio graph. General questions may use OpenAI world knowledge. Company/document questions remain citation-required RAG. Genuine mixed scope returns clarification. Failed or low-confidence profile inference records typed degradation and may return an honest general answer that explicitly says company documents were not searched. Never fall back from insufficient company evidence to world knowledge.

- Recorded in [`docs/adr/ADR-general-chat-strict-split.md`](../../../docs/adr/ADR-general-chat-strict-split.md).
- Preserve `query_studio` as the deterministic, unbound, no-cost graph. Live retrieval uses only `query_studio_live` with a real developer JWT.
- No service-role key or synthetic live identity is permitted.
- The production query path may spend one counted `profile` call under existing caps. Pure greetings/small talk are profile-model classified and general-model answered, normally consuming one profile plus one answer call.
- Keep existing scope values and route families. Deterministic company signals override model output; a server-derived degradation reason never authorizes evidence.
- After plan compilation, validated plans select explicit company, general, mixed, or fail-closed nodes. Direct paths skip retrieval/correction/fusion/table/tool/verifier-model work and still receive deterministic verification.
- P06-10 remains the first historical coding packet after this markdown amendment. User-approved 2026-09-10 overlay packets P06-19 through P06-26 run before Packet 10.

## Approved planned deviation: local PDF evaluation workspace

User approval on 2026-09-10: after Packet 9, prioritize a local-only owner/admin PDF evaluation workspace, label repair, and evidence-driven retrieval diagnosis before Packet 10 coding. Private questions and answers stay under gitignored `.private-eval/`. The API process never uses an operator or service-role DSN. Holdout custody stays outside the repository and is never listed or opened from the workspace. The feature is disabled by default and forbidden in staging and production.

- Recorded in [`docs/adr/ADR-local-pdf-evaluation-workspace.md`](../../../docs/adr/ADR-local-pdf-evaluation-workspace.md).
- Integrity cannot insert packets between 9 and 10, so overlay packets are P06-19 through P06-26. Execute them immediately after Packet 9, then resume Packet 10.
- Automatic draft generation may propose questions and extractive answers. A named human must approve. The answering model never receives expected answers before a run.
- Do not freeze `hybrid_long_document_v1`, retune RRF, or open holdout until grounded labels and open-split gates pass.
- Rollback disables `PDF_EVAL_WORKSPACE_ENABLED`, removes the Compose bind mount, and leaves historical packets 1–18 unchanged.

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

The Phase 6 runtime Hybrid dependency contract and legacy Sections 8–11 are redistributed into the shared contract and eight historical packets. Additive packets P06-09 through P06-15 record the approved general-chat strict-split amendment. Additive packet P06-16 records the co-owned LangGraph custom SSE progress and paced verified-answer presentation contract. Additive packets P06-19 through P06-26 record the 2026-09-10 local PDF evaluation workspace overlay. Every linked file remains normative; this wrapper intentionally does not duplicate the former monolithic body. Legacy section numbers remain mapped through the [section map](../hybrid-graph-rag_ab5281ef.plan.md#legacy-section-map).

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
