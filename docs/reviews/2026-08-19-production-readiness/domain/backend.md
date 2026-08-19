---
title: Domain review — FastAPI backend
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: engineering, security
reviewed_commit: 09a102a
---

# Domain: backend

Canonical findings: [critical](../01-critical.md) C-008 C-009 C-010 C-014 · [high](../02-high.md) H-001 H-003 H-004 H-005 H-011 H-016 H-019 H-025 H-026 H-028 H-029 · [medium](../03-medium.md) M-001 M-002 M-008 M-013 M-014 M-016 M-021 M-022 M-023 M-024 M-028 · [low](../04-low.md) L-002 L-009 L-010.

## Shape

`create_app()` is a thin transport: routers for ops, auth/team, documents, conversations, query runs, ingestion, glossary, graph inspect, entity rules, tables, tools, usage. Lifespan binds JWKS, Valkey clients (no connect at bind), LightRAG adapter without schema-admin DDL, model gateway, in-memory `QueryRunRegistry`.

Middleware order (outer first as registered): correlation → preauth IP limits → body limit → security headers → CORS. Error handlers installed. Security headers include `CSP default-src 'none'` for JSON and do not advertise HTML (they rewrite `text/html` to JSON). SSE keeps `text/event-stream`.

## Route posture (summary)

| Surface | Auth | Notes |
| --- | --- | --- |
| `/health/live` | No | Process only |
| `/health/ready` | No | Honest mock/graph flags |
| `/api/meta` | No | Version handshake |
| `/docs` `/redoc` `/openapi.json` | **No** | **H-001** |
| Ingestion / documents | Bearer JWKS + profile | **GET status IDOR (C-010)** |
| Admin/tools/usage company | Role-checked in services | Verify each mutation in pentest |
| Auth team / invitations | Mixed | Privileged boundary for Auth Admin |

## SSE

Persist-then-flush with sequence IDs, heartbeats (15s default), GET resume, cancel. Events sanitized (`sse/sanitize.py`). This is one of the best parts of the **transport** — then the live executor sits in a dict (H-005) and compiles an unbound graph (C-009).

## Hardening list (backend-owned)

1. Bind retrievers into `QueryGraphDeps` (C-009) without `asyncio.run` on the event loop (C-014).
2. ACL on GET ingestion status; drop `USING (true)` table reads (C-010).
3. Disable docs in non-test.
4. Environment-specific CORS headers (no X-Test in prod).
5. Byte-counting body limit.
6. Production settings refuse `APP_ENV=test` and loopback CORS.
7. Single-task API until live registry is leased.
8. Split Auth Admin secret off the query replica.
9. Invitation owner-invite + accept overwrite (H-025).
10. Do not write `worker_unavailable` while status is `running` on another color (H-005).
11. Rate-limit `POST /graph/inspect` (M-021). Require query idempotency keys (M-023).

## Compatibility

`/api/meta` publishes `api_version`, `sse_schema_version`, `min_client_version`. Frontend handshake can block paid POSTs. Good for version skew; unproven through Vercel/API skew on staging.
