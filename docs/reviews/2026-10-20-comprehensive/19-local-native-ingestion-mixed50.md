# Local native ingestion and mixed 50-question evaluation

Verified on 2026-10-22 under the user's temporary local Supabase authorization.

## Native ingestion

The original 355-page PDF passed fresh ClamAV scanning, authenticated detector
review, parsing, embedding, and BM25 verification as real company content. Graph
indexing remains disabled under the existing Hybrid-only PDF workflow.

- Original bytes and SHA-256 match the source file.
- 1,206 canonical chunks; all have page locators.
- 1,134 embedded representatives and verified rows in an isolated local BM25 DB.
- 40 private PNG figures; all stored hashes, sizes, and images were checked.
- 20 private Parquet tables containing 104 rows; all files and row counts checked.
- Authenticated figure access returns 200; unauthenticated access returns 401.

The image uses native parser v5, PyMuPDF 1.25.5, and Tesseract 5.5.2. Unused explicit
Mesa/GLib packages were removed from its Dockerfile; required transitive libraries
remain installed. Read-only, network-disabled runtime checks and ingestion passed.

## Evaluation

All 50 prompts ran through authenticated app conversation/message/SSE endpoints:
42 completed and 8 partial runs, with no runner infrastructure exceptions. All
conversations belong to the local admin and have numbered Mixed50 titles.

The set contains 19 text, 9 code, 11 table, 9 figure, and 2 unsupported-answer cases.
It reuses 25 development cases and adds 25 source-checked prompts, including Arabic,
arithmetic, and multi-part requests. It is not a holdout.

The initial checker passed 39/50. A documented audit corrects native-format false
alarms and adds completion, Python grammar, arithmetic, and Arabic-language checks:
38/50. Spot review additionally flags an irrelevant excerpt appended to an absence
statement. **37 clear the combined recorded checks; 13 are flagged.** This does not
establish independently adjudicated semantic accuracy.

All 24 query-stage artifact HTTP checks succeeded: 15 PDF-page PNGs and 9 figure
PNGs. All 55 distinct usable cited chunk IDs resolve to the current local PDF.

## Material findings

1. Unsupported questions can receive unrelated excerpts instead of a clean
   lack-of-evidence response (`x24`, `x25`).
2. Function assembly is incomplete across code boundaries/pages (`c03`, `c06`,
   `x18`). The signature on physical page 205 continues on page 206. The emitted
   signature alone fails Python grammar. Code was parsed, not executed.
3. Arabic output loses a citation in one case and returns English tables in two
   others (`x09`, `x10`, `x11`). The `x09` checkpoint contains retrieved evidence and
   a skipped citation; the terminal verifier alone is not a root-cause finding.
4. The numeric comparison omits the requested subtraction (`x16`). Multiline
   numeric table header reconstruction also merits review.
5. A multi-part answer omits storage (`x23`). Some source-excerpt fallbacks remain
   poorly organized or partial (`p04`, `p05`, `x08`).

Preserve clean refusals first, then repair bounded code assembly, citation
resolution, native-table language handling, numeric execution, and subquestion
coverage. Keep this baseline immutable for comparison.

## Evidence and boundaries

Private folder: `.private-eval/local-mixed50-20261022/`.

- `REPORT.md`: findings, scoring limits, and repair priorities.
- `QUESTIONS.md` / `questions.json`: all prompts and source expectations.
- `answers.md` / `results.json`: actual responses and citations.
- `assessment-v2.json`, `spot-review.json`, `post-run-audit-policy.md`: grading audit.
- `terminal.log`: visible per-question process.
- `provenance.json`, `persistence-verification.json`: build and persistence checks.

Native integrity proof is in `.private-eval/local-ingestion-verification.json`.
Source PDF and question/answer contents remain private and uncommitted.

Separately, 20 PDF/parser/page-label tests and 30 Compose/migration-policy tests
passed. Browser automation was disconnected; frontend HTTP and real API/SSE checks
passed, but no browser-click or visual UI pass is claimed. The API used the stable
checkpoint-fix image; the pending excerpt-context candidate was not deployed for
this baseline. Hosted data and its verified checkpoint backup remain preserved.
