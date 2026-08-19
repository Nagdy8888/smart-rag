---
title: Comprehensive audit critical findings
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: engineering, security, operations, client-approver
---

# Critical findings

These are production release blockers. A finding remains open until its stated
verification evidence exists; a code change alone is insufficient.

## AUD-C-001: Intended hosted Supabase state was not audited

### Evidence

- The Supabase connection available during review belongs to another
  application and is excluded from all Smart RAG conclusions.
- The repository contains 59 Smart RAG migration files under
  `supabase/migrations/`.
- New security/correctness migrations in the current source include ingestion
  status ACL, citation recheck, pagination, invitation guard, profile update
  freeze, document deletion, and crawl enqueue policy changes.

### Failure scenario

An intended staging or production project may be missing migrations, contain
drift, expose different grants/policies, lack backups, or use incompatible Auth
settings. Source inspection cannot detect those conditions.

### Required remediation

Connect the intended project through a least-privileged reviewed channel. Do
not reuse or modify the unrelated database. Compare ordered migration versions,
schema fingerprints, policies, grants, extensions, Auth/JWKS settings, plans,
PITR, and advisors against a clean local reset.

### Exit evidence

- exact 59-file chain applied without duplicate or missing versions;
- zero unexpected schema drift;
- reviewed security and performance advisors;
- live RLS/role matrix and forbidden cross-user tests;
- backup/PITR and restore evidence for the intended environment.

**Confidence:** High that the evidence gap exists; no claim is made about the
unseen database's actual condition.

## AUD-C-002: Required verification gates are red

### Evidence

Targeted runs on the current dirty tree produced:

- 200 Pyright errors against a recorded zero-error baseline;
- 7 unit-test failures;
- 9 contract-test failures;
- 10 Python files failing formatting;
- Ruff lint/security findings, including import-order, hardcoded-secret
  heuristics, and string-built SQL warnings;
- documentation lint/link failures.

The contract failures include security and integration contracts for admission,
Compose privacy, UI/auth journeys, MFA upload behavior, docstrings, environment
access, and workspace boundaries.

### Failure scenario

A release can contain real authorization, runtime, configuration, or
integration regressions while documentation and baseline files still claim
green status. Reviewers cannot distinguish product defects from stale tests
without resolving each failure.

### Required remediation

Triage every failure. Fix product behavior when the contract is correct; update
tests only when the contract has been deliberately changed and documented. Do
not raise the Pyright baseline or add skips to obtain green output.

### Exit evidence

All format, lint, types, unit, contract, docs, frontend, and build tiers pass
from a clean checkout, with mandatory dependencies present and a zero
unexpected-skip policy.

**Confidence:** High; the commands were executed during this audit.

## AUD-C-003: Managed staging and production are not full-stack qualified

### Evidence

- `.cursor/plans/hybrid-graph-rag/11-phase-production.md` remains unchecked.
- `infra/ec2/docker-compose.t3micro.yml` intentionally excludes worker,
  ClamAV, parser sandbox, and green API services from the accepted small-host
  profile.
- phase-10 gate matrices still mark migration, full-stack, live-model,
  restore, alert, and promotion work as blocked or not run.
- `.github/workflows/staging-deploy.yml` sends an SSM command without a proven
  wait-for-completion, readiness gate, or automated rollback.

### Failure scenario

The edge API can appear healthy while ingestion, scanning, migration,
background jobs, alerts, or restore procedures do not function. A failed
asynchronous SSM deployment may still look successful to CI.

### Required remediation

Run the complete immutable stack on an approved host, prove protected
migration and deployment end to end, wait for SSM completion, gate on
readiness, exercise rollback, and record alert delivery.

### Exit evidence

One managed-staging evidence bundle proves API, worker, ClamAV, parser,
ParadeDB, Valkey, Supabase, SSE, migration, alert, backup, restore, and rollback
under the exact candidate image digests.

**Confidence:** High from repository plans, workflows, and evidence files.

## AUD-C-004: Capacity, latency, and recovery claims exceed proof

### Evidence

- `docs/QUALITY_TARGETS.md` and phase-09 evidence bound the proven corpus to 8
  Hybrid versions, 16 chunks, and 15 graph documents.
- query concurrency is proven at 5 simultaneous runs, not 25 users.
- connection budgets are calculated for one API and one worker.
- live first-token/completion p95, a 70-percent maintenance pause event, and a
  timed RTO/RPO recovery drill remain unproven.

### Failure scenario

Increasing replicas, users, or corpus size can exhaust Supabase connections,
grow graph and ingestion backlogs, breach latency budgets, or make recovery
miss its target while the product is marketed beyond its measured envelope.

### Required remediation

Publish one explicit launch envelope. Run managed load, connection, backlog,
latency, failover, and timed restore tests at that envelope. Treat aspirational
10k/1M/25-user values as unapproved until evidence is signed.

### Exit evidence

Signed capacity results include per-role `pg_stat_activity`, queue age,
first-token and completion p95, error rate, provider cost, rebuild time, RTO,
and RPO.

**Confidence:** High from the current quality targets and evidence records.
