# G4b - Re-ingest the book with reflow v5 and measure

Read [`00-rules-and-commands.md`](./00-rules-and-commands.md) first.

**Depends on:** G4a committed, pushed, green, and its parse check passed.
**Live run:** yes - re-ingest (pre-approved by the user, see Step 1) and
dev40. Run every step in order without asking; stop only where a step
says "stop".
**Target:** on dev40, strict passes of `code` plus `table` questions go
up against the last kept run, and total strict passes do not drop by
more than 3. **Stop rule:** if either fails, revert G4a and re-ingest
again (Rollback).

## Read first

- `.cursor/plans/answer-loss-repair/A8-reingest-book.md` Steps 4 to 7
  (the proven re-ingest procedure this packet reuses).
- `.private-eval/a8_version_report.py` (private).
- `.private-eval/runs/g4-reingest/parse-before.txt` and
  `parse-after.txt` from G4a.

## Step 1 - Pre-checks (no user approval needed)

The user pre-approved this packet's re-ingest and its rollback re-ingest
on 2026-10-06 with the words "no need for my approval make g4b". Do not
ask again. The approval covers only what this packet lists: soft-deleting
the current book document with `scripts/ops/soft_delete_duplicate_documents.py`,
uploading the same PDF as a new document with `scripts/ops/ingest_private_pdf.py`
(one new Auth owner user is created), and the same pair once more in
Rollback. It does not cover SQL edits, other documents, or the holdout.

Before Step 2, confirm all three, and stop if any is false:

1. `git log --oneline -1 --grep "(G4a)"` prints the G4a commit, and
   `gh pr checks` shows every check passing.
2. `.private-eval/runs/g4-reingest/parse-after.txt` exists and meets the
   G4a Step 9 pass criteria.
3. `.cursor/plans/general-answer-quality/00-rules-and-commands.md`
   "Current book" line still names document `b56d5774-8810-4ee9-a4d3-f3c93fa90ea7`
   and version `d7e3206a-b262-44d7-90bc-b1572d864c35`. If it names other
   ids, stop and report them; Steps 3 and 5 hard-code these two ids.

Write one line to `.private-eval/runs/g4-reingest/approval.txt`:
`pre-approved 2026-10-06: "no need for my approval make g4b"`.

## Step 2 - Private version report

Copy `.private-eval/a8_version_report.py` to
`.private-eval/g4_version_report.py`. In the copy only:

1. First docstring line:
   `"""Count-only report on one stored book version (general answer-quality G4b)."""`.
2. `NEW_PARSER_VERSION = "parser_v1_pdf_reflow_v5"`.
3. Rename the check key `"only_v4_parser"` to `"only_current_parser"`.
4. In `build_report`, directly after the `terms = one_row(...)` call, add:

   ```python
       layout = one_row(
           connection,
           """
           SELECT
             count(*) FILTER (WHERE strpos(raw_text, %s) > 0),
             count(*) FILTER (WHERE raw_text ~ %s)
           FROM app.document_chunks
           WHERE version_id = %s::uuid AND deleted_at IS NULL
           """,
           ("| --- |", r"\n {4}\S", version_id),
       )
   ```

5. In `counts`, after `"representatives_with_terms": terms[1],` add:

   ```python
           "pipe_table_chunks": layout[0],
           "indented_line_chunks": layout[1],
   ```

6. In `checks`, after `"terms_on_all_representatives": ...,` add:

   ```python
           "pipe_tables_present": layout[0] >= 20,
           "indented_lines_present": layout[1] > 0,
   ```

Never commit this file.

## Step 3 - Baseline before deleting

```powershell
New-Item -ItemType Directory -Force .private-eval/runs/g4-reingest | Out-Null
.venv\Scripts\python.exe .private-eval/g4_version_report.py --version-id d7e3206a-b262-44d7-90bc-b1572d864c35 --write-title-file .private-eval/g4-book-title.txt --out .private-eval/runs/g4-reingest/report-before.json
Copy-Item .private-eval/ingest-ids.json .private-eval/runs/g4-reingest/ingest-ids.before.json
```

Expected: exit 1 with exactly these checks false, because the stored
version is v4: `only_current_parser`, `pipe_tables_present`, and
`indented_lines_present`. `chunks_total` 1005. Any other failed check:
stop and report the JSON (counts only).

## Step 4 - Restart the stack (A8 Step 4)

Run A8 Step 4 exactly. The parser image probe there must now print
`parser_v1_pdf_reflow_v5 3`. Also check the chunking version in the
host worker environment:

```powershell
uv run python -c "from smart_rag_core.ingestion.chunking.limits import CHUNKING_POLICY_VERSION, LINE_STRUCTURED_MAX_TOKENS; print(CHUNKING_POLICY_VERSION, LINE_STRUCTURED_MAX_TOKENS)"
```

Expected: `chunking_v3 536`. On any failure, stop; nothing is deleted yet.

## Step 5 - Soft-delete the current book document (A8 Step 5)

