# Testing, evaluations, and observability review

See [scope and evidence conventions](README.md). Verdict: **extensive test infrastructure, but the current checkout has material red gates and incomplete live proof**.

## QA-01 — P1: required deterministic gates currently fail

**Evidence: reproduced.** The normal fast command stops at formatting, so additional checks were run independently to reveal the full picture.

Python unit suite: **1,906 passed, 5 failed, 4 skipped**. Failures:

1. `test_langsmith_tracing.py::test_production_openai_calls_use_traced_helpers` finds a direct `OpenAI` constructor in `gateways/openai_figure.py:66` outside the approved traced helper pattern.
2. Three `test_retrieve_token_accounting.py` cases fail with `answer_stage_reserve_exhausted` before reaching the mocked send. Their three-call starting budget no longer fits the three-call answer-stage reserve plus another retrieval call.
3. `test_routing_plan_snapshots.py::test_representative_plans_match_pre_split_snapshots` differs on `media_scoped_refusal`.

Frontend full run: **695 passed, 2 failed**. Stable architecture-budget failure plus a timing-sensitive citation-image error-state assertion. Focused repeat: **17 passed, 1 failed**, with only the architecture budget still red.

Other results:

- Pyright: **107 errors**, including organizer payload narrowing, PDF renderer/test types, and a native-content Literal return mismatch.
- Ruff lint: one import-order failure in `apps/backend/src/smart_rag_api/main.py:379`.
- Ruff formatting: 16 files need formatting.
- Frontend typecheck, ESLint, and production build: passed.
- Three selected unauthenticated Chromium checks: passed.

**Impact:** a new contributor or PR pipeline cannot obtain a clean baseline from this checkout. Some failures indicate functional boundary drift; others indicate tests/snapshots out of sync with contracts. Neither category should be dismissed without diagnosis.

**Recommendation:** fix actual provider-boundary violations first, decide the intended route/reserve contracts, then update tests only where the new behavior is justified. Do not bless a new snapshot simply because the old one is red. Repair typing at narrow vendor boundaries rather than globally reducing strictness.

**Acceptance:** the current repository commands pass on the reviewed commit after fixes, with no unexplained skips or broad ignores. This review does not assert anything about current remote GitHub job status; GitHub was not queried.

## QA-02 — P1 release verification gap: live security and authenticated journeys can be skipped

**Evidence: confirmed harness behavior and actual skipped checks.** The selected contracts produced **42 passes and 11 skips**. Database-dependent SSE scenarios in the selection did not provide live proof. `apps/frontend/tests/e2e/live-auth.ts` calls `test.skip` when live credentials or the local API are absent.

**Impact:** green developer/CI commands can coexist with missing RLS, real session, query, citation, graph, and reconnect proof. Optional local integration is reasonable; relying on it as a mandatory release gate is not.

**Recommendation:** split deterministic mock/static tests from an explicitly mandatory authenticated integration job against an isolated test target. Required release journeys must fail as “environment unavailable” rather than silently skip. Archive executed/total/skip counts by category.

**Acceptance:** a release attempt without its required test account/database cannot pass; the report distinguishes deterministic contract assertions from actual database/RLS assertions.

## Evaluation evidence and how to interpret it

The repository has extensive evaluation tools, stage exports, frozen profiles, private datasets, scoring helpers, and latency reports. This is a valuable foundation. However, no fresh paid-model evaluation was run during this review.

Aggregate context inspected from existing local private summaries:

- `mix-hard-24-summary.json`: 16/24 strict and grounded-fact passes; zero reported deadline failures and empty retrieval in that saved summary.
- `mix-hard-24-fresh8-summary.json`: 7/8 strict and grounded-fact passes.
- Other nearby summaries are repair subsets, including one-question reruns.

These are existing snapshots with potentially different code/model/corpus states. **They are not the current checkout's measured quality, must not be combined, and do not replace a full regression.** The README's older 37/100 strict-substring baseline is likewise explicitly historical.

For a release, freeze commit/image, corpus/parser version, model/prompt/profile versions, dataset checksum, auth scope, and scorer version. Report strict correctness, grounded-fact correctness, correct document/page citations, refusals, latency percentiles, cost, infrastructure errors, and stage-specific loss. Retry a crashed question before treating it as a content miss.

## Observability strengths and gaps

There are structured logs, correlation IDs, LangSmith helpers, redaction boundaries, provider usage rows, ingest progress, stage timings, run events, and external-trace deletion mechanisms. Readiness distinguishes dependencies and query runtime warmup instead of equating “HTTP responds” with “queries work.”

The direct vision client already violates an observability test. Organizer usage is also outside the durable attempt wrapper despite adding state token totals. Both paths must enter the same authoritative accounting and trace model as answer/retrieval calls.

Unexpected verifier exceptions are intentionally swallowed into partial draft release. That preserves availability but can hide a trust-boundary failure. Record stage/outcome/error type without raw prompt/source content, and alert on changes in verifier-skipped, citation-leaf-unresolved, source-unavailable, budget-exhausted, repeated vision work, and run orphan/reaper rates.

No live GlitchTip/Sentry issues, LangSmith traces, dashboards, alerts, deletion confirmations, or production p95 values were inspected. A configured DSN or tracing flag is not read access or proof of useful telemetry.

## Test quality improvements

- Add semantic-negative organizer cases: negation, relation reversal, temporal changes, Arabic, and exact-block overflow.
- Change the verifier exception tests so they establish safe refusal or release only of already-proven claims, rather than requiring unchecked draft preservation.
- Test post-organization live/replayed/historical citation mappings, not just whether the answer contains a title.
- Add two-process executor-claim tests; a run-row event lock test covers a different property.
- Add provider-denied and budget-denied figure-description tests, plus crash/replay accounting.
- Synchronize asynchronous UI error assertions with their actual terminal state.
- Replace the misleading “200% zoom” test name or add a genuine zoom/text-resize test.

## Practical verification sequence

Run formatting/lint and types first, then unit/contract suites, frontend tests/build, authenticated browser journeys, isolated hosted database/security tests, and finally the fixed full live-model regression. Archive summaries and skip reasons. Broaden tests only when a new change or failure warrants it; avoid repeatedly running paid target subsets without a stable full-set comparison.
