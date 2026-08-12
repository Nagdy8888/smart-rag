---
name: hybrid-graph-rag-plan-review
status: complete
reviewed: 2026-08-12
scope: .cursor/plans/hybrid-graph-rag_ab5281ef.plan.md and all files under .cursor/plans/hybrid-graph-rag/
reviewer: AI architecture/security review (Fable 5)
resolution_status: incorporated
resolved: 2026-08-12
---

# Review: Hybrid Graph RAG plan (global contracts + Phases 1–11)

This document reviews the split plan for system-design completeness, security, Hybrid RAG design, and GraphRAG design. It audits the plan only; it does not authorize implementation or change any plan semantics. Findings are prioritized: **P1** = amend the plan before the affected phase starts, **P2** = decide and document before launch, **P3** = improvement opportunity.

## Executive verdict

This is an exceptionally strong plan — well above typical industry practice for RAG systems. Grounding discipline (graph output as leads resolved to canonical passages), durable reserve-once budgets, bounded work everywhere, holdout hygiene, deletion/ACL semantics, SSRF/prompt-injection coverage, and honest degradation paths are all specified at a level most production systems never reach. The split-plan audit (`98-split-plan-completeness-audit.md`) already repaired the major internal ownership conflicts.

The remaining weaknesses are not missing ambition; they are a small number of **unspecified load-bearing mechanisms** (how end-user identity reaches database authorization; cache invalidation vs. the "immediate exclusion" invariant; who owns auth rate limits), a few **scope blind spots** (figures/images, whole-document summarization, temporal graph, Arabic graph extraction quality, RTL UI), and **delivery risk** from the plan's own process weight against a single-developer 23–35 week estimate.

## Amendment outcome

All P1 and P2 findings and the actionable P3/delivery-risk recommendations were incorporated into the canonical global and phase contracts on 2026-08-12. The conservative v1 decisions are:

- Figures/charts/diagrams are a signed text+OCR limitation with explicit UI notice and a vision-captioning ADR trigger.
- Whole-document summaries require deterministic coverage of every major section within the bounded evidence budget; otherwise the system refuses the full-summary claim and offers section/page-range guidance. V1 does not add ungrounded map-reduce summarization.
- Historical relationship/multi-hop questions use authorized Hybrid retrieval with a current-graph limitation notice; v1 LightRAG remains current-version-only.
- Identity reaches Postgres through server-derived typed RPC arguments validated against current membership/authorization state; transaction-pooled paths do not rely on session GUC identity.
- Browser-direct Auth limits belong to Supabase Auth; Valkey/Postgres degraded limits cover only FastAPI-mediated operations.
- Retrieval cache entries are authorization-scoped, visibility-versioned, short-lived, invalidated best-effort, and always rechecked against authoritative Postgres before evidence use.

The affected `Deliver`, `Review`, and `Done when` gates now cover governance for all external processors, explicit ACL semantics/read auditing, quarantine quotas/cleanup, UTC temporal fixtures, negation, per-language graph quality, RTL/bidirectional UI, expand/contract migrations, API/SSE compatibility, database-plus-Storage restore reconciliation, an external security assessment, and AWS/Supabase billing alarms. [`99-source-coverage.md`](../../.cursor/plans/hybrid-graph-rag/99-source-coverage.md) records the amendment, and the current hashes are protected by the plan integrity lock.

A subsequent user-approved lexical amendment on the same date promoted true BM25 into v1. Because managed Supabase does not expose the required `pg_search` extension, the canonical plan now uses a private digest-pinned ParadeDB projection in local Docker/EC2 while Supabase retains canonical text, authorization, durable projection jobs, vector/term retrieval, and final evidence. BM25 candidates are bounded and batch-rechecked in Supabase; ParadeDB outage visibly degrades to dense plus exact/trigram term retrieval.

## Scorecard

| Area | Rating | One-line assessment |
| --- | --- | --- |
| System design | Strong | Clear boundaries, durability, and bounded work; a few consistency mechanisms unspecified. |
| Security | Strong | Deep defense-in-depth; identity-to-database propagation and auth-limit ownership are the open holes. |
| Hybrid RAG | Very strong | State-of-practice multilingual pipeline with disciplined deferrals; product-level gaps (summarization, figures). |
| GraphRAG | Strong | Best-in-class evidence mapping; temporal and multilingual graph quality are unaddressed. |
| Operations/release | Strong | Restore drill omits Storage objects; no zero-downtime migration policy; no external pen test. |
| Deliverability | At risk | Gate weight vs. one developer; the Hybrid Pilot cut line needs a pre-agreed decision point. |

## What the plan gets right (condensed)

