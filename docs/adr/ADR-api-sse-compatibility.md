---
title: ADR — Additive API and SSE compatibility
adr_id: ADR-api-sse-compatibility
status: accepted
owner: engineering-lead
last-reviewed: 2026-08-12
approver: "user (Cursor chat; Phase 1–5 mandate)"
approval_date: "2026-08-12"
---

# ADR: Additive API / SSE compatibility

## Decision

Within a major version, OpenAPI fields and SSE events evolve **additively**. Removals/renames require a major bump and staging version-skew proof (Phase 10). Foundation snapshot: `docs/api/openapi.foundation.json` (health only).

## Consequences

Frontend types generate from OpenAPI. CI OpenAPI drift check fails on unexpected routes or snapshot mismatch.
