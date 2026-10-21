# Local implementation evidence

This folder contains local development checks, not hosted or production proof.
See the [implementation report](../12-agent-fix-results.md) for interpretation.

## Final evidence

- `implementation-manifest.json`: base commit, dataset SHA256, changed source
  hashes, installed Python package versions, and focused JUnit totals.
- `agent-regression.txt` / `agent-regression.xml`: 107 passing checks from the
  five test modules listed in the [test specification](../../../evaluation/AGENT_RELEASE_TESTSET.md).
- `unit-final.txt`: full `uv run pytest tests/unit --tb=short`; 1,981 passed,
  two existing failures, four skipped. Exit status is failing.
- `pyright-final.txt`: full `uv run pyright`; 96 existing type errors.
- `frontend-final.txt`: full frontend Vitest run; 699 tests passed.
- `frontend-build.txt`: production Next.js build passed.
- `frontend-changed-lint.txt`: scoped ESLint for six changed TS/TSX files passed
  with no output. `frontend-lint.txt` records the separate global lint failures.
- `contracts.txt`: selected SSE/PDF/citation contracts; 15 passed, 18 skipped
  because the database prerequisite was unavailable.
- `architecture-budget.txt`: existing composition-budget checks passed.

## Baseline and intermediate evidence

`release-baseline.txt` captures 9 passes and 16 failures on the immutable-release
set before the repair. `release-after.txt` captures all 25 passing afterward.
`question-set.txt` captures the 50 paired healthy and immutable-release checks.
Other logs are intermediate checks, not the final full-suite result.

PowerShell may append `NativeCommandError` framing around a native program's
stderr warning. Use the actual pytest summary and recorded failing test names;
warnings do not change a failing suite into a pass or vice versa.
