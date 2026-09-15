---
title: P06-38 bounded Exa REST gateway
owner: engineering-lead
status: draft
last-reviewed: 2026-09-14
audience: engineering, reviewers, security
---

# P06-38 — Bounded Exa REST gateway (2026-09-14)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

## Plan requirement

Quote: implement bounded Exa REST gateway, configuration, and controlled
provider egress.

Positive checks: `httpx` REST only, origin `https://api.exa.ai`,
`x-api-key`, `type=auto`, moderation, 12-result cap, contents allow-list,
one retry on 429/502/503/504 or pre-accept connect failure, hosted
`WEB_SEARCH_ENABLED=true` rejected, canary key absent from logs.

Negative checks: no agents, frontend, SQL, `exa-py`, provider-egress IaC,
or `.env` values.

## Docs retrieved

- [Exa Search](https://docs.exa.ai/reference/search) OpenAPI 2.0.0 on
  2026-09-14
- [Exa Contents](https://docs.exa.ai/reference/get-contents) on 2026-09-14

## Fixture hashes

| File | SHA-256 |
| --- | --- |
| `search_success.json` | `9945e0fe415e54990dedde77139eece24a413d68560e9cd86841aa6fcc8133c3` |
| `contents_success.json` | `2a72d25d1b77a9a881e43681f0e79cbcc23a9e0d7b5f870695559cfbce997074` |
| `error_error_field.json` | `3a5abef1858283a07cec746ec061e0b763310ec5050058e80f45d6dca9e0aef3` |
| `error_message_field.json` | `41f7b1c6ff9c3725029b21d454829916d7634fc149d49ba8fc16d72967dcb312` |

## Verification

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_exa_search_gateway.py tests/unit/test_settings.py tests/contract/test_exa_search_contract.py -q` | 0 |
| `uv run python -m ruff check` on gateway/settings/tests | 0 |
| `uv run python -m pyright packages/core/src/smart_rag_core/gateways/exa_search.py` | 0 |

## Proven

- Disabled settings return no live gateway.
- Enabled without a key fails startup.
- Staging/production plus `WEB_SEARCH_ENABLED=true` fail startup.
- MockTransport happy path returns frozen DTOs with 8,000-character text.
- Arbitrary contents URLs fail closed.
- A third HTTP attempt never occurs.

## Unverified

- Live Exa quota against the operator free tier.
- Managed `api.exa.ai` egress. Not added in this packet.

## Rollback

Set `WEB_SEARCH_ENABLED=false` and delete the gateway module. Do not
enable hosted Web.

## Handoff

Next packet is P06-39 run-scoped web evidence and citations. DTOs:
`ExaSearchCandidate`, `ExaContentItem`, `ExaSearchResponse`,
`ExaContentsResponse`, `create_exa_search_gateway`.
