---
phase: 6
packet: 43
status: complete
title: "Verify integrated Web gates, then resume P06-17."
requirement_ids: [P06-43]
---

# Packet 43 — Verify integrated Web gates, then resume P06-17.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`verify-release-gates`](../../../../../.cursor/skills/verify-release-gates/SKILL.md),
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

Do not start P06-17 live qualification in this packet.

## Preconditions

- Packets 38–42 are implemented on `feature/advanced-web-research-mode`.
- Local Exa live tests run only when `WEB_SEARCH_LIVE=1` and
  `APP_ENV=local`. Do not read `.env` into evidence.

## Allowed outputs

- Integrated tests: routing, citations, migration, streaming, frontend
- Gated live Exa test file that is skip-by-default
- Docs updates: QUERY_ROUTING, SSE, CONFIGURATION, CORE_RAG_SURFACES,
  packet evidence
- Wrapper checkbox for this packet after gates pass
- Explicit resume note that the canonical queue returns to P06-17

## Forbidden outputs

- Enabling Web in staging/production
- Adding `api.exa.ai` to provider-egress
- Logging keys, queries, page text, or full URLs
- Claiming production readiness
- Opening holdout or freezing Hybrid
- Checking P06-17/P06-18

## Ordered actions

1. Run unit/contract/frontend tests for packets 38–42.
2. Run migration/RPC privilege tests.
3. Run SSE tests proving progress-only until verify and no body leak.
4. Run a skip-by-default live Exa test only when explicitly gated.
5. Confirm hosted settings still reject `WEB_SEARCH_ENABLED=true`.
6. Record residual risk: free-tier quota, no managed egress, no paid
   budget.
7. Append evidence and resume P06-17 as the next canonical packet.

## Acceptance checks

- Disabled Web fail-closed is proven.
- Auto never blends company and web.
- Web citations are URL metadata only.
- Company citations remain ACL-gated and non-clickable.
- Hosted enablement is rejected.
- Live Exa, if run, is local-only and skip-by-default in CI.

## Negative tests

- `WEB_SEARCH_LIVE` unset → live test skipped.
- Staging settings + enabled flag → startup ValueError.

## Stop routes

- Stop if any packet 38–42 acceptance is unproven.
- Stop if evidence would include secrets or page bodies.

## Required evidence

- Command matrix with exits, skipped live test, hosted-rejection proof,
  residual-risk list, and P06-17 resume statement.
