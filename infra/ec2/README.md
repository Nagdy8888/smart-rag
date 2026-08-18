---
title: EC2 / CloudFront / SES staging IaC
owner: engineering-lead
status: draft
last-reviewed: 2026-08-18
audience: engineering, ops
---

# Managed staging IaC (`infra/ec2`)

Reviewed Terraform, staging Compose, and Caddy for Phase 10 Packet 1. This
directory is **not** live provision evidence. AWS CLI session expiry and
missing Terraform/OpenTofu classify apply as **Blocked**. Do not run
`aws login` or `terraform apply` from Packet 1 CI.

Related: [MANAGED_STAGING.md](../../docs/deployment/MANAGED_STAGING.md) ·
[STREAMING_TIMEOUTS.md](../../docs/deployment/STREAMING_TIMEOUTS.md) ·
[intended topology](./intended-topology.json)

## Intended freeze (not a live project)

| Item | Value |
| --- | --- |
| AWS region | `us-east-1` |
| Supabase region | `us-east-1` |
| Supabase plan | Pro (PITR for signed RPO ≤24h) |
| SES | sandbox only |
| Envelope | QT-CAP-001-P9=8, QT-CAP-002-P9=16, QT-CAP-005-P8=15 |
| ParadeDB | `paradedb/paradedb:pg17@sha256:dca046b8a0ddd070c368d5254cbb7f596b3b7bc67bc2efa7c0fbe881087883bb` |
| CloudFront timeouts | `origin_read_timeout = 90`, `origin_keepalive_timeout = 90` |

The Terraform AWS provider 5.100 website still mentions a 60s default upper
bound for origin timeouts. The AWS CloudFront API allows OriginReadTimeout
1-120. Packet 1 encodes **90** and must not silently lower it.

Packet 5 adds `kms_s3_audit.tf` and `alerts.tf`. Live KMS PutObject, SNS
delivery, and the 50 USD budget alert remain **Blocked**. HMAC is not KMS.

## Review locally (no cloud)

```powershell
uv run python scripts/phase10_staging.py assert-iac
uv run python scripts/ci/check_phase10_packet1.py
uv run python scripts/ci/check_phase10_packet2.py
uv run python scripts/ci/check_phase10_packet3.py
uv run python scripts/ci/check_phase10_packet4.py
uv run python scripts/ci/check_phase10_packet5.py
```

## Apply later (when accounts and a valid session exist)

1. Copy `terraform.tfvars.example` to a gitignored `terraform.tfvars`.
2. Set sensitive origin header name/value current and previous (no commit).
3. Install Terraform or OpenTofu. Do not download them from Packet 1 CI.
4. `aws login --profile Nagdy` (or the current profile). The AWS provider
   does not read `aws login` sessions through IMDS. Export keys in the same
   shell, disable IMDS, then plan:

```powershell
$env:AWS_EC2_METADATA_DISABLED = "true"
$env:AWS_REGION = "us-east-1"
aws configure export-credentials --profile Nagdy --format powershell | Invoke-Expression
Set-Location infra/ec2
terraform init
terraform plan -input=false
```

Do not commit `terraform.tfvars`, `tfplan`, or exported keys. Packet 1 CI
still must not apply.

5. Apply only after Packet 1 review sign-off. Packet 2 adds GitHub OIDC,
   named SSM documents, and Secrets Manager placeholders without values.
   Live OIDC assume is still Blocked until GitHub Environments and a valid
   session exist.

Hosted Supabase is online project `qsjivtwtmlmtksufqjik`, not local Docker.
See [ADR-phase10-hosted-supabase-reuse.md](../../docs/adr/ADR-phase10-hosted-supabase-reuse.md).

Live health, prefix-list reachability, and private-port network scans remain
**Blocked** until a real scan artifact exists.

## Vercel

Staging Vercel may receive only `NEXT_PUBLIC_API_BASE_URL`,
`NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. See
[vercel-public-env.json](./vercel-public-env.json).
