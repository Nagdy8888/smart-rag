# Company knowledge reliability implementation

Implementation started 25 October 2026; local verification continued 26 October.
This is an additive implementation record. Existing approved plans and evaluation
history remain unchanged. Hosted rollout and live-model qualification are not
established by these local checks.

## Delivered behavior

- Canonical document responsibility, knowledge area, review date, and per-version
  authority: unreviewed, draft, approved, superseded. Existing documents default to
  unreviewed. Approval requires an active owner and an explicit effective date.
- Owner/admin governance controls, version selection, explicit approved-current
  replacement links, optimistic document-wide revisions, and atomic audit/cache
  generation updates. Metadata updates do not re-embed or publish source content.
- Authority-aware Hybrid selection and a shared pre-generation/final-release
  check for Hybrid, graph-resolved passages, and table evidence. Draft, replaced,
  and future-effective evidence cannot establish current answers. Unreviewed
  evidence remains usable with warnings. Overdue review does not imply expiry.
- Durable supported/partial/insufficient/conflicting outcomes, authorized source
  authority in citation detail, and specific uncovered headings when available.
  In reliability mode, checked prose and its outcome persist together before
  release; stream and transcript use the same outcome. Operational verifier
  failure stays outside the supported-knowledge classification.
- A saved single-document selection per conversation, with explicit clearing,
  paginated document choices, and immutable per-run document/version snapshots.
  ACL changes or version replacement fail closed instead of broadening scope.
- One optional focused clarification from the existing preparation call. Pending
  context is creator-private and durable. Its response resumes after normal
  admission; replay is idempotent and another clarification is suppressed.
- Four employee-facing feedback categories supplement existing diagnostic tags.
  Sharing a question, answer, and feedback with reviewers requires explicit
  consent. Admin role alone does not expose another employee's private thread.
- Knowledge maintenance lists missing owners, overdue reviews, consented negative
  feedback, and authorized insufficient/conflicting outcomes. Assignments and
  reasoned resolution/dismissal use optimistic revisions and audit records.
  Reviewed feedback can be exported as an explicitly unsealed regression draft;
  it never automatically changes gold, prompts, or company guidance.
- Restored company answers are hidden when supporting evidence is deleted,
  replaced, or inaccessible. Stored messages remain unchanged. The underlying
  event-replay RPC also blocks old answer tokens; hiding citations alone would
  leave a disclosure path. Private review records cascade with their source
  feedback/runs on conversation deletion.

## Deliberate v1 limits

- Selection is one document or all authorized company documents, not collections
  or multiple selected documents.
- Automatic conflicts are conservative: two approved sources must explicitly
  match knowledge area, applicability/scope, field name, and unit while giving
  different numeric values. Both exact passages are cited and checked. General
  semantic contradiction detection is not claimed.
- Existing canonical current-version authorization remains intact. Older-version
  governance metadata is manageable, but this change does not introduce a new
  historical-text retrieval bypass. Historical/version-comparison questions that
  need unavailable noncurrent evidence still require a truthful limitation.
- Unanswered headings are exposed when the existing retrieval diagnostics supply
  them. Complete semantic coverage detection for every multipart question is not
  established by deterministic checks alone.
- Readiness diagnostics retain the existing extraction/indexing distinctions;
  authority/review warnings are presented separately in document detail.

## Baseline and evaluation custody

The initial source inspection confirmed existing temporal filtering, coverage,
feedback, source resolution, and checked-answer release. The first focused
baseline passed 106 tests. Historical accuracy/review reports remain historical;
their old scores are not a current baseline or evidence that a finding persists.

`scripts/build_company_knowledge_pack.py` snapshots the allow-listed private
development gold without modifying it. The locally built pack at
`.private-eval/company-knowledge-v1-20261026` contains the existing 40 private
development questions, 216 synthetic development cases (205 English and 11 mixed),
source hashes, existing connected 50-turn regression references, release-integrity
references, governance contracts, and the quality-target mapping. Private gold
and source bytes are not committed. Qualification and immutable holdout files are
not copied, opened, or relabeled. An Arabic-only company-question slice still
needs reviewed labels; mixed-language coverage does not establish that slice.

Live reporting must retain correctness, citation support, outcome/refusal,
current-source selection, permission isolation, p50/p95 latency, and cost by
category. Use the existing authenticated runners and budgets, with verbose
per-question progress. A local deterministic pass is not a live quality pass.
The existing company Ask runner now captures checked outcomes and usage from
SSE and writes an additional `*-knowledge-metrics.json` report grouped by question
category and language. Missing cost/outcomes remain unmeasured; citation-support,
current-source, and permission judgments require explicit reviewed annotations.
Their absence produces null rates, not inferred passes. The reporter does not
declare a quality gate passed.

