---
phase: 6
packet: 66
status: complete
title: "Deploy the reviewed seven-argument term RPC and prove live term_unavailable is gone."
requirement_ids: [P06-66]
---

# Packet 66 — Deploy the reviewed seven-argument term RPC and prove live term_unavailable is gone.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-hybrid-retrieval`](../../../../../.cursor/skills/implement-hybrid-retrieval/SKILL.md).

Do not load frontend skills.

## Preconditions

- P06-65 is recorded. Branch is `fix/honest-rag-accuracy`.
- Hosted project is `smart-rag` `qsjivtwtmlmtksufqjik`.
- Live 2026-09-21 fact: `pg_proc` exposes only
  `app.retrieve_term_candidates(uuid,text,bigint,text,integer,text)`.
  [`TermRetriever.retrieve`](../../../../../packages/core/src/smart_rag_core/retrieval/terms.py)
  binds seven arguments and maps `psycopg.Error` to `term_unavailable`.
- Local reviewed SQL is
  [`20260917120000_retrieve_term_candidates_extra_terms_v1.sql`](../../../../../supabase/migrations/20260917120000_retrieve_term_candidates_extra_terms_v1.sql).
  Do not rewrite that body unless review finds a defect.
- Last hosted migration names may not match local filenames. Prove
  deploy by `pg_proc` signature plus `pg_get_functiondef`, never by
  `list_migrations` name matching.

## Allowed outputs

- Hosted apply of the existing reviewed extra-terms SQL through the
  protected migration path used by
  [`apply_pdf_overlay_migrations.py`](../../../../../scripts/ops/apply_pdf_overlay_migrations.py)
- Registration of that version in `supabase_migrations.schema_migrations`
  when the path requires it
- Count-only checkpoint proof of Hybrid `BranchResult.fallback_reason`
- Three-question private Ask smoke records under `.private-eval/`
- Updates to
  [`p06-61-term-bm25-candidate-repair-2026-09-17.md`](../../../../../docs/development/phase-06/p06-61-term-bm25-candidate-repair-2026-09-17.md)
  and this packet's evidence file
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- Any change to `terms.py`, `channels.py`, or the reviewed migration
  body
- Creating a duplicate extra-terms SQL file
- Editing applied migrations
- Deleting documents, renaming titles, or reindexing
- Embedding sample-PDF hash, title, questions, gold, pages, or aliases
  in production files
- Starting Packet 67 title-rename work

## Ordered actions

1. Prove the outage first. Using the operator DSN (`SET ROLE postgres`,
   count-only, never text), read Hybrid `BranchResult.fallback_reason`
   from checkpoint state for company runs in the last 7 days. Record
   `term_unavailable` share; expected 100%.
2. Confirm project id `qsjivtwtmlmtksufqjik` and the file hash of the
   reviewed SQL against
   [`check_migrations.py`](../../../../../scripts/ci/check_migrations.py)
   and
   [`packet2-migration-hash.json`](../../../../../docs/deployment/phase-10/packet2-migration-hash.json).
   Apply only that file. Register the version the way
   `apply_pdf_overlay_migrations.py` does.
3. Verify by signature: seven arguments, `prosecdef=false`,
   `search_path=pg_catalog, app, extensions, search`, `EXECUTE` on
   `app_api` only besides the owner, no `PUBLIC` grant. Record
   `md5(pg_get_functiondef(...))`.
4. Smoke A (unscoped; no title change yet): three fresh-conversation
   Ask questions (acronym, named entity, paraphrase) through
   [`run_company_ask.py`](../../../../../scripts/run_company_ask.py)
   with a three-row private gold file. Read checkpoint
   `fallback_reason` per Hybrid branch.
5. Update P06-61 evidence "Hosted application" from unverified to the
   measured result with commit `d1376ad`, prompt versions, and profile
   digests.

## Acceptance checks

- Every Hybrid branch `fallback_reason` is in
  `{none, bm25_unavailable, retrieval_timeout, timeout}`.
- `term_unavailable = 0` on the three-question smoke.
- The BM25 reason, now unmasked, is recorded.
- Seven-argument signature, `SECURITY INVOKER`, fixed `search_path`,
  and `app_api`-only grant are proven.
- P06-61 hosted-application evidence is no longer unverified.
- No sample-PDF literals were added to production files.

## Negative tests

- Calling the seven-argument function before deploy still fails with
  undefined-function.
- An extra-terms deploy that drops ACL/current-version predicates or
  becomes `SECURITY DEFINER` fails.
- A smoke that still records `term_unavailable` fails.

## Stop routes

- Stop if the RPC cannot be applied `app_api`-only.
- Stop if the smoke still shows `term_unavailable`.
- Stop if live Ask cannot run without embedding credentials in git.
- Do not change Python term-binding in this packet.

## Required evidence

Create
[`p06-66-term-rpc-live-2026-09-21.md`](../../../../../docs/development/phase-06/p06-66-term-rpc-live-2026-09-21.md)
and append to
[`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md):

- Pre-deploy `fallback_reason` counts
- Hosted signature, `prosecdef`, grants, and functiondef digest
- Smoke A: three run IDs, fallback reasons, `term_unavailable=0`
- Commands/exits
- Rollback: drop the 7-argument overload and restore the 6-argument
  function; do not delete documents

Commands:

```powershell
uv run python -m pytest tests/unit/test_term_candidates.py -q
uv run python scripts/ci/check_migrations.py
git diff --check
```
