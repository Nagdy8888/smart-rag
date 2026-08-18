---
phase: 9
status: complete
title: Phase 9 shared contracts
source_wrapper: ../09-phase-local-release-candidate.md
evidence_path: docs/development/phase-09-local-release-candidate-evidence.md
---

# Phase 9 shared contracts

## Scope and ownership

Phase 9 qualifies the exact immutable candidate images entirely against the local Docker stack. It owns local security, evaluation, load, contention, degradation, restart/resume, restore/reconciliation, derived BM25 rebuild, scans, sizing, and no-go evidence.

Phase 9 does not provision or require AWS, Vercel production, managed Supabase proof, SES, KMS/S3 Object Lock, CloudFront/WAF, managed origin controls, protected managed migrations, managed restore, or an external assessment. It records each managed requirement as an open Phase 10 blocker with the expected evidence and owner. An unavailable cloud environment cannot block Phase 9 once every locally applicable gate passes, but a local gate cannot be relabeled managed to avoid failure.

Read the [global contracts](../00-global-contracts.md) and [Phase 9 wrapper](../09-phase-local-release-candidate.md) before this file. Then read exactly one linked packet and only the shared/release contracts that packet names.

## Prerequisites and skills

Phases 1–8 and every required sign-off, including approved quality, cost, capacity, RTO/RPO, governance, embedding, graph, frontend, and provider decisions, must be complete. Inspect the exact repository state, schemas, migrations, tests, dependency pins, image digests, configuration profile, frozen evaluation corpora, and documented commands before a packet begins.

Load `.cursor/skills/implement-plan-phase/SKILL.md` and `.cursor/skills/verify-release-gates/SKILL.md`. Load another workspace skill only when the selected packet requires its concern. If a prerequisite or sign-off is incomplete, stop and return the blocker to its owner.

## Cross-packet invariants

- Supabase canonical passages and deterministic table values are the only final-answer evidence.
- Authorization, current-version, deletion, ACL, and identity checks execute at authoritative boundaries and receive negative tests.
- ParadeDB remains private, rebuildable, and non-authoritative; every candidate is batch-rechecked in Supabase.
- LightRAG remains private and graph-eligible only for company-visible documents.
- Budgets, jobs, checkpoints, idempotency, usage, and security state remain durable.
- Work is bounded by signed candidates, rows, bytes, tokens, calls, tools, retries, hops, concurrency, deadlines, recursion, connections, and resources.
- Failures follow approved visible degradation or refusal routes; no fake success, skipped mandatory integration, unauthorized evidence, or uncited answer is allowed.
- Every integration job fails if zero matching tests execute.
- No packet or phase is marked complete before accepted evidence.

## Evidence contract

Every packet appends to `docs/development/phase-09-local-release-candidate-evidence.md`:

- requirement ID and packet title;
- source snapshot, immutable image digests, dependency/model versions, ParadeDB digest, `pg_search`, BM25 schema/index/normalization, migrations, dataset, and configuration profile;
- local hardware, Docker/WSL2 resources, container limits, roles, and corpus boundaries;
- exact repository-defined commands;
- machine-readable results, logs, traces, measurements, and artifact locations without secrets or raw sensitive text;
- authorization, failure, idempotency, fallback, bounded-resource, and degraded-path evidence;
- Passed, Failed, Blocked, and Not Run classification;
- deviations, approved ADRs, rollback notes, owner, and next action; and
- managed items handed to Phase 10 with expected proof.

Later packets reference earlier evidence only by immutable artifact/result identity. Changed candidate identity invalidates dependent evidence.

## Shared stop routes

Stop when a prerequisite is incomplete; repository reality changes security, data, cost, topology, or acceptance semantics; a pin or contract is unverifiable; a real authorization, idempotency, deadline, budget, provenance, restore, or fallback boundary cannot be exercised; only fake/skipped/empty proof could pass; candidate identity changes; a local launch gate fails after bounded repair; or a missed envelope has no approved repair, resize/isolation, or reduced-and-re-signed route.

Record genuinely managed-only requirements as Phase 10 blockers. Do not stop Phase 9 solely because cloud proof is unavailable.

## Concern-contract loading map

- Local CI, security, quality, compatibility, degradation, and restore gates: `../shared/release/01-local-release-gates.md`.
- Managed blocker classification: `../shared/release/02-managed-gates.md`.
- Load, capacity, latency, resource, cost, and envelope decisions: `../shared/release/05-sizing-envelope.md`.

Read only concern contracts linked by the active packet.
