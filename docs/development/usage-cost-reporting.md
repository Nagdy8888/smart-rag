# Usage cost reporting correction

## Problem and preserved data

The October 22 dashboard displayed USD 88.836001 from the immutable usage ledger.
This total mixed priced usage with timeout and unknown-model safety allowances.
The pricing registry lacked GPT-6 Luna, causing successful calls to fall back to
per-operation budget caps. Calling the entire total spending was misleading.

The correction preserves ledger amounts, row counts, token totals, reservations,
and approved limits. Historical totals remain available as original
budget-accounted amounts, not provider charges. No model calls or provider-billing
API requests were made to produce these projections.

## Pricing and provenance

GPT-6 Luna Standard pricing was verified on 2026-10-26 against the
[official model page](https://developers.openai.com/api/docs/models/gpt-6-luna):
USD 0.10 input, 0.01 cached input, and 0.50 output per million tokens. Above
272,000 input tokens the full request uses 2x input/cache rates and 1.5x output.
Regional/Fast premiums and cache-write charges are not inferred. Unknown cache
usage receives no discount; all reconstructed figures explicitly assume Standard
uncached processing. Historical prices are a reconstruction, not invoice evidence.

New counted calls append immutable reporting provenance atomically with ledger
recording: supplied cost estimate, Standard token estimate, or safety allowance.
The sidecar has forced RLS, no direct runtime grants, creator-authorized mutation,
and append-only protection. Provider timeouts never become priced token usage.
Missing token counters remain unresolved. Duplicate provenance writes are
idempotent only when identical.

Legacy rows have no reliable provenance. The versioned reporting projection
reconstructs estimates for known models from usable stored counters. Counters
matching configured caps, timeouts, missing positive-cost token counts, and
unknown models remain unresolved; they are not repriced as measured usage.
Original rows are never backfilled or overwritten.

## API and display

Overview summary/daily buckets and caller/company usage add `cost_reporting`:
estimated cost (nullable), unresolved allowance amount/count, estimated-operation
count, historical reconstruction count, original budget-accounted total, and
pricing assumptions. Existing `cost_usd` contracts remain compatible.

Overview and Usage show estimates and incomplete coverage prominently. The cost
chart excludes unresolved allowances; unknown daily estimates remain gaps, not
zero-dollar claims. Daily tables include unresolved amounts/counts. Run details
label their existing totals as budget accounting, including safety allowances.

For the local October 22 snapshot, the usable subset reconstructs to USD
1.20688733, displayed as about USD 1.21. There are 104 unresolved operations with
USD 38.45 of original allowance amounts. This is a partial estimate, not the full
daily bill. The remaining difference from the original total reflects corrected
pricing of known token counts. Coverage may change when additional trustworthy
billing/provenance evidence becomes available; automatic ledger repricing is not
part of this change.

## Verification and delivery boundary

Tests cover Luna rates/cache/long context, unknown pricing, immutable/idempotent
provenance, caller and company authorization, historical reconstruction,
cap/timeout exclusion, preserved budget accounting, and private response fields.
The authenticated local browser flow covers Overview and Usage on desktop/mobile,
period selection, daily tables, keyboard charts, and visible uncertainty.

The migration was tested first in the isolated local fixture, then applied to the
local application database with a schema snapshot. Ledger counts/amounts/token
totals were checked unchanged. The local API was restarted with no active query;
the database remained running. Hosted migration/deployment was not performed.

Final local checks passed: 2,260 backend unit tests (four existing skips), 774
frontend tests, 15 selected database contracts, authenticated Overview/Usage
Playwright coverage, production build, Pyright, Ruff/format, TypeScript, OpenAPI,
migration/action inventories, and markdown lint. Frontend lint retains three
existing image warnings with no errors. The local API and database are healthy.

## Provider usage measurements follow-up (2026-10-26)

Provider Responses counters are now captured before status/JSON/semantic
validation, inside an attempt-local collector shared through copied async/thread
contexts. An incomplete response or invalid answer can therefore retain its
observed input/output usage instead of being replaced by timeout caps. Missing
or invalid counters remain unmeasured. Reasoning output is already included in
provider output tokens and is not added again.

The additive `20261026120000` migration records immutable token measurements,
cached input, cache-write lifetimes, and returned processing tier with owner-only
mutation and no direct runtime table grants. Standard, Flex/Batch, and Fast Luna
rates include known cache-read/write categories and long-context multipliers.
Unknown tiers or incomplete cache-write pricing details remain unresolved.
Other supported models now honor their cached-input rates. Costs are never
clipped to the reservation cap and presented as measured charges.

Usage cards and run summaries use measured-token projections rather than summing
synthetic reservation counters. Historical records without measurement provenance
remain excluded from measured token totals; their existing cost reconstructions
stay explicitly labelled. Run/chat/account costs use the reporting projection,
excluding unresolved allowances. Parent SSE traces use the per-operation cost
projection when supplied; an explicitly unresolved cost cannot silently become a
default-model charge. Small run costs retain eight decimal places.

The local database forward migration was applied after an isolated fixture test
and a schema snapshot. Ledger row counts, USD totals, and original input/output
totals were byte-identical before and after application. No active queries were
interrupted. The local API was restarted. No hosted migration or deployment was
performed, and no paid model calls or provider billing requests were made.

Verification includes provider-counter/cache/error-path regression tests, strict
Python/TypeScript checks, frontend production build, nine database reporting and
privacy contracts, and an authenticated local desktop/mobile Usage journey.
Private evidence is under `.private-eval/provider-usage-20261026/`.

Official API references checked during implementation:
[GPT-6 Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna),
[prompt-cache token categories](https://developers.openai.com/api/docs/guides/prompt-caching),
[GPT-4.1 Mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini), and
[GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

Provider invoices remain the source for verified billed dollars. The application
now preserves the evidence needed for token-rate calculations but does not claim
that unavailable historical counters or provider billing data were recovered.

Final follow-up checks: 2,275 Python unit tests passed (four existing skips),
774 frontend tests passed, nine database contracts passed, strict types and
production build passed, OpenAPI/migration checks passed, and the authenticated
desktop/mobile browser test passed. Frontend lint has three existing image
warnings and no errors. These checks do not establish hosted deployment or a
verified provider invoice.

## Checkpoint-backed app reporting (2026-10-26)

The user requested that imported checkpoint tokens and costs appear in the app.
`app.checkpoint_usage_runs` now contains one content-free cumulative snapshot per
query run. Recovery reads root query snapshots and decodes only primitive runtime
identities. It chooses the latest nonzero counters per run rather than summing
repeated saves. Source checkpoints and `llm_usage` remain unchanged.

The local recovery command defaults to a read-only preview:

```powershell
uv run python scripts/ops/recover_checkpoint_usage.py
uv run python scripts/ops/recover_checkpoint_usage.py --write
```

The operator tool is restricted to the fixed local Docker database or explicitly
named isolated local fixtures. Repeated recovery is idempotent by run ID.

Recorded token totals use provider measurements when a run has them; otherwise
its recovered checkpoint total is added once. Cost totals use the ledger estimate
for any run already represented there, adding only recovered costs from runs
absent from the ledger. Missing stored costs remain unknown. Costs at or above
the smallest operation allowance (currently USD 0.02) remain unresolved because
per-operation provenance is unavailable; the original stored value is retained.
This conservative screen is not a claim that every excluded amount was a timeout.
No single-model rate is guessed for a mixed-model run.

Caller usage includes only checkpoint rows with that original caller UUID.
Owner/admin company usage includes anonymous workspace-wide aggregates, including
hosted users absent from local Auth. Hosted identities are never reassigned to a
local user. Forced RLS and revoked table grants protect the recovery projection;
only validated caller/company aggregate RPCs are exposed to the API.

Usage now displays recorded input/output totals, combined cost, recovered run
counts, original stored estimates, costs added after ledger deduplication, date
coverage, and unresolved coverage. Overview uses the same deduplication for its
period cost and daily chart. Existing budget-accounted fields remain separate.

At the verified local snapshot, 2,291 recovered runs contain 25,845,103 input and
1,261,013 output tokens. Their usable stored estimates total USD 4.55844231.
After excluding 611 ledger-overlapping runs from added costs, the additional
checkpoint estimate is USD 3.09179156. Together with the ledger estimate of USD
1.40747214, the app displays USD 4.49926370 (USD 4.50). Eighty-five recovered runs
have unresolved costs. Coverage begins October 7; no August history is implied.

The additive local migrations and recovery preserve checkpoint/ledger counts and
ledger token/cost totals. Verification: 2,284 Python unit tests (four existing
skips), 782 frontend tests, eleven selected database contracts, strict types, build,
OpenAPI and migration checks, and authenticated desktop/mobile Usage/Overview
browser checks. Frontend lint retains three existing image warnings. Private
schema snapshots, preservation checks, recovery counts, totals, and screenshots
are in `.private-eval/checkpoint-usage-reporting-20261026/`.

This displays stored history and estimated cost; it does not manufacture provider
measurements or invoice verification. No hosted deployment or paid model call was
performed for this change.
