---
phase: 6
packet: 57
status: complete
title: "Run full deterministic/live/browser gates and existing P06-17 development/qualification without opening holdout."
requirement_ids: [P06-57]
---

# Packet 57 — Run full deterministic/live/browser gates and existing P06-17 development/qualification without opening holdout.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`verify-release-gates`](../../../../../.cursor/skills/verify-release-gates/SKILL.md),
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).

This packet records gates. It does not add a special-case fixture to
hide a failed owning packet.

## Preconditions

- Packets P06-50 through P06-56 are recorded with green commits.
- Branch is `fix/rag-reliability-and-citations`.
- Private label/ID paths remain gitignored. `git status --short` shows
  none of them before qualification.

## Allowed outputs

- Phase 6 evidence files for P06-49 through P06-57
- P06-17 development/qualification evidence under the existing P06-17
  path
- Docs index last-reviewed dates
- Wrapper checkbox for this packet only after every scenario passes
- Repair commits only by returning to the owning packet listed below

## Forbidden outputs

- Opening P06-18 or setting `holdout_opened=true`.
- Weakening citation/faithfulness/routing thresholds.
- Marking P06-17, P06-18, or Phase 6 complete unless P06-17’s own
  packet checks all pass. This overlay does not check P06-17.
- Adding a live-only branch or special-case fixture to pass a failed
  scenario.
- Pasting passwords, DSNs, unrestricted PDF text, or raw excerpts.
- `--no-verify`, force-push, or `gh pr merge --admin`.

## Ordered actions

1. Run repository gates from a clean tree: fast tier, Compose config,
   OpenAPI, migrations, plan integrity, and `pre-commit run --all-files`.
2. Start the repaired local stack. Exercise live/browser scenarios:
   MCP acronym, four-approach comparison, unsupported company refusal,
   Company/Web reload citations and feedback, two sequential Web runs,
   cancellation, delete Cancel/Confirm, idle SSE replay after 60
   seconds, and one synthetic PDF to Hybrid Ready through the host
   worker.
3. Record one sanitized acceptance block per scenario. Never copy
   unrestricted PDF text.
4. If a scenario fails, stop and reopen the owning packet with a new
   fix commit: P06-50 fit/reserve, P06-51 unsupported prose, P06-52
   terminals, P06-53 transcript/ACL, P06-54 reload/delete UI, P06-55
   Postgres/readiness, P06-56 worker/Exa.
5. After every scenario passes, run existing P06-17 exactly as
   written: development live split, freeze hashes only after
   development passes, then qualification once. Require citation
   correctness ≥98%, completeness ≥90%, faithfulness ≥90%, routing
   ≥90%, zero ACL leaks, no BM25/rerank fallback for applicable
   cases, and `holdout_opened=false`.
6. Invalid/timeout judge output is `unscored`, never pass. Do not
   rerun a failed frozen qualification candidate under the same
   prompt/config hash.

## Acceptance checks

- Fast, Compose, OpenAPI, migrations, integrity, and pre-commit pass.
- Acronym answer is `Model Context Protocol` with a citation whose
  authorized detail contains that phrase. Never `Method Call Protocol`.
- Four-approach comparison has non-zero completion tokens, covers
  democratic/manager/hierarchical/actor-critic, stays within the
  fitted bound, and does not emit `gateway_failed`/`empty_answer`.
- Unsupported company question is a graceful refusal with no
  Web/general fallback.
- Company and Web citations plus feedback survive reload and
  conversation switching.
- Two sequential Web runs succeed without event-loop cleanup errors.
- Cancellation remains terminal/idempotent.
- Delete Cancel preserves data; Confirm deletes once.
- After more than 60 seconds idle, SSE replay/query works without 500.
- Synthetic PDF reaches Hybrid Ready; parser networking remains
  disabled.
- P06-17 qualification metrics meet the thresholds above.
- P06-18 remains unopened.

## Negative tests

- Opening holdout fails the packet.
- Weakening a threshold to pass qualification fails.
- Repairing a failed live case with a one-off fixture fails.

## Stop routes

- Stop on external authentication, authorization, quota, or provider
  denial.
- Stop if P06-17 development fails; repair/version the candidate
  instead of opening holdout.
- Do not merge until this evidence exists.

## Required evidence

- Commands, exit codes, live scenario blocks, P06-17 aggregates, and
  explicit `holdout_opened=false`.
- Commands:

  ```powershell
  uv run python scripts/check.py --tier fast
  docker compose --env-file .env.example config --quiet
  uv run python scripts/ci/check_openapi.py
  uv run python scripts/ci/check_migrations.py
  uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py
  pre-commit run --all-files
  uv run python scripts/eval_pdf_agent.py --live --split development
  ```

- Commit `test(rag): prove live reliability and citation gates` only
  when every scenario passes. P06-17 evidence/check stays on the
  existing P06-17 packet and is not marked complete by this overlay.
