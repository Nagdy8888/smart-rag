---
phase: 6
packet: 38
status: pending
title: "Implement bounded Exa REST gateway, configuration, and controlled provider egress."
requirement_ids: [P06-38]
---

# Packet 38 — Implement bounded Exa REST gateway, configuration, and controlled provider egress.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md).

Do not load frontend, query-graph, or Supabase-migration skills.

## Preconditions

- P06-37 is recorded. Branch is `feature/advanced-web-research-mode`.
- `httpx==0.28.1` is already pinned. Do not add `exa-py`.
- Verify current Exa `/search` and `/contents` contracts from official docs
  before coding. Never guess request fields.

## Allowed outputs

- `packages/core/src/smart_rag_core/gateways/exa_search.py`
- Lazy exports in `packages/core/src/smart_rag_core/gateways/__init__.py`
- `WEB_SEARCH_ENABLED` and `EXA_API_KEY` on `SharedSettings`; hosted
  rejection validator on `BackendSettings`
- `.env.example` and `docs/development/CONFIGURATION.md` placeholders
- `tests/unit/test_exa_search_gateway.py`,
  `tests/contract/test_exa_search_contract.py`, additive
  `tests/unit/test_settings.py`
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- Agents, frontend, SQL migrations, optional-tool catalog, browser
  automation, `exa-py`, provider-egress Caddy/allowlist changes, `.env`
  values, graph routing, or Web tables.

## Ordered actions

1. Confirm Exa REST from current official docs. Pin request fixtures.
2. Add `web_search_enabled` (default false) and `exa_api_key` (`SecretStr`).
   Reject `WEB_SEARCH_ENABLED=true` unless `APP_ENV=local`. Require the key
   when enabled.
3. Implement `ExaSearchGateway` with frozen DTOs, `search`, `get_contents`,
   and `aclose`. Origin is the module constant `https://api.exa.ai`. Header
   is `x-api-key`. Host is not caller-configurable.
4. `POST /search` uses `type="auto"`, moderation true, at most 12 results,
   bounded highlights, and at most 8,000 text characters when requested.
5. `POST /contents` accepts only URLs already returned by the current
   search, at most six unique URLs.
6. Normalize every URL with crawl `normalize_url`. Reject credentials,
   fragments, unsupported schemes, loopback/private IP literals, and
   oversized URLs.
7. One bounded `httpx.AsyncClient`. Explicit timeouts. Close on shutdown.
8. At most two attempts. Retry only 429/502/503/504 or pre-accept connect
   failure. Do not retry 400/401/402/403/422, schema failure, cancellation,
   or post-send read timeout.
9. Map failures to `web_search_disabled`, `web_search_unconfigured`,
   `web_search_auth_failed`, `web_search_quota_exhausted`,
   `web_search_rate_limited`, `web_search_timeout`,
   `web_search_transport_failed`, `web_search_invalid_response`.
10. Logs may include event, request id, status, attempt, result count,
    elapsed ms, and reported cost. Never log keys, queries, page text,
    highlights, or full URLs.

## Acceptance checks

- Disabled settings build no live gateway.
- Enabled without a key fails startup.
- Staging/production plus `WEB_SEARCH_ENABLED=true` fails startup.
- MockTransport happy path returns bounded immutable DTOs.
- Tests cover nullable metadata, malformed JSON, unsupported URL, too many
  results, truncation, both error envelopes, 401/402/429/5xx, cancellation,
  connect failure, post-send timeout, exactly one allowed retry, deadline
  exhaustion, and client closure.
- Canary key is absent from `repr`, exceptions, and captured logs.

## Negative tests

- Caller-supplied base URL is ignored or rejected.
- Arbitrary contents URLs that were not search hits fail closed.
- A third HTTP attempt never occurs.

## Stop routes

- Stop if official Exa docs disagree with the request/response contract.
- Stop if a staged patch includes agents, frontend, SQL, provider-egress
  IaC, browser dependencies, or `.env`.

## Required evidence

- Verified Exa documentation URLs and date, fixture hashes, command exits,
  hosted-rejection proof, and DTO handoff to P06-39/P06-41.
