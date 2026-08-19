---
title: EC2 / CloudFront / SES staging IaC
owner: engineering-lead
status: draft
last-reviewed: 2026-08-19
audience: engineering, ops
---

# Managed staging IaC (`infra/ec2`)

Reviewed Terraform, staging Compose, and Caddy for Phase 10 Packet 1.
Live inventory is
[packet1-live-aws.json](../../docs/deployment/phase-10/packet1-live-aws.json).
Do not run `terraform apply` from Packet 1 CI. `user_data_replace_on_change`
is false and `lifecycle.ignore_changes` covers `ami` and `user_data` so AMI
churn cannot replace the host.

Related: [MANAGED_STAGING.md](../../docs/deployment/MANAGED_STAGING.md) ·
[STREAMING_TIMEOUTS.md](../../docs/deployment/STREAMING_TIMEOUTS.md) ·
[demo local ingest / AWS ask](../../docs/runbooks/demo-local-ingest-aws-ask.md) ·
[intended topology](./intended-topology.json)

## Intended freeze (not a live project)

| Item | Value |
| --- | --- |
| AWS region | `us-east-1` |
| EC2 type | `t3.micro` (accepted; never `m6i.xlarge`) |
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
4. This workstation uses IAM user `Muna` via local profile `Nagdy-iam`
   (`%USERPROFILE%\.aws\credentials`). Those keys are not in git and must
   not be pasted into chat, `.env`, or the instance. Terraform 5.x can use
   this profile directly (no `export-credentials` into the shell).

```powershell
Remove-Item Env:AWS_ACCESS_KEY_ID, Env:AWS_SECRET_ACCESS_KEY, Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
$env:AWS_EC2_METADATA_DISABLED = "true"
$env:AWS_REGION = "us-east-1"
$env:AWS_PROFILE = "Nagdy-iam"
Set-Location infra/ec2
terraform init
terraform plan -input=false
```

Keep `aws login` profiles (`Nagdy`, `Nagdy-terraform`) only as a fallback
when `Nagdy-iam` is absent. Do not pipe `export-credentials` into env vars.

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
