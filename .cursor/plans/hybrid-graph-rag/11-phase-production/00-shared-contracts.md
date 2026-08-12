---
phase: 11
status: pending
title: Phase 11 shared contracts
source_wrapper: ../11-phase-production.md
evidence_path: docs/development/phase-11-production-evidence.md
---

# Phase 11 shared contracts

## Scope and ownership

Phase 11 promotes exact Phase 10-qualified immutable artifacts and configuration through protected production procedures, applies only documented production-safe environment deltas, performs bounded production-safe verification, tests the qualified rollback boundary, and completes documentation and operational handoff.

It does not redesign topology, expand scale claims, change image or engine pins, add retrieval methods, relax security/cost/acceptance criteria, or recreate destructive staging proof with production data. Material artifact, topology, contract, security, data, cost, or capacity drift returns to Phase 10 synthetic qualification and approval.

Read the [global contracts](../00-global-contracts.md) and [Phase 11 wrapper](../11-phase-production.md) before this file. Then read exactly one linked packet and only its linked shared/release contracts.

## Prerequisites and skills

Phase 10 must be accepted with exact application/infrastructure/ParadeDB/migration/configuration/schema/index/normalization/frontend/API identities; complete synthetic/redacted production-equivalent proof; managed Auth/pooling/Storage, JWKS, private ParadeDB, OIDC/migration, version skew, origin/egress, real CDN, Valkey, rotation, KMS/S3, alarm, restore/rebuild/parity, instance rebuild, failed deploy, and rollback proof; zero open Critical/High findings; owned residual risk; and signed promotion inputs.

The external assessment is at most 90 days old or has a completed delta review. Load `.cursor/skills/implement-plan-phase/SKILL.md` and `.cursor/skills/verify-release-gates/SKILL.md`; load another skill only for the active packet.

## Cross-packet invariants

- Exact Phase 10-qualified artifacts are promoted; no release-time rebuild changes identity.
- Only reviewed environment-specific production values may differ.
- Protected OIDC, SSM, Secrets Manager, approval, immutable migration hash, and expand-compatible deployment remain mandatory.
- The old API remains compatible with expanded schema; contraction is deferred.
- Supabase remains canonical; ParadeDB is derived and candidates receive mandatory authorization/current-version/deletion recheck.
- Production checks are bounded, non-destructive, and redacted before user access.
- User access remains closed on any failed launch check.
- Every alert, RTO/RPO, availability, isolation, growth, retention, legal-hold, engine, rebuild, degradation, and disable route has a named owner.
- No packet or phase is marked complete before accepted evidence.

## Evidence contract

Every packet appends to `docs/development/phase-11-production-evidence.md`:

- requirement ID and packet title;
- exact Phase 10 report and artifact identities;
- production environment, region, resource, plan, and configuration identifiers without secrets;
- immutable image, ParadeDB, migration, schema/index/normalization, engine/model/prompt, frontend/API, and IaC identities;
- reviewed production-safe delta list and approvers;
- change window, operators, owner routes, and rollback decision;
- protected commands and bounded production-safe results;
- smoke, security, redaction, compatibility, BM25, anchor, alarm, backup, consistency, deployment, and rollback artifacts;
- documentation/handoff links with owner, status, and last-reviewed date;
- Passed, Failed, Blocked, and Not Run classification; and
- deviations, delta review, residual risk, rollback, and user-access decision.

Evidence excludes secrets, credentials, raw private source text, and unredacted sensitive payloads.

## Shared stop routes

Stop and keep access closed on missing Phase 10 acceptance/assessment/artifact identity, unapproved production delta, immutable artifact drift, unverifiable provider contract, failed migration/health/origin/egress/Auth/RLS/Storage/budget/rate/BM25/redaction/backup/anchor/alarm/rollback gate, missing documentation/owner/retention/quarterly capacity/disable path, or when only destructive/fake/skipped production proof could pass.

## Concern-contract loading map

- Exact promotion, allowed deltas, protected deployment, production topology, backup, alarms, and safe verification: `../shared/release/04-production-promotion-delta.md`.
- Capacity and no-expansion constraints: `../shared/release/05-sizing-envelope.md`.
- Documentation, retention, runbooks, pins, ownership, quarterly qualification, and disable handoff: `../shared/release/06-documentation-operational-handoff.md`.

Read only concern contracts linked by the active packet.
