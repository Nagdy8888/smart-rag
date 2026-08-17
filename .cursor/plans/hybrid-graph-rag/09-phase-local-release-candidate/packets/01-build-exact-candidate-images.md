---
phase: 9
packet: 1
status: complete
title: "Build the exact candidate images and seed only the approved local evaluation corpus through all readiness states."
requirement_ids: [P09-01]
---

# Packet 1 — Build the exact candidate images and seed only the approved local evaluation corpus through all readiness states.

Required contracts: [phase shared](../00-shared-contracts.md), [local release gates](../../shared/release/01-local-release-gates.md), and [sizing envelope](../../shared/release/05-sizing-envelope.md).

## Preconditions

- Phases 1–8 and signed quality/cost/capacity/governance gates are accepted.
- Build, scan, startup, migration, reset, seed, and readiness commands are discovered.
- Pins, image inputs, approved corpus, split boundaries, and local resources are recorded.

## Allowed outputs

- Immutable candidate image digest manifest, reset local stack, approved local corpus, readiness report, and Phase 9 evidence updates.

## Forbidden outputs

- Managed/AWS/production resources or data; mutable images; holdout leakage; manual fake readiness; completion/status changes.

## Ordered actions

1. Record source, dependency/model/prompt/migration/configuration, ParadeDB/`pg_search`/BM25, and LightRAG identities.
2. Build and scan exact images; reset/start the complete local stack and verify private health.
3. Seed only approved role/ACL/language/temporal/table/media/code/alias/graph fixtures.
4. Drive real jobs through every required readiness and failure/deletion state.
5. Freeze candidate, data, and configuration identities for later packets.

## Acceptance checks

- **P09-01-A:** Digest-bound builds and health pass. Evidence: build/scan/health artifacts. Failure: rebuild; changed identity invalidates evidence.
- **P09-01-B:** Migrations reset/reapply and runtime pins match. Evidence: migration/version inventory. Failure: stop on drift.
- **P09-01-C:** Only approved disjoint corpus is seeded. Evidence: immutable manifest. Failure: reset and reseed.
- **P09-01-D:** Real state transitions cover all required readiness states. Evidence: job/state export. Failure: stop on fake or unreachable state.
- **P09-01-E:** Counts/resources map to the signed local envelope without managed claims. Evidence: sizing baseline. Failure: use sizing ladder.

## Negative tests

- Reject digest mismatch, unapproved/production/holdout data, restricted LightRAG input, duplicate/fake readiness, and public ParadeDB/Valkey/LightRAG ports.

## Stop routes

- Stop on prerequisite, pin, migration, corpus, private-port, or readiness failure; return semantic changes to their owner.
- Record cloud-only checks for Phase 10; do not provision or require cloud proof.

## Required evidence

Append P09-01 to `docs/development/phase-09-local-release-candidate-evidence.md`: identities, commands, resources, corpus/split manifest, readiness transitions, negative tests, failures/repairs, artifact paths, and managed blockers, classified Passed/Failed/Blocked/Not Run.
