---
phase: 6
packet: 39
status: pending
title: "Add durable run-scoped web evidence, URL citations, and merged source_kind listing."
requirement_ids: [P06-39]
---

# Packet 39 — Add durable run-scoped web evidence, URL citations, and merged source_kind listing.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-supabase-security`](../../../../../.cursor/skills/implement-supabase-security/SKILL.md),
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md),
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).

Do not load frontend skills.

## Preconditions

- P06-37 is recorded. P06-38 DTO/API is inspectable.
- Inspect live `app.citations`, `app.insert_run_citation`,
  `app.list_run_citations_v2`, persist/verify paths, and
  `delete_conversation`. Never edit an applied migration.

## Allowed outputs

- One forward migration for `app.web_research_operations`,
  `app.web_sources`, `app.web_citations`, RLS, grants, and RPCs
- `scripts/ci/check_migrations.py` allowlist and generated types
- Core repository, answer models, web citation helpers, deterministic
  checks, backend `CitationResponse` additive fields, SSE preview IDs
- Data dictionary, FastAPI security/OpenAPI notes, packet evidence
- Tests: `tests/unit/test_web_citations.py`,
  `tests/contract/test_web_citation_persist.py`, additive ACL/deletion/
  OpenAPI cases

## Forbidden outputs

- ALTER/DROP of `app.citations` ACL recheck or previous list RPC
- Returning HTML/body/excerpt/snippet over HTTP or SSE
- Direct table DML grants to `app_api`, `anon`, `authenticated`, or PUBLIC
- Merging web rows into `app.citations`
- Service-role/operator DSN in API
- Frontend files, Exa network calls, or optional-tool catalog edits

## Ordered actions

1. Inspect the latest migration timestamp. Choose a new sortable filename.
2. Create deny-by-default tables with cascade from `app.runs`:
   operations (unique operation_key per run, request hash, kind
   search|contents|fetch, status planned|sent|succeeded|failed|ambiguous,
   attempts 0–2), sources (index 0–5, unique URL per run, excerpt 1–8000,
   SHA-256 hash), citations (index 0–11, same-run source FK, span ≤1000).
3. Force RLS. Revoke table access. Grant only SECURITY DEFINER RPCs with
   `search_path = pg_catalog, app` and live caller validation.
4. Add begin/mark-sent/complete/fail operation RPCs. Same key and hash
   replays; different hash conflicts; sent-without-terminal is ambiguous
   and must not auto-repeat.
5. Add insert source/citation RPCs with ownership, caps, URL policy, hash,
   and exact span containment.
6. Add the next `list_run_citations` version. Keep the previous function.
   Union company and web rows. Company branch copies v2 ACL recheck
   verbatim. Web branch returns URL/title/hash metadata, never excerpt.
7. Extend `AnswerPayload` with `web_citations` and `AtomicLink` with
   `web_source_ids`. Persist only after verification.
8. Extend conversation deletion and lingering-id search.
9. Regenerate `database.ts` UTF-8 without PowerShell `>`.

## Acceptance checks

- Owned insert/list succeeds; foreign run is not found.
- Duplicate operation key with same hash replays; different hash conflicts.
- Seventh source, thirteenth citation, cross-run source, bad URL, bad hash,
  oversized excerpt, and non-contained span fail closed.
- Merged API returns `source_kind` and no evidence body.
- Company ACL revocation still strips locators exactly as before.
- Deletion purges all three new tables.

## Negative tests

- Direct table INSERT as `app_api` fails.
- Span not in excerpt is rejected at RPC and Python.
- Listing never returns excerpt, span, query, or HTML keys.

## Stop routes

- Stop if v2 company ACL output would change.
- Stop if the local fixture cannot execute real RLS/RPC tests.
- Stop if operation crash/replay cannot be tested at the database boundary.

## Required evidence

- Migration/RPC names, RLS command exits, body-omitted response examples,
  deletion proof, and types handed to P06-41.
