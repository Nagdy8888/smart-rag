# A8 - Re-ingest the book with `parser_v1_pdf_reflow_v4` and `navigation_v1`

Read [`00-rules-and-commands.md`](./00-rules-and-commands.md) first.
This packet is operational: it changes stored data, not tracked code. It
ends with one docs-only commit on `fix/answer-loss-repair`.

**Depends on:** A6 and A7 committed, pushed, and green. **Probes:** the
00-rules `api` probe prints `A6 present` and `A7 present`; the parser
image prints `parser_v1_pdf_reflow_v4 3`. **Live run:** yes (11
questions, about 11 minutes, plus the ingest).

Current book: document `95e6c763-24ca-444b-b667-cd075d4f40cd`, version
`e119bf87-1c70-4e10-abb1-5666c4f728c4` (`graph_ineligible`,
`company_visible`, parser `parser_v1_pdf_reflow_v3`, 1,016 chunks).

## Approval gate (do this first; do nothing else until the user answers)

ADR Fix 4 step 4 says "Re-ingest the book as a new version ... Keep the
previous version for rollback." The code cannot add a version to an
existing document:

- `POST /documents/uploads` always inserts a new `app.documents` row
  (`supabase/migrations/20260824140000_remove_mfa_aal2_enforcement_v1.sql`,
  line ~155).
- Finalize refuses bytes that match a visible document with
  `duplicate_content`
  (`apps/backend/src/smart_rag_api/services/upload_finalize.py` lines
  ~130-138).
- No RPC restores a deleted document or version.

Open the plan index `.cursor/plans/answer_loss_repair_9c24e1a0.plan.md`,
decision **D6**. If its **Answer** line says `approved`, the user already
approved the path below on 2026-09-24: do not send the message, write
`D6 approved in the plan index (2026-09-24)` under **Deviations** in your
report, and continue. Otherwise send the user exactly this message, then
stop and wait:

```text
A8 needs approval for a different re-ingest path than the ADR states.
The only pipeline path is: soft-delete the current book document
(95e6c763) with app.delete_visible_document, then upload the same PDF as a
NEW document with scripts/ops/ingest_private_pdf.py. Effects:
- The book gets a new document ID and new chunk IDs; old answer traces stop applying.
- The old version is marked deletion_pending; its chunks stay in the database
  soft-deleted, its BM25 rows are removed, and nothing in the app can make it
  current again. Rollback means reverting A6/A7 and uploading again.
- The book is not searchable from the delete until the new ingest finishes.
- ingest_private_pdf.py creates one new Auth owner user (with TOTP) per run.
- The new document's BM25 title field keeps the upload filename; the title
  rename restores the canonical title for search terms only.
Reply "approved" to proceed, or say what to change.
```

Proceed only on an explicit approval. Record the date as `<RUN_DATE>`
(`$runDate = Get-Date -Format yyyy-MM-dd`).

## Goal

Re-parse and re-chunk the book with the A6 hyphen joins and the A7
navigation exclusion, keep it `graph_ineligible` and `company_visible`,
restore its title, prove the stored counts with a private report, and
rerun the 11-question subset (a01-a10, a38) to report stage-trace counts.

## Read first (confirm each quote exists)

`.private-eval/answer50_stage_trace.py` lines 11-13 and 76-97:

```python
import json
import re
from pathlib import Path
```

```python
def main() -> None:
    """Print one row per question plus stage totals."""

    gold = json.loads(Path(".private-eval/answer50-v1.json").read_text(encoding="utf-8"))
    answers = json.loads(
        Path(".private-eval/answer50-answers.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        Path(".private-eval/answer50-summary.json").read_text(encoding="utf-8")
    )
    outcome = {o["question_id"]: o["outcome"] for o in summary["outcomes"]}
    env = load_env(Path(".env"))
    env.update(load_env(Path(".env.compose")))
    any_id = str(answers["a01"]["stages"]["dense_ids"][0])
    with psycopg.connect(env["OPERATOR_SUPABASE_DB_URL"], connect_timeout=20) as conn:
        conn.execute("SET ROLE postgres")
        row = conn.execute(
            "SELECT document_id::text, version_id::text FROM app.document_chunks WHERE id = %s::uuid",
            (any_id,),
        ).fetchone()
        assert row is not None
        document_id, version_id = row
```

`.private-eval/answer50_checkpoint_dump.py`: imports at lines 10-18
(`import json`, `import sys`, `from pathlib import Path`, ...,
`from latency_probe import connect  # noqa: E402`), `def summary() -> None:`
at line 47, the `print("failure_counts", failure_counts)` line, `def
main(qids: list[str]) -> None:` at line 102, and the `__main__` block at
lines 151-155.

Also read (no edits): `scripts/ops/ingest_private_pdf.py` `main`,
`scripts/ops/soft_delete_duplicate_documents.py`,
`scripts/ops/rename_one_document_title.py`, `scripts/dev.ps1`,
`scripts/stop.ps1`.

## Step 1 - Preflight

