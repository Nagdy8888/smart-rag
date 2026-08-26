---
phase: 8
packet: 23
status: pending
title: "Final review, pull request, and normal merge"
requirement_ids: [P08-23]
---

# Packet 23 — Final review, pull request, and normal merge

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-11 and P08-12 are both present. P08-21 passed. P08-22 passed or is an explicit documented blocker that forbids merge.

## Allowed outputs

Full-diff review, push, PR, required checks, normal merge, local main fast-forward.

## Forbidden outputs

Force-push main. Bypassing branch protection. Merging with MFA packets split. Weakening failed checks.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-23 — Final review, pull request, and normal merge

Purpose: deliver the requested branch-to-main integration without bypassing safety.

Implementation:

- Confirm no unrelated/generated/secret file is staged.
- Review `main...feat/frontend-functional-overhaul`, every packet commit, migration/API compatibility, action inventory, docs, and evidence.
- Ensure every packet has a concise repository-style commit and the feature branch is pushed.
- If `origin/main` advanced, use a non-destructive update and rerun affected gates; never force-push main.
- Create the pull request with summary and test plan, then wait for required GitHub checks.
- Merge only when P08-11 and P08-12 are both present, P08-21 and P08-22 pass, checks are green, and the diff matches scope.
- Use the repository’s normal merge commit method; never bypass branch protection.
- Synchronize local `main` with `git pull --ff-only` and prove it equals `origin/main`.
- Report PR URL, merge commit, verification summary, and any provider residue that is documented but not falsely claimed removed.
- On auth, protection, conflict, entitlement, or CI failure, stop and report; do not rewrite history or weaken gates.

## Acceptance checks

PR URL, merge commit, verification summary, and any honest provider residue are reported. Local main equals origin/main.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

On auth, protection, conflict, entitlement, or CI failure, stop and report.

## Required evidence

Append `P08-23` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