- Canonical-evidence invariant: graph prose is never answer evidence; every graph candidate resolves through versioned maps to authorized canonical chunks with survival telemetry and quarantine on failure (Phase 5).
- Deterministic routing with one global correction budget, hard deadlines, model-call ceilings per route, and verified-partial/refusal on exhaustion (Phase 6).
- Reserve-once/true-up durable budgets covering every gateway call including LightRAG internals; crash reaping; no shared-row hot locking (Phase 6).
- Realistic failure modes: Valkey-down endpoint-specific behavior, graph quarantine, rerank fallback to RRF, partial graph readiness messaging.
- Evaluation hygiene: disjoint embedding-qualification slice, immutable launch holdout, per-field profile attribution before blaming ranking, skipped-rerank counterfactuals, ablation-gated complexity (RRF variants, fusion vs. naive union).
- Security depth: asymmetric JWKS with rollover drills, schema-scoped DB roles with no runtime `service_role`, quarantine-scan-promote upload flow with signature freshness, crawl proxy with DNS-rebinding defense, hash-chained anchored audit log, append-only provenance.
- Honest deferrals with promotion triggers: SPLADE, HyDE, RAPTOR, ColBERT, local rerankers, Arabic stemming, per-ACL graph workspaces, multi-host availability.

## P1 findings — amend before the affected phase

### P1-1. End-user authorization propagation into Postgres is unspecified

**Evidence:** Phase 2 (schema-scoped roles; "Runtime API/worker containers do not receive the Supabase `service_role` key"), Phase 4 §6.3 ("The security-invoker Supabase RPC always constrains results by role/ACL/current-version/metadata"), Phase 2 connection budgets ("API request/RPC traffic may use transaction pooling").

FastAPI connects with a shared API database role through pooled connections. A `security_invoker` RPC enforces the *database role's* RLS context, not the end user's — so per-user ACL filtering inside the retrieval RPC requires the end-user identity to be injected somehow: per-transaction `set_config('request.jwt.claims', ...)`/custom GUC, explicit `user_id`/role function arguments validated server-side, or PostgREST calls carrying the user JWT. The plan never names the mechanism, and the GUC approach interacts badly with Supavisor **transaction pooling** (settings leak or reset across pooled transactions) — exactly the pooling mode the plan permits for API RPC traffic.

This is the single most load-bearing security mechanism in the query path. Left implicit, an implementer will guess, and the zero-ACL-leak gate will be testing an accidental design.

**Recommendation:** Phase 2 must specify the identity-propagation contract explicitly (recommended: explicit typed arguments to `security definer`-reviewed or invoker RPCs, validated against a server-resolved membership row, never trusting client-supplied role), state its pooling-mode compatibility, and add a negative test where a forged/missing user context yields zero rows.

### P1-2. Valkey retrieval cache has no keying/invalidation contract

**Evidence:** Global contracts ("Valkey cache: short-lived query-profile/retrieval cache only… Losing it affects latency only") vs. the invariant "Document deletion and ACL downgrade immediately exclude the affected version" (Phase 3/5).

Nothing requires cache keys to include the user's authorization scope and index/document-version identifiers, and nothing bounds cache staleness against the "immediate exclusion" guarantee. A cached candidate set or profile can serve a just-deleted or just-restricted document to a user who should no longer see it — a real ACL leak through a component the plan classifies as latency-only.

**Recommendation:** Add a cache contract to global contracts or Phase 6: keys must incorporate (user or role+ACL scope, index/profile versions); cached retrieval entries must either have a TTL below the accepted exclusion latency (seconds, and stated) or be invalidated transactionally on deletion/ACL events; final evidence assembly must always recheck current-version/ACL against Postgres (the Phase 5 resolver does this for graph — state it for Hybrid cache hits too). Add an eviction/leak test to the Phase 9 ACL suite.

### P1-3. Auth rate-limit ownership is split-brain

**Evidence:** Architecture diagrams route sign-in directly from browser to Supabase Auth (`frontend -->|SupabaseAuth| supabase`); Phase 6 places "sign-in attempts, MFA challenges, invitation acceptance" limits in FastAPI/Valkey with a Postgres degraded path.

Limits enforced in FastAPI cannot throttle credential-stuffing against the Supabase Auth endpoint the browser talks to directly. Either those flows are proxied through FastAPI (contradicting the `@supabase/ssr` direct-auth architecture), or the primary sign-in throttle is actually Supabase Auth's own rate-limit configuration and the FastAPI limits only cover FastAPI-mediated flows. The plan currently implies both without deciding.