```powershell
git status --short
git log --oneline -3
gh pr checks
uv run python -c "from smart_rag_core.ingestion.parser.helpers import LINE_END_HYPHENS; from smart_rag_core.ingestion.parser.limits import PDF_PARSER_VERSION; from smart_rag_core.ingestion.chunking.navigation import NAVIGATION_POLICY_VERSION; print(PDF_PARSER_VERSION, len(LINE_END_HYPHENS), NAVIGATION_POLICY_VERSION)"
New-Item -ItemType Directory -Force .private-eval/runs/a8-reingest | Out-Null
$env:PYTHONIOENCODING = "utf-8"
```

Pass: the two newest commits are the A7 and A6 commits, checks are green,
no tracked file is modified, and the probe prints
`parser_v1_pdf_reflow_v4 3 navigation_v1`. The host worker runs chunking
from this working tree, so it must stay on this commit until Step 7 ends.

## Step 2 - Private scripts (gitignored; never `git add` them)

Save the current default outputs first (the database still has the old
book, so these reproduce the 2026-09-24 baseline):

```powershell
.venv\Scripts\python.exe .private-eval/answer50_stage_trace.py > .private-eval/runs/a8-reingest/trace-default-before-edit.txt
.venv\Scripts\python.exe .private-eval/answer50_checkpoint_dump.py summary > .private-eval/runs/a8-reingest/checkpoint-default-before-edit.txt
```

### 2a. `answer50_stage_trace.py` (exact edits)

Replace the three import lines quoted above with:

```python
import argparse
import json
import re
from pathlib import Path
```

Replace the whole quoted `def main()` block (through
`        document_id, version_id = row`) with:

```python
def main() -> None:
    """Print one row per question plus stage totals.

    Options (defaults reproduce the 2026-09-24 baseline trace): ``--answers``
    and ``--summary`` name a runner output, and gold questions missing from
    ``--answers`` are skipped. ``--version-id`` names the version to trace;
    without it, the version of the first dense id of ``a01`` (or of the first
    answered question) is used.
    """

    cli = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    cli.add_argument("--version-id", default="")
    cli.add_argument(
        "--answers", type=Path, default=Path(".private-eval/answer50-answers.json")
    )
    cli.add_argument(
        "--summary", type=Path, default=Path(".private-eval/answer50-summary.json")
    )
    args = cli.parse_args()
    answers = json.loads(args.answers.read_text(encoding="utf-8"))
    gold = [
        item
        for item in json.loads(
            Path(".private-eval/answer50-v1.json").read_text(encoding="utf-8")
        )
        if item["id"] in answers
    ]
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    outcome = {o["question_id"]: o["outcome"] for o in summary["outcomes"]}
    env = load_env(Path(".env"))
    env.update(load_env(Path(".env.compose")))
    with psycopg.connect(env["OPERATOR_SUPABASE_DB_URL"], connect_timeout=20) as conn:
        conn.execute("SET ROLE postgres")
        if args.version_id:
            row = conn.execute(
                "SELECT document_id::text, id::text FROM app.document_versions"
                " WHERE id = %s::uuid",
                (args.version_id,),
            ).fetchone()
        else:
            first = "a01" if "a01" in answers else gold[0]["id"]
            any_id = str(answers[first]["stages"]["dense_ids"][0])
            row = conn.execute(
                "SELECT document_id::text, version_id::text FROM app.document_chunks WHERE id = %s::uuid",
                (any_id,),
            ).fetchone()
        assert row is not None
        document_id, version_id = row
```

### 2b. `answer50_checkpoint_dump.py` (exact edits)

Replace `import json\nimport sys\n` (lines 10-11) with:

```python
import argparse
import json
import sys
```

Replace the line `from latency_probe import connect  # noqa: E402` with:

```python
from latency_probe import connect  # noqa: E402

DEFAULT_ANSWERS = Path(".private-eval/answer50-answers.json")
```

Replace from `def summary() -> None:` through the line
`    gold = json.loads(Path(".private-eval/answer50-v1.json").read_text(encoding="utf-8"))`
with:

```python
def summary(answers_path: Path = DEFAULT_ANSWERS, version_id: str = "") -> None:
    """Print one row per question: fact in generated text vs released text.

    Args:
        answers_path: Runner answers file. Gold questions missing from it are
            skipped, so a subset run works.
        version_id: When set, also print how many distinct selected evidence
            ids belong to this document version.
    """

    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    gold = [
        item
        for item in json.loads(
            Path(".private-eval/answer50-v1.json").read_text(encoding="utf-8")
        )
        if item["id"] in answers
    ]
```

Replace these four lines (end of the question loop, start of the totals):

```python
                f"status={answers[qid]['status']} failures={failures}"
            )
    print()
    print("generated_text_has_fact", generated_hits)
```

with:

```python
                f"status={answers[qid]['status']} failures={failures}"
            )
        selected = sorted(
            {
                str(chunk_id)
                for item in gold
                for chunk_id in (answers[item["id"]].get("stages") or {}).get(
                    "selected_ids"
                )
                or []
            }
        )
        on_version = None
        if version_id:
            count_row = connection.execute(
                "SELECT count(*) FROM app.document_chunks"
                " WHERE id = ANY(%s::uuid[]) AND version_id = %s::uuid",
                (selected, version_id),
            ).fetchone()
            on_version = count_row[0] if count_row else 0
    print()
    print("generated_text_has_fact", generated_hits)
```

