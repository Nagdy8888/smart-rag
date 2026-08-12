---
title: ADR — Expand/contract migrations
adr_id: ADR-expand-contract-migrations
status: accepted
owner: engineering-lead
last-reviewed: 2026-08-12
approver: "user (Cursor chat; Phase 1–5 mandate)"
approval_date: "2026-08-12"
---

# ADR: Expand → deploy → contract migrations

## Decision

Database changes follow **expand → deploy compatible code/backfill → contract** across separate releases. Destructive DDL never shares a release with its expansion. Phase 1 has **zero** application migrations; Phase 2 introduces schema under this policy.

## Consequences

CI migration check must not claim RLS/reset proof in Phase 1. Rollback keeps expanded schema until contract release.
