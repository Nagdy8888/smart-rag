---
phase: 6
packet: 48
status: pending
title: "Prove PDF citation accuracy across regression, authorization, history, and UI gates."
requirement_ids: [P06-48]
---

# Packet 48 — Prove PDF citation accuracy across regression, authorization, history, and UI gates.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md),
[`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md).

## Preconditions

- P06-45 through P06-47 code exists on `fix/pdf-paragraph-citations`.
- Requirement IDs: `CIT-PAGE-001` through `CIT-BOUNDS-012`.
- Do not open the sealed holdout.

## Allowed outputs

- Deterministic PDF regression fixture and owning tests
- `packages/core/src/smart_rag_core/evaluation/private_pdf/agent_scores.py`
  plus owning unit tests
- Docs: `ANSWER_VERIFICATION.md`, `CHUNKING_CONTRACT.md`,
  `FASTAPI_SECURITY.md`, `SSE.md`, `API_UI_MAPPING.md`,
  `THIN_DEVELOPER_UI.md`, Phase 6 evidence, prompt changelog, docs index
- Playwright citation journey updates
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- Claiming the global ≥98% citation target without a measured approved
  evaluation run.
- Opening holdout.
- Skipping required database contract tests and treating skips as proof.
- Force-push, squash merge, or pushing before full gates pass.

## Ordered actions

1. Add a deterministic fixture: title `AI Agents`; target evidence on
   `page_index=24`; `page_label="12"` on that page; parent spanning
   multiple pages; one unique exact span; one duplicated span for
   ambiguity.
2. Assert chip text `AI Agents · PDF page 25`. Forbid `p. 12` and
   `PDF page 12`. Drawer excerpt must match the persisted span after
   transport decoding.
3. Score evaluation with resolved leaf IDs, paragraph completeness, and
   `pdf_page_number` versus gold `page_number`, never `page_label`.
   Keep ACL/forbidden-source hard failures.
4. Update documentation for viewer page versus printed label, schema,
   leaf-resolution failures, excerpt disclosure, history, legacy,
   migration/backfill, no source text in SSE, and measured versus
   unverified evaluation.
5. Run narrow failures first, then format, lint, types, unit, contract,
   docs, frontend, and the Playwright citation journey.
6. After a clean worktree and passing gates, fetch `origin/main`, merge
   it with a merge commit if it advanced, rerun gates, push
   `fix/pdf-paragraph-citations` once without force, open one PR, and
   merge-commit to `main` only after required checks pass.

## Acceptance checks

- The 25-versus-12 regression shows `PDF page 25`.
- Every test answer paragraph maps to its exact authorized excerpt.
- Wrong, missing, stale, ambiguous, or unsupported mappings fail closed.
- ACL downgrade/deletion/current-version tests leak no title, page,
  chunk, or excerpt.
- Current and historical chat render the same mapping.
- No General/Web behavior regresses.
- Evidence distinguishes fixture proof from measured evaluation.
- Per-packet commits are preserved. Feature branch is not deleted.

## Negative tests

- Treating skipped contract tests as proof fails the packet.
- Presenting `page_label` as the PDF viewer page fails the packet.
- Squash/rebase merge that drops packet commits fails the packet.

## Stop routes

- Stop if GitHub authentication, branch protection, required review, or
  merge authorization blocks the operation.
- Stop if merging `origin/main` conflicts with active P06-41 semantics.
- Stop rather than claim 98% citation correctness from locator unit
  tests alone.

## Required evidence

- Exact commands, exit codes, passed/failed/skipped counts, whether a
  non-hosted Postgres fixture was available, whether an approved PDF
  evaluation was run, commit SHAs, PR URL, and merge verification.
