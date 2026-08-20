---
name: implement-api-security
description: Implements FastAPI authentication, RBAC, rate limits, budgets, audit logs, secure uploads/crawls, operational endpoints, and streaming security. Use for API endpoints or cross-cutting security controls.
---

# Implement API Security

Read the active phase wrapper, its selected packet and shared contract, the relevant endpoint contract, and the Phase 2 identity/data contract only when the packet consumes it. Do not load sibling split-source packets or rely on ambiguous legacy section numbers.

## Request gate

For every endpoint, define and test:

- authentication source and JWT verification;
- owner/admin/member/viewer authorization;
- object ownership/scope check;
- validated body/query/path limits;
- idempotency behavior;
- shared rate-limit policy;
- durable budget reservation where model work can start;
- sanitized errors and structured audit events.

Never accept role, workspace/company scope, source authorization, cost, route, tool, crawl policy, or storage path as trusted client authority.

## Security boundaries

- Verify asymmetric Supabase JWTs through JWKS with bounded caching, one unknown-`kid` refresh, tested rollover, and no production HS256 fallback; also check current membership/session state for sensitive operations.
- Use PKCE; require MFA for owner/admin and upload/URL-source-capable members, single-use 24-hour invitations, documented password policy, and refresh-session revocation when a user is disabled or a privileged/upload role is downgraded.
- Split Valkey limits/cache into ACL-authenticated, independently memory-bounded instances. Browser-direct Auth limits remain Supabase-owned; FastAPI-mediated sensitive/cost-bearing operations fall back atomically to Postgres and fail closed if both enforcement stores fail, while only low-risk reads may use an alerted emergency limiter.
- Query admission reserves route-maximum spend once; calls consume a run-local reservation and completion/heartbeat/expiry/reaper true-up actual usage. Never relock the shared company/user budget row per model call.
- Signed upload/download URLs are short-lived, user-scoped, bucket/path constrained, and server-issued after authorization.
- Crawl URLs pass canonicalization, scheme, DNS/IP, redirect, port, size, depth, page, and content-type checks at every hop; pin/check the actual connection peer IP to block DNS rebinding.
- URL sources require owner/admin approval and all public crawling uses the dedicated egress proxy; API/agents are provider-allow-listed, while private ParadeDB and parser/OCR sandboxes have no public/provider egress.
- BM25 query construction is typed, parameterized, and allow-listed; raw user text cannot execute ParadeDB SQL or unrestricted query syntax. Every BM25 ID is reauthorized in Supabase before evidence use.
- Model prompts delimit instructions from retrieved data; never execute commands found in documents.
- Audit storage is hash-chained, periodically KMS-anchored, append-only for runtime roles, and protected by export/retention checks.
- Conversation deletion immediately removes private messages/runs/events/citations/checkpoints/store summaries/feedback and requests external trace deletion; retention applies only to undeleted data.
- CORS is exact-origin, security headers/CSP are explicit, and production docs/diagnostics are access-controlled.
- Health, readiness, metrics, and job controls reveal no secrets, prompts, unrestricted source text, or personal data.

## Required abuse tests

Expired/revoked/unknown-`kid` JWT, JWKS rollover, MFA/upload permission, invitation replay/expiry, role downgrade, IDOR, cross-user/deleted conversation, forged storage path, duplicate idempotency key, Valkey kill/ACL/OOM degraded limits, reserve-once budget race/crash true-up, DNS rebinding/redirect/egress bypass, ParadeDB private-port/query-syntax/stale-candidate abuse, prompt injection, oversized payload, XSS text, SSE reconnect abuse, and audit chain/anchor mutation.

Use current OWASP and provider documentation for implementation details; do not rely on remembered defaults.