After the line `    print("failure_counts", failure_counts)` add:

```python
    if on_version is not None:
        print(f"selected_ids_on_version={on_version}/{len(selected)}")
```

Replace from `def main(qids: list[str]) -> None:` through
`    serde = JsonPlusSerializer()` (the one inside `main`) with:

```python
def main(qids: list[str], answers_path: Path = DEFAULT_ANSWERS) -> None:
    """Print decoded answer and verification writes.

    Args:
        qids: Question ids to print.
        answers_path: Runner answers file holding each ``conversation_id``.
    """

    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    serde = JsonPlusSerializer()
```

Replace the `if __name__ == "__main__":` block with:

```python
if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    cli.add_argument("targets", nargs="*", help="'summary' or question ids")
    cli.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS)
    cli.add_argument("--version-id", default="")
    args = cli.parse_args()
    if args.targets == ["summary"]:
        summary(args.answers, args.version_id)
    else:
        main(args.targets, args.answers)
```

### 2c. New `.private-eval/a8_version_report.py` (exact code)

```python
"""Count-only report on one stored book version (answer-loss repair A8).

Private, read-only diagnostic. It prints structural counts for one document
version: chunk kinds, parser versions, U+2010 line-split leftovers,
navigation exclusions, embedding, BM25, and search-term completeness, plus a
``checks`` map and ``all_checks_pass``. It never prints chunk text, the
document title, or the database URL.

Example:
    ``.venv/Scripts/python.exe .private-eval/a8_version_report.py
    --version-id <uuid> --out .private-eval/runs/a8-reingest/report-after.json``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from latency_probe import connect  # noqa: E402

NEW_PARSER_VERSION = "parser_v1_pdf_reflow_v4"
SPLIT_PATTERN = "[[:alpha:]]\u2010 [[:alpha:]]"
MAX_SPLIT_CHUNKS = 25
CONTENTS_PAGES = (7, 13)
INDEX_PAGES = (341, 353)
GLOSSARY_PAGES = (337, 340)
STAGES = ("dense_ids", "bm25_ids", "fused_ids", "rerank_pool_ids", "selected_ids")
ACTIVE_JOB_STATES = ("pending", "processing", "failed", "dead_letter")


def private_path(path: Path) -> Path:
    """Resolve an output path and refuse anything outside ``.private-eval``.

    Args:
        path: Path from the command line.

    Returns:
        The resolved path.

    Raises:
        SystemExit: If the path is outside ``.private-eval``.
    """

    resolved = path.resolve()
    if ".private-eval" not in {part.casefold() for part in resolved.parts}:
        raise SystemExit(f"refusing to write outside .private-eval: {path}")
    return resolved


def one_row(connection: Any, sql: str, params: tuple[object, ...]) -> tuple[Any, ...]:
    """Run a query that must return one row.

    Args:
        connection: Open psycopg connection.
        sql: Query text.
        params: Query parameters.

    Returns:
        The row as a tuple.

    Raises:
        SystemExit: If the query returns no row (unknown version id).
    """

    row = connection.execute(sql, params).fetchone()
    if row is None:
        raise SystemExit("version_not_found")
    return tuple(row)


def stage_id_counts(connection: Any, version_id: str, answers_path: Path) -> dict[str, int]:
    """Classify every distinct stage chunk id in a runner answers file.

    Args:
        connection: Open psycopg connection.
        version_id: Version the book ids should belong to.
        answers_path: Runner ``answers.json`` with per-question ``stages``.

    Returns:
        Counts of ids on this version, non-representatives on this version,
        soft-deleted ids, and ids not found. Ids of other live documents are
        the remainder.
    """

    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    ids = sorted(
        {
            str(chunk_id)
            for row in answers.values()
            for stage in STAGES
            for chunk_id in (row.get("stages") or {}).get(stage) or []
        }
    )
    rows = connection.execute(
        """
        SELECT id::text, version_id::text, is_search_representative,
               deleted_at IS NOT NULL
        FROM app.document_chunks
        WHERE id = ANY(%s::uuid[])
        """,
        (ids,),
    ).fetchall()
    found = {row[0]: row[1:] for row in rows}
    return {
        "stage_ids_total": len(ids),
        "stage_ids_on_version": sum(
            1 for f in found.values() if f[0] == version_id and not f[2]
        ),
        "stage_ids_non_representative_on_version": sum(
            1 for f in found.values() if f[0] == version_id and not f[1]
        ),
        "stage_ids_deleted": sum(1 for f in found.values() if f[2]),
        "stage_ids_unknown": len(ids) - len(found),
    }


def build_report(connection: Any, version_id: str) -> dict[str, Any]:
    """Collect count-only facts and pass/fail checks for one version.

    Args:
        connection: Open read-only psycopg connection.
        version_id: Document version UUID.

    Returns:
        JSON-ready counts, ``checks``, and ``all_checks_pass``.
    """

    v = one_row(
        connection,
        """
        SELECT v.document_id::text, v.status::text, v.is_current,
               v.retrieval_eligible, v.graph_eligible,
               v.hybrid_verified_at IS NOT NULL, v.bm25_verified_at IS NOT NULL,
               v.deleted_at IS NULL, d.visibility::text,
               d.current_version_id IS NOT DISTINCT FROM v.id, d.deleted_at IS NULL
        FROM app.document_versions AS v
        JOIN app.documents AS d ON d.id = v.document_id
        WHERE v.id = %s::uuid
        """,
        (version_id,),
    )
    c = one_row(
        connection,
        """
        SELECT
          count(*),
          count(*) FILTER (WHERE jsonb_array_length(
            coalesce(provenance->'child_chunk_ids', '[]'::jsonb)) > 0),
          count(*) FILTER (WHERE is_search_representative),
          count(*) FILTER (WHERE duplicate_of_chunk_id IS NOT NULL),
          count(*) FILTER (
            WHERE provenance->>'search_exclusion_reason' = 'navigation_page'),
          count(*) FILTER (
            WHERE provenance->>'search_exclusion_reason' = 'navigation_page'
              AND jsonb_array_length(
                coalesce(provenance->'child_chunk_ids', '[]'::jsonb)) > 0),
          count(*) FILTER (
            WHERE NOT is_search_representative AND duplicate_of_chunk_id IS NULL
              AND provenance->>'search_exclusion_reason'
                IS DISTINCT FROM 'navigation_page'),
          count(*) FILTER (
            WHERE provenance->>'search_exclusion_reason' = 'navigation_page'
              AND NOT (page_number BETWEEN %s AND %s
                       OR page_number BETWEEN %s AND %s)),
          count(*) FILTER (WHERE page_number BETWEEN %s AND %s),
          count(*) FILTER (
            WHERE page_number BETWEEN %s AND %s AND is_search_representative),
          count(*) FILTER (WHERE regexp_count(raw_text, %s) > 0),
          coalesce(sum(regexp_count(raw_text, %s)), 0),
          count(*) FILTER (WHERE is_search_representative AND embedding IS NULL),
          count(*) FILTER (
            WHERE NOT is_search_representative AND embedding IS NOT NULL)
        FROM app.document_chunks
        WHERE version_id = %s::uuid AND deleted_at IS NULL
        """,
        (
            *CONTENTS_PAGES,
            *INDEX_PAGES,
            *GLOSSARY_PAGES,
            *GLOSSARY_PAGES,
            SPLIT_PATTERN,
            SPLIT_PATTERN,
            version_id,
        ),
    )
    parsers = connection.execute(
        """
        SELECT provenance->>'parser_version', count(*)
        FROM app.document_chunks
        WHERE version_id = %s::uuid AND deleted_at IS NULL
        GROUP BY 1 ORDER BY 1
        """,
        (version_id,),
    ).fetchall()
    ledger = connection.execute(
        """
        SELECT status, input_count FROM app.embedding_operation_ledger
        WHERE version_id = %s::uuid ORDER BY 1, 2
        """,
        (version_id,),
    ).fetchall()
    bm25 = connection.execute(
        """
        SELECT operation::text, status::text, count(*) FROM app.bm25_index_jobs
        WHERE version_id = %s::uuid GROUP BY 1, 2 ORDER BY 1, 2
        """,
        (version_id,),
    ).fetchall()
    jobs = connection.execute(
        """
        SELECT job_kind, status::text, count(*) FROM app.ingestion_jobs
        WHERE version_id = %s::uuid GROUP BY 1, 2 ORDER BY 1, 2
        """,
        (version_id,),
    ).fetchall()
    terms = one_row(
        connection,
        """
        SELECT
          count(*) FILTER (WHERE NOT dc.is_search_representative),
          count(DISTINCT dc.id) FILTER (WHERE dc.is_search_representative)
        FROM app.document_search_terms AS t
        JOIN app.document_chunks AS dc ON dc.id = t.chunk_id
        WHERE dc.version_id = %s::uuid AND dc.deleted_at IS NULL
        """,
        (version_id,),
    )
    total, parents, reps = c[0], c[1], c[2]
    counts: dict[str, Any] = {
        "version_id": version_id,
        "document_id": v[0],
        "status": v[1],
        "visibility": v[8],
        "chunks_total": total,
        "parents": parents,
        "passages": total - parents,
        "representatives": reps,
        "duplicates": c[3],
        "navigation_excluded": c[4],
        "navigation_excluded_parents": c[5],
        "unexplained_exclusions": c[6],
        "navigation_outside_contents_or_index": c[7],
        "glossary_chunks": c[8],
        "glossary_representatives": c[9],
        "hyphen_split_chunks": c[10],
        "hyphen_split_occurrences": int(c[11]),
        "representatives_without_embedding": c[12],
        "excluded_with_embedding": c[13],
        "parser_versions": {str(name): n for name, n in parsers},
        "embedding_ledger": [[status, n] for status, n in ledger],
        "bm25_jobs": [[op, status, n] for op, status, n in bm25],
        "ingestion_jobs": [[kind, status, n] for kind, status, n in jobs],
        "search_terms_on_excluded": terms[0],
        "representatives_with_terms": terms[1],
    }
    checks = {
        "status_graph_ineligible": v[1] == "graph_ineligible",
        "current_and_eligible": bool(v[2] and v[3] and v[7] and v[9] and v[10]),
        "graph_not_eligible": not v[4],
        "hybrid_and_bm25_verified": bool(v[5] and v[6]),
        "company_visible": v[8] == "company_visible",
        "only_v4_parser": counts["parser_versions"] == {NEW_PARSER_VERSION: total},
        "hyphen_splits_near_zero": c[10] <= MAX_SPLIT_CHUNKS,
        "navigation_excluded": c[4] > 0,
        "no_unexplained_exclusions": c[6] == 0,
        "navigation_only_in_contents_or_index": c[7] == 0,
        "glossary_searchable": c[8] > 0 and c[9] == c[8],
        "embeddings_complete": c[12] == 0 and c[13] == 0,
        "ledger_matches_representatives": ["completed", reps]
        in counts["embedding_ledger"],
        "bm25_upsert_completed": any(
            op == "upsert" and status == "completed" for op, status, _ in bm25
        )
        and not any(status in ACTIVE_JOB_STATES for _, status, _ in bm25),
        "no_terms_on_excluded": terms[0] == 0,
        "terms_on_all_representatives": terms[1] == reps,
    }
    counts["checks"] = checks
    counts["all_checks_pass"] = all(checks.values())
    return counts


def main(argv: list[str] | None = None) -> int:
    """Print the report as one JSON object and optionally save it.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 when every check passes, 1 otherwise.

    Side Effects:
        Writes ``--out`` and ``--write-title-file`` (both must be under
        ``.private-eval``). The title is never printed; only its length goes
        to stderr.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version-id", required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--answers", type=Path, default=None)
    parser.add_argument("--write-title-file", type=Path, default=None)
    args = parser.parse_args(argv)
    with connect() as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        result = build_report(connection, args.version_id)
        if args.answers is not None:
            result.update(stage_id_counts(connection, args.version_id, args.answers))
        if args.write_title_file is not None:
            title = one_row(
                connection,
                "SELECT d.title FROM app.documents AS d"
                " JOIN app.document_versions AS v ON v.document_id = d.id"
                " WHERE v.id = %s::uuid",
                (args.version_id,),
            )[0]
            target = private_path(args.write_title_file)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(title), encoding="utf-8")
            print(f"title_chars={len(str(title))}", file=sys.stderr)
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.out is not None:
        target = private_path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    return 0 if result["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

The page ranges are verification constants for this book only; the
detector never sees them. If `.private-eval/gold_subset.py` is missing,
create it from 00-rules.

### 2d. Prove the defaults did not change

```powershell
.venv\Scripts\python.exe .private-eval/answer50_stage_trace.py > .private-eval/runs/a8-reingest/trace-default-after-edit.txt
.venv\Scripts\python.exe .private-eval/answer50_checkpoint_dump.py summary > .private-eval/runs/a8-reingest/checkpoint-default-after-edit.txt
Compare-Object (Get-Content .private-eval/runs/a8-reingest/trace-default-before-edit.txt) (Get-Content .private-eval/runs/a8-reingest/trace-default-after-edit.txt)
Compare-Object (Get-Content .private-eval/runs/a8-reingest/checkpoint-default-before-edit.txt) (Get-Content .private-eval/runs/a8-reingest/checkpoint-default-after-edit.txt)
Select-String -Path .private-eval/runs/a8-reingest/trace-default-after-edit.txt -Pattern '^fact_chunk_in_'
```

Pass: both `Compare-Object` print nothing; totals are dense 50, bm25 26,
fused 48, rerank_pool 44, selected 35.

## Step 3 - Baseline snapshot (before anything is deleted)

```powershell
.venv\Scripts\python.exe .private-eval/a8_version_report.py --version-id e119bf87-1c70-4e10-abb1-5666c4f728c4 --write-title-file .private-eval/a8-book-title.txt --out .private-eval/runs/a8-reingest/report-before.json
.venv\Scripts\python.exe .private-eval/gold_subset.py --gold .private-eval/answer50-v1.json --ids a01,a02,a03,a04,a05,a06,a07,a08,a09,a10,a38 --out .private-eval/runs/a8-reingest/gold.json
.venv\Scripts\python.exe -c "import json,pathlib; ids=[i['id'] for i in json.loads(pathlib.Path('.private-eval/runs/a8-reingest/gold.json').read_text(encoding='utf-8'))]; a=json.loads(pathlib.Path('.private-eval/answer50-answers.json').read_text(encoding='utf-8')); pathlib.Path('.private-eval/runs/a8-reingest/baseline-answers.json').write_text(json.dumps({k: a[k] for k in ids}, ensure_ascii=False), encoding='utf-8'); print('baseline_answers', len(ids))"
.venv\Scripts\python.exe .private-eval/answer50_stage_trace.py --version-id e119bf87-1c70-4e10-abb1-5666c4f728c4 --answers .private-eval/runs/a8-reingest/baseline-answers.json > .private-eval/runs/a8-reingest/trace-before.txt
Select-String -Path .private-eval/runs/a8-reingest/trace-before.txt -Pattern '^(questions|fact_not_in_any_chunk|fact_chunk_in_)'
.venv\Scripts\python.exe .private-eval/answer50_checkpoint_dump.py summary --answers .private-eval/runs/a8-reingest/baseline-answers.json --version-id e119bf87-1c70-4e10-abb1-5666c4f728c4 > .private-eval/runs/a8-reingest/checkpoint-before.txt
Select-String -Path .private-eval/runs/a8-reingest/checkpoint-before.txt -Pattern '^(generated_text_has_fact|released_text_has_fact|selected_ids_on_version)'
.venv\Scripts\python.exe -c "import json,collections; ids=set(json.load(open('.private-eval/runs/a8-reingest/baseline-answers.json',encoding='utf-8'))); o=[x for x in json.load(open('.private-eval/answer50-summary.json',encoding='utf-8'))['outcomes'] if x['question_id'] in ids]; print('outcomes', dict(collections.Counter(x['outcome'] for x in o)), 'strict_pass', sum(bool(x['strict_pass']) for x in o), 'grounded_fact_pass', sum(bool(x['grounded_fact_pass']) for x in o))"
Copy-Item .private-eval/ingest-ids.json .private-eval/runs/a8-reingest/ingest-ids.before.json
```

Pass: the report exits 1 with only `only_v4_parser`,
`hyphen_splits_near_zero`, and `navigation_excluded` false, and shows
`chunks_total` 1016, `hyphen_split_chunks` 719,
`hyphen_split_occurrences` 2732, `glossary_representatives` 7; stderr
shows `title_chars=<n>` (never print the file). `questions=11`,
`baseline_answers 11`; trace totals `questions 11`,
`fact_not_in_any_chunk 0`, dense 11, bm25 5, fused 9, rerank_pool 9,
selected 8; checkpoint `generated_text_has_fact 8`,
`released_text_has_fact 2`, `selected_ids_on_version=101/101`; outcomes
`strict_phrase` 3, `verifier_refusal_after_fusion` 4, `wrong_phrasing` 4,
`strict_pass 3`, `grounded_fact_pass 3`. (These values were measured
read-only while this packet was written.)

## Step 4 - Rebuild images and restart the stack

```powershell
.\scripts\stop.ps1
.\scripts\dev.ps1
Invoke-RestMethod http://127.0.0.1:8000/health/ready | ConvertTo-Json -Compress
docker run --rm --network none smart-rag-parser-sandbox:local python -c "from smart_rag_core.ingestion.parser.helpers import LINE_END_HYPHENS; from smart_rag_core.ingestion.parser.limits import PDF_PARSER_VERSION; print(PDF_PARSER_VERSION, len(LINE_END_HYPHENS))"
Select-String -Path logs/laptop-ingest-worker.log -Pattern '^(laptop_ingest_worker|mock_model_mode|langsmith_export_io|subprocessor_matrix_verified|worker_graph_enabled)='
```

Then run the 00-rules `api` probe. Pass: `"query_ready": true`; the
parser image prints `parser_v1_pdf_reflow_v4 3`; every packet A1-A7
prints `present`; the log shows `laptop_ingest_worker=host`,
`langsmith_export_io=false`, `subprocessor_matrix_verified=true`,
`worker_graph_enabled=false`, and `mock_model_mode=` not `true`/`1`. On
any failure, stop; nothing has been deleted yet.

## Step 5 - Soft-delete the current book document

```powershell
Set-Content -Path .private-eval/a8-delete-ids.txt -Value "95e6c763-24ca-444b-b667-cd075d4f40cd" -Encoding ascii
uv run python scripts/ops/soft_delete_duplicate_documents.py --ids-file .private-eval/a8-delete-ids.txt --keep 00000000-0000-0000-0000-000000000000
```

Pass: `deleted=95e6c763-24ca-444b-b667-cd075d4f40cd`,
`current_non_deleted=3`, `book_hash_current=0`. Anything else: stop and
report the output.

## Step 6 - Upload and ingest

```powershell
$ingest = Start-Process -FilePath "uv" -ArgumentList @("run", "python", "scripts/ops/ingest_private_pdf.py") -RedirectStandardOutput .private-eval/runs/a8-reingest/ingest.log -RedirectStandardError .private-eval/runs/a8-reingest/ingest.err.log -PassThru -WindowStyle Hidden
Get-Content .private-eval/runs/a8-reingest/ingest.log -Tail 3
```

Check the tail every few minutes (use AwaitShell or a fresh shell call,
not `sleep`). The first JSON line must show
`"document_graph_eligible": false`, `"version_graph_eligible": false`,
and a `content_class` that is not `synthetic`. When `$ingest.HasExited`
is true, run `$ingest.ExitCode` and:

```powershell
$new = Get-Content .private-eval/ingest-ids.json -Raw | ConvertFrom-Json
"doc=$($new.document_id) version=$($new.version_id) status=$($new.terminal_status)"
```

Pass: exit code 0, the log ends with `terminal_status=graph_ineligible`
and `ids_path_set=true`, and `$new.version_id` differs from
`e119bf87-...`. If the shell was restarted, `$ingest` is gone: treat
`ids_path_set=true` in the log as exit 0. Re-create `$new` with the two
lines above in every later shell session before Steps 7 and 8.

Stop and report the last 40 log lines (IDs, statuses, finding families,
and counts only) without retrying when:

- the log shows `blocked=`, `unreviewed_detector_family=`,
  `finalize_failed`, `timeout_ingest`, or a status other than
  `graph_ineligible`; or
- `ingest.err.log` holds a traceback.

Do not run the older helpers `review_reflow_findings.py` or
`requeue_reflow_index.py` (they hard-code another version). If a failed
new document exists, the user decides whether to soft-delete it (Step 5
command with its ID) and upload again.

## Step 7 - Restore the title and verify the stored version

```powershell
uv run python scripts/ops/rename_one_document_title.py --document-id $new.document_id --title-file .private-eval/a8-book-title.txt
.venv\Scripts\python.exe .private-eval/a8_version_report.py --version-id $new.version_id --out .private-eval/runs/a8-reingest/report-after.json
Invoke-RestMethod http://127.0.0.1:8000/health/ready | ConvertTo-Json -Compress
```

Pass: `renamed_document=<new document id>`, `after_new_title_matches=1`,
`current_version_id=<new version id>`. The report exits 0 with
`all_checks_pass: true`, `parser_versions` `{"parser_v1_pdf_reflow_v4":
<chunks_total>}`, `hyphen_split_chunks` at most 25 (about 7 are expected:
splits whose right fragment is uppercase stay by design),
`navigation_excluded` between 55 and 80 (68 on the old text),
`navigation_outside_contents_or_index` 0, `unexplained_exclusions` 0,
`glossary_representatives` equal to `glossary_chunks`, and
`query_ready` true. A failed check: stop and report the JSON (counts
only).

## Step 8 - Live subset run and stage trace (live proof)

Use the 00-rules full-run command with `<run-name>` = `a8-reingest` and
`--gold .private-eval/runs/a8-reingest/gold.json`. Then:

```powershell
.venv\Scripts\python.exe .private-eval/answer50_stage_trace.py --version-id $new.version_id --answers .private-eval/runs/a8-reingest/answers.json --summary .private-eval/runs/a8-reingest/summary.json > .private-eval/runs/a8-reingest/trace-after.txt
Select-String -Path .private-eval/runs/a8-reingest/trace-after.txt -Pattern '^(document|leaf_chunks|questions|fact_not_in_any_chunk|fact_chunk_in_)'
.venv\Scripts\python.exe .private-eval/answer50_checkpoint_dump.py summary --answers .private-eval/runs/a8-reingest/answers.json --version-id $new.version_id > .private-eval/runs/a8-reingest/checkpoint-after.txt
Select-String -Path .private-eval/runs/a8-reingest/checkpoint-after.txt -Pattern '^(generated_text_has_fact|released_text_has_fact|killed_after_generation|failure_counts|selected_ids_on_version)'
.venv\Scripts\python.exe .private-eval/a8_version_report.py --version-id $new.version_id --answers .private-eval/runs/a8-reingest/answers.json --out .private-eval/runs/a8-reingest/report-after-run.json | Select-String '"(stage_ids_\w+|all_checks_pass)"'
.venv\Scripts\python.exe -c "import json,collections; o=json.load(open('.private-eval/runs/a8-reingest/summary.json',encoding='utf-8'))['outcomes']; print('outcomes', dict(collections.Counter(x['outcome'] for x in o)), 'strict_pass', sum(bool(x['strict_pass']) for x in o), 'grounded_fact_pass', sum(bool(x['grounded_fact_pass']) for x in o))"
```

Pass: `questions 11`; the trace's `document` line shows the new IDs;
`stage_ids_deleted` 0, `stage_ids_non_representative_on_version` 0, and
`all_checks_pass` true. Stage totals and outcomes are reported, not
gated (the ADR expects a small effect; A9 owns acceptance). If
`fact_chunk_in_selected_ids` falls below the Step 3 value, say so in the
report.

## Step 9 - Docs (exact edits; counts and IDs only)

1. `docs/ingestion/CHUNKING_CONTRACT.md`: insert after the Navigation
   pages section (before `## Heading inventory (Phase 4 consumer)`),
   filling `<...>` from `report-before.json`, `report-after.json`, and
   Step 8 (IDs as the first 8 hex characters):

   ```markdown
   ## Stored book after the answer-loss re-ingest (<RUN_DATE>)

   Counts only (private report `a8_version_report.py`). Document `95e6c763`
   was soft-deleted and the same PDF was uploaded as document
   `<NEW_DOC_8>`, version `<NEW_VER_8>` (`parser_v1_pdf_reflow_v4`,
   `navigation_v1`, `graph_ineligible`).

   | Measure | Before (`e119bf87`) | After (`<NEW_VER_8>`) |
   | --- | ---: | ---: |
   | Chunks (passages / parents) | 1,016 (742 / 274) | <T> (<P> / <PA>) |
   | Search representatives | 1,015 | <R> |
   | Exact duplicates | 1 | <D> |
   | Navigation exclusions (parents) | 0 (0) | <N> (<NP>) |
   | Chunks with a letter, U+2010, space, letter split | 719 | <S> |
   | Split occurrences | 2,732 | <SO> |
   | Glossary chunks searchable (pp. 337-340) | 7 / 7 | <GR> / <GC> |
   | Representatives without an embedding | 0 | <E> |
   | Completed embedding ledger inputs | 1,015 | <L> |

   On the 11-question subset (a01-a10, a38), the fact chunk reached
   dense, BM25, fused, rerank-pool, and selected evidence in <d>, <b>, <f>,
   <r>, and <s> questions, against 11, 5, 9, 9, and 8 before. The
   generated answer held the fact in <g> questions and the released answer
   in <rel>, against 8 and 2 before. Outcomes: <outcome counts>.
   ```

   Set the front matter `last-reviewed:` to `<RUN_DATE>`.

