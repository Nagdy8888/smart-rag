---
phase: 6
packet: 36
status: complete
title: "Run integrated verification, reconcile docs, and write the close evidence."
requirement_ids: [P06-36]
---

# Packet 36 — Run integrated verification, reconcile docs, and write the close evidence.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-supabase-security`](../../../../../.cursor/skills/implement-supabase-security/SKILL.md),
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md),
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md),
[`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md),
[`verify-release-gates`](../../../../../.cursor/skills/verify-release-gates/SKILL.md).

This packet adds no missing core feature. It may make narrowly scoped fixes
for failures discovered by its required gates.

## Preconditions

- Packets P06-28 through P06-35 have evidence. P06-10 is accepted.

## Allowed outputs

- Narrow fixes for gate failures discovered here.
- Documentation reconciliation listed below.
- Close evidence and handoff back to P06-11.

## Forbidden outputs

- Hiding failures, weakening thresholds, or opening holdout.
- Freeze/profile mutation.
- Claiming live exam proof from mocks.
- Down-migrating populated hosted tables.

## Ordered actions

1. Run canonical plan integrity and Markdown links/Mermaid.
2. Prove migration reset/reapply, allowlist, generated hash, hosted
   migration presence, RLS, grants, function search paths, and advisors.
3. Prove owner/admin CRUD and member/viewer, forged/stale/revoked, run
   ownership, document ACL, and generic IDOR negatives.
4. Prove capacity concurrency, CAS, idempotency collision, audit, immediate
   delete, and 365-day purge.
5. Prove hidden conversation exclusion and ordinary conversation regression.
6. Prove exam one-active, qualification-once, lease heartbeat/reclaim,
   crash resume, cancellation, reservation true-up, and budget/rate failure.
7. Prove production-Hybrid parity, cold-cache behavior, all-required-gold
   scoring, stale-version preflight, degradation, gate minimums, and no
   denominator cherry-picking.
8. Prove private canary absence from logs, errors, reports, traces, query
   keys, and frontend DOM before authorized detail/reveal.
9. Prove ordinary feedback regression, quiz role/capability, curation,
   progress/refresh, accessibility, XSS/RTL, and owner plus member E2E.
10. Prove staging/production/disabled route omission.
11. Reconcile docs: both evaluation-workspace ADRs, PDF eval workspace/hybrid
    docs, ADMINISTRATION, API_UI_MAPPING, FASTAPI_SECURITY, OpenAPI,
    AUTHORIZATION_MODEL, SUBPROCESSOR_GOVERNANCE, CONFIGURATION, data
    dictionary, QUALITY_TARGETS, action inventory, docs index.
12. Write close evidence and request user acceptance. Handoff to P06-11.

## Acceptance checks

- Repository-wide commands in this packet's evidence table have recorded
  exit codes.
- Hosted migration/project verification exists without secrets, or is marked
  unverified with a blocker.
- Metric version, hashes, case count, numerator/denominator, Recall@10, gates,
  and degradation are recorded when a live exam ran; otherwise live proof is
  an explicit blocker.
- `holdout_opened=false`.
- Rollback steps are documented.

## Negative tests

- A skipped required authorization, crash, budget, migration, frontend, or
  live boundary test cannot be reported as pass.
- Private canary data in logs/traces/reports/errors fails the packet.

## Stop routes

- Stop instead of substituting mocks for unavailable live proof.
- Do not check this packet if any required gate is hidden.

## Required evidence

- Append exact commands and exit codes, unverified live/staging assumptions,
  rollback, and an explicit request for user acceptance before returning to
  P06-11.
