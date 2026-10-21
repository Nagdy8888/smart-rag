# Agent fix implementation handoff

Date: 20 October 2026. Base reviewed commit:
`a2164952a3ea4bfd87879b2d6d6d0dadf5643f27`. Changes are local and uncommitted.

Subsequent update: the user requested real app messages. See the
[live user-flow follow-up](13-live-user-flow-results.md) for 25 actual questions,
observed problems, and private terminal evidence. The unavailable-services notes
below describe the original implementation handoff, before that follow-up.

## Implemented scope

This implements the agent answer-release slice of the
[approved fix plan](11-fix-execution-plan.md): baseline/test set, Packet 1's local
release protections, removal of the organizer spend from Packet 2, verifier
accounting, and associated tests/UI wording. Historical canonical plan checkboxes
have not been rewritten or marked complete.

- **AG-01:** removed the semantic model rewrite after verification. The compatibility
  organizer now returns the exact state and makes zero model calls.
- **AG-02:** removed organizer paragraph/citation remapping. The SSE mapper releases
  the frozen verifier artifact, including its per-paragraph sources.
- **AG-03:** removed uncounted organizer sends and live prompt binding. Also found
  and repaired the live verifier's missing durable accounting wrapper.
- **AG-04:** checker, release, schema, and persistence failures produce a typed safe
  refusal instead of restoring draft claims. The public refusal contains no
  original claims, citations, or exception messages.
- **AG-05:** removed organizer block slicing; native append logic preserves checked
  paragraphs and marks capacity-limited results partial instead of evicting prose.
- Verifier verdict IDs must match the selected batch exactly, with no duplicates.
- Raw successful verifier responses are accounted before semantic-payload parsing;
  uncertain sent outcomes use conservative caps. Paid runtime without an accounting
  connection is rejected before the verifier send. No verifier retry was added.
- Safe refusals refresh usage from the durable ledger when available, so refusing
  invalid output does not hide its recorded spend.
- Answer-stage reserve is now two calls, matching answer plus verifier. Existing
  family ceilings and cost caps were not raised.
- UI copy distinguishes verification-unavailable refusals from supported partial
  answers. A small ChatApp presentation-hook extraction also restores the existing
  320-line composition budget without changing its threshold.

## New test set and results

See [test-set specification](../../evaluation/AGENT_RELEASE_TESTSET.md) and
[dataset](../../../tests/fixtures/agent_release_v1.json).

- 25 fixed synthetic questions, covering English, Arabic, mixed language, source
  mappings, code, tables, figures, native overflow, and injection-like document text.
- Original immutable-release baseline: **9 passed, 16 failed**.
- Patched immutable-release cases: **25/25 passed**.
- Supported source-exact question path through verification and mocked citation
  persistence: **25/25 passed**. These healthy checks ensure the fix is not merely
  refusing every question.
- Dedicated new release/fault/accounting coverage plus existing verifier/SSE
  regressions: **107 passed**; see `implementation-evidence/agent-regression.txt`
  and its JUnit XML. Of these, 78 checks are new.
- Full frontend suite after extraction and copy fixes: **699 passed**, across all
  89 test files. Frontend production build passed.
- Selected SSE/PDF/citation contracts: **15 passed, 18 skipped**. Skips explicitly
  require `SUPABASE_DB_URL`; no live RLS/page-persistence proof is claimed.
- Changed Python source/test lint and formatting checks pass; `git diff --check`
  passes. Full Python/static results and known failures are detailed below.

## Known full-repository gates

The final full Python unit suite reported
**1,981 passed, 2 failed, 4 skipped**. The remaining failures were present in the
original review:

1. Direct unapproved figure-provider construction in `openai_figure.py` violates
   the traced-helper call-site contract. Ingestion vision governance is still an
   unresolved finding; this change does not weaken the scan to hide it.
2. The media routing snapshot expects pre-search refusal, whereas current code
   routes figure questions through Hybrid. This is an existing contract mismatch;
   its golden file was not blindly updated to force a pass.

The most recent full Pyright run reports **96 errors**, down from the review's 107.
The remaining errors concern existing PDF/vendor typing, related fixtures, and
existing citation/routing test code. New agent release/accounting files have no
reported type errors. This is not a clean project-wide type gate.

Full frontend ESLint still reports two errors in the unchanged
`citation-drawer.tsx` (ref mutation during render and synchronous effect updates),
plus warnings. Changed UI files are checked separately. Build/tests passing does
not erase the lint failures.

## Not completed or claimed

- No live paid-model answer-quality comparison, retrieval recall measurement,
  latency percentile, provider-dollar reduction, or actual hosted citation write
  was measured. Provider doubles and persistence spies are explicitly synthetic.
- Local API/console probes were unreachable. Docker Compose could not connect to
  `dockerDesktopLinuxEngine`; the Docker engine is not running. This prevents the
  normal local full-stack PDF regression in the current environment.
- No deployment, hosted migration, source re-ingestion, immutable holdout access,
  credential export, production issue inspection, or production-readiness claim.
- The rest of the application plan remains open: full figure-provider governance,
  PDF process isolation/resource admission, durable executor leases, registry
  retention, JWKS burst controls, dependency remediation, richer PDF/mobile/focus
  UX, and managed deployment/restore verification.

## Evidence and follow-up

All saved command output is under `implementation-evidence/`. The original review
and its exploratory reproductions are historical snapshots; its removed private
organizer helpers are no longer the supported test entrypoint. Use the versioned
pytest dataset and new tests for the patched behavior.

Next live gate: run the full fixed company-document suite on the exact patched
image and original baseline with identical corpus/model/prompt/profile settings,
inspect stage loss per miss, and preserve correctness/citation/cost limits. Do not
mark the full fix plan or Phase 6 complete from these local results.
