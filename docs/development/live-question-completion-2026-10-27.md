# Live question completion — 2026-10-27

**Execution complete: 50 company questions and 15 Web questions attempted once. This is not an accuracy pass or release qualification.** Earlier failed attempts and answers were preserved, not resent or rewritten.

Follow-up: [October 28 repair evidence](diagnostic12-repairs-2026-10-28.md) confirms the formerly unexplained citation deadlock and records the remaining code repairs. This October 27 snapshot is retained as historical evidence.

## Scope and accounting

The remaining company questions 24–50 ran in `61608a28-dbbd-4e2d-8579-fabd9955c417`. Web questions 3–15 ran in `b7e655ca-315d-4a53-aa72-589adbf77095`, using `web-citations-smoke15-v2.json`. Exactly 40 additional questions were sent through normal authenticated admission/SSE. No paid post-fix evaluation was run.

Company/caller monthly limits were temporarily $150, with a $45 continuation accounting ceiling and automatic restoration. Both original $100 limits were independently verified afterward. The ledger moved from $100.076814 to $123.029888: **$22.953074 additional accounting**, substantially including safety allowances. This is not verified provider spend or an invoice. No ledger rows or amounts were edited. Normal admission is again blocked by the restored monthly limit.

Final database and API audit:

- Company: 50 user and 50 assistant messages; 37 completed, 12 partial and 1 cancelled run.
- Web: 15 user and 12 assistant messages; 11 completed, 1 partial and 3 failed runs.
- No active runs; local API query-ready. Run states are not correctness scores.

## Confirmed defects and repairs

1. **Term fallback failed on valid text.** The RPC evaluated `chr(0)`, which PostgreSQL rejects. Forward migration `20261027100000_live_diagnostic_contract_repairs_v1.sql` removes that invalid expression. PostgreSQL still rejects NUL input. Normalization, bounds, current-version predicates, RLS and API-only privileges remain. This explains the missing term fallback when company question 31's embedding connection failed.
2. **Origin/progress events were rejected by SQL.** The same migration aligns the event CHECK with the application catalog, including `answer_origin` and `tool_progress`. Foreign callers remain denied, and the one-terminal constraint remains. Missing historical events are not fabricated or backfilled.
3. **Public comparisons entered invalid scope.** Web questions 7 and 15 were treated as company/mixed questions from comparison shape. Standalone explicit public-source comparisons now stay in the admitted Web envelope. Private references, identifiers, document scope, secrets and referential follow-ups retain the disclosure guard. No new route or retry loop was added.
4. **Prompt fitting discarded decisive evidence.** Question 4's saved RFC excerpts contained the 429 cache rule after the retained prefix. Fitting now chooses a contiguous query-relevant window from the immutable excerpt. Offline replay retains the rule in all five recorded sources, with exact containment and unchanged IDs.
5. **Arabic synthesis used an English search rewrite.** Search may use its rewrite; synthesis now receives the original employee request. An offline node test proves this separation. Question 5's English response remains in history as a language failure; question 9 returned Arabic during the live run.
6. **The answer denied an image it attached.** Company question 38 claimed the original image was unavailable while rendering it. A deterministic pre-verification check now removes an availability-denial claim when its own authorized citation has a figure ID. It does not infer availability from unrelated images or semantically rewrite a verified answer.
7. **Failed questions lost their state on reload.** Transcript responses now include recorded run status through the existing creator-authorized run RPC. The frontend shows a failure/cancellation notice beside an unanswered question, without inventing an assistant answer or inferring status for older records.
8. **Diagnostic fields disappeared from JSON logs.** Bounded machine reasons, SQLSTATEs and valid run IDs now survive formatting. Citation-persistence failures emit these fields. Arbitrary extras, source passages and exception messages remain excluded.

## Remaining limitations

- Company question 46 hit an answer-provider timeout. The operational timeout message was correct. No extra retry or deadline increase was introduced.
- The earlier question 23 citation-persistence failure did not reproduce: its saved draft inserted inside a rollback-only transaction. Its original cause remains unknown. Better diagnostics are not proof of a root-cause repair.
- The extracted headings of company table 2-1 remain awkward and need source-layout review. No corpus text was silently rewritten or re-ingested.
- Presence/citation heuristics missed the incomplete Web answer, language mismatch and image contradiction. Those are recorded quality findings, not successful semantic answers.
- The campaign spans implementation versions. It is not a frozen holdout or SME accuracy adjudication. Reliability mode remains disabled; hosted readiness is unqualified.

## Validation

- Full Python unit run: 2,304 passed, 4 existing skips. Later focused Web/routing/figure/logging checks: 34 passed, without providers.
- Standard contract run: 300 passed, 287 skipped. Skips are not live integration approval.
- Explicit isolated local database fixture: 25 contracts passed, covering repaired SQL, term privileges/NUL rejection, creator-only transcripts, citation ACL rechecks and term recall. The initial six SQL regressions failed before the migration and passed afterward.
- Ruff, strict Pyright, migration policy and OpenAPI checks passed. Generated database types confirm the term RPC interface is unchanged.
- Frontend: 789 tests, TypeScript and production build passed; lint retains three existing image warnings.
- Two authenticated read-only browser journeys passed on desktop/mobile: actual failed Web history and the citation-reader fixture. They submitted no questions. The standard browser suite passed 25 tests with 22 credential-dependent skips. An initial startup-lock problem and a missing-public-Auth test configuration were corrected without changing screenshot baselines.
- The migration was applied locally after verifying zero active runs. Ledger counts and amounts remained identical across it. No hosted deployment was performed.

Private evidence remains gitignored: `.private-eval/finish-live-company-20261027T161723Z`, `.private-eval/finish-live-web-20261027T163011Z`, `finish-live-final-audit.json`, `finish-live-budget-lease.json`, `diagnostic-migration-baseline.txt`, `diagnostic-migration-after.txt`, `finish-live-contracts.txt`, `w04-window-replay.json`, `finish-live-browser.txt`, and `finish-live-standard-browser.txt`.
