---
phase: 8
packet: 22
status: pending
title: "Run production-like stack, role, visual, and real-answer verification"
requirement_ids: [P08-22]
---

# Packet 22 — Run production-like stack, role, visual, and real-answer verification

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-21 deterministic gates passed. Docker and credentials are checked without printing secrets.

## Allowed outputs

Clean Docker build, local stack health, role Playwright, visual baselines, one bounded real-provider answer, reconnect/settlement proof, evidence closure.

## Forbidden outputs

Resetting non-disposable data. Accessing the frozen holdout. Merging when blocked. Treating generic error as a successful chat outcome.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-22 — Run production-like stack, role, visual, and real-answer verification

Purpose: prove the application works against the real local topology and one bounded provider call, with explicit prerequisites and no hidden “when available” pass.

Prerequisites and stop conditions:

- Required: Docker, repository-supported local Supabase/Compose tooling, sufficient disk/ports, approved synthetic fixtures, valid OpenAI credential, and available existing query budget.
- Check prerequisites without printing credentials. If a credential, entitlement, Docker service, or budget is unavailable, record a blocked result and stop; P08-23 may not merge.
- This packet is expected to be long-running on Windows/PowerShell. Use repository commands and bounded health waits; do not replace checks with ad hoc shell behavior.
- Never reset or destroy non-disposable data. Use only the repository’s isolated/disposable path when a reset is required.

Verification:

- Build from a clean Docker context and prove no local `.env`, privileged key, token, `.next`, or host dependency entered an image layer.
- Start local Supabase/Compose through repository scripts and health gates.
- Prove live/meta/readiness, direct/session checkpoint/store connectivity, and optional graph degradation semantics.
- Seed only approved synthetic users/documents for owner, admin, member, and viewer; never access the frozen holdout.
- Run role-aware Playwright journeys for every retained route/action and capture intentional visual baselines at 390px and 1280px for the normative states.
- Run one bounded real-provider browser query. It must show real Generating/Verifying progress, then a non-empty verified answer or grounded refusal, at least one durable compatibility `token_delta`, exactly one terminal, correct settlement, and citations when evidence exists.
- Prove reconnect/resume with monotonic sequences and no duplicate provider call/cost. Test refresh, cancel, API/model/checkpoint error, BM25/graph degradation, 402, 403, 426, 429, and revoked session.
- Tighten any test that treats generic `error` as a successful chat outcome.

Evidence closure:

- Update Phase 6 and Phase 8 evidence with commands, exit codes, durations, test counts, live/manual classification, retained screenshot paths, authorization/idempotency/fallback proof, rollback, and external assumptions.
- Any skipped mandatory journey, chat error terminal, answer before verification, zero-answer completion, wrong settlement, unresolved secret, or authorization failure blocks delivery.
- Do not mark remediation packets or Phase 8 complete until required evidence is committed and user-accepted under canonical rules.

## Acceptance checks

Real Generating/Verifying then non-empty verified answer or grounded refusal. One terminal. Correct settlement. Role journeys pass or the packet is explicitly blocked.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

If credential/Docker/budget is unavailable, record blocked and stop. P08-23 may not merge.

## Required evidence

Append `P08-22` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
