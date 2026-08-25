---
name: hybrid-graph-rag-source-coverage
status: verified-at-split-amended-current-locked
original_monolith_sha256: 41e3ee603ddb25d985b3636f13969e942cb8f53d0ab9c0753234f71fe46bb8ab
last_amended: 2026-08-25
current_integrity_lock: ./plan-integrity-lock.json
---

# Source coverage and redistribution manifest

This file is an audit aid, not an implementation plan. Models use the [global contract](./00-global-contracts.md) plus one active phase wrapper. Inline Phases 1–5 embed their packet contracts; split Phases 6–11 additionally load the phase shared contract, exactly one linked packet, and only that packet's named shared concern contracts.

The original monolith SHA-256 proves only the source read by the one-time split. The current amended plan is independently protected by [`plan-integrity-lock.json`](./plan-integrity-lock.json) and the reproducible [integrity verifier](./scripts/verify_plan_integrity.py).

## Coverage map

- **Front matter/overview/todos:** Canonical index. _Rewritten as phase-linked todos._
- **Sections 1–2:** 00 Global contracts. _Shared by every phase._
- **Section 3:** Phase 1. _Foundation owner._
- **Section 4:** Phase 2 canonical owner; Phases 3 and 5 consume explicit security/data contracts. _Phase 2 alone owns pgvector and private ParadeDB/`pg_search` compatibility plus the Arabic-normalization migration/conformance fixture._
- **Section 5:** Phase 3 owns ingestion through verified canonical vector/term plus BM25 projection `Hybrid Ready`/`Graph Pending`; Phase 5 owns graph mutation, `Graph Ready`, version switching, and graph cleanup. _The former mixed lifecycle text is now phase-scoped._
- **Section 6:** Phase 4 owns Supabase vector/term plus private ParadeDB BM25 retrieval/fusion/tuning; Phase 6 embeds a short frozen runtime Hybrid contract. _Phase 6 does not need to load Phase 4 or retune it._
- **Section 7:** Phase 5. _GraphRAG owner._
- **Sections 8–10:** Phase 6 wrapper and [`06-phase-agent-intelligence/`](./06-phase-agent-intelligence/). _Agent, tools, and API/security requirements are redistributed across one shared contract and eight historical packets, plus additive P06-09 through P06-15 for the approved general-chat strict split._
- **Section 11:** Phase 3 owns signed OpenAI governance; Phase 4 owns dataset/retrieval evaluation; Phase 6 owns prompts, production tracing, agent/API evaluation, and feedback wiring. _Later phases consume rather than recreate earlier artifacts._
- **Section 12:** Phase 6 owns the thin UI, Phase 7 owns complete Stitch/API specifications and design decision, and Phase 8 owns implementation/E2E. _The shared [`stitch-nextjs-contract.md`](./shared/frontend/stitch-nextjs-contract.md) records the consumer boundary; Phase 7/8 actions remain in their own packet files._
- **Section 13:** Phase 1 owns CI tiers, Phase 9 owns only local release gates, and Phase 10 owns managed OIDC/CDN/KMS/IaC gates. _Canonical local and managed release concerns are split under [`shared/release/`](./shared/release/) and consumed only by the owning packets._
- **Section 14:** Phase 10 owns managed staging/IaC proof; Phase 11 owns qualified production promotion and handoff. _Shared staging topology and production-delta contracts prevent duplicated infrastructure instructions._
- **Section 15:** Phases 1 and 11. _Documentation enforcement starts in foundation; the shared release handoff contract and Phase 11 packets close it._
- **Section 16 sequence:** 00 Global contracts and each phase. _Program order plus phase-specific sequence statement._
- **Section 16 checkpoints:** Each corresponding phase. _Deliver/review/done text preserved._

## Current verification

Run from the repository root:

```powershell
python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py
```

The verifier checks all required phase wrappers and gates, split wrapper-to-packet parity, packet headings/order/requirement ownership, shared-contract navigation, repaired ownership boundaries, local-versus-managed release separation, Phase 6 runtime Hybrid self-containment, and SHA-256 hashes for every discovered canonical wrapper, packet, shared contract, audit/manifest, rule, named phase skill, and verifier.

