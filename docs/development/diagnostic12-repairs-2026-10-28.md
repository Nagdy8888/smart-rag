# Repairs for the 12 flagged diagnostic cases — 2026-10-28

This is a repair record for the original 65-question development campaign. It does **not** replace the original results, claim 65 correct answers, or report a new live pass. No additional paid questions were sent and no budget cap was raised.

## New root causes confirmed

### Citation persistence and cancellation deadlock

The retained PostgreSQL log at 2026-10-26 20:13:30 UTC includes the recorded company question 23 run ID. It shows `insert_run_citation_v2` waiting on the run while another transaction executes `cancel_query_run`. Provider accounting held the reservation first; cancellation updated the run before true-up tried to lock the reservation. The resulting opposite lock order caused the deadlock.

Forward migration `20261028100000_cancel_reservation_lock_order_v1.sql` authenticates ownership, locks the reservation, then locks/reloads the run before cancellation. The status, authorization, settlement and replay rules remain. It does not change grants, amounts, deadlines or call ceilings.

A real two-connection regression fails under the previous definition with a run-row lock timeout and passes under the repair. The test holds the reservation as an admitted model operation would, starts cancellation, and proves the verifier can still acquire its run. The migration passed isolated local database checks before local application; ledger rows/amounts and the original $100 cap remained unchanged. Generated types confirm the cancellation interface is unchanged.

### Incorrect source binding

Company question 12's saved draft cited an unrelated memory passage. Its actual explanation contained a distinctive five-word phrase in an authorized fitted persistence passage. The existing repair required high overall lexical coverage and missed the paraphrase.

Binding now has a bounded fallback requiring a long verbatim phrase, at least three content words, exactly one fitted prose holder, and materially stronger coverage than the current citation. It preserves the claim and visible text. Citations remain exact canonical slices, and the ordinary verifier can still reject the claim. Ambiguous and absent sources cannot be chosen.

Offline replay of the recorded authorized evidence retargets the citation correctly without changing answer text. A separate creator-authorized SQL replay inserted the rebound citation successfully inside a rollback-only transaction, with no skipped spans or historical changes. Tests also prove an unsupported inference still fails the verifier.

### Answer time allowance

Company questions 21 and 46 each paid for two attempts cut off at approximately 15 seconds. Counted answer generation now shares that existing 30-second combined allowance, allowing one slow successful request to finish. It retains route deadlines, five seconds of verification headroom, two-attempt maximum, durable reservation accounting and model-call ceilings. Exhausting the combined allowance prevents another send. Isolated gateway calls retain their original cap.

Fake-clock tests cover a 16-second success, exhausted time, short route deadlines, budget denial, counted lost responses and retry ceilings. They do not prove an upstream outage is repaired.

### Optional Web search discarded successful discovery

Web question 1 recorded a successful first search followed by a failed optional follow-up. The executor aborted before reading any candidates. Optional follow-up searches now reserve time shares for the remaining searches, reading and synthesis. A timeout/transport failure can retain already discovered candidates and proceed through the normal authorized contents/persist/synthesis path, with an explicit partial result. No snippets become evidence, and there are no added calls or retries. First-search, authorization, privacy and ambiguous-operation failures remain fail-closed.

The Exa transport also enforces the remaining **total** operation time, rather than only separate connect/read phase limits. An offline hanging-transport test proves cancellation and no retry after that deadline.

## Coverage of the original 12 cases

1. **Company 12:** unique literal source-binding repair; recorded draft/evidence replay and verifier-rejection regression.
2. **Company 19:** previously repaired numeric-only salvage mismatch; existing verifier/figure regressions retained.
3. **Company 21:** shared bounded answer allowance; fake-clock and durable-attempt accounting tests.
4. **Company 23:** cancellation/citation deadlock root cause now confirmed and repaired; two-connection SQL regression.
5. **Company 31:** previous NUL-expression term-fallback repair; term recall, permissions and NUL-input contracts retained.
6. **Company 46:** same bounded answer-time repair as question 21; no deadline or call-ceiling increase.
7. **Web 1:** preserve first-search discovery when optional follow-up fails; partial-result and total-time cancellation regressions.
8. **Web 7:** previous public-comparison scope repair; explicit Web-envelope and private-reference regressions retained.
9. **Web 15:** same public-comparison repair; no accidental Hybrid branch in an admitted Web run.
10. **Web 4:** previous contiguous relevant-excerpt fitting; recorded RFC replay retains the cache rule without mutating sources.
11. **Web 5:** previous separation of search rewrite from original answer language; offline synthesis-closure regression.
12. **Company 38:** previous deterministic image-availability guard; only the claim's own authorized figure metadata can invalidate the disclaimer.

The restored-history failure notice and content-free diagnostic logging from October 27 remain. Earlier outputs, including wrong answers and timeouts, have not been rewritten.

## Verification and limits

- Full Python unit tier: 2,315 passed, four existing skips; eval registry passed. Later binding-bound changes use the focused regressions.
- Explicit isolated database suite: 38 passed, including lock order, creator privacy, citation ACLs, admission authorization, budget consume and settlement.
- Full contract tier: 300 passed, 290 environment-dependent skips. These skips are not live integration approval; the explicit 38-contract database run is separate.
- Ruff format/lint, strict Pyright and migration policy passed. The final focused regression/docstring/migration run passed 73 tests.
- No frontend changes were made in this repair pass; October 27 frontend/build and desktop/mobile browser evidence remains separately documented.
- Local application only; no hosted migration, deployment, commit or push performed in this pass.

External model/search availability can still fail. These repairs address reproducible application causes and bounded degradation; they do not establish that the original 12 questions now pass live. A paid post-fix rerun requires separate scope/budget authorization under the user's one-round restriction.

Private evidence: `.private-eval/m23-deadlock-private.log`, `cancel-lock-baseline.txt`, `cancel-lock-after.txt`, `remaining12-contracts.txt`, `m12-authorized-replay.json`, and `m12-binding-repair-proof.json`. They remain local and gitignored.
