---
title: Domain review — operations and release
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: ops, engineering, security
reviewed_commit: 09a102a
---

# Domain: operations and release

Canonical findings: [critical](../01-critical.md) C-002 C-003 C-004 C-013 · [high](../02-high.md) H-006 H-007 H-013 H-014 H-015 H-020 H-032 H-033 · [unverified gates](../05-unverified-gates.md).

## Local RC vs staging vs production

| Layer | State at `09a102a` |
| --- | --- |
| Phase 9 local RC | Closed on **reduced** envelope (8/16, graph 15) |
| Phase 10 IaC | Committed, policy-tested |
| Phase 10 live AWS | VPC/CloudFront/WAF/SES/OIDC/KMS/S3/EC2 exist; **Compose not started** |
| Phase 10 live DB | Hosted project reused, not isolated Pro/PITR freeze |
| Phase 11 | All packets open |

## What is already strong for a local RC

- Distroless non-root API image with pinned digests.
- Trivy/CVE pin ADRs.
- Runbooks: JWKS rollover, origin secret, ClamAV, crawl egress, BM25 rebuild, instance rebuild, protected migration, graph snapshot, alert routing.
- Expand/contract migration ADR.
- Gitleaks config; `.env` gitignored.
- Honest evidence files that say Blocked/Not Run instead of fake green.

## What ops must not do

1. Point production DNS at the t3.micro EIP.
2. Promote project `qsjivtwtmlmtksufqjik` as production without a new isolated project (or a brutal signed ADR).
3. Start Compose on 916 MiB and call the crash a "security incident."
4. Put `service_role` in Vercel (already rejected by Phase 10 tests — keep it that way).
5. Open the sealed holdout to "get a dashboard green."
6. Leave operator AWS keys unrotated after they were pasted in chat (H-032).

## On-call / RTO

Single-host best-effort is signed. There is still no timed restore drill on managed topology. Do not sell 4-hour RTO until that clock exists.
