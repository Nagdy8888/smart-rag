# Web answer and history repair — 2026-10-28

**Offline validated; live quality unconfirmed.** No paid questions, budget
changes or deployment were performed. Historical answers and
campaign evidence were preserved.

## Behavior

- Research reads ranked candidates before its single evidence-gap critique.
  Optional searches retain synthesis/verifier time inside the existing two
  rounds, three formulations, five operations, six sources and 50-second
  envelope. Explicitly incompatible documentation versions are excluded;
  unversioned Python requests prefer current documentation.
- Query-relevant contiguous windows use both original and discovery-language
  anchors before persistence and prompt fitting. Persisted excerpts are not
  rewritten during synthesis. Missing production synthesis fails closed;
  extractive mocks require an explicit fixture opt-in.
- The immutable `web_answer_v2` prompt preserves language, requested examples,
  comparisons and limitations. Validated `[[cite:index]]` markers retain exact
  stored citation positions. Malformed or shifted references are rejected.
- One counted `web_verifier_v1` call checks the whole draft for support,
  coverage, language, references and explicit limitations. Unsupported or
  unchecked prose is refused. Incomplete coverage survives only as an explicitly
  partial draft whose other checks pass. There is no second synthesis attempt.
- Exa child work is cancelled at the supplied timeout. Optional proxy reads
  receive the remaining research budget. Accounting retains consumed reservation
  versions on attempted-call failure.
- History restores recorded requested scope and separately displays recorded
  answer origin. Missing legacy metadata stays unknown. Company-document
  controls are hidden in Web mode. At most four visible historical runs query
  cached citation metadata; passages are fetched only when selected.
- Shared one-based display numbering leaves stored identities unchanged.
  Structured references open their exact supporting passage; legacy numeric
  references use their historical indices. Clipboard output uses display
  numbers. Sources group identical normalized Web pages while retaining every
  passage. Full company/Web source lists appear only after clicking Sources;
  chat retains compact Web reference numbers. Failed-history notices stack
  below the question on mobile.

## Persistence and compatibility

Migration `20261028110000_run_presentation_metadata_v1.sql` adds a read-only
presentation RPC using the existing creator-authorized run lookup. It returns
recorded scope and the latest recorded origin event, never guessed origin.
Anonymous, browser-authenticated and worker roles receive no execution grant.
Old/reaped origin events remain null. Transcript fields are additive; the
OpenAPI snapshot, frontend parser/types and generated RPC type were updated.

The migration was applied to the explicit local test instance and its fresh
schema-only test database. **It was not applied to the runtime hosted database.**
The application release must apply the forward migration before starting the
updated backend. Hosted Web enablement remains forbidden by existing settings.

## Evidence

- Full Python unit run: **2,340 passed, four skipped**, exit code zero.
- Latest focused Web/routing/prompt checks: **67 passed**.
- Full frontend run after the on-demand Sources refinement: **793 passed**;
  the source-specific surface/interaction run also passed **96 tests**. TypeScript and
  production build passed. ESLint reports only the three existing image warnings.
- Standard offline contracts: **300 passed, 291 skipped**. Skips are not live
  integration approval. The initial authored-docstring failure was repaired
  without changing the checker.
- Isolated database: **32 contracts passed**, covering creator/foreign metadata,
  transcript compatibility, citation containment, source deletion/unavailability,
  privileges and Web persistence. Expected SQL-error tests now use savepoints
  instead of leaving their enclosing test transaction aborted.
- Desktop 1440px and mobile 390px mocked-Auth/API journeys both passed. They
  submit exactly one intercepted question each, read the Arabic answer, open
  both exact supporting passages and original links, inspect grouped sources,
  reload, restore Web and retain failure history. A ten-citation company
  fixture additionally proves no source list or filenames appear in chat and
  all ten source controls appear after clicking Sources. Screenshots were visually
  inspected; no real admission or provider endpoint was called.
- Saved HTTP-429 evidence replay: ten exact contained windows; every recorded
  excerpt containing the cache rule retained it in the selected window.
- Full strict Pyright, Ruff, migration policy and OpenAPI checks passed.

Private evidence is retained under `.private-eval/`: `web-repair-unit.xml`,
`web-repair-python-exit.json`, `web-repair-ui-confirmed.json`,
`web-repair-vitest-focused-final.json`, `web-repair-contracts-final.txt`,
`web-repair-sources-browser.txt`, `sources-on-demand-chat-390.png`,
`sources-on-demand-sheet-390.png`,
`web-repair-saved-evidence-replay.json` and the associated build/lint/type logs.
CI also runs the Web journey through `playwright.web-fixture.config.ts` after
the standard browser suite. Its loopback-only Auth fixture is started and stopped
by Playwright; no hosted test credentials or private helper scripts are required.

The isolated browser copy used separate mocked Auth/API services; those helpers
were stopped after verification. The local frontend was started on port 3000
with the final source changes for review.

## Remaining live gate

Obtain a separately approved accounting allowance before rerunning the 15 Web
questions through normal admission. Read the new responses and citations in the
actual app on desktop/mobile and adjudicate factual support, completeness,
language, source versions and latency. Offline fake-provider verdicts prove the
release gates and failure behavior; they do not establish live model accuracy.
Do not raise monthly limits, rewrite accounting or relabel estimates as bills.
