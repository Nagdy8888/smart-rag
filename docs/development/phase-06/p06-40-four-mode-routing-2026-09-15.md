---
title: P06-40 four-mode admission and Web envelope
owner: engineering-lead
status: draft
last-reviewed: 2026-09-15
audience: engineering, reviewers, security
---

# P06-40 — Four-mode admission, Auto default, Web envelope (2026-09-15)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

## Plan requirement

Quote: implement four-mode admission, Auto default, exactly-one-source
routing, and Web envelope.

Positive checks: Auto company/general/web/conflict/greeting; forced Web
never searches company; forced company never searches web; disabled Web
is typed fail-closed; envelope matches family; OpenAPI includes `web`
and `answer_origin=web`.

Negative checks: invalid requested scope remains 422; company-insufficient
evidence still never becomes Web; optional-tool catalog still has no
`web_search`.

## Routing

| Case | Effective path |
| --- | --- |
| Auto + company signals | `company_documents` |
| Auto + ordinary world knowledge | `general_knowledge` |
| Auto + explicit/current public web | `web` / `web_research` |
| Auto + company and web together | mixed-scope clarification |
| Greeting / small talk | existing general/user-text paths |
| Forced `web` | `web_scope` only; no company retrieve |
| Forced `company_documents` | existing company matrix; never Exa |
| Forced `web` + company/privacy/secrets | clarification, never Exa |
| Forced `web` + disabled/unconfigured | HTTP 503 before reserve |

Omitted `search_scope` stays Auto. Auto still reserves Composite.
Forced Web reserves `web_research`. Company-insufficient evidence never
falls back to Web or general. Company and web never blend.

## Envelope

Hosted `app.query_route_envelope('web_research')` on project
`qsjivtwtmlmtksufqjik`:

| Field | Value |
| --- | ---: |
| deadline_seconds | 50 |
| model_call_ceiling | 5 |
| tool_ceiling | 5 |
| envelope_usd | 2.00 |
| envelope_prompt_tokens | 40000 |
| envelope_completion_tokens | 10000 |
| recursion_limit | 24 |
| correction_ceiling | 0 |

That envelope fits inside Composite (50s / 9 model / 5 tools / 3.60 USD /
72000 / 18000). A Web route that cannot fit raises
`web_envelope_cannot_fit` and never Hybrid-clamps.

## Files

- [supabase/migrations/20260915120000_query_run_admission_web_v3.sql](../../../supabase/migrations/20260915120000_query_run_admission_web_v3.sql)
- [web_scope.py](../../../apps/agents/src/smart_rag_agents/query/nodes/web_scope.py)
- [test_web_scope_routing.py](../../../tests/unit/test_web_scope_routing.py)
- [QUERY_ROUTING.md](../../agent/QUERY_ROUTING.md)
- [QUERY_ADMISSION.md](../../agent/QUERY_ADMISSION.md)
- [QUERY_BUDGETS.md](../../agent/QUERY_BUDGETS.md)

## Hosted apply (no secrets, no private rows)

Canonical SQL remains one repo file. Hosted history records sliced MCP
names because a single payload is easier to review. Behavior matches the
repo file after the slices below.

| Slice | Result |
| --- | --- |
| `query_run_admission_web_checks_v3` | success |
| `query_route_envelope_web_research_v3` | success |
| `admit_query_run_v3` | success |
| `load_get_query_run_v3` | success (retried after a same-second version collision) |

Privileges proven on project `qsjivtwtmlmtksufqjik` via catalog queries:

| Check | Result |
| --- | --- |
| `runs_requested_search_scope_chk` includes `web` | true |
| `runs_route_family_allowed` includes `web_research` | true |
| `admit_query_run_v2` / `v3` both exist | true |
| `load_query_run_runtime_v2` / `v3` both exist | true |
| `get_query_run_v2` / `v3` both exist | true |
| v3 EXECUTE for `app_api` | true |
| v3 EXECUTE for `anon` / `authenticated` / `app_worker` | false |

Fail-closed HTTP: `web_search_disabled` and `web_search_unconfigured`
map to 503 with typed detail. The production `web_scope` stub returns
`routing_rejected` and never drafts an answer or retrieves company
passages.

## Verification

| Command | Exit |
| --- | --- |
| `uv run python scripts/ci/check_migrations.py` | 0 (85 files; sha256 `8ddcdf48057c78946fa9044fda5a042713a5cfc510e5a47a2a30be2c7de36765`) |
| `uv run python scripts/ci/check_openapi.py` | 0 after snapshot (enum `web`; `source_kind` / `web_source_id` additive) |
| `uv run python -m pytest` P06-40 routing/admission/OpenAPI suites | 155 passed, 4 skipped |
| `uv run python -m ruff check` on P06-40 Python | 0 |
| `uv run python -m pyright` on P06-40 modules | 0 |
| `tests/contract/test_web_scope_admission.py` live SQL | skipped (`SUPABASE_DB_URL` unset; [ADR-cloud-only-supabase-no-local-fixture.md](../../adr/ADR-cloud-only-supabase-no-local-fixture.md)) |

## Proven

- Auto and forced mapping settle exactly one source.
- Forced Web never searches company documents; forced company never
  searches the web.
- Disabled/unconfigured Web is typed 503, not a silent general answer.
- Hosted CHECK, envelope numbers, and v3 wrappers match the repo file.
- Optional-tool catalog still has no `web_search`.
- OpenAPI `RequestedSearchScope` includes `web`; SSE origin accepts `web`.

## Unverified

- Mutation/idempotency tests against a non-hosted `SUPABASE_DB_URL`.
- `supabase gen types --project-id` (CLI not installed). `database.ts`
  was patched UTF-8 to copy v2 function types as v3.

## Rollback

Do not down-migrate the widened CHECK. Disable Web at settings
(`WEB_SEARCH_ENABLED=false`). v2 admit/load/get remain callable.

## Handoff

Next packet is P06-41 bounded iterative Web research graph. Store API
from P06-39 is unused until that graph binds Exa. Ask dropdown remains
P06-42 (`apps/frontend/src/lib/types/chat.ts` and `chat-run.ts` stay
out of this commit).
