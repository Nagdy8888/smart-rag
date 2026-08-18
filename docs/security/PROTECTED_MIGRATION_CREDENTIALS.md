---
title: Protected migration and privileged credentials
owner: engineering-lead
status: proven-local / iac-reviewed-managed / unverified-live
last-reviewed: 2026-08-18
audience: engineering, security, ops
phase_packet: Phase 10 Packet 2
---

# Protected migration credentials

## Local custody (proven)

| Item | Local practice |
| --- | --- |
| Bootstrap / migration DB password | Developer `.env` / `.env.compose` (**gitignored**) |
| Supabase CLI | `npx supabase db reset` / `migration up` using local stack credentials |
| Runtime containers | `api` / `worker` / `frontend` receive only least-privilege URLs (`app_api`, BM25 reader/writer, Valkey) |
| Auth Admin secret | Isolated boundary module only (`apps/backend/.../auth_admin/`); absent from `SharedSettings` / `BackendSettings` |
| Storage Admin secret | Isolated boundary modules only (`apps/backend/.../storage_admin/` and worker `privileged_storage`); absent from `SharedSettings` / `BackendSettings` / `WorkerSettings` / `AgentSettings` |
| `service_role` | Never declared on general runtime settings; never shipped to frontend |

Contract: `tests/contract/test_privileged_secrets_absent.py` plus Packet 4/5 secret-scan tests. That contract inspects runtime settings **field names and env aliases only**; isolated package or loader names such as `storage_admin` / `load_privileged_storage_settings` are not treated as secret declarations.

## Runtime must not load bootstrap

General API/worker/frontend processes must not read:

- migration/bootstrap Postgres superuser URLs
- `SUPABASE_SERVICE_ROLE_KEY` / Auth Admin / Storage Admin secrets for ordinary request paths
- ParadeDB bootstrap DDL credentials (runtime uses reader/writer only)

Health endpoints must not echo privileged secret names or values.

## Managed IaC and workflows (Phase 10 Packet 2 — reviewed, not live)

Committed Terraform and protected workflows now exist:

1. GitHub OIDC provider `https://token.actions.githubusercontent.com` with audience `sts.amazonaws.com`.
2. Staging migrate/deploy roles trust `repo:Nagdy8888/Demo_Project_3:environment:staging` and the matching `job_workflow_ref`. Production migrate trusts `environment:production` only.
3. Roles may `ssm:SendCommand` only to `SmartRagStagingMigrate`, `SmartRagStagingDeploy`, or `SmartRagProductionMigrate` plus Environment-tagged instances. No `ssm:*` Allow, no `iam:*` Allow, no production secret ARNs on staging Allow.
4. Secrets Manager resources `smart-rag/staging/db` and `smart-rag/production/db` are placeholders **without values**.
5. One-shot SSM documents fetch the secret via the **instance** role, redact output, unset process env on EXIT, and record hash/operator/result. They reject `CREATE EXTENSION` and contraction DDL.
6. Workflows `.github/workflows/staging-migrate.yml`, `staging-deploy.yml`, and `production-migrate.yml` use `id-token: write` plus `contents: read`. They pin `aws-actions/configure-aws-credentials@7474bc4690e29a8392af63c5b98e7449536d5c3a` (`v4.3.1`). They store **no** AWS access keys and no database secrets. They are not called from `pr-fast.yml`.

Operator procedure: [PROTECTED_MIGRATION.md](../runbooks/PROTECTED_MIGRATION.md).

**Honest status:** IaC and workflow policy tests **Passed**. Live OIDC assume, SSM migrate, Secrets Manager values, and 90-day rotation are **Blocked**. hashicorp/aws 5.100 requires a rotation Lambda for `aws_secretsmanager_secret_rotation` on non-RDS secrets; this packet does not invent one. Do not treat live migrate as proven.

KMS/S3 Object Lock anchoring remains a later Phase 10 packet.

## Related

- [ADR-expand-contract-migrations.md](../adr/ADR-expand-contract-migrations.md)
- [ADR-privileged-auth-administration-boundary.md](../adr/ADR-privileged-auth-administration-boundary.md)
- [ADR-upload-capability-and-storage-privilege.md](../adr/ADR-upload-capability-and-storage-privilege.md)
- [AUDIT_CHAIN.md](./AUDIT_CHAIN.md)
- [phase-10 evidence](../development/phase-10-managed-staging-evidence.md)
