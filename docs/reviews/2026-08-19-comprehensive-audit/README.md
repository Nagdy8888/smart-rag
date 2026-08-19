---
title: Smart RAG comprehensive audit
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: engineering, security, operations, product, client-approver
---

# Smart RAG comprehensive audit

This review independently evaluates the current Smart RAG working tree at
commit `ed1866dabfc97ed8b74fd190f9be6e90948ccfd5`. The tree was dirty during
review: 68 tracked files were modified and 26 files were untracked before this
report pack was added. Findings therefore describe a moving release candidate,
not a reproducible release artifact.

## Verdict

**NO-GO for production.**

The design contains strong security and durability controls, but the intended
hosted Supabase database was not connected for this audit, automated release
gates are red, managed full-stack proof is incomplete, and the tested capacity
envelope is much smaller than a production SaaS claim.

## Important Supabase scope correction

The Supabase project exposed through the review connection belongs to another
application. Its tables, migration history, advisors, extensions, project URL,
and branches are **excluded** from this report.

The Supabase assessment is therefore split deliberately:

- **Verified in source:** 59 local Smart RAG migrations, their SQL contracts,
  grants, policies, functions, indexes, and application call sites.
- **Not verified:** migration application, drift, advisors, RLS state, plans,
  backups, JWKS, and performance on the intended hosted Smart RAG project.
- **Release consequence:** hosted database approval remains blocked until the
  correct project is connected and the live checks in
  [validation results](./04-validation-results.md) pass.

## Read this pack

1. [Executive verdict](./00-executive-verdict.md)
2. [Critical findings](./01-critical.md)
3. [High findings](./02-high.md)
4. [Medium and low findings](./03-medium-low.md)
5. [Validation results](./04-validation-results.md)
6. [Supabase and migrations](./domain/supabase-migrations.md)
7. [Security and backend](./domain/security-backend.md)
8. [Architecture and scalability](./domain/architecture-scalability.md)
9. [Frontend and UX](./domain/frontend-ux.md)
10. [Deployment and operations](./domain/deployment-operations.md)
11. [Code quality and documentation](./domain/code-quality-documentation.md)
12. [Remediation plan](./90-remediation-plan.md)
13. [Interactive audit dashboard](./audit-dashboard.canvas.tsx)

## Method

The review combined:

- independent static inspection across SQL, Python, TypeScript, Docker, IaC,
  workflows, tests, and documentation;
- reconciliation of the earlier production-readiness pack against the current
  tree rather than accepting its claims;
- targeted execution of format, lint, type, unit, contract, documentation,
  frontend, and dependency-audit tiers;
- static migration inventory and RLS/grant/function/index inspection;
- a local browser inspection at desktop and 390-by-844 mobile dimensions;
- parallel domain reviews, followed by central evidence and severity
  calibration.

No production mutation, hosted migration, credential rotation, exploit attempt,
or destructive database test was performed.

## Severity rubric

- **Critical:** blocks release or can cause broad compromise/data loss without
  another compensating proof.
- **High:** material security, correctness, scalability, availability, or
  maintainability risk that must close before production.
- **Medium:** bounded risk, important hardening, or a likely scaling/UX problem.
- **Low:** defense in depth, documentation, or intentional trade-off to track.
- **Unverified:** not asserted as a defect; evidence is missing and must be
  produced before approval.

## Reconciliation with the earlier review

Several earlier findings are fixed in the current working tree:

- query graph dependencies are bound rather than empty;
- ingestion status uses an ACL-aware RPC;
- parser execution fails closed unless the Docker sandbox is available;
- asynchronous query bridging no longer nests directly on the FastAPI loop;
- dead-letter transitions are lease conditional;
- crawled content is scanned before indexing;
- graph indexing loads scan/provider governance from persisted evidence.

Important earlier concerns remain:

- hosted release evidence is incomplete;
- auth-lifecycle tables lack source-level RLS;
- direct `app_api` table policies remain too broad;
- type, unit, contract, format, lint, and documentation checks are red;
- large modules and migrations continue to grow;
- capacity, recovery, alerting, and external assessment are unproven.

## Review status

This pack is `draft` because live intended-Supabase verification, managed
full-stack testing, disaster-recovery proof, and external security testing are
still missing. It may be promoted only after the acceptance checklist in the
[remediation plan](./90-remediation-plan.md) is evidenced.
