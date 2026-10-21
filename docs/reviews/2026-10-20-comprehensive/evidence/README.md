# Review evidence

All results apply to the local checkout reviewed on 20 October 2026, commit `a2164952a3ea4bfd87879b2d6d6d0dadf5643f27`. Start with the [review index](../README.md).

## Reproduce the synthetic findings

From the repository root:

```powershell
.venv\Scripts\python.exe docs/reviews/2026-10-20-comprehensive/evidence/reproduce_findings.py
```

The script uses synthetic answer text and fake key sources. It does not need credentials and does not contact the database or providers. It intentionally asserts the reviewed defective behavior; it is a review demonstration, not a regression test to keep green after fixes.

- [reproduce_findings.py](reproduce_findings.py): executable demonstrations of semantic rewrite acceptance, Arabic guard bypass, native-block loss, retained input registry, and repeated JWKS refresh.
- [reproduction-results.txt](reproduction-results.txt): output of that script.
- [targeted-reproductions.txt](targeted-reproductions.txt): earlier exploratory output. Its first Arabic attempt was mangled by Windows pipe encoding; the later explicit Unicode attempt and saved reproduction script verify the actual Arabic case. Do not use the mangled display as Unicode evidence.

## Local commands and logs

The following commands were run from the repository root. Logs contain test/audit output, not provider keys or corpus content.

```powershell
.venv\Scripts\python.exe scripts/check.py --tier fast
.venv\Scripts\python.exe -m pytest tests/unit --tb=short
.venv\Scripts\python.exe -m ruff check apps packages scripts tests --output-format concise
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pyright
pnpm --filter smart-rag-frontend test
pnpm --filter smart-rag-frontend typecheck
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend build
```

- [python-unit.txt](python-unit.txt): 1,906 passed, 5 failed, 4 skipped.
- [ruff-lint.txt](ruff-lint.txt): one import-order issue.
- [ruff-format.txt](ruff-format.txt): 16 files need formatting. The fast command stopped at this stage; that original combined output was inspected in the session, and the formatting command was repeated to save a standalone log.
- [pyright.txt](pyright.txt): 107 errors.
- [frontend-full-run-summary.txt](frontend-full-run-summary.txt): transcription of the full run's key result, because its original stdout was inspected through the terminal tool rather than redirected to a file. This is a summary, not a complete raw log.
- [frontend-failure-recheck.txt](frontend-failure-recheck.txt): focused repeated execution of the two initially failing files; citation tests pass, architecture-budget failure remains.
- [frontend-typecheck.txt](frontend-typecheck.txt), [frontend-lint.txt](frontend-lint.txt), [frontend-build.txt](frontend-build.txt): successful checks.

Focused repeat:

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/components/core-rag-surfaces.test.tsx src/lib/architecture-budget.test.ts
```

Some versions of pnpm append “Command vitest not found” after a nonzero `exec` result even though Vitest ran and printed its test summary. The test output before that wrapper message establishes the actual failure. Similarly, Windows PowerShell wraps native stderr warnings in `NativeCommandError`; the pytest summary, not that warning wrapper, supplies pass/fail counts.

## Selected security/API contracts

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_jwks_auth.py tests/contract/test_jwks_rollover.py tests/contract/test_auth_rate_limits.py tests/contract/test_crawl_ssrf.py tests/contract/test_privileged_secrets_absent.py tests/contract/test_pdf_figure_access.py tests/contract/test_citation_page_preview.py tests/contract/test_sse_run_lock.py tests/contract/test_sse_resume.py --tb=short
```

[security-contracts.txt](security-contracts.txt): **42 passed, 11 skipped**. Database-dependent tests skipped; this is not a hosted RLS/SSE certification. No general migration reset/reapply was attempted.

## Browser/UI evidence

```powershell
pnpm --filter smart-rag-frontend exec playwright test tests/e2e/a11y-security.spec.ts --grep 'Tab order|200% zoom|login never'
.agents\skills\impeccable\scripts\impeccable.cmd detect apps/frontend/src
```

- [browser-login-checks.txt](browser-login-checks.txt): three passing unauthenticated Chromium tests using the configured temporary Next.js server. The zoom-named test uses viewport dimensions, not a real zoom change.
- [ui-detector.txt](ui-detector.txt): six matches: four bounce-easing instances and two test-string image matches. The latter are false positives for shipped UI. The scan is advisory, not an accessibility test.

Existing API `127.0.0.1:8000/health/live` and console `127.0.0.1:3000/login` probes returned connection errors. Authenticated flows were not run. Historical README and visual-route fixtures were visually inspected; no new authenticated screenshot or overlay is claimed.

## Dependency evidence

```powershell
pnpm audit --audit-level high
pnpm audit --json
uv export --frozen --all-packages --group dev --no-emit-workspace --format requirements.txt --output-file docs/reviews/2026-10-20-comprehensive/evidence/requirements-audit.txt
.venv\Scripts\python.exe -m pip_audit --strict --ignore-vuln PYSEC-2026-113 --requirement docs/reviews/2026-10-20-comprehensive/evidence/requirements-audit.txt
```

- [node-audit.txt](node-audit.txt): 11 findings, including one ignored high; high-threshold command exited zero.
- [node-audit.json](node-audit.json): dependency/advisory paths and muted metadata. Interpret exposure separately.
- [python-audit.txt](python-audit.txt): three nonignored advisory entries for aiohttp; two ignored entries were reported by the configured exception. The listed fix is 3.14.4.
- [requirements-audit.txt](requirements-audit.txt): frozen exported dependency input.
- [dependency-export.txt](dependency-export.txt): export command output.

Audit results are time-sensitive. They describe the advisory databases consulted during this review, not future vulnerability status. Configured ignores mean a successful audit command is not equivalent to zero vulnerabilities.

## What the initial review did not run

No paid-model evaluation, deployed-site authentication, hosted database migration, cloud deployment, production penetration test, real multi-process race, restore drill, or external issue/trace inspection. No raw private evaluation questions, credentials, or corpus documents are included.

Later authenticated live-provider API/SSE and checkpoint work is documented in
the [checkpoint repair follow-up](../14-checkpoint-failure-repairs.md). Its scope
does not include a hosted deployment or production qualification.

## Checkpoint-repair follow-up - 21 October 2026

[checkpoint-repair-validation.json](checkpoint-repair-validation.json) contains
aggregate-only proof from the final single-build authenticated 25-question run:
25 fixed checks passed, 20 completed and five partial. The export verifies frozen
input/criteria, unchanged image/source fingerprints, source-line comparisons,
manual reviews and authorized figure PNGs. Private questions, answers, checkpoints,
images and credentials remain under gitignored `.private-eval/`. See the
[full repair report](../14-checkpoint-failure-repairs.md) for limitations and the
remaining repository release blockers.
