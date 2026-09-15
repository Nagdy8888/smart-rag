---
title: P06-43 integrated Web gates
owner: engineering-lead
status: draft
last-reviewed: 2026-09-15
audience: engineering, reviewers, security
---

# P06-43 — Integrated Web gates, then resume P06-17 (2026-09-15)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Git SHA at this record's parent: `f061500` (P06-42). This packet's commit
follows. Do not treat this overlay as production-ready.

## Plan requirement

Quote: verify integrated Web gates, then resume P06-17.

Positive checks: disabled Web fail-closed; Auto never blends company and
web; Web citations are URL metadata only; company citations stay
ACL-gated and non-clickable; hosted enablement is rejected; live Exa is
skip-by-default.

Negative checks: `WEB_SEARCH_LIVE` unset skips the live call; staging
settings plus enabled flag raise at startup.

## Command matrix

| Command | Result |
| --- | --- |
| `uv run python -m pytest` Exa/web/SSE/settings/persist suites | 86 passed, 8 skipped |
| `tests/contract/test_exa_search_live.py::test_exa_search_live_local_only` | skipped (`WEB_SEARCH_LIVE unset`) |
| `tests/contract/test_web_citation_persist.py` | 7 skipped (`SUPABASE_DB_URL` unset) |
| `uv run python -m pytest tests/unit/test_settings.py::test_web_search_rejected_outside_local` | passed (included above) |
| `uv run python scripts/ci/check_migrations.py` | 0 (85 reviewed files) |
| `pnpm exec vitest run` P06-42 origin/scope/citation helpers | 25 passed |
| `uv run python -m ruff check tests/contract/test_exa_search_live.py` | 0 |
| `uv run python -m pyright tests/contract/test_exa_search_live.py` | 0 |

Live Exa was not invoked. No key, query, page body, or result URL is in
this record.

## Hosted rejection

`test_web_search_rejected_outside_local` loads staging and production
settings with `WEB_SEARCH_ENABLED=true` and expects
`SettingsValidationError`. Provider-egress `allowlist.txt` still omits
`exa.ai`.

## Residual risk

- Free-tier Exa quota and no paid production budget.
- No managed `api.exa.ai` provider-egress.
- Hosted persist RPCs were not re-run here (`SUPABASE_DB_URL` unset).
- Playwright member session was not re-run.
- Production Web stays disabled.

## Resume

The canonical Phase 6 queue returns to **P06-17** (PDF Hybrid agent
evaluation). P06-17 and P06-18 remain unchecked. This packet does not
open holdout or freeze Hybrid.

## Rollback

Leave `WEB_SEARCH_ENABLED=false`. Do not add `api.exa.ai` to
provider-egress.
