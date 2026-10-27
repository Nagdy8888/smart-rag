# Diagnostic continuation and real Web citations — 2026-10-26

This delivery is **incomplete as an evaluation**. It does not qualify the agent for release.

## What was exercised

The existing account-owned company conversation reached **23 of 50 actual questions**. Question 22 correctly compared reflex agents with multistep reasoning. Question 23 ended with `verification_unavailable:citation_persist_failed`; the checkpoint identifies citation persistence as the failing stage, but does not retain the underlying database exception. Attempts at question 24 rejected by admission are not counted as memory or answer-quality failures.

The first Web conversation ran four valid English questions, then a cancelled request whose Arabic fixture text had been damaged in terminal transport. Those first four results were clipped source openings despite passing weak nonempty/citation heuristics. They are not successful semantic answers. The original private driver datasets and hashes remain preserved. The corrected UTF-8 development question pack is `tests/fixtures/web-citations-smoke15-v2.json`; no Arabic result from the malformed attempt is claimed.

After repair, the new Web conversation `b7e655ca-315d-4a53-aa72-589adbf77095` ran two requests: question 1 failed at Web search with `web_search_timeout`, while question 2 produced a direct supported answer with a contained RFC citation. The 15-question Web pack is **not complete**. No new paid requests are running.

Normal authenticated API/SSE calls were used for the batch questions under the same account as the browser. The actual app was then used to open the saved answer, Sources list, supporting passage, and original-page link. The personal browser was left displaying the real citation reader. Old answers were preserved rather than rewritten.

## Repairs shipped locally

- `provider_usage.py` accepts nested cache-write counters retained as dictionaries by the installed SDK. A regression uses the real installed SDK response model. Missing retention counters still remain unknown; this fix does not infer prices when fields are actually absent.
- Web synthesis now calls the existing durable consume/usage boundary exactly once and decrements the admitted model-call counter. Reservation state survives failure. Budget rejection never sends; known pre-send input/configuration failures do not fabricate usage. No new retries or retrieval loops were added.
- Persisted Web excerpts are fitted within the configured model input limit before building the prompt copy. Canonical source rows and IDs are preserved. Live synthesis failure no longer silently releases the extractive mock through `web_scope_node`.
- The Web citation-detail RPC now returns the saved, contained citation span instead of the first 1,000 characters of the page. Creator ownership, URL checks, and company ACL checks remain. Forward migration `20261026150000_web_citation_exact_span_v1.sql` is applied locally.
- The real browser confirmed the exact supporting sentence for the Retry-After answer. The separate safe website link opens the original page. This is live evidence, not the earlier reader fixture screenshot.

## Budget and remaining blockers

The original $2 diagnostic allowance plus the approved additional $2 establishes a $4 total accounting cap. The immutable ledger increased from $96.545895 to **$100.076814**, a diagnostic accounting delta of **$3.530919**. The conservative guard stopped further work before using the remaining allowance. This is **not provider spend or an invoice**. Successful calls with missing cache-retention prices still use safety allowances. Earlier Web synthesis attempts did not have the new counted wrapper, and redacted Exa logs omitted returned cost fields, so a verified total external-provider cost cannot be established.

All temporary company/caller limit changes were restored to **$100**, verified independently in the database and recorded in the budget lease/audit events. The resulting original monthly budget is now admission-blocked by accounting usage; no permanent increase or ledger rewrite was made. The database and local API remain healthy.

Remaining material issues:

1. Obtain compatible provider cache-retention usage metadata; do not repeatedly burn test allowances on unpriced successful calls or guess a bill.
2. Diagnose the underlying company citation-persistence exception with content-free error codes. Existing checkpoints only name the failing boundary.
3. Persist an employee-visible failure state in restored history: the failed first Web question currently reappears without an explanatory assistant/error row.
4. Restore/show source mode clearly for externally started/history Web conversations; the browser currently shows Auto and company scope while reading a Web result.
5. Correct user-facing zero-based citation numbering without changing stored citation identity or references.
6. Complete company m24–m50, the full 15 Web questions, and independent semantic review once budget accounting permits. Heuristic passes are not correctness scores.

## Validation and evidence

- Complete backend unit suite passed with existing skips retained after the final counted-Web changes.
- Strict Pyright and Ruff lint/format passed on changed Python files.
- Twenty relevant database contracts passed in a separate schema-only fixture: Web citation detail, ownership, company citation ACL recheck, and conversation transcript behavior.
- Four broader Web error-path contract failures were reproduced with the previous RPC definition: operation replay/conflict, caps/foreign-run, thirteenth/invalid inputs, and direct-insert denial. Their test transaction remains aborted after expected SQL errors. They remain recorded failures, not skipped or weakened checks.
- Generated local database types using the cached Supabase postgres-meta generator after the CLI download stalled. The citation-detail generated signature is unchanged; no generated interface update is required.
- Earlier frontend validation remains 787 tests, production build, typecheck, lint with three existing image warnings, and two browser journeys. No frontend behavior was changed during this continuation.
- Live screenshot: `.private-eval/user-app-review-20261026/web-reader-real-citation.png`.
- Per-turn source fingerprints, results, checkpoint snapshots, node writes and terminal logs remain in `.private-eval/continuation-company-20261026T201208Z`, `.private-eval/continuation-web-20261026T201926Z`, and `.private-eval/continuation-web-20261026T202920Z`.
- Lease files: `.private-eval/continuation-budget-lease.json`, `.private-eval/continuation-v2-budget-lease.json`, `.private-eval/continuation-v3-budget-lease.json`, each restored.

The reliability feature flag remains disabled. No holdout, corpus document, checkpoint history, production deployment, or model family was changed. Missing dates, governance/authority rollout, hosted readiness and full live quality targets remain unqualified.
