# Agent release regression set

Dataset: [agent_release_v1.json](../../tests/fixtures/agent_release_v1.json).
This is a public synthetic **development regression**, not a sealed holdout,
retrieval benchmark, live-model evaluation, or production accuracy score.

## What the 25 questions cover

- English negation, order, permissions, modality, comparisons, conditions,
  causality, and units.
- Arabic and mixed Arabic/English content.
- Independent paragraphs with different canonical evidence IDs.
- Code, unclosed fences, tables, figures, and mixed native content.
- Six paragraphs and a seven-block example that previously lost content.
- Document text resembling prompt injection, existing headings, and a short answer.

Each record contains a stable case ID, question, source-exact expected paragraph
bodies, and an unsafe candidate rewrite. The bodies are synthetic source evidence;
there are no customer documents, JWTs, or credentials in this set.

## Two checks for every question

1. **Supported-answer path:** build canonical synthetic evidence; run the real
   verifier node with a no-network provider double; record the citation-persistence
   call; check retained expected content and paragraph/source mapping. The captured
   persistence payload must equal the final answer payload.
2. **Immutable release path:** offer the unsafe rewrite to a recording provider;
   assert zero organizer sends, exact payload identity, unchanged usage/call counts,
   exact SSE text, and one terminal event.

The simulated persistence call proves application payload consistency, not actual
Postgres authorization or committed citation rows. Synthetic source IDs do not
prove retrieval recall or live document/page resolution.

Additional tests inject checker/persistence failures, missing/duplicate/foreign
verifier verdicts, poisoned post-verification updates, budget denial, invalid
provider output, uncertain timeout, missing accounting, and durable refusal usage.

## Run with visible per-case progress

From the repository root:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_agent_release_regression.py tests/unit/test_agent_release_failures.py tests/unit/test_verifier_accounting.py tests/unit/test_verify_verifier_skipped.py tests/unit/test_query_sse_mapping.py -vv --tb=short
```

The `-vv` is intentional because the repository's default `-q` otherwise hides
question IDs. JUnit XML can be added for machine-readable results.

## Baseline and release discipline

Before the changes, the 25 immutable-release cases returned **9 passes and 16
failures**. After the changes, all 25 passed. The 25 supported-answer checks were
added afterward; their 25/25 result must not be presented as a measured before/after
accuracy gain. Both checks now run for every question.

Dataset bytes and current source hashes are recorded in the implementation
manifest. Keep this set fixed for comparisons; add new cases under a new version
when changing expected behavior. It is deliberately tuned development coverage,
so do not relabel it qualification or holdout.

## Live follow-up

Once the API, Docker sidecars, and authorized test environment are available, run
the existing full fixed company-document regression with per-question progress,
stage export, strict and grounded-fact scoring, correct-page citations, latency,
cost, and infrastructure-error classification. Compare the original and patched
versions on the same corpus/configuration; never combine overlapping repair
subsets or use these synthetic checks as proof of that result.
