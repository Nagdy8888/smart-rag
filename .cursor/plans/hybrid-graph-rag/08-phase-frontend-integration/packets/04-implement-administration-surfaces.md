---
phase: 8
packet: 4
status: pending
title: "Implement team, tools, alias/entity curation, usage, budgets, restricted read/download audit, profile, and company settings with server-enforced permissions. Preserve frame 14's usage/budget information hierarchy and degradation/critical-reserve patterns. Because the remaining administration surfaces have no delivered frame, derive them from `API_UI_MAPPING.md`, reuse approved primitives and shell patterns, and list the design gap in exit evidence."
requirement_ids: [P08-04]
---

# Packet 4 — Implement team, tools, alias/entity curation, usage, budgets, restricted read/download audit, profile, and company settings with server-enforced permissions. Preserve frame 14's usage/budget information hierarchy and degradation/critical-reserve patterns. Because the remaining administration surfaces have no delivered frame, derive them from `API_UI_MAPPING.md`, reuse approved primitives and shell patterns, and list the design gap in exit evidence.

Read the [Phase 8 shared contracts](../00-shared-contracts.md) and [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

- `P08-01` through `P08-03` provide approved primitives, Auth/typed clients, and core surfaces.
- Real team, tool, curation, usage/budget/rate, audit, profile, and company-setting contracts and roles are available.
- Phase 7 mapping specifies every missing administration surface.

## Allowed outputs

- Production administration/settings surfaces, components, routes, tests, gap designs, and documentation.
- Frame-14 traceability and missing-frame evidence.

## Forbidden outputs

- Client-only role enforcement, invented administration endpoints, fake budgets/rates/audit events, or privileged browser credentials.
- Exposure of restricted evidence text, internal trace data, unauthorized member/source identity, or raw errors.
- Treating absent frames 02/08/11/12/13 as optional scope.

## Ordered actions

1. Implement team invitations, role management, offboarding/session state, and allowed owner/admin/member/viewer actions through real contracts.
2. Implement tool cards/manifests/version/enable/permission/usage and Hybrid alias plus graph type/alias/do-not-merge curation with categorized feedback approval.
3. Recreate frame 14's usage metrics, route-cost views, graph-maintenance degradation, budget policies, critical reserve, rate feedback, and notification hierarchy.
4. Implement authorized restricted read/preview/download audit history without full passage leakage.
5. Implement profile and company settings, including approved localization and policy controls.
6. Reuse approved primitives for every missing administration frame and record each gap/design decision.

## Acceptance checks

- Server denial protects every mutation and restricted read even if controls are forged or revealed.
- Frame 14 hierarchy and degradation/critical-reserve patterns match the accepted reference.
- Tool/curation changes display version, permission, enable state, and auditable outcomes.
- Audit history exposes only authorized metadata and records restricted access consistently.
- Every absent administration frame has an approved, mapped, primitive-based solution in evidence.

## Negative tests

- Forge roles and tool permissions; attempt cross-user/team access, disabled-session use, budget mutation, curation without authority, and restricted audit export.
- Verify viewer/member/admin/owner differences at both UI and server boundaries.
- Test rate/budget/graph-reserve degradation and sanitized failure behavior without fake success.
- Scan for static diagnostics, placeholder routes, hard-coded identities, client secrets, inline scripts, and unsafe rendered metadata.

## Stop routes

- Stop when a required administration action lacks real server authorization or an auditable contract.
- Return missing API/mapping or security contradictions to the owning phase; do not approximate with UI state.

## Required evidence

Append `P08-04` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): frame-14 parity, each missing-frame decision, role matrix and forged-request results, audit privacy proof, budget/rate/degradation tests, changed paths, and blockers.