2. `docs/adr/ADR-retrieved-answer-loss-repair.md`. Replace Fix 4 step 4
   (`4. Re-ingest the book as a new version through the normal pipeline. Keep`
   / `   the previous version for rollback.`) with:

   ```markdown
   4. Re-ingest the book through the normal pipeline. The upload API always
      creates a new document and refuses bytes that match a visible one,
      and no RPC restores a deleted document, so the book is soft-deleted
      with `app.delete_visible_document` and uploaded again as a new
      document. The old rows stay soft-deleted but cannot be made current
      through the application.
   ```

   Replace the Rollback bullet
   (`- **Fix 4:** make the previous book version current again. The parser`
   / `  revert affects only new ingests.`) with:

   ```markdown
   - **Fix 4:** revert the A6 and A7 commits, rebuild the parser image,
     restart the worker, soft-delete the re-ingested document, and upload
     the PDF again. Restoring the old soft-deleted rows by SQL is not
     approved. Both reverts affect only new ingests.
   ```

   Under **Approvals recorded**, after the Fix 4 bullet, add:

   ```markdown
   - **Fix 4 re-ingest path (<RUN_DATE>):** soft-delete the book document
     and upload the same PDF as a new document, with a new chunk and
     document ID.
   ```

3. `docs/README.md`: set the date cell of the
   `ingestion/CHUNKING_CONTRACT.md` and
   `adr/ADR-retrieved-answer-loss-repair.md` rows to `<RUN_DATE>`.

