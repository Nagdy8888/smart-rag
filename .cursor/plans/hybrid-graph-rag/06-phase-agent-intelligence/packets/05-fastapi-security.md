---
phase: 6
packet: 5
status: pending
title: "Implement thin FastAPI routers/services, Supabase-Auth/FastAPI rate ownership, authorization-safe retrieval caching, endpoint-specific authorization, CPU offload, and prompt/data isolation."
requirement_ids: [P06-05]
---

# Packet 5 — Implement thin FastAPI routers/services, Supabase-Auth/FastAPI rate ownership, authorization-safe retrieval caching, endpoint-specific authorization, CPU offload, and prompt/data isolation.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

## Preconditions

- Packets 1–4 are accepted; Phases 1–5 provide actual backend boundaries, Supabase Auth/RLS/provider-throttle qualification, private rate/cache Valkey contracts, audit chain, crawl/upload protections, repositories/gateways, and route/tool services.
- Inspect current routers/services, migrations, CORS/security configuration, cache invalidation events, local Compose networks/memory limits, and repository verification commands before editing.
- Phase 6 owns application/API configuration, local behavior, exporter/signing interfaces, and local automated tests. Phase 10 owns CloudFront/WAF/Caddy IaC, real staging-CDN 50-second stream proof, AWS KMS/S3 Object Lock, origin restrictions, and managed-topology verification; record blockers without provisioning or faking AWS.

## Allowed outputs

- Thin routers/services/dependency factories, endpoint authorization, application-owned rate/degraded paths, separate Valkey limit/cache configuration, authorization-safe retrieval cache, event-loop/CPU offload controls, prompt/data isolation, audit-export interfaces/local adapters, local tests/docs/evidence.
- Additive schemas/functions/configuration only when required by the accepted Phase 6 API/security contracts.

## Forbidden outputs

- Repository injection directly into routers, browser/user/service-role access to private state, wildcard credentialed CORS, claiming FastAPI throttles browser-direct Supabase Auth, cost/mutation fail-open, stale cache evidence, blocking work on the event loop, raw source HTML/instructions, or full passage text in audit events.
- Managed AWS resources/proof, production UI, packet 6 SSE implementation, packet 7 retention/deletion implementation, speculative Phase 10 IaC, or invented endpoint/schema state.

## Ordered actions

1. Build thin routers under [`apps/backend/src/smart_rag_api/routers/`](../../../../../apps/backend/src/smart_rag_api/routers/) using services injected through `Depends`; services receive core repositories/gateways or agent entrypoints through factories/dependencies, and routers never inject repositories directly.
2. Implement endpoint-specific authorization for:
   - Auth/team: current user, initial owner bootstrap, invitations, allowed domains, MFA state, disabled/session-revoked state, role changes, offboarding, user export/delete.
   - Documents: signed upload creation, ingestion finalization, URL source, list/detail/status, retry, delete, graph rebuild.
   - Chat: conversation create/list/delete, idempotent query submit/stream handoff, authorized event resume/run fetch/cancel, citation detail.
   - Graph: authorized entity search and bounded neighborhood/path debugging.
   - Tables: authorized manifests and validated bounded internal analysis.
   - Tools: catalog search and admin create/version/enable/permission.
   - Feedback/usage: thumbs, correction text, retrieval diagnostics, company/user usage.
   - Operations: separate `/health` liveness and dependency-aware `/ready` readiness.
   - Compatibility: `/api/meta` or documented equivalent exposes `api_version`, `sse_schema_version`, and `min_client_version`; packet 6 owns handshake behavior.
3. Configure explicit production/preview CORS allowlists with no wildcard credentials. Enforce request/body/file/page/query limits, safe pagination, parser timeouts, URL SSRF controls, generic errors, security headers, structured audit, and sanitized filename/log fields.
4. Preserve rate ownership: browser-direct email/password, Google OAuth, password reset, and Supabase MFA enrollment/challenge use Phase 2-qualified Supabase Auth rate/captcha controls. FastAPI/Valkey never claims those requests.
5. For FastAPI-owned work, use burst-tolerant pre-auth IP limits plus normalized invitation identifiers, then post-auth user/company/concurrency limits for invitation acceptance, general API, chat starts, streams, uploads/finalization, URL crawl approval/start, and admin operations; return `Retry-After`.
6. Make Valkey loss endpoint-specific and observable:
   - Invitation/auth-adjacent FastAPI mutations use a bounded Valkey timeout then atomic private Postgres `auth_rate_limit_buckets`; if both fail, return `503` plus `Retry-After`.
   - Cost-bearing or mutating starts fail closed.
   - Only low-risk authenticated reads may use a conservative per-process emergency limiter and fail open, with durable `rate_limit_degraded` audit, in-app notification, alert, and degraded readiness.
   - Kill/restart/ACL/OOM/recovery tests prove application throttles do not disappear or double-admit; Phase 2 separately proves direct Supabase Auth throttles.
