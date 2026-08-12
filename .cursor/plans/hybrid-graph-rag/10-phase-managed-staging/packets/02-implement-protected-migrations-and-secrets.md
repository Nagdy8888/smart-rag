---
phase: 10
packet: 2
status: pending
title: "Implement GitHub OIDC, protected immutable expand/contract migrations, short-lived credential retrieval, environment separation, and secrets custody."
requirement_ids: [P10-02]
---

# Packet 2 — Implement GitHub OIDC, protected immutable expand/contract migrations, short-lived credential retrieval, environment separation, and secrets custody.

Required contracts: [phase shared](../00-shared-contracts.md), [managed gates](../../shared/release/02-managed-gates.md), and [staging topology](../../shared/release/03-staging-topology.md).

## Preconditions

- P10-01 accepted; expand/contract ADR, protected approvers, branch/tag/OIDC/SSM boundaries, secret owners, immutable migration hash, old/new images verified.

## Allowed outputs

- Scoped OIDC roles, protected workflows, named SSM jobs, separated short-lived secrets/rotation, static migration policy, and evidence.

## Forbidden outputs

- Long-lived/broad CI or database credentials; runtime extension-create; mutable/unapproved/destructive same-release migration; shared environments; unsafe schema rollback.

## Ordered actions

1. Scope OIDC to repository/workflow/branch/tag/protected environment and named SSM targets.
2. Store environment-specific secrets with just-in-time least privilege and rotation.
3. Hash immutable migration and run expand/contract policy.
4. Require approval/hash review; execute one-shot SSM migration with redaction/environment destruction/audit.
5. Run old API on expanded schema; defer contraction; prove no long-lived/runtime-create path.

## Acceptance checks

- **P10-02-A:** OIDC assumes only scoped role/SSM targets. Evidence: allow/deny policy tests. Failure: narrow/stop.
- **P10-02-B:** No persistent secret in GitHub/Vercel/log/image/process. Evidence: scans/lifecycle. Failure: revoke/rotate.
- **P10-02-C:** Approved immutable expansion runs; incompatible DDL is rejected. Evidence: approval/audit. Failure: block.
- **P10-02-D:** Old API remains healthy and contraction absent. Evidence: drain smoke/diff. Failure: redesign.
- **P10-02-E:** Staging/production credentials separate and rotate ≤90 days/after exposure. Evidence: custody policy. Failure: block.

## Negative tests

- Wrong repo/branch/tag/workflow/environment; arbitrary SSM/IAM/database/runtime DDL; incompatible migration; denied approval; credential scan.

## Stop routes

- Stop on overbroad role, exposure, missing approval, mutable/destructive migration, old-slot incompatibility, or unverifiable provider contract; rotate and invalidate.

## Required evidence

Append P10-02 to `docs/development/phase-10-managed-staging-evidence.md`: OIDC policies/denials, SSM targets, approval/hash, compatibility, secret lifecycle/scans/separation/rotation, old-slot smoke, operator/result, forward-fix boundary.
