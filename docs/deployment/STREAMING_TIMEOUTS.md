---
title: Streaming timeouts (local plus staging IaC)
owner: engineering-lead
status: draft
last-reviewed: 2026-08-18
audience: engineering, ops
---

# Streaming timeouts

Local and staging **configuration** contract for SSE. This document
does **not** claim that Caddy, CloudFront, or WAF are live or that a
50-second CDN stream has been proven. Phase 10 Packet 1 asserts
90-second CloudFront timeouts in reviewed IaC. Packet 3 asserts the same
90-second values in staging Caddy and Terraform plus origin-denial
policy. Packet 4 owns a real staging 50-second stream.

Related: [SSE.md](../api/SSE.md) ·
[local Caddyfile](../../infra/caddy/Caddyfile) ·
[staging Caddyfile](../../infra/ec2/Caddyfile) ·
[cloudfront_waf.tf](../../infra/ec2/cloudfront_waf.tf) ·
[MANAGED_STAGING.md](./MANAGED_STAGING.md) ·
[ADR-api-sse-compatibility](../adr/ADR-api-sse-compatibility.md)

## Required values

Every timeout below is **exactly 90 seconds**. Composite's hard deadline is
50 seconds, so 90 seconds leaves margin. Do not rely on provider defaults.

| Input | Value | Owner |
| --- | --- | --- |
| Caddy upstream/read timeout | 90s | `infra/caddy/Caddyfile` (local) and `infra/ec2/Caddyfile` (staging) |
| CloudFront `OriginReadTimeout` | 90s | `infra/ec2/cloudfront_waf.tf` (IaC asserted; live CDN unproven) |
| CloudFront `OriginKeepaliveTimeout` | 90s | `infra/ec2/cloudfront_waf.tf` (IaC asserted; live CDN unproven) |

Caddy buffering is disabled with `flush_interval -1`.

AWS CloudFront API `CustomOriginConfig.OriginReadTimeout` is min 1, max 120,
default 30. `OriginKeepaliveTimeout` is min 1, max 300, default 5. Source:
[CustomOriginConfig](https://docs.aws.amazon.com/cloudfront/latest/APIReference/API_CustomOriginConfig.html).
The Terraform AWS provider 5.100 website still mentions a 60s default upper
bound. Packet 1 encodes 90 and must not silently lower it to 60. Live apply
uses the AWS API contract.

Cache policy for API/SSE is managed CachingDisabled
`4135ea2d-6df8-44a3-9df3-4b5a84be39ad` (no response caching).

## Phase 10 remaining

- Prove a deliberately slow Composite run through staging CloudFront for at
  least 50 seconds without buffering or premature origin close (Packet 4).
- Independent Vercel/API deploy skew.

Packet 3 origin-denial, egress, private-port, WAF/Caddy, and 90s IaC
assertions are recorded in
[phase-10-managed-staging-evidence.md](../development/phase-10-managed-staging-evidence.md).
Live CDN requests, port scans, and CloudWatch alarm delivery remain Blocked.

## Verification

```text
uv run python -m pytest tests/contract/test_streaming_timeout_contract.py tests/contract/test_phase10_packet1.py tests/contract/test_phase10_packet3.py -q
```