7. Run limits and cache as separate Valkey instances/containers. Disable default `nopass`; use named least-command/key-prefix ACL users and long rotating Secrets-Manager credentials. Limits use explicit `maxmemory`, `maxmemory-policy noeviction`, TTL on every counter, a hard container cap, and `maxmemory` at most 70% of that cap; cache uses an independent cap and evaluated evicting policy. Fit total memory to EC2 budget and alert before host OOM. Omit TLS only on same-host isolated networks under an ADR; no untrusted/parser container joins either network.
8. Implement retrieval cache using the Phase 4 key/recheck interface: principal/ACL-scope hash + profile/index versions + document-visibility generation. Store IDs/ranks only; default result TTL is 30 seconds and profile/embedding TTL is 300 seconds. Best-effort invalidate on delete/ACL/current-version events, but authoritatively recheck Postgres current-version/deletion/ACL on every hit before evidence assembly. Phase 4 does not own Valkey instances.
9. Emit `cache_hit`, `cache_miss`, `cache_invalidated`, and `cache_recheck_failed`. A failed recheck drops candidates or performs live retrieval and never serves stale evidence.
10. Keep async nodes free of blocking SDK/filesystem/database work. Instrument event-loop lag and per-node CPU. Pure-Python fusion, MMR, mapping transforms, and validation remain in process only while measured p95 CPU slice is at most 10 ms; above it use a bounded process pool. Use a bounded thread pool for blocking I/O/C-extension work where appropriate; server-control queues/concurrency and propagate cancellation.
11. At five simultaneous Composite runs prove p95 event-loop lag below 50 ms, heartbeat jitter below two seconds, and no missed 15-second heartbeat. A miss blocks release or requires an independent query-runner design. Packet 6 supplies heartbeat transport and packet 8 integrates the proof.
12. Treat every source as untrusted: structured unique delimiters/source IDs, explicit instruction-isolation policy, citations only from supplied IDs, and schema validation for tool arguments, profiles, LightRAG mode/limits, table plans, and source references. React output-encodes entity/relation/crawl/OCR content with no raw HTML/dangerous insertion.
13. Preserve append-only audit roles and private serialized daily/company hash-chain insertion (`previous_hash` plus canonical row hash). Implement exporter/signing interface, schedule, chain/anchor payload contract, failure handling, and local adapters. Missing/reordered/changed rows, forks, export/anchor gaps, or signing failures alert and block audit readiness.
14. Record the managed handoff: Phase 10 provides a KMS key unavailable to database roles, 15-minute chain-head anchors, signed daily batches to S3 Object Lock, and verification of every anchor. Phase 6 claims no managed proof and documents that anchoring reduces but does not eliminate privileged-compromise risk.
15. Verify packet 1's reserve-once integration remains separate from rate limits. Phase 9 later measures reservation-lock wait at maximum concurrency with provisional p95 below 50 ms and zero lock timeouts/overspend.

## Acceptance checks

- Every endpoint has explicit role/ownership/current-version/deletion/ACL behavior; routers remain thin and dependency direction is router → service → factory-injected core/agent boundary.
- Provider-owned Auth and FastAPI-owned rate controls are independently proven; Valkey loss follows exact endpoint policy with no vanished/double throttle and observable degraded readiness.
- Separate Valkey ACL/network/memory policies pass, including limits `noeviction`, every-counter TTL, and `maxmemory <= 70%` of its container limit.
- Cache downgrade/deletion/current-version fixtures yield zero stale evidence after mandatory Postgres recheck; defaults remain 30-second results and 300-second profiles/embeddings.
- Five simultaneous Composite runs meet p95 event-loop lag `<50 ms`, heartbeat jitter `<2 s`, and zero missed 15-second heartbeats; CPU slices over 10 ms are offloaded through bounded cancellable pools.
- Injection/XSS/schema-validation fixtures fail closed, and local audit chain/export/signing adapters detect row changes, gaps, forks, and signing failures without storing full restricted passage text.

## Negative tests

- Direct repository injection, cross-role endpoint call, revoked/offboarded session, wildcard CORS credentials, oversized/pageless request, SSRF redirect/DNS rebinding, unsafe filename/log field, direct-Auth throttle claim, Valkey/DB dual outage, cost mutation fail-open, emergency limiter without audit/alert, default Valkey user, ACL/key-prefix escape, missing TTL, cache key missing scope/version/generation, stale hit, failed recheck served, event-loop blocking/cancel leak, prompt/tool injection, raw HTML/XSS, audit row mutation/fork/gap, or fake AWS proof fails.

## Stop routes

- Stop if authoritative endpoint authorization, provider rate ownership, atomic Postgres degraded limiter, cache recheck, bounded offload, or append-only audit boundary cannot be exercised locally.
- Stop rather than provisioning Phase 10 infrastructure, weakening fail-closed behavior, or inventing missing schemas/configuration.

## Required evidence

- Append to [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md): route/service dependency map, endpoint authorization matrix, CORS/limits/SSRF tests, provider/FastAPI rate traces, Valkey kill/restart/ACL/OOM/recovery results, memory/TTL/config fingerprints, cache invalidation/recheck leak fixtures, CPU/event-loop/pool/cancellation metrics, injection/XSS captures, audit chain/export/local signing faults, explicit Phase 9/10 blockers, exact commands/exit codes, deviations, rollback, and packet 6 handoff.