**Recommendation:** Phase 2/6 should state per auth operation which boundary owns the limit, require explicit configuration of Supabase Auth's built-in rate limits (and captcha if available on the selected plan), and scope the Valkey/Postgres degraded path to the operations FastAPI actually mediates.

### P1-4. Data-governance record covers OpenAI only

**Evidence:** `OPENAI_DATA_GOVERNANCE.md` (Phase 3) is thorough for OpenAI; LangSmith receives redacted traces, Supabase holds all corpus/PII data, Vercel serves the frontend — none has an equivalent signed retention/region/DPA/subprocessor record.

Redacted traces still contain queries, entity names, and usage metadata; Supabase region/encryption/subprocessor terms are the actual custodianship of company data. A client signing the OpenAI record may reasonably believe governance is complete when it is not.

**Recommendation:** Extend the Phase 3 governance packet (or add a sibling document) covering LangSmith retention/redaction/DPA, Supabase region/encryption/subprocessors, and Vercel, with the same owner sign-off gate.

## P2 findings — decide and document before launch

### System design

- **P2-1. No zero-downtime migration policy.** Blue/green same-host API slots (Phase 10/11) mean old code briefly runs against a newly migrated schema. Adopt an expand/contract rule (migrations must be backward-compatible one release; destructive changes split across releases) and test the old-slot-on-new-schema window in staging.
- **P2-2. Restore drill omits Storage objects.** Drills verify "application schemas, canonical chunks, source mappings, and private LightRAG tables together" — but not `documents-originals`, `web-snapshots`, or `table-artifacts`, and DB PITR vs. Storage recovery can diverge (chunk rows referencing missing objects, or orphaned objects). Add Storage objects to the drill and define a reconciliation procedure for DB/Storage divergence after restore.
- **P2-3. Frontend/API compatibility across decoupled deploys.** Vercel and EC2 deploy independently; no compatibility policy exists for the SSE event schema or OpenAPI surface during deploy windows. Adopt additive-only event/schema evolution plus a version handshake or minimum-API-version check.
- **P2-4. Temporal anchoring is undefined.** `latest`/`current`/`as_of` compare against "now" with no timezone specification, and the Arabic-first corpus raises date-parsing questions (locale formats; whether Hijri dates ever appear as authoritative `effective_at` sources). Specify UTC (or company timezone) anchoring in Phase 4 and add mixed-locale date fixtures.

### Security

- **P2-5. Document ACL model is never defined.** `document_acl` is named and "company-visible versus restricted" is used throughout, but grant granularity (individual users, roles, groups?), who may grant/revoke, the default state of new uploads, and interaction with the viewer role are unspecified — yet RLS, graph eligibility, and the zero-leak gate all hinge on these semantics. Define the ACL model in Phase 2.
- **P2-6. No read-access auditing.** Audit events cover corpus writes, admin operations, and deletion; nobody records who viewed/downloaded a restricted document or received it as evidence. At minimum, audit signed-download-URL issuance and restricted-document evidence exposure.
- **P2-7. No independent security assessment.** All security proof is first-party fixtures. Add a third-party penetration test (or at minimum an external review of auth/RLS/SSRF/injection surfaces) as a Phase 10 gate.
- **P2-8. Quarantine-bucket abuse and size enforcement mechanics.** "Validate declared size before upload" is not enforceable by Supabase signed upload URLs per-object; enforcement is post-hoc. Specify per-user upload quotas, a TTL cleanup job for never-finalized quarantine objects, and bucket-level size limits.

### Hybrid RAG

- **P2-9. Figures, charts, and images are silently dropped.** Ingestion is text+OCR only; a PDF whose answer lives in a diagram or chart yields nothing, with no stated limitation. Either declare this a signed non-goal in `QUALITY_TARGETS.md` and user-facing docs, or add a vision-captioning ADR trigger.
- **P2-10. Whole-document summarization cannot be served.** "Summarize this document/contract" is among the most common real user requests; the broad-synthesis route retrieves 8–12 evidence units, which cannot faithfully summarize a 200-page document. RAPTOR deferral covers cross-document synthesis quality, not this product expectation. Decide: explicit scoped refusal with guidance, a bounded map-reduce summarization tool, or a documented single-document parent-walk mode — and put the decision in the route matrix.
- **P2-11. Negation/exclusion intents missing from the query taxonomy.** "Which suppliers are *not* covered by policy X" fits no profile field; retrieval will return the opposite evidence confidently. Add negation detection to the profile with a calibrated refusal/clarification path.

### GraphRAG