After an approved plan amendment, run the same structural checks and then deliberately refresh the lock:

```powershell
python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update
python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py
```

Do not use `--update` merely to hide an unexplained mismatch.

## Amendment log

- **2026-08-12 — Original split:** redistributed every original numbered section and phase checkpoint from monolith SHA-256 `41e3ee603ddb25d985b3636f13969e942cb8f53d0ab9c0753234f71fe46bb8ab`.
- **2026-08-12 — Completeness repair:** separated Phase 3/5 graph ownership, moved final Combined quality proof to Phase 6, made Phase 9 local-only, embedded the Phase 6 runtime Hybrid contract, strengthened all weak `Done when` gates, assigned governance/migration/UI/infrastructure owners, disambiguated legacy Section 10 links, strengthened the always-applied rule/phase skill, and added reproducible integrity checks.
- **2026-08-12 — Architecture/security/RAG review amendment:** resolved the linked [`docs/reviews/2026-08-12-hybrid-graph-rag-plan-review.md`](../../../docs/reviews/2026-08-12-hybrid-graph-rag-plan-review.md) findings across global contracts and Phases 1–11: server-derived transaction-pool-safe identity propagation, explicit ACL/read-audit and Auth-limit ownership, authorization-safe cache rechecks, full subprocessor governance, quarantine quotas/cleanup, UTC/negation/media/summary/historical route decisions, Arabic/mixed graph gates, RTL/bidirectional UX, expand/contract migrations, additive API/SSE versioning, Storage-inclusive restore reconciliation, independent security assessment, infrastructure billing alarms, and dated Hybrid Pilot decision criteria.
- **2026-08-12 — BM25 lexical amendment:** replaced PostgreSQL `ts_rank_cd` FTS as the Hybrid lexical channel with a private digest-pinned ParadeDB/`pg_search` BM25 projection in local Docker and EC2. Supabase remains canonical for text, authorization, current-version state, durable projection jobs, vector/term retrieval, and final evidence; every bounded BM25 candidate is batch-rechecked in Supabase. Added projection versioning/replay/purge, Arabic Unicode normalization parity, dense+term outage degradation, private reader/writer roles, resource/split triggers, rebuild-from-Supabase recovery, telemetry/UI states, security/load/quality gates, and production handoff requirements.
- **2026-08-12 — Lean Phase 6–11 expansion:** retained Phases 1–5 inline and converted Phases 6–11 to thin wrappers plus canonical phase-shared and one-packet-per-file contracts. Single-sourced the Phase 7/8 frontend contract and Phase 9–11 release concerns, updated model loading rules, and extended integrity validation to discover, validate, navigate, and hash every packet/shared source.
- **2026-08-15 — Phase 4 engineering-close amendment:** added inline Packet 9 for open-split ranked-ID close after Packet 8 no-go; split Phase 4 retrieval-slice latency from Phase 6 answer-token/faithfulness/25s run deadline; froze BM25 as one top-300; named HybridRetriever/heading-inventory/fallback enums; mapped Phase 4 QueryType to Phase 6 route families; counted batched query embeddings in the Hybrid call ceiling; recorded SME-holdout waiver for engineering-complete Phase 4 in ADR-phase4-engineering-close without opening the synthetic holdout.

## Preserved split evidence

- Every original numbered section (1–16) is covered.
- Every original phase sequence item is present in its phase wrapper and the global sequence.
- Every original `Deliver`, `Review`, and `Done when` checkpoint is present in its phase wrapper.
- Original checkpoint wording was retained as the baseline and strengthened where its completion condition was weaker than its deliverables.
- Cross-cutting requirements now use explicit canonical owners and small consumer contracts instead of unscoped duplicated actions; split phases load only one packet and its named dependencies.
- Relative repository links were rebased for the deeper plan directory; future planned targets may not exist until their owning phase creates them.
- Current navigation and hashes are checked by the committed verifier and lock rather than relying on the deleted one-time generator.
