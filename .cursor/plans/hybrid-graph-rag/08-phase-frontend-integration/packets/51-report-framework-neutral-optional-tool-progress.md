---
phase: 8
packet: 51
status: pending
title: "Report framework-neutral optional-tool progress"
requirement_ids: [P08-51]
---

# Packet 51 — Report framework-neutral optional-tool progress

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BEP-04` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-50 complete. Optional-tool service signatures are inspected.

## Allowed outputs

core tools/progress.py, agents streaming/tool_progress.py, optional_tools node wiring, and tests.

## Forbidden outputs

langgraph imports in core. Reporting keys not in the selected role-visible tuple. Changing tool outcomes when the reporter fails.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Add ToolProgressReporter selected/phase. Report only after authorization/policy filtering. started immediately before execution; completed/failed on existing paths. Adapter writes kind/tool_key/phase only.

## Acceptance checks

Intent none/skipped: no phases. Success: started then completed. Safe failure: started then failed. Import-boundary tests pass.

## Negative tests

Callback receiving query/args/result/exception text fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if core would need a LangGraph import.

## Required evidence

Append `P08-51` (`BEP-04`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
