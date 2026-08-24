---
phase: 8
packet: 7
status: pending
title: "Canonical remediation amendment and baseline"
requirement_ids: [P08-07]
---

# Packet 7 — Canonical remediation amendment and baseline

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

Documentation and plan-integrity only. No application source, migration, dependency, or runtime config edits.

## Allowed outputs

Phase 8 packets 1-6 remain checked. Wrapper status stays pending.

## Forbidden outputs

Application code, migrations, dependency pins, runtime secrets, or hash-only lock refresh that conceals structural errors.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-07 — Canonical remediation amendment and baseline

Purpose: make this approved plan executable under the repository’s plan-source rules without unchecking or rewriting completed historical packets.

Implementation:

- Create `feat/frontend-functional-overhaul` from clean, current `main`; use `git pull --ff-only` before branching if the remote advanced.
- Add ordered unchecked remediation packet links P08-07 through P08-23 to [`08-phase-frontend-integration.md`](.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration.md). Do not alter checked P08-01 through P08-06.
- Add one packet markdown file for each packet below under [`.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration/packets/`](.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration/packets/). Each file must carry exact scope, files, forbidden work, acceptance checks, verification commands, evidence fields, and stop conditions from this plan.
- Copy the exact global theme/primitive specification into a Phase 8 shared visual contract, then copy each page/component subsection into its owning packet. Do not replace exact values with phrases such as “follow the design system,” “make it modern,” or “research best practices.” Amend the wrapper loading contract so a model reads only the shared primitive contract plus its selected page packet.
- Add maintained frontend design documentation split by concern so no catch-all document grows unchecked: design tokens/primitives, workspace screens, and admin/auth screens. Each document must reproduce the approved values and link to the canonical packet that implements it.
- Create every packet with the exact required metadata, ownership, headings, checklists, and evidence sections. Run the plan-integrity validator without `--update` first and correct all structural errors. Only after structural validation passes may the repository’s verified `verify_plan_integrity.py --update` path rewrite hashes; rerun validation afterward. Never use hash refresh to conceal an invalid packet.
- Add [`docs/adr/ADR-frontend-functional-overhaul.md`](docs/adr/ADR-frontend-functional-overhaul.md) recording the user-approved streamlined IA, removal-over-placeholder policy, backend-defect allowance, explicit complete MFA/AAL2 removal approval and its security consequences, alternatives rejected, compensating controls retained, accessibility/security constraints, and rollback strategy.
- Amend the canonical global/Phase 8 contracts to mark complete MFA removal as an approved planned deviation and P08-09 as a Phase 6/Phase 8 co-owned defect repair. Do not claim MFA removal is implemented until both P08-11 and P08-12 evidence pass.
- Create [`docs/frontend/action-inventory.json`](docs/frontend/action-inventory.json) as a machine-readable baseline. Each visible action records `action_id`, route, label, control kind, contract owner, Auth method or HTTP method/path or local state result, role, success state, failure state, idempotency behavior, and test ID. Unsupported actions are recorded as removed, not shipped.
- Record baseline evidence: frontend checks, live readiness state, blank/failed run symptoms, wrong DSN class, node-keyed LangGraph update shape, zero-token completion risk, stale reservation risk, and current route/control inventory.

Acceptance:

- Plan integrity checks pass.
- The wrapper remains `status: pending`.
- P08-08 is the next and only selected coding packet.
- No application source, migration, dependency, or runtime config changes occur in this packet.
- Commit and push only the approved plan/ADR/inventory/evidence amendment.

## Acceptance checks

Plan integrity checks pass. Wrapper remains pending. P08-08 is the next coding packet. No application source changed.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Do not edit application code. Do not check historical packets 1-6. Stop if structural validation fails.

## Required evidence

Append `P08-07` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
