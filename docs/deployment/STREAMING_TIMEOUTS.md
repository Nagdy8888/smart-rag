---
title: Streaming timeouts (local contract)
owner: engineering-lead
status: draft
last-reviewed: 2026-08-16
audience: engineering, ops
---

# Streaming timeouts

Local configuration contract for SSE. This document does **not** claim that
Caddy, CloudFront, or WAF are deployed. Phase 10 owns CloudFront/WAF/Caddy
IaC and a real staging 50-second CDN stream.

Related: [SSE.md](../api/SSE.md) · [Caddyfile](../../infra/caddy/Caddyfile) ·
[ADR-api-sse-compatibility](../adr/ADR-api-sse-compatibility.md)

## Required values

Every timeout below is **exactly 90 seconds**. Composite's hard deadline is
50 seconds, so 90 seconds leaves margin. Do not rely on provider defaults.

| Input | Value | Owner |
| --- | --- | --- |
| Caddy upstream/read timeout | 90s | `infra/caddy/Caddyfile` (local contract file) |
| CloudFront `OriginReadTimeout` | 90s | Phase 10 IaC |
| CloudFront `OriginKeepaliveTimeout` | 90s | Phase 10 IaC |

Caddy buffering is disabled with `flush_interval -1`.

## Phase 10 blockers

- Assert the same 90-second values in managed CloudFront/WAF/Caddy IaC.
- Prove a deliberately slow Composite run through staging CloudFront for at
  least 50 seconds without buffering or premature origin close.
- Independent Vercel/API deploy skew and origin-restriction checks.

## Verification

```
uv run python -m pytest tests/contract/test_streaming_timeout_contract.py -q
```
