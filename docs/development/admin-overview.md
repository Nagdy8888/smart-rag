# Admin overview

Implemented locally on 2026-10-26. `/admin` now defaults to Overview; explicit
Team, Tools, Knowledge, Usage, and Evaluation bookmarks retain their behavior.

## Data and privacy

`GET /admin/overview?days=7|30|90` uses the additive `app.admin_overview` RPC.
Both boundaries validate owner/admin access, and the response is private/no-store.
Normal integer query parameters are parsed through an integer enum. The UI caches
by session and period for 60 seconds, refreshes on focus, and offers manual refresh.
It does not poll or invoke a model.

Questions count distinct stored runs with `graph_name = query`, excluding deleted
conversations and future/out-of-period creation times. Outcomes come only from
completed/partial runs with recorded knowledge outcomes. Completed runs without
outcomes are explicitly unmeasured. Failures and cancellations are separate.
Median response time uses valid creation-to-completion durations, including queue
time, for completed runs. All intervals use UTC calendar days including today.

The original `cost_usd` fields remain immutable budget-accounting totals for
compatibility. The UI now reads additive `cost_reporting` projections instead:
usable historical token counts are reconstructed at Standard uncached rates,
while timeouts, cap-shaped token counters, and unknown models remain unresolved.
Safety allowances are shown separately, never added to the usage-cost chart.
Projections and their uncertainty do not rewrite ledger or reservation records.
See [usage-cost-reporting.md](./usage-cost-reporting.md).

Authority is a current snapshot of authorized, undeleted documents' current
versions; unversioned documents are reported separately. Backlog counts cover all
currently visible open tasks, not a paginated subset. Maintenance items preserve
the existing conversation-review consent and evidence-access checks. Only up to
five task summaries are returned, in conflict/feedback/gap/review/owner priority.
Anonymous totals do not expose individual activity, questions, or answers.

## Interface

Four summary metrics accompany daily activity, outcome breakdown, current document
authority, and daily cost charts. A Needs attention list links to real source and
maintenance destinations. Charts use straight segments/columns, direct labels,
keyboard day inspection, touch selection, and native data-table alternatives.
Mobile order is summary, attention, activity, outcomes, authority, then cost.
Missing/error/loading states do not invent successful measurements. Failed
refreshes label retained data as the last successful snapshot.

## Local verification

- Backend unit suite: 2,258 passed; four existing skips remain skips.
- Frontend suite: 773 passed across 97 files.
- Database: five new dashboard contracts and eight governance contracts passed on
  the isolated local fixture, including UTC boundaries, private feedback,
  invalid durations, deletion, current versions, and backlog counts above 100.
- The endpoint test covers role denial, normal/invalid URL periods, and no-store.
- Authenticated Playwright owner flow passed against the running local app at
  desktop 1440px and mobile 390px, including period changes, keyboard inspection,
  table disclosure, zero horizontal overflow, and no page errors.
- Production build, frontend types, Pyright, Ruff, OpenAPI, action inventory, and
  migration allowlist checks passed. Frontend lint has three preexisting image
  warnings and no errors.

Private logs and desktop/mobile screenshots are under `.private-eval/overview-*`.
The migration was first applied and tested in an isolated fixture, then applied
atomically to the local application database with a pre-change schema snapshot.
Generated database types and OpenAPI were refreshed through existing workflows.
The local API was restarted to register its route; the database stayed running.
No authority records, answering flags, model settings, or budgets were changed.

## Hosted rollout

Hosted migration, deployment, and managed-environment validation were not run.
Apply the additive migration through the normal authorized staging workflow
before deploying code that reads the RPC. Validate role boundaries, ledger totals,
and representative query plans there before hosted enablement. Rolling back the
UI/API does not require deleting the RPC or any historical records.
