---
phase: 11
packet: 5
status: pending
title: "Publish the complete documentation index, ADRs, API/config/provider records, retention policy, and all required operational runbooks."
requirement_ids: [P11-05]
---

# Packet 5 — Publish the complete documentation index, ADRs, API/config/provider records, retention policy, and all required operational runbooks.

Required contracts: [phase shared](../00-shared-contracts.md) and [documentation/handoff](../../shared/release/06-documentation-operational-handoff.md).

## Preconditions

- P11-01–04 pass; exact production evidence; doc lint/link/Mermaid/API/docstring commands; assigned authors/reviewers; access closed.

## Allowed outputs

- README/index, concern docs, ADRs, API/config/provider records, retention policy, runbooks, Mermaid and validation evidence.

## Forbidden outputs

- Catch-all/copied conflicting/stale-unlabeled/broken/unowned docs; secrets/private content; missing rollback/verification/escalation; diagram-only contracts; completion.

## Ordered actions

1. Keep root README concise; publish complete owner/status/last-reviewed reciprocal `docs/README.md`.
2. Update required architecture/ingestion/retrieval/eval/API/config/deployment/security/governance/retention/frontend docs.
3. Verify all required ADRs and canonical provider governance.
4. Publish all runbooks with prerequisites/auth/bounds/rollback/verification/escalation/evidence.
5. Publish exact retention/legal-hold defaults and immediate/24-hour behaviors.
6. Update/render required Mermaid diagrams.
7. Verify documentation of all APIs/env/migrations/jobs/providers/prompts/config/deployment/workflows; run all gates.

## Acceptance checks

- **P11-05-A:** Complete owned dated index/links. Evidence: link report. Failure: block.
- **P11-05-B:** Canonical document/ADR/runbook coverage matches production. Evidence: matrix. Failure: owner.
- **P11-05-C:** Retention preserves 30-day, 90-day, 12-month, 24-month, 30-day traces, seven-year audit, immediate deletion, 24-hour derived purge. Evidence: approval. Failure: no access.
- **P11-05-D:** Required Mermaid renders supplement contracts/limits/failures. Evidence: report. Failure: repair.
- **P11-05-E:** Markdown/link/API/type/docstring/secret gates pass. Evidence: outputs. Failure: block.

## Negative tests

- Broken link, unlabeled stale claim, missing metadata/rollback/escalation, broken/diagram-only Mermaid, secret/private fixture, undocumented API/config change.

## Stop routes

- Stop on missing/stale/broken/unowned/contradictory docs, failed validation, or exposure; label external uncertainty; access closed.

## Required evidence

Append P11-05 to `docs/development/phase-11-production-evidence.md`: index/coverage paths and metadata, retention approval, inventories, Mermaid outputs, docs/API/type/docstring/secret gates, negatives, unresolved labels, repairs.
