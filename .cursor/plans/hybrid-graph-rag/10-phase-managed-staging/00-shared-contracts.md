---
phase: 10
status: pending
title: Phase 10 shared contracts
source_wrapper: ../10-phase-managed-staging.md
evidence_path: docs/development/phase-10-managed-staging-evidence.md
---

# Phase 10 shared contracts

## Scope and ownership

Phase 10 consumes the exact Phase 9-qualified images and local evidence, provisions isolated production-equivalent managed staging, and owns managed provider, topology, security, restore, rebuild, streaming, rotation, alert, rollback, and independent-assessment proof.

Only synthetic or redacted fixtures are permitted. Production corpus, production users, final DNS cutover, and irreversible production promotion are forbidden. Phase 10 may not weaken, replace, or retroactively fail valid Phase 9 local evidence; it proves managed extensions and reruns applicable shared gates against staging.

Read the [global contracts](../00-global-contracts.md) and [Phase 10 wrapper](../10-phase-managed-staging.md) before this file. Then read exactly one linked packet and only its linked shared/release contracts.

## Prerequisites and skills

Phase 9 must be accepted with exact immutable candidate identities, no skipped local mandatory test, a proven/isolated/resized or reduced-and-re-signed envelope, local database plus all-Storage restore/reconciliation followed by clean BM25 rebuild, explicit managed blockers, and no unresolved local launch blocker. Phases 1–8 remain inherited prerequisites.

Load `.cursor/skills/implement-plan-phase/SKILL.md`, `.cursor/skills/verify-release-gates/SKILL.md`, and `.cursor/skills/implement-supabase-security/SKILL.md`. Load another skill only for the active packet. Missing or changed Phase 9 artifact/evidence identity returns to Phase 9.

## Cross-packet invariants

- Staging uses the production-intended managed Supabase plan/features, Supavisor modes, regions, CloudFront/WAF/Caddy topology, EC2 images, private ParadeDB digest/configuration, Valkey/proxy boundaries, Vercel configuration, and deployment contracts.
- Synthetic or redacted staging data is mandatory.
- Supabase is canonical; ParadeDB is private, bounded, derived, and rebuildable.
- GitHub and runtime hold no long-lived AWS, database, or bootstrap credential.
- OIDC, SSM, Secrets Manager, protected environments, immutable migration hashes, and expand/contract compatibility enforce deployment custody.
- Direct origin, private ports, unrestricted provider/crawl/parser/ParadeDB egress, and metadata are denied.
- The real 50-second SSE test passes under asserted 90-second CloudFront/Caddy settings.
- Restore reconciles database and every durable bucket before rebuilding ParadeDB from authorized current Supabase state.
- Critical/High external-assessment findings are remediated and independently retested before Phase 11.
- No packet or phase is marked complete before accepted evidence.

## Evidence contract

Every packet appends to `docs/development/phase-10-managed-staging-evidence.md`:

- requirement ID and packet title;
- exact Phase 9 image/configuration/report identities;
- staging account, project, plan, feature, endpoint-mode, and region identifiers without secrets;
- immutable IaC, image, ParadeDB, migration, configuration, schema/index/normalization, and frontend/API identities;
- exact repository and current-primary-documentation checks;
- machine-readable policy, test, load, restore, alarm, rotation, rollback, and assessment artifacts;
- synthetic/redacted dataset identity and absence of production data;
- authorization, failure, topology, idempotency, fallback, bounded-resource, and degraded-path proof;
- Passed, Failed, Blocked, and Not Run classification;
- deviations, accepted-risk ADRs, remediation owner, rollback, and next action; and
- exact qualified promotion inputs for Phase 11.

Evidence excludes secrets, credentials, raw private source text, and sensitive exploit details.

## Shared stop routes

Stop on missing Phase 9 acceptance, production data/users in staging, intended plan/feature/region/artifact/topology drift, unverifiable provider contract, fake/skipped managed proof, direct-origin/private-port/unrestricted-egress/long-lived-credential reachability, failed migration/restore/rebuild/stream/rotation/alert/rollback gate, open Critical/High finding, or unapproved sizing/topology change.

## Concern-contract loading map

- Managed security, protected migration, release, and assessment gates: `../shared/release/02-managed-gates.md`.
- Network, EC2, Supabase, Vercel, CDN, restore, rotation, alert, and rollback topology: `../shared/release/03-staging-topology.md`.
- Managed load, resource, recovery-duration, and envelope decisions: `../shared/release/05-sizing-envelope.md`.

Read only concern contracts linked by the active packet.