- **P2-12. The graph is current-version-only; temporal relationship questions get no graph support.** Version pointer flips delete superseded graph data, so `as_of`/historical relationship queries silently degrade with no stated limitation. Document this as a v1 limitation in the route matrix and user docs; route explicit historical relationship queries to Hybrid with a notice rather than Combined.
- **P2-13. Graph extraction quality is never gated per language.** Hybrid has extensive Arabic gates; Phase 5's mapping/survival gates say nothing about language, and LightRAG's extraction prompts are English-centric. Arabic/mixed documents may produce systematically poor entities/relations and low mapping coverage that per-document thresholds mask in aggregate. Add Arabic/mixed graph extraction and mapping-coverage fixtures to the Phase 5 evaluation, and per-language mapping-coverage telemetry.
- **P2-14. Authorized users get no signal about ACL-driven graph blindness.** Restricted documents are correctly invisible to the graph, and restricted counts are correctly hidden from unauthorized users — but an *authorized* user asking a relationship question whose evidence is ACL-restricted gets a degraded answer with no explanation. Mirror the existing partial-readiness message: for users authorized to see the restricted documents, indicate that relevant accessible documents are not graph-indexed.

### Frontend

- **P2-15. RTL/Arabic UI is absent from the Stitch brief.** The retrieval stack is Arabic-first, but Phase 7 requires no RTL layout behavior, bidirectional text handling in chat/citations/highlights, or Arabic UI localization decision. Mixed-direction citation rendering with offsets is genuinely hard; specify it before design generation, not during Phase 8.

## P3 findings — improvement opportunities

- **P3-1.** Query-embedding/result caching for repeated queries is an easy latency/cost win — but only under the P1-2 cache contract.
- **P3-2.** MFA recovery appears only as UI screens; define the actual lost-factor procedure (admin-initiated reset semantics, identity re-verification, audit).
- **P3-3.** Idempotency-key and sequenced-run-event retention/GC is unspecified (the budget reaper is; these rows are not).
- **P3-4.** Cost alarms cover OpenAI spend only; add AWS and Supabase billing alerts.
- **P3-5.** Admin anomaly alerts ("alert admins on upload spikes…") have no defined channel before SES/alert-routing exists in Phase 10; specify the local/in-app channel for Phases 3–9.
- **P3-6.** The graph maintenance reserve `max(USD 800, 4 × rebuild cost)` can dwarf the USD 200/month normal ceiling. It is correctly separated and visible, but surface this expected cost reality explicitly in the Phase 1 sign-off conversation, not only in the contracts file.
- **P3-7.** The single-writer graph and seven-day rebuild ceiling are honestly triggered but have no sketched forward design. Note candidate directions now (workspace sharding by domain, dedicated graph Postgres, incremental compaction) so a trigger review does not start from zero.

## Delivery risk (not a plan defect, but the biggest practical threat)

The estimate is 23–35 weeks for one experienced developer, and the plan's own process weight — universal docstrings, exit records per packet, ADR discipline, Mermaid-validated docs, hard CI tiers — is a significant fraction of that. This rigor is the plan's strength, but it means the schedule has little slack for the genuinely hard technical risks (Arabic retrieval quality, LightRAG contract stability, evidence-mapping coverage in practice).

The plan already defines the right escape valve: the `0.x Hybrid Pilot` cut line (Phases 1–4 + thin Phase 6 path + minimal UI). **Recommendation:** pre-agree with the client, during Phase 1 sign-off, the concrete decision date and criteria for exercising that cut (the plan's own re-estimate points after Phases 1 and 4 are the natural moments) rather than deciding under schedule pressure mid-Phase-5.

Secondary schedule risks that are already bounded but worth tracking: the Phase 7 five-day client-side Stitch loop, SME availability for the 12–20 labeling hours that gate Phase 4, and the owner sign-offs that gate Phases 1 and 3.

## Suggested amendment order

1. P1-1 identity propagation contract (Phase 2) — blocks Phase 2 correctness.
2. P1-3 auth rate-limit ownership (Phases 2/6) — blocks Phase 2 Auth configuration.
3. P1-2 cache keying/invalidation contract (global contracts / Phase 6).
4. P2-5 ACL model definition (Phase 2).
5. P1-4 subprocessor governance scope (Phase 3 packet).
6. P2-9/P2-10/P2-12 scope decisions (figures, summarization, temporal graph) — client conversation, then route-matrix/QUALITY_TARGETS updates.
7. P2-13 Arabic graph gates (Phase 5 evaluation), P2-15 RTL requirements (Phase 7 brief).
8. Remaining P2 operational items (P2-1..P2-4, P2-6..P2-8, P2-14) before their owning phases (2, 9, 10).

Per the plan's own amendment rule, each accepted change should go through the ADR/plan-update path and a deliberate integrity-lock refresh (`verify_plan_integrity.py --update` after review), not silent edits.