```powershell
Set-Content -Path .private-eval/g4-delete-ids.txt -Value "b56d5774-8810-4ee9-a4d3-f3c93fa90ea7" -Encoding ascii
uv run python scripts/ops/soft_delete_duplicate_documents.py --ids-file .private-eval/g4-delete-ids.txt --keep 00000000-0000-0000-0000-000000000000
```

Pass: `deleted=b56d5774-8810-4ee9-a4d3-f3c93fa90ea7`, `book_hash_current=0`
(report `current_non_deleted` as printed). Anything else: stop.

## Step 6 - Upload and ingest (A8 Step 6)

Run A8 Step 6 with log paths `.private-eval/runs/g4-reingest/ingest.log`
and `.private-eval/runs/g4-reingest/ingest.err.log`. Same pass and stop
conditions as A8 (`terminal_status=graph_ineligible`,
`ids_path_set=true`, new `version_id`).

## Step 7 - Restore the title and verify (A8 Step 7)

```powershell
$new = Get-Content .private-eval/ingest-ids.json -Raw | ConvertFrom-Json
uv run python scripts/ops/rename_one_document_title.py --document-id $new.document_id --title-file .private-eval/g4-book-title.txt
.venv\Scripts\python.exe .private-eval/g4_version_report.py --version-id $new.version_id --out .private-eval/runs/g4-reingest/report-after.json
Invoke-RestMethod http://127.0.0.1:8000/health/ready | ConvertTo-Json -Compress
```

Pass: `renamed_document=<new id>`, `all_checks_pass: true`,
`parser_versions` `{"parser_v1_pdf_reflow_v5": <chunks_total>}`,
`pipe_table_chunks` at least 20, `indented_line_chunks` above the
before value, and `query_ready` true. A failed check: stop and report
the JSON (counts only).

Then update the "Current book" line in `00-rules-and-commands.md` with
the new document id, version id, `parser_v1_pdf_reflow_v5`, and the new
chunk count.

## Step 8 - dev40 run and stop rule

Rebuild the `api` image (00-rules), run the probe, then dev40 with
`$run = "dev40-g4"`, the stage report, and the "Latency p90" command.
Count code and table strict passes for this run and the last kept run:

```powershell
.venv\Scripts\python.exe -c "import json,sys; g={q['id']:q.get('kind') for q in json.load(open('.private-eval/dev40-2026-10-v1.json',encoding='utf-8'))}; [print(r, {k: sum(1 for o in json.load(open(f'.private-eval/runs/{r}/summary.json',encoding='utf-8'))['outcomes'] if g.get(o['question_id'])==k and o['strict_pass']) for k in ('code','table','text')}) for r in sys.argv[1:]]" dev40-g4 <last kept run name>
```

Apply the stop rule at the top (code + table must go up; total must not
drop by more than 3).

## Step 9 - Evidence and commit

Fill `## After G4` in `docs/evaluation/GENERAL_ANSWER_QUALITY_2026-10.md`
(counts only): the parse-before and parse-after lines from G4a, the
report-before and report-after `chunks_total`, `pipe_table_chunks`, and
`indented_line_chunks`, the stage table, strict passes per kind, p90,
and the stop-rule decision. Under `## Approvals recorded` add:
`2026-10-06 - G4b re-ingest pre-approved: "no need for my approval make g4b".`

```powershell
uv run python scripts/check.py --tier docs
git add docs/evaluation/GENERAL_ANSWER_QUALITY_2026-10.md
git commit -m "docs(eval): G4 re-ingest and dev40 results"
git push
gh pr checks --watch --fail-fast
```

(The 00-rules "Current book" edit is a plan file; commit it with the
same command by adding `.cursor/plans/general-answer-quality/00-rules-and-commands.md`.)

## Rollback (stop rule failed)

1. `git revert --no-edit <G4a sha>`, push, wait for green checks.
2. Repeat Steps 3 to 7 with the **new** document id in
   `.private-eval/g4-delete-ids.txt` and the new version id in Step 3.
   With v4 restored, `only_current_parser`, `pipe_tables_present`, and
   `indented_lines_present` fail by design; every other check must pass.
   No new approval is needed (Step 1 covers it).
3. Record `Reverted by stop rule` and the numbers in `## After G4`.
4. Never undelete rows, change `current_version_id`, or edit chunks with
   SQL.

## Done when

- [ ] Step 1 pre-checks passed; `approval.txt` written; the
      pre-approval quote is in the evidence doc `## Approvals recorded`.
- [ ] report-before, re-ingest, title restore, report-after with
      `all_checks_pass: true`; 00-rules "Current book" updated.
- [ ] dev40 ran; per-kind strict passes and stop-rule decision recorded;
      evidence doc committed; PR checks green.

## Commit message

```text
docs(eval): G4 re-ingest and dev40 results
```

## Do not

- Do not stop to ask the user for approval; it was given in advance.
- Do not start Step 3 until all Step 1 pre-checks pass.
- Do not delete or upload any document other than the two named in this
  packet.
- Do not change code in this packet.
- Do not run the holdout.