```powershell
uv run python scripts/check.py --tier docs
```

## Rollback

- **Before Step 5:** nothing changed; stop the run.
- **Ingest failed after Step 5:** the book is not searchable. Report and
  wait for the user; the fix is to upload again (Step 6), after
  soft-deleting any failed new document with the Step 5 command.
- **Revert A6/A7 in stored data (user approval required):** on a new
  branch from `fix/answer-loss-repair`, run
  `git revert --no-edit <A7 sha> <A6 sha>`, then Steps 4 to 7 with the
  new document's ID in `.private-eval/a8-delete-ids.txt`. The report must
  then show `parser_v1_pdf_reflow_v3` and `navigation_excluded` 0 (its
  exit code is 1 by design).
- Never undelete rows, change `current_version_id`, or edit chunks with
  SQL.

## Done when

- [ ] The user approved the delete-and-re-upload path (quote the reply).
- [ ] Step 2d: default outputs unchanged (both diffs empty; totals 50,
      26, 48, 44, 35).
- [ ] Step 3: `report-before.json` shows 1016 chunks and 719 split
      chunks; the subset baseline totals are 11, 5, 9, 9, 8.
- [ ] Step 4: `query_ready` true; parser image and `api` probes pass;
      worker flags as listed.
- [ ] Step 5: `deleted=95e6c763-...`, `current_non_deleted=3`,
      `book_hash_current=0`.
