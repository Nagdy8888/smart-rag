---
phase: 9
packet: 2
status: pending
title: "Run all applicable hard CI, expand/contract migration compatibility, identity/RLS/BM25/cache/read-audit, graph isolation, injection, parsing, deletion, idempotency/GC, API/SSE compatibility, and redaction gates with no skipped required tests."
requirement_ids: [P09-02]
---

# Packet 2 — Run all applicable hard CI, expand/contract migration compatibility, identity/RLS/BM25/cache/read-audit, graph isolation, injection, parsing, deletion, idempotency/GC, API/SSE compatibility, and redaction gates with no skipped required tests.

Required contracts: [phase shared](../00-shared-contracts.md) and [local release gates](../../shared/release/01-local-release-gates.md).

## Preconditions

- P09-01 exact candidate/data identity is accepted.
- Repository CI/security commands and all local identity, ACL, parser, injection, deletion, compatibility, and redaction fixtures exist.
- Integration jobs fail on zero matching tests.

## Allowed outputs

- Digest-bound CI, security, migration/API/SSE, scan, evaluation, and negative-test reports; narrow gate repairs and evidence updates.

## Forbidden outputs

- Skipped/empty/flaky-ignored/`|| true`/mock-only mandatory gates; fake managed proof; security bypass; holdout tuning; silent image drift.

## Ordered actions

1. Run format, lint, strict types, unit/component, OpenAPI, migration-static, secret/dependency, frontend-build, and nonzero-test assertions.
2. Run reset/reapply, expand-contract lint, and old-API/new-schema authenticated smoke.
3. Run identity/RLS/RPC/roles/MFA/ACL/graph isolation/Storage/read-audit/conversation ownership and deletion.
4. Run replay/quota/quarantine/parser/malware/structure/BM25/graph/deletion/cache/idempotency/GC.
5. Run routing/grounding/table/injection/governance/egress/budget/rate/API/SSE/reconnect/redaction.

## Acceptance checks

- **P09-02-A:** All locally applicable gates execute and pass with no skip/empty result. Evidence: suite matrix. Failure: local no-go.
- **P09-02-B:** Identity/ACL/deletion/cache/BM25/graph negatives yield zero unauthorized or stale evidence. Evidence: role/state assertions. Failure: launch blocker.
- **P09-02-C:** Replay/idempotency/GC creates no duplicate paid run, chunk, active BM25 row, or graph version. Evidence: before/after state. Failure: repair.
- **P09-02-D:** Expansion, old-slot/new-schema, minimum client, additive SSE/OpenAPI, reconnect, and no destructive DDL pass. Evidence: compatibility matrix. Failure: defer/repair.
- **P09-02-E:** Injection/parser/malware/governance/egress/budget/rate/redaction pass without bypass. Evidence: adversarial reports. Failure: launch blocker.

## Negative tests

- Missing/forged/disabled/stale caller, unknown/revoked `kid`, restricted graph/cache/BM25, injection/XSS, overspend/rate outage, unsupported client, unknown SSE event, and zero-test selection.

## Stop routes

- Stop on authorization, grounding, deletion, budget, redaction, parser, egress, compatibility, skipped, or fake-proof failure.
- Hand real-CDN/managed JWKS/KMS/OIDC/managed restore/external assessment to Phase 10.

## Required evidence

Append P09-02 to `docs/development/phase-09-local-release-candidate-evidence.md`: exact candidate, commands/test counts, full gate matrix, role/ACL and compatibility matrices, negative/redaction/network artifacts, repair history, and managed-only handoff.
