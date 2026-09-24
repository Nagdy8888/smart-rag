# P6 - Phrasing misses: adjudicate, then add aliases (data only)

## Goal

`k06`, `k29`, `k30`, `k33`, `k42` finished `completed` / `verified` with
the gold page in evidence and every product check passing; the strict
scorer failed them only because a canonical phrase was not a substring
of the answer. The scorer (`dual_metric.py`) is NFKC + casefold
substring: a correct paraphrase fails strict but can pass
`grounded_fact_pass` if an approved alias matches.

This packet changes **no product code**. It adds approved aliases to the
private gold file after a human reads each answer. The implementing model
prepares the adjudication sheet; the human decides; the model applies the
decisions.

## Read first

- `docs/evaluation/DUAL_METRIC_SCORING.md` (strict vs alias-aware fact
  coverage; alias approval rule).
- `packages/core/src/smart_rag_core/evaluation/dual_metric.py`
  `normalize_answer_text`, `phrase_is_present`, `score_company_answer`.
- `.private-eval/known-answer-50-v1.json` structure:
  `{id, page, kind, prompt, facts:[{id, canonical:[...], aliases:[...]}]}`.
- `.private-eval/check_gold_phrases.py` (proves a phrase exists on the
  gold page in the database).
- `.private-eval/ka50-answers.json` from the latest full run (answer
  text per question id).

## Steps

1. For each of the five ids, write to
   `.private-eval/adjudication-p6.md` (private, never under `docs/`):
   the prompt, the gold page, each fact's canonical phrases, the stored
   `answer_text`, and the model's proposed alias per missed fact (the
   exact substring of the answer that states the same fact). If the
   answer does not state the fact, write `NO ALIAS - answer is wrong`
   for that fact.
2. Run `uv run python .private-eval/check_gold_phrases.py` for each
   proposed alias to confirm the alias text (or its factual content) is
   supported by the gold page. Record the result next to the proposal.
3. Stop and hand the sheet to the user. Do not edit the gold file until
   the user marks each proposal `APPROVED` or `REJECTED`.
4. Apply approvals: append each approved alias to the fact's `aliases`
   array in `.private-eval/known-answer-50-v1.json`. Do not change
   `canonical`, `page`, `prompt`, or any other question.
5. Re-score offline without a live run: load the gold and the existing
   `ka50-answers.json`, call `score_company_answer` for the five ids,
   and confirm `grounded_fact_pass` flips to true for approved cases.
   Check `scripts/` for an existing offline rescoring entry point
   (`rg "score_company_answer" scripts`); if none exists, run the five
   calls from a throwaway script under `%TEMP%`, not in the repo.
6. Note in the P7 evidence doc how many of the five became
   `fact_covered` and how many stayed `wrong_phrasing` (answer was
   actually wrong).

## Done when

- [ ] Adjudication sheet exists in `.private-eval/` with one row per
      missed fact and a proposed alias or `NO ALIAS`.
- [ ] Every alias added to the gold file has a user `APPROVED` mark on the
      sheet.
- [ ] Offline rescoring shows the approved cases as `fact_covered`.
- [ ] No file under `docs/`, `packages/`, `apps/`, or `scripts/` changed.
- [ ] `git status --short` shows no tracked changes.

## Commit

Nothing to commit. The gold file and the adjudication sheet live in
gitignored `.private-eval/`. Prove it with `git status --short` (empty
apart from untracked noise) and record "P6: no commit, data-only" in the
report. Do not create an empty commit.

## Do not

- Do not loosen `phrase_is_present` or add fuzzy matching to the scorer.
- Do not add aliases the user did not approve.
- Do not copy gold phrases or answer text into any tracked file.