- [ ] Step 6: `terminal_status=graph_ineligible`, `ids_path_set=true`,
      exit code 0.
- [ ] Step 7: rename lines as listed; `report-after.json` has
      `all_checks_pass: true`.
- [ ] Step 8: 11 questions ran; `stage_ids_deleted` 0 and
      `stage_ids_non_representative_on_version` 0; the stage totals and
      outcomes are in the report.
- [ ] Step 9: docs updated; the `docs` tier exits 0.
- [ ] `git status --short` lists only the three docs as modified tracked
      files; commit pushed; `gh pr checks --watch --fail-fast` exits 0.

## Commit

```text
docs(ingestion): record the book re-ingest with reflow v4 and navigation_v1 (A8)
```

Files to `git add`, one by one:

```text
docs/ingestion/CHUNKING_CONTRACT.md
docs/adr/ADR-retrieved-answer-loss-repair.md
docs/README.md
```

## Do not

- Do not start before the approval, and do not delete any document other
  than `95e6c763-24ca-444b-b667-cd075d4f40cd`.
- Do not run SQL that writes; the report and the diagnostics are
  read-only. Do not undelete or re-point versions.
- Do not run `ingest_private_pdf.py --requeue-hybrid-index`, the older
  `review_reflow_findings.py` or `requeue_reflow_index.py`, or a second
  upload while one is running.
- Do not change tracked code in this packet, and do not switch commits
  while the worker is ingesting.
- Do not print or commit the title file, `.env*`, the database URL,
  chunk text, answer text, or gold phrases; do not `git add` anything
  under `.private-eval/`.
- Do not run the unseen set.