## Local checks and external gates

The final schema-only fixture `knowledge_reliability_verified_20261026` reapplied
all seven migrations, including tombstone cleanup, in the existing local Supabase
PostgreSQL container. Earlier isolated fixtures remain preserved. No corpus,
users, conversations, or checkpoints were copied. PostgreSQL 17.11 and pgvector
0.8.2 were observed locally; managed-target versions were not verified. Contract
tests seed synthetic data; the new governance contracts roll it back, while some
existing concurrent contracts commit their synthetic setup. Existing databases
were not reset.

The local verification run passed 2,257 backend unit tests (four skipped), 768
frontend tests, and 44 selected database contracts. Ruff, Pyright, frontend type
checking, production build, OpenAPI compatibility, and frontend action inventory
checks passed.
Frontend lint had no errors and three existing image warnings. Browser checks
passed seven tests and skipped nine requiring a reachable authenticated backend;
these skips do not satisfy the authenticated release gate.

Verification commands:

```powershell
uv run pytest tests/unit --tb=short
uv run pytest tests/contract/test_company_knowledge.py --tb=short
uv run python scripts/ops/verify_knowledge_migrations.py --database knowledge_reliability_new_fixture --run-contracts
uv run pyright
uv run python scripts/ci/check_openapi.py
pnpm --filter smart-rag-frontend typecheck
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend test
pnpm --filter smart-rag-frontend build
```

The migration verifier creates a new schema-only local database and refuses an
existing database name. It records redacted contract logs and JUnit results under
`.private-eval/<database>`. Use a new name for each reproduction.

The direct database contract command requires an explicit local fixture
`SUPABASE_DB_URL`; the existing test helper refuses hosted destructive targets.
No DSN/password is recorded here. Database TypeScript types were regenerated
through the Supabase CLI against that isolated fixture; OpenAPI was regenerated
from the application. The type refresh also captures existing local schema
features absent from the prior generated snapshot.

Desktop (1280px) and mobile (390px) component fixtures were inspected in Chromium,
with no horizontal overflow or browser errors. The fixture exercised actual
components with synthetic API responses, including the approval form. It is
separate from authenticated end-to-end testing against a running application.
Captures are local under `.private-eval/knowledge-preview-20261026`.

The UI refinement groups authority fields into a responsive definition list,
uses semantic status labels, keeps report details expandable, and places review
forms in two columns on desktop and one on mobile. Feedback-sharing consent
appears before submission. Repeated reviewer controls have unique field IDs.
Desktop/mobile fixtures had no overflow, duplicate IDs, or page errors; keyboard
focus moved from consent to submission. The 768 frontend tests and production
build passed, with the focused nine interaction tests repeated after icon reuse.

After the user reported an empty Knowledge tab, the running local app was found
to lack all seven migrations. They were applied atomically to the local
`postgres` database, with a pre-change schema snapshot preserved privately.
The user's authenticated browser then displayed the real missing-owner item.
This is local verification only. The answering flag remains false, existing
sources remain unreviewed, and the local database remains running.

Release remains gated on a complete new-code live evaluation, reviewed Arabic
company labels, managed migration/RLS verification, authenticated browser flows,
staging load/reconnect/cancellation checks, and the existing accepted targets in
`docs/QUALITY_TARGETS.md`. Missing/skipped mandatory gates remain non-passes.

## Rollout and rollback

1. Apply the seven `20261025` migrations in order using the existing migration
   workflow in an authorized staging environment. Verify privileges, RLS,
   deletion, consent, event replay, and optimistic updates there.
2. Deploy compatible backend contracts, then frontend controls. Review imported
   document metadata; do not bulk-approve existing sources.
3. Enable `app.company_settings.knowledge_reliability_enabled` only in the
   authorized validation environment. The migration default is false. Selection
   controls state explicitly when scoped answering is not enabled.
4. Run the frozen evaluation and applicable release gates under existing budgets
   before company-wide activation. No budget increase, production deployment, or
   destructive cleanup is authorized by this implementation.
5. Roll back behavior by disabling the flag. Keep metadata, audit, and evaluation
   records. Keep the history/event permission guard and safe checked-answer
   release; never restore inaccessible prose or an unchecked draft.

Monitor the recorded outcome distribution, feedback categories, unresolved
maintenance backlog, overdue ownership/reviews, latency, and gateway spend. Keep
raw questions, answers, source text, and personal metadata out of exported traces.
