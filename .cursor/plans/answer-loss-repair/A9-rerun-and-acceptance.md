# A9 - Rerun both sets, adjudicate, and record acceptance

## Goal

Measure the repaired branch against every acceptance target in the ADR.
Rebuild the `api` image, prove that A1 to A8 are in it, then run the
diagnosed answer-only set and the sealed unseen set. Score both with the
same "right" rule the baseline used, run the diagnostics, review every
released claim on the unseen set, and run the freeze tests. Record the
result, pass or fail, in
`docs/evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md`.

This packet changes no product code. It adds private helper scripts
(gitignored) and one evidence doc, and it adds three index/link lines.

## Depends on

- A0 to A8 all committed and pushed on `fix/answer-loss-repair`, and
  `gh pr checks` green on the branch head.
- A0 outputs exist: `.private-eval/unseen50-v1.json`, its sidecar
  `.private-eval/unseen50-v1.sha256`, the helpers
  `.private-eval/unseen50_pages.py`, `.private-eval/unseen50_validate.py`,
  `.private-eval/gold_leak_check.py`, and the baseline run folder
  `.private-eval/runs/a0-unseen-baseline/` (with `summary.json` and
  `answers.json`).

## Read first

- `00-rules-and-commands.md`: all of it (**Docker rebuild**, **Live eval
  commands**, **Git workflow**, **Reporting template**).
- [`docs/adr/ADR-retrieved-answer-loss-repair.md`](../../../docs/adr/ADR-retrieved-answer-loss-repair.md),
  section "Expected effect and acceptance" and section "Links".
- [`docs/evaluation/ANSWER_ONLY_50_2026-09-24.md`](../../../docs/evaluation/ANSWER_ONLY_50_2026-09-24.md):
  the definition of a right answer (first paragraphs) and its **Limits**
  section. The adjudication rules below follow it.
- [`docs/evaluation/ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md`](../../../docs/evaluation/ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md):
  the stage table, the Mermaid waterfall, and the **Reproduce** section.
- [`docs/evaluation/KNOWN_ANSWER_50_REPAIR_EVIDENCE_2026-09-22.md`](../../../docs/evaluation/KNOWN_ANSWER_50_REPAIR_EVIDENCE_2026-09-22.md):
  the shape of an evidence doc (front matter, provenance, commands,
  acceptance table).

## Facts verified for this packet (2026-09-24, read-only)

- Baseline for the diagnosed set (`answer50-v1.json`), reproduced with the
  helper scripts below from the 2026-09-24 files: right 21/50 (strict 19
  plus a14 and a19 in other words), bookkeeping kills 7 (a02, a09, a10,
  a17, a34, a38, a45), rerank completed 14/50, fact chunk in final
  evidence 35/50, scorer deadlines 3 (a31, a32, a37), run-total p90 49.9 s,
  stage survival 50/50/48/44/35/28/21. `a9_metrics.py waterfall` on the
  baseline prints exactly the buckets in the root-cause doc (15, 2, 5, 9,
  19).
- The parser version is stored per chunk in
  `app.document_chunks.provenance->>'parser_version'`.
  `app.document_versions` has no parser column.
- On 2026-09-24 four documents are live: two `text/plain` (`parser_v1`),
  one 3-chunk PDF (`parser_v1_pdf_headings_v2`), and the book
  (`95e6c763-24ca-444b-b667-cd075d4f40cd`, version
  `e119bf87-1c70-4e10-abb1-5666c4f728c4`, `parser_v1_pdf_reflow_v3`). The
  previous reflow re-ingest soft-deleted the book and uploaded it again,
  so the book's document id can change in A8. The version check finds the
  book by its reflow parser family instead of by id.
- `answer50_stage_trace.py` and `answer50_checkpoint_dump.py` (as of
  2026-09-24) read hard-coded `.private-eval/answer50-*.json` paths, and the
  trace finds the version from the first dense id of `a01`. This packet
  assumes A8 added `--version-id` and `--answers`. Step 8 checks that
  before calling them.
- `latency_probe.py stages <answers.json>` prints one
  `<qid> total=<seconds> status=<status> :: ...` line per run. Its
  `TOTAL` line has no p90, so `a9_metrics.py latency` computes it with
  the same index the stage table uses.
- The 00-rules subset recipe (`ConvertTo-Json | Set-Content -Encoding utf8`)
  does not work on Windows PowerShell 5.1: the file gets a UTF-8
  byte-order mark and the runner stops with
  `JSONDecodeError: Unexpected UTF-8 BOM`, and a one-item list becomes a
  bare object. Use `gold_subset.py` (below) instead.
- The only private out-of-scope negative question is `ka-12` in
  `.private-eval/known-answer-smoke-v1.json` (`kind` `negative`).
- The three invented-expansion regression tests exist in
  `tests/unit/test_answer_verifier.py`:
  `test_wrong_mcp_expansion_in_link_is_rejected_despite_mock_verifier`,
  `test_free_prose_mcp_expansion_cannot_stay_verified`,
  `test_verify_node_rejects_ungrounded_mcp_expansion`.
- `tests/unit/test_phase4_freeze.py` pins the holdout freeze and the
  `hybrid_default_v1` digest only. The other pins live in
  `test_answer_verifier.py`, `test_answer_paragraph_citations.py`,
  `test_hybrid_rerank.py`, `test_graph_mapping_hybrid.py`,
  `test_long_document_profile.py`, `test_pdf_hybrid_overlay.py`, and
  `test_prompt_registry.py`. Step 10 runs all of them and adds a byte
  diff of the frozen files against `origin/main` (empty on 2026-09-24).
- Released claims: the last `verification` write of node `verify_answer`
  in `langgraph.checkpoint_writes` (rows where `thread_id` equals the
  conversation id) holds `answer.atomic_links` (the released claims) and
  `answer.citations`. On the baseline, 39 answered questions released 91
  claims. 7 of those claims had lost their citation before release.

## Step 1 - Preconditions

```powershell
git checkout fix/answer-loss-repair
git pull --ff-only
git status --short
git log --oneline -15
gh pr checks
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe .private-eval/unseen50_validate.py --hash-only
Test-Path .private-eval/runs/a0-unseen-baseline/summary.json
Test-Path .private-eval/runs/a0-unseen-baseline/answers.json
```

Required:

- `git status --short` lists nothing. (A0 committed both plans,
  including `.cursor/plans/query-latency-repair/`.) `.private-eval/` is
  gitignored and never shows.
- `git log --oneline -30` shows the A0-A8 commits and the L0-L3 commits
  (L4 only if it ran). The second diff below lists
  `scripts/run_company_ask.py` because L0 added client timing; that is
  expected.
- `gh pr checks` shows every check `pass`. If some are pending, run
  `gh pr checks --watch --fail-fast`. On red, stop; A9 does not fix code.
- `seal_match=yes`. Copy the `sha256=` value; it must equal the hash in
  the A0 report. On `seal_match=no`, stop: the unseen set was changed.
- Both `Test-Path` lines print `True`.

The scoring rule must be the one A0 used. Check that the scorer did not
change after the A0 plan commit:

```powershell
$a0 = git log --format=%H -1 --grep "docs(plan): answer-loss repair ADR"
git diff --stat $a0 HEAD -- packages/core/src/smart_rag_core/evaluation/dual_metric.py
git diff --stat $a0 HEAD -- packages/core/src/smart_rag_core/evaluation/company_ask_regression.py scripts/run_company_ask.py
```

The first diff must be empty. If it is not, stop and ask the user: the
unseen baseline and the A9 run would use different scoring. The second
diff is information for the report only.

The run folders must be new. For each of
`.private-eval/runs/a9-answer50`, `.private-eval/runs/a9-unseen50`, and
`.private-eval/runs/a9-negative`: if the folder exists and its
`head.txt` equals `git rev-parse HEAD`, a previous A9 attempt on the same
commit was interrupted, and the runner may resume there. If it exists
with a different or missing `head.txt`, stop and ask for a new run name.

## Step 2 - Write the four A9 private helpers

Create each file with **exact code**. They live in the gitignored
`.private-eval/`. Then confirm:

```powershell
git check-ignore -v .private-eval/a9_preview.py .private-eval/a9_metrics.py .private-eval/a9_claim_review.py .private-eval/gold_subset.py
```

Each path must print a `.gitignore:99:.private-eval/` line.

### `.private-eval/a9_preview.py` (exact code)

```python
"""Write a private reading sheet for adjudicating one eval run.

Private helper for packet A9 of the answer-loss repair plan. It generalizes
``answer50_preview.py`` to any gold, answers, and summary files. Each
question is labelled:

* ``STRICT_RIGHT``: the scorer's ``strict_pass`` is true.
* ``ADJUDICATE``: not strict, the outcome is ``wrong_phrasing`` or
  ``partial``, and a real answer was released (not a refusal, deadline, or
  error). A human decides whether it states the same fact in other words.
* ``NOT_RIGHT``: everything else (refusals, deadlines, errors, empty).

The sheet holds private question, gold, and answer text, so ``--out`` must
be under ``.private-eval/``. With ``--version-id`` the sheet also shows the
leaf-chunk text of the gold page for every ``ADJUDICATE`` question (read-only
SELECT through ``latency_probe.connect()``). Standard output lists labels and
question ids only.

Example:
    ``.venv/Scripts/python.exe .private-eval/a9_preview.py --gold
    .private-eval/answer50-v1.json --answers .private-eval/runs/a9-answer50/answers.json
    --summary .private-eval/runs/a9-answer50/summary.json
    --out .private-eval/runs/a9-answer50/preview.txt --version-id <uuid>``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ADJUDICABLE_OUTCOMES = frozenset({"wrong_phrasing", "partial"})
NOT_ANSWER_STATUSES = frozenset(
    {
        "insufficient_evidence",
        "refused",
        "deadline_exhausted",
        "error",
        "failed",
        "timeout",
    }
)
REFUSAL_TEXT = "Insufficient authorized evidence."
DEFAULT_ANSWER_CHARS = 2000


def collapse(text: object) -> str:
    """Collapse whitespace in any value.

    Args:
        text: Any value; ``None`` becomes an empty string.

    Returns:
        One-line text.
    """

    return " ".join(str(text or "").split())


def needs_adjudication(outcome: dict[str, object], row: dict[str, object]) -> bool:
    """Decide whether a human must judge this answer.

    Args:
        outcome: The question's row from ``summary.json`` ``outcomes``.
        row: The question's row from ``answers.json``.

    Returns:
        True when the answer is not strict, has an adjudicable outcome, and
        is a released answer rather than a refusal, deadline, or error.
    """

    if outcome.get("strict_pass"):
        return False
    if outcome.get("outcome") not in ADJUDICABLE_OUTCOMES:
        return False
    if str(row.get("status") or "") in NOT_ANSWER_STATUSES:
        return False
    text = collapse(row.get("answer_text"))
    return bool(text) and text.casefold() != REFUSAL_TEXT.casefold()


def label_for(outcome: dict[str, object], row: dict[str, object]) -> str:
    """Return the sheet label for one question.

    Args:
        outcome: The question's summary outcome row.
        row: The question's answers row.

    Returns:
        ``STRICT_RIGHT``, ``ADJUDICATE``, or ``NOT_RIGHT``.
    """

    if outcome.get("strict_pass"):
        return "STRICT_RIGHT"
    return "ADJUDICATE" if needs_adjudication(outcome, row) else "NOT_RIGHT"


def load_run(gold: Path, answers: Path, summary: Path) -> tuple[list[dict], dict, dict]:
    """Load gold items, answers rows, and summary outcomes keyed by id.

    Args:
        gold: Private gold JSON list.
        answers: Runner ``answers.json``.
        summary: Runner ``summary.json``.

    Returns:
        Gold items, answers by question id, and outcomes by question id.

    Raises:
        SystemExit: If a gold id is missing from answers or summary.
    """

    items = json.loads(gold.read_text(encoding="utf-8"))
    rows = json.loads(answers.read_text(encoding="utf-8"))
    outcomes = {
        row["question_id"]: row
        for row in json.loads(summary.read_text(encoding="utf-8"))["outcomes"]
    }
    missing = [
        item["id"]
        for item in items
        if item["id"] not in rows or item["id"] not in outcomes
    ]
    if missing:
        raise SystemExit(
            f"ERROR ids missing from answers or summary: {','.join(missing)}"
        )
    return items, rows, outcomes


def page_texts(version_id: str, pages: set[int]) -> dict[int, list[str]]:
    """Read leaf-chunk text for the given pages of one version.

    Args:
        version_id: Document version UUID.
        pages: Page numbers to read.

    Returns:
        Page number mapped to whitespace-collapsed leaf texts in chunk order.
    """

    from latency_probe import connect

    texts: dict[int, list[str]] = {page: [] for page in pages}
    if not pages:
        return texts
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT page_number, raw_text FROM app.document_chunks
            WHERE version_id = %s::uuid AND deleted_at IS NULL
              AND parent_chunk_id IS NOT NULL AND page_number = ANY(%s)
            ORDER BY page_number, chunk_index
            """,
            (version_id, sorted(pages)),
        ).fetchall()
    for page, text in rows:
        texts[int(page)].append(collapse(text))
    return texts


def main(argv: list[str] | None = None) -> int:
    """Write the sheet and print label counts.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 on success.

    Raises:
        SystemExit: If ``--out`` is outside ``.private-eval`` or ids are
            missing.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--version-id", default="")
    parser.add_argument("--answer-chars", type=int, default=DEFAULT_ANSWER_CHARS)
    args = parser.parse_args(argv)
    if ".private-eval" not in args.out.resolve().parts:
        raise SystemExit(f"refusing to write outside .private-eval: {args.out}")
    items, rows, outcomes = load_run(args.gold, args.answers, args.summary)
    labels = {
        item["id"]: label_for(outcomes[item["id"]], rows[item["id"]]) for item in items
    }
    wanted = {item["page"] for item in items if labels[item["id"]] == "ADJUDICATE"}
    pages = page_texts(args.version_id, wanted) if args.version_id else {}
    lines: list[str] = []
    for item in items:
        qid = item["id"]
        row, outcome = rows[qid], outcomes[qid]
        facts = " | ".join(
            phrase for fact in item["facts"] for phrase in fact["canonical"]
        )
        lines.append(
            f"{qid} page={item['page']} strict={int(bool(outcome['strict_pass']))} "
            f"outcome={outcome['outcome']} status={row.get('status')} label={labels[qid]}"
        )
        lines.append(f"  Q: {item['prompt']}")
        lines.append(f"  FACT: {facts}")
        lines.append(f"  A: {collapse(row.get('answer_text'))[: args.answer_chars]}")
        for index, text in enumerate(pages.get(item["page"], []), 1):
            lines.append(f"  PAGE leaf {index}: {text}")
        lines.append("")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    for name in ("STRICT_RIGHT", "ADJUDICATE", "NOT_RIGHT"):
        ids = [qid for qid, label in labels.items() if label == name]
        print(f"{name.lower()}={len(ids)} ids={','.join(ids) or '-'}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### `.private-eval/a9_metrics.py` (exact code)

````python
"""Compute A9 acceptance metrics from run files and diagnostic outputs.

Private helper for packet A9 of the answer-loss repair plan. Every
subcommand prints counts, tokens, and question ids only, never question,
gold, answer, or book text, so its output may be pasted into the tracked
evidence doc. Database access (``version`` only) is read-only.

Subcommands:
    version: Find the book's current version and check its parser version.
    run: Scorer counts, statuses, deadlines, and rerank completion.
    right: Strict passes plus adjudicated right answers.
    latency: Run-total p90 and deadline count from ``latency_probe`` output.
    killed: Bookkeeping kills from ``answer50_checkpoint_dump.py summary``.
    evidence: Fact-chunk stage counts from ``answer50_stage_trace.py``.
    waterfall: The loss waterfall and its Mermaid source.
    claims: Verdict counts from the released-claim review file.
    negative: Whether out-of-scope negative questions were refused.

Example:
    ``.venv/Scripts/python.exe .private-eval/a9_metrics.py run
    --summary .private-eval/runs/a9-answer50/summary.json
    --answers .private-eval/runs/a9-answer50/answers.json``
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import statistics
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from a9_preview import REFUSAL_TEXT, collapse, load_run, needs_adjudication

PARSER_TARGET = "parser_v1_pdf_reflow_v4"
PARSER_FAMILY = "parser_v1_pdf_reflow"
OLD_VERSION_ID = "e119bf87-1c70-4e10-abb1-5666c4f728c4"
EXPECTED_LIVE_DOCUMENTS = 4
RERANK_COMPLETED = frozenset({"none"})
BOOKKEEPING_CODES = frozenset({"paragraph_index_invalid", "paragraph_unmapped"})
REFUSAL_STATUSES = frozenset({"insufficient_evidence", "refused"})
NON_COMPANY_ORIGINS = frozenset({"web", "general_knowledge", "user_supplied_text"})
ADJUDICATION_VERDICTS = frozenset({"right_other_words", "wrong"})
CLAIM_VERDICTS = frozenset({"supported", "unsupported"})
LATENCY_ROW = re.compile(r"^(\S+) total=([0-9.]+) status=(\S*) ::")
DUMP_ROW = re.compile(
    r"^(\S+) generated_has_fact=(\d) released_has_fact=(\d) status=(\S*) failures=(\[.*\])\s*$"
)
DUMP_KILLED = re.compile(r"^killed_after_generation (\d+) ?(\S*)\s*$")
TRACE_ROW = re.compile(r"^(\S+) p\d+\s.*\bselec=\s*(\S+)")
TRACE_TOTAL = re.compile(
    r"^(questions|fact_chunk_in_\w+|fact_not_in_any_chunk) (\d+) ?(\S*)\s*$"
)


def histogram(values: Iterable[object]) -> str:
    """Render a sorted ``token:count`` histogram.

    Args:
        values: Tokens to count; ``None`` becomes ``missing``.

    Returns:
        Comma-separated histogram, or ``none`` when empty.
    """

    counts = Counter("missing" if value is None else str(value) for value in values)
    return ",".join(f"{key}:{count}" for key, count in sorted(counts.items())) or "none"


def read_output(path: Path) -> list[str]:
    """Read a saved command output, tolerating the BOM ``Out-File`` writes.

    Args:
        path: Text file written with ``Out-File -Encoding utf8``.

    Returns:
        The file's lines.
    """

    return path.read_text(encoding="utf-8-sig").splitlines()


def ids_text(ids: Iterable[str]) -> str:
    """Join question ids for printing.

    Args:
        ids: Question ids.

    Returns:
        Sorted comma-separated ids, or ``-`` when empty.
    """

    return ",".join(sorted(ids)) or "-"


def cmd_version(_: argparse.Namespace) -> int:
    """Check that the book's current version was parsed by the A8 parser.

    Args:
        _: Parsed arguments (unused).

    Returns:
        0 when exactly one live reflow-parsed document exists, all its
        current-version chunks carry ``parser_v1_pdf_reflow_v4``, its
        version differs from the old one, the old version row still exists
        for rollback, and 4 documents are live.
    """

    from latency_probe import connect

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT d.id::text, d.current_version_id::text, v.media_type,
                   coalesce(ch.provenance->>'parser_version', '<none>'), count(ch.id)
            FROM app.documents d
            LEFT JOIN app.document_versions v ON v.id = d.current_version_id
            LEFT JOIN app.document_chunks ch
              ON ch.version_id = d.current_version_id AND ch.deleted_at IS NULL
            WHERE d.deleted_at IS NULL
            GROUP BY 1, 2, 3, 4
            ORDER BY 1, 4
            """
        ).fetchall()
        old = connection.execute(
            "SELECT deleted_at IS NULL FROM app.document_versions WHERE id = %s::uuid",
            (OLD_VERSION_ID,),
        ).fetchone()
    documents: dict[str, tuple[str | None, str | None, dict[str, int]]] = {}
    for document_id, version_id, media_type, parser, count in rows:
        entry = documents.setdefault(document_id, (version_id, media_type, {}))
        entry[2][str(parser)] = int(count)
    for document_id, (version_id, media_type, parsers) in documents.items():
        print(
            f"doc={document_id} version={version_id} media={media_type} "
            f"chunks={sum(parsers.values())} parsers={histogram_from(parsers)}"
        )
    books = [
        (document_id, entry)
        for document_id, entry in documents.items()
        if any(name.startswith(PARSER_FAMILY) for name in entry[2])
    ]
    print(f"live_documents={len(documents)} expected={EXPECTED_LIVE_DOCUMENTS}")
    print(f"reflow_documents={len(books)} expected=1")
    old_state = "missing" if old is None else ("live" if old[0] else "soft_deleted")
    print(f"old_version={OLD_VERSION_ID} row={old_state}")
    if len(books) != 1:
        print("version_check=fail")
        return 1
    document_id, (version_id, _, parsers) = books[0]
    parser_ok = set(parsers) == {PARSER_TARGET}
    new_version = version_id != OLD_VERSION_ID
    print(f"book_document_id={document_id} book_version_id={version_id}")
    print(
        f"parser_ok={'yes' if parser_ok else 'no'} new_version={'yes' if new_version else 'no'}"
    )
    ok = (
        parser_ok
        and new_version
        and old is not None
        and len(documents) == EXPECTED_LIVE_DOCUMENTS
    )
    print(f"version_check={'pass' if ok else 'fail'}")
    return 0 if ok else 1


def histogram_from(counts: dict[str, int]) -> str:
    """Render an existing count mapping as ``key:count`` pairs.

    Args:
        counts: Token to count.

    Returns:
        Comma-separated pairs sorted by key.
    """

    return ",".join(f"{key}:{value}" for key, value in sorted(counts.items())) or "none"


def rerank_completed(stages: dict[str, object]) -> bool:
    """Decide whether rerank finished fully or partially for one question.

    Args:
        stages: The ``stages`` mapping of one answers row.

    Returns:
        True when the fallback is ``none`` and at least one rerank call was
        recorded. A3 keeps ``rerank_fallback="none"`` for a partial ranking
        and marks it with a separate boolean ``rerank_partial``, so partial
        rankings are already counted here.
    """

    calls = stages.get("rerank_call_count")
    return (
        stages.get("rerank_fallback") in RERANK_COMPLETED
        and isinstance(calls, int)
        and calls >= 1
    )


def cmd_run(args: argparse.Namespace) -> int:
    """Print scorer counts, statuses, deadlines, and rerank completion.

    Args:
        args: Parsed arguments with ``summary`` and ``answers``.

    Returns:
        0 on success, 1 when the files disagree on question ids.
    """

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    answers = json.loads(args.answers.read_text(encoding="utf-8"))
    block, outcomes = summary["summary"], summary["outcomes"]
    keys = ("questions", "strict_pass", "grounded_fact_pass", "deadline_failures")
    print(" ".join(f"{key}={block.get(key)}" for key in keys))
    print("outcomes=" + histogram(row["outcome"] for row in outcomes))
    print("statuses=" + histogram(row.get("status") for row in answers.values()))
    stages = {qid: row.get("stages") or {} for qid, row in answers.items()}
    print(
        "rerank_fallback="
        + histogram(stage.get("rerank_fallback") for stage in stages.values())
    )
    done = [qid for qid, stage in stages.items() if rerank_completed(stage)]
    print(f"rerank_completed={len(done)} of={len(stages)}")
    print(f"rerank_not_completed_ids={ids_text(set(stages) - set(done))}")
    deadline_ids = {
        row["question_id"] for row in outcomes if row.get("deadline_failure")
    }
    deadline_ids |= {
        qid for qid, row in answers.items() if row.get("status") == "deadline_exhausted"
    }
    print(f"deadlines={len(deadline_ids)} ids={ids_text(deadline_ids)}")
    if {row["question_id"] for row in outcomes} != set(answers):
        print("ERROR summary and answers disagree on question ids")
        return 1
    return 0


def right_ids(args: argparse.Namespace) -> tuple[set[str], set[str], list[str], int]:
    """Combine strict passes with the human adjudication file.

    Args:
        args: Parsed arguments with ``gold``, ``answers``, ``summary``, and
            ``adjudication``.

    Returns:
        Strict ids, right-in-other-words ids, problem messages, and the
        question count.
    """

    items, rows, outcomes = load_run(args.gold, args.answers, args.summary)
    needed = {
        item["id"]
        for item in items
        if needs_adjudication(outcomes[item["id"]], rows[item["id"]])
    }
    strict = {item["id"] for item in items if outcomes[item["id"]].get("strict_pass")}
    decisions: dict[str, dict[str, str]] = {}
    if args.adjudication.is_file():
        decisions = json.loads(args.adjudication.read_text(encoding="utf-8"))
    problems: list[str] = []
    missing = needed - set(decisions)
    extra = set(decisions) - needed
    if missing:
        problems.append(f"adjudication missing ids {ids_text(missing)}")
    if extra:
        problems.append(
            f"adjudication has ids that need no adjudication {ids_text(extra)}"
        )
    for qid, decision in decisions.items():
        if decision.get("verdict") not in ADJUDICATION_VERDICTS:
            problems.append(f"{qid} verdict must be right_other_words or wrong")
        if not str(decision.get("reason") or "").strip():
            problems.append(f"{qid} reason is empty")
    other = {
        qid
        for qid, decision in decisions.items()
        if qid in needed and decision.get("verdict") == "right_other_words"
    }
    return strict, other, problems, len(items)


def cmd_right(args: argparse.Namespace) -> int:
    """Print strict, adjudicated, and total right counts.

    Args:
        args: Parsed arguments (see :func:`right_ids`).

    Returns:
        0 when the adjudication file covers exactly the needed ids with
        valid verdicts, else 1.
    """

    strict, other, problems, total = right_ids(args)
    for problem in problems:
        print(f"ERROR {problem}")
    right = strict | other
    print(
        f"strict_right={len(strict)} right_other_words={len(other)} "
        f"right_total={len(right)} questions={total}"
    )
    print(f"right_other_words_ids={ids_text(other)}")
    return 1 if problems else 0


def cmd_latency(args: argparse.Namespace) -> int:
    """Compute run-total statistics from saved ``latency_probe`` output.

    The p90 uses the same index as ``latency_probe``'s stage table:
    ``sorted_values[min(n - 1, int(0.9 * n))]``.

    Args:
        args: Parsed arguments with ``probe_output`` and ``expected``.

    Returns:
        0 when the run count equals ``--expected``, else 1.
    """

    rows = []
    for line in read_output(args.probe_output):
        match = LATENCY_ROW.match(line)
        if match:
            rows.append((match.group(1), float(match.group(2)), match.group(3)))
    if not rows:
        print("ERROR no 'total=' rows found")
        return 1
    values = sorted(total for _, total, _ in rows)
    p90 = values[min(len(values) - 1, int(0.9 * len(values)))]
    print(
        f"runs={len(values)} mean={statistics.mean(values):.1f} "
        f"median={statistics.median(values):.1f} p90={p90:.1f} max={values[-1]:.1f}"
    )
    deadline = [qid for qid, _, status in rows if status == "deadline_exhausted"]
    slow = [qid for qid, total, _ in rows if total > args.limit_seconds]
    print(f"deadline_status={len(deadline)} ids={ids_text(deadline)}")
    print(f"over_{args.limit_seconds:g}s={len(slow)} ids={ids_text(slow)}")
    print(f"p90_target={'pass' if p90 <= args.limit_seconds else 'fail'}")
    if len(values) != args.expected:
        print(f"ERROR runs={len(values)} but expected={args.expected}")
        return 1
    return 0


def parse_dump(path: Path) -> tuple[dict[str, tuple[bool, bool, list[str]]], list[str]]:
    """Parse ``answer50_checkpoint_dump.py summary`` output.

    Args:
        path: Saved output file.

    Returns:
        Per-question ``(generated_has_fact, released_has_fact, failures)``
        and the ``killed_after_generation`` ids.

    Raises:
        SystemExit: If no row or no killed line is found.
    """

    rows: dict[str, tuple[bool, bool, list[str]]] = {}
    killed: list[str] | None = None
    for line in read_output(path):
        match = DUMP_ROW.match(line)
        if match:
            failures = [str(code) for code in ast.literal_eval(match.group(5))]
            rows[match.group(1)] = (
                match.group(2) == "1",
                match.group(3) == "1",
                failures,
            )
            continue
        match = DUMP_KILLED.match(line)
        if match:
            killed = [qid for qid in match.group(2).split(",") if qid]
    if not rows or killed is None:
        raise SystemExit(f"ERROR could not parse checkpoint dump output {path}")
    return rows, killed


def strict_ids(summary: Path) -> set[str]:
    """Return the question ids the scorer marked ``strict_pass``.

    Args:
        summary: Runner ``summary.json``.

    Returns:
        Strict-pass question ids.
    """

    outcomes = json.loads(summary.read_text(encoding="utf-8"))["outcomes"]
    return {row["question_id"] for row in outcomes if row.get("strict_pass")}


def cmd_killed(args: argparse.Namespace) -> int:
    """Report answers removed after generation and the bookkeeping kills.

    The dump matches facts after lowercasing only, while the scorer also
    applies HTML unescape and NFKC. A question the scorer passed was not
    removed, so strict passes are taken out of the killed list.

    Args:
        args: Parsed arguments with ``dump_output`` and ``summary``.

    Returns:
        0 after printing (the target is read from ``bookkeeping_target``).
    """

    rows, killed = parse_dump(args.dump_output)
    strict = strict_ids(args.summary)
    generated = sum(1 for value in rows.values() if value[0])
    released = sum(1 for value in rows.values() if value[1])
    removed = [qid for qid in killed if qid not in strict]
    bookkeeping = [qid for qid in removed if BOOKKEEPING_CODES & set(rows[qid][2])]
    print(
        f"rows={len(rows)} generated_has_fact={generated} released_has_fact={released}"
    )
    print(f"killed_after_generation_raw={len(killed)} ids={ids_text(killed)}")
    print(f"killed_but_strict_pass={ids_text(set(killed) & strict)}")
    print(f"killed_after_generation={len(removed)} ids={ids_text(removed)}")
    for qid in sorted(removed):
        print(f"killed id={qid} failures={','.join(rows[qid][2]) or '-'}")
    print(f"bookkeeping_kills={len(bookkeeping)} ids={ids_text(bookkeeping)}")
    print(f"bookkeeping_target={'pass' if not bookkeeping else 'fail'}")
    return 0


def parse_trace(path: Path) -> tuple[dict[str, bool], dict[str, tuple[int, str]]]:
    """Parse ``answer50_stage_trace.py`` output.

    Args:
        path: Saved output file.

    Returns:
        Per-question "fact chunk in selected evidence" flags and the total
        lines as ``name -> (count, ids)``.

    Raises:
        SystemExit: If no question row is found.
    """

    selected: dict[str, bool] = {}
    totals: dict[str, tuple[int, str]] = {}
    for line in read_output(path):
        match = TRACE_ROW.match(line)
        if match:
            selected[match.group(1)] = match.group(2) != "-"
            continue
        match = TRACE_TOTAL.match(line)
        if match:
            totals[match.group(1)] = (int(match.group(2)), match.group(3))
    if not selected:
        raise SystemExit(f"ERROR could not parse stage trace output {path}")
    return selected, totals


def cmd_evidence(args: argparse.Namespace) -> int:
    """Print fact-chunk counts per retrieval stage.

    Args:
        args: Parsed arguments with ``trace_output`` and ``target``.

    Returns:
        0 after printing.
    """

    selected, totals = parse_trace(args.trace_output)
    for name, (count, ids) in totals.items():
        print(f"{name}={count}" + (f" ids={ids}" if ids else ""))
    final = sum(1 for value in selected.values() if value)
    print(f"fact_chunk_in_final_evidence={final} of={len(selected)}")
    print(f"evidence_target={'pass' if final >= args.target else 'fail'}")
    return 0


def cmd_waterfall(args: argparse.Namespace) -> int:
    """Print the loss waterfall and its Mermaid source.

    Buckets, first match wins: fact chunk not in final evidence; deadline;
    generated answer lacks the fact; released answer lost it; released
    with the fact. A strict pass counts as generated and released with the
    fact even when the dump's simpler matching missed it.

    Args:
        args: Parsed arguments with run files, ``adjudication``,
            ``trace_output``, and ``dump_output``.

    Returns:
        0 on success, 1 when inputs disagree or adjudication is invalid.
    """

    strict, other, problems, total = right_ids(args)
    if problems:
        for problem in problems:
            print(f"ERROR {problem}")
        return 1
    right = strict | other
    items, rows, outcomes = load_run(args.gold, args.answers, args.summary)
    selected, totals = parse_trace(args.trace_output)
    dump, _ = parse_dump(args.dump_output)
    missing = [
        item["id"]
        for item in items
        if item["id"] not in selected or item["id"] not in dump
    ]
    if missing:
        print(f"ERROR ids missing from trace or dump output: {ids_text(missing)}")
        return 1
    order = ("evidence_no", "deadline", "different_fact", "removed", "kept")
    buckets: dict[str, list[str]] = {name: [] for name in order}
    for item in items:
        qid = item["id"]
        deadline = (
            outcomes[qid].get("deadline_failure")
            or rows[qid].get("status") == "deadline_exhausted"
        )
        generated, released, _ = dump[qid]
        generated = generated or qid in strict
        released = released or qid in strict
        if not selected[qid]:
            buckets["evidence_no"].append(qid)
        elif deadline:
            buckets["deadline"].append(qid)
        elif not generated:
            buckets["different_fact"].append(qid)
        elif not released:
            buckets["removed"].append(qid)
        else:
            buckets["kept"].append(qid)
    counts = {name: len(ids) for name, ids in buckets.items()}
    hits = {
        name: len([qid for qid in ids if qid in right]) for name, ids in buckets.items()
    }
    for name in order:
        print(
            f"bucket={name} total={counts[name]} right={hits[name]} "
            f"wrong={counts[name] - hits[name]} ids={ids_text(buckets[name])}"
        )
    in_evidence = total - counts["evidence_no"]
    generated_in_time = in_evidence - counts["deadline"]
    states_fact = generated_in_time - counts["different_fact"]
    stored = total - totals.get("fact_not_in_any_chunk", (0, ""))[0]
    survival = [
        ("fact_in_stored_chunk", stored),
        ("fact_chunk_in_dense", totals.get("fact_chunk_in_dense_ids", (0, ""))[0]),
        ("fact_chunk_in_fused", totals.get("fact_chunk_in_fused_ids", (0, ""))[0]),
        (
            "fact_chunk_in_rerank_pool",
            totals.get("fact_chunk_in_rerank_pool_ids", (0, ""))[0],
        ),
        ("fact_chunk_in_final_evidence", in_evidence),
        ("generated_answer_states_fact", states_fact),
        ("right", len(right)),
    ]
    print("stage_survival " + " ".join(f"{name}={count}" for name, count in survival))

    def split(name: str) -> str:
        """Render the wrong/right split of one bucket for a Mermaid label."""

        return f"{counts[name] - hits[name]} wrong, {hits[name]} right"

    print("```mermaid")
    print("flowchart TD")
    print(
        f'  allNode["{total} facts, diagnosed set"] --> evidenceQ{{"Fact chunk in final evidence?"}}'
    )
    print(
        f'  evidenceQ -->|"no: {counts["evidence_no"]}"| rankLoss["Ranking loss: {split("evidence_no")}"]'
    )
    print(
        f'  evidenceQ -->|"yes: {in_evidence}"| generatedQ{{"Answer generated before deadline?"}}'
    )
    print(
        f'  generatedQ -->|"no: {counts["deadline"]}"| deadlineLoss["Deadline: {split("deadline")}"]'
    )
    print(
        f'  generatedQ -->|"yes: {generated_in_time}"| statesQ{{"Generated answer states the fact?"}}'
    )
    print(
        f'  statesQ -->|"no: {counts["different_fact"]}"| genLoss["Different fact: {split("different_fact")}"]'
    )
    print(
        f'  statesQ -->|"yes: {states_fact}"| releaseQ{{"Released answer keeps it?"}}'
    )
    print(
        f'  releaseQ -->|"no: {counts["removed"]}"| releaseLoss["Removed after generation: {split("removed")}"]'
    )
    print(
        f'  releaseQ -->|"yes: {counts["kept"]}"| rightNode["Released with the fact: {split("kept")}"]'
    )
    print("```")
    return 0


def cmd_claims(args: argparse.Namespace) -> int:
    """Count verdicts in the released-claim review file.

    Args:
        args: Parsed arguments with ``review``.

    Returns:
        0 when every claim has a valid verdict and a note for each
        ``unsupported`` verdict, else 1.
    """

    review: dict[str, dict[str, str]] = json.loads(
        args.review.read_text(encoding="utf-8")
    )
    verdicts = Counter(str(entry.get("verdict")) for entry in review.values())
    markers = Counter(str(entry.get("marker")) for entry in review.values())
    invalid = [
        key
        for key, entry in review.items()
        if entry.get("verdict") not in CLAIM_VERDICTS
    ]
    unsupported = [
        key for key, entry in review.items() if entry.get("verdict") == "unsupported"
    ]
    silent = [
        key for key in unsupported if not str(review[key].get("note") or "").strip()
    ]
    questions = {key.split(":", 1)[0] for key in review}
    print(f"claims={len(review)} questions_with_claims={len(questions)}")
    print("verdicts=" + histogram_from(dict(verdicts)))
    print("markers=" + histogram_from(dict(markers)))
    print(f"unsupported={len(unsupported)} keys={','.join(sorted(unsupported)) or '-'}")
    if invalid:
        print(f"ERROR claims without a supported/unsupported verdict: {len(invalid)}")
    if silent:
        print(f"ERROR unsupported claims without a note: {','.join(sorted(silent))}")
    print(f"claims_target={'pass' if not unsupported and not invalid else 'fail'}")
    return 1 if invalid or silent else 0


def cmd_negative(args: argparse.Namespace) -> int:
    """Check that every negative question in a run was refused.

    Args:
        args: Parsed arguments with ``answers``.

    Returns:
        0 after printing (the target is read from ``negative_target``).
    """

    answers = json.loads(args.answers.read_text(encoding="utf-8"))
    refused_all = bool(answers)
    for qid, row in sorted(answers.items()):
        status = str(row.get("status") or "")
        origin = str(row.get("origin") or "")
        refusal_text = (
            collapse(row.get("answer_text")).casefold() == REFUSAL_TEXT.casefold()
        )
        refused = status in REFUSAL_STATUSES and origin not in NON_COMPANY_ORIGINS
        refused_all = refused_all and refused
        print(
            f"negative id={qid} status={status} origin={origin or '-'} "
            f"refusal_text={'yes' if refusal_text else 'no'} result={'refused' if refused else 'not_refused'}"
        )
    print(f"negative_target={'pass' if refused_all else 'fail'}")
    return 0


def add_run_files(command: argparse.ArgumentParser, *, gold: bool) -> None:
    """Add the run-file options shared by several subcommands.

    Args:
        command: Subcommand parser.
        gold: Whether ``--gold`` and ``--adjudication`` are required too.
    """

    command.add_argument("--summary", type=Path, required=True)
    command.add_argument("--answers", type=Path, required=True)
    if gold:
        command.add_argument("--gold", type=Path, required=True)
        command.add_argument("--adjudication", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Parser with the nine subcommands.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version").set_defaults(handler=cmd_version)
    run = sub.add_parser("run")
    add_run_files(run, gold=False)
    run.set_defaults(handler=cmd_run)
    right = sub.add_parser("right")
    add_run_files(right, gold=True)
    right.set_defaults(handler=cmd_right)
    latency = sub.add_parser("latency")
    latency.add_argument("--probe-output", type=Path, required=True)
    latency.add_argument("--expected", type=int, default=50)
    latency.add_argument("--limit-seconds", type=float, default=45.0)
    latency.set_defaults(handler=cmd_latency)
    killed = sub.add_parser("killed")
    killed.add_argument("--dump-output", type=Path, required=True)
    killed.add_argument("--summary", type=Path, required=True)
    killed.set_defaults(handler=cmd_killed)
    evidence = sub.add_parser("evidence")
    evidence.add_argument("--trace-output", type=Path, required=True)
    evidence.add_argument("--target", type=int, default=43)
    evidence.set_defaults(handler=cmd_evidence)
    waterfall = sub.add_parser("waterfall")
    add_run_files(waterfall, gold=True)
    waterfall.add_argument("--trace-output", type=Path, required=True)
    waterfall.add_argument("--dump-output", type=Path, required=True)
    waterfall.set_defaults(handler=cmd_waterfall)
    claims = sub.add_parser("claims")
    claims.add_argument("--review", type=Path, required=True)
    claims.set_defaults(handler=cmd_claims)
    negative = sub.add_parser("negative")
    negative.add_argument("--answers", type=Path, required=True)
    negative.set_defaults(handler=cmd_negative)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        Process exit code.
    """

    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
````

### `.private-eval/a9_claim_review.py` (exact code)

```python
"""Build the private released-claim review sheet for one eval run.

Private helper for packet A9 of the answer-loss repair plan. For every
question in an answers file it reads the LangGraph checkpoint writes of that
conversation (``langgraph.checkpoint_writes`` rows whose ``thread_id`` equals
the conversation id) and decodes each blob with
``JsonPlusSerializer().loads_typed((type, bytes(blob)))``. The last
``verification`` write from the ``verify_answer`` node holds the released
answer; its ``atomic_links`` are the released claims and its ``citations``
the released spans. Each claim is listed with every cited span, whether the
span occurs in the cited chunk's stored text, and the text around it. A
claim with no released citation shows the spans ``generate_answer`` gave
that link, marked ``CITATION_DROPPED_BEFORE_RELEASE``; a claim with neither
is marked ``NO_CITATION``. A released composed conclusion is listed as its
own claim. Database access is read-only.

Outputs (both private and under ``.private-eval/``):
    ``--out``: the reading sheet (holds answer and book text).
    ``--review``: a skeleton JSON with one ``"UNREVIEWED"`` verdict per
        claim; the script never overwrites an existing review file.

Example:
    ``.venv/Scripts/python.exe .private-eval/a9_claim_review.py
    --answers .private-eval/runs/a9-unseen50/answers.json
    --out .private-eval/runs/a9-unseen50/claim-sheet.txt
    --review .private-eval/runs/a9-unseen50/claim-review.json``
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import unicodedata
from pathlib import Path

import psycopg
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from latency_probe import connect

CONTEXT_CHARS = 250
FALLBACK_CHUNK_CHARS = 600


def collapse(text: object) -> str:
    """Collapse whitespace in any value.

    Args:
        text: Any value; ``None`` becomes an empty string.

    Returns:
        One-line text.
    """

    return " ".join(str(text or "").split())


def normalize(text: object) -> str:
    """Normalize text like the scorer (HTML unescape, NFKC, casefold).

    Args:
        text: Any value.

    Returns:
        Whitespace-collapsed normalized text.
    """

    folded = unicodedata.normalize("NFKC", html.unescape(str(text or ""))).casefold()
    return " ".join(folded.split())


def require_private(path: Path) -> Path:
    """Refuse any output path outside a ``.private-eval`` directory.

    Args:
        path: Candidate output path.

    Returns:
        The same path.

    Raises:
        SystemExit: If no path component is ``.private-eval``.
    """

    if ".private-eval" not in path.resolve().parts:
        raise SystemExit(f"refusing to write outside .private-eval: {path}")
    return path


def node_writes(
    connection: psycopg.Connection, serde: JsonPlusSerializer, thread_id: str
) -> list[tuple[str, str, dict]]:
    """Decode the ``answer`` and ``verification`` writes of one conversation.

    Args:
        connection: Operator connection from ``latency_probe.connect()``.
        serde: LangGraph serializer.
        thread_id: Conversation id used as the LangGraph thread id.

    Returns:
        ``(node, channel, value)`` in write order, dict values only.
    """

    rows = connection.execute(
        """
        SELECT task_path, channel, type, blob
        FROM langgraph.checkpoint_writes
        WHERE thread_id = %s AND channel IN ('answer', 'verification')
        ORDER BY checkpoint_id, task_id, idx
        """,
        (thread_id,),
    ).fetchall()
    writes: list[tuple[str, str, dict]] = []
    for task_path, channel, kind, blob in rows:
        if blob is None:
            continue
        value = serde.loads_typed((kind, bytes(blob)))
        if isinstance(value, dict):
            writes.append((str(task_path).split(",")[-1].strip(), str(channel), value))
    return writes


def last_write(
    writes: list[tuple[str, str, dict]], node: str, channel: str
) -> dict | None:
    """Return the last write of one node on one channel.

    Args:
        writes: Output of :func:`node_writes`.
        node: LangGraph node name.
        channel: State channel name.

    Returns:
        The last matching value, or ``None``.
    """

    found = None
    for write_node, write_channel, value in writes:
        if write_node == node and write_channel == channel:
            found = value
    return found


def chunk_texts(connection: psycopg.Connection, chunk_ids: set[str]) -> dict[str, str]:
    """Load stored text for cited chunks.

    Args:
        connection: Operator connection.
        chunk_ids: Cited chunk UUIDs.

    Returns:
        Chunk id mapped to whitespace-collapsed ``raw_text``.
    """

    if not chunk_ids:
        return {}
    rows = connection.execute(
        "SELECT id::text, raw_text FROM app.document_chunks WHERE id = ANY(%s::uuid[])",
        (sorted(chunk_ids),),
    ).fetchall()
    return {chunk_id: collapse(text) for chunk_id, text in rows}


def context(chunk: str, span: str) -> tuple[bool, str]:
    """Check a span against its chunk and cut the text around it.

    Args:
        chunk: Whitespace-collapsed chunk text.
        span: Cited span.

    Returns:
        Whether the normalized span occurs in the normalized chunk, and up
        to 250 characters either side of the span (or the chunk head when
        the span is not found verbatim).
    """

    present = bool(span) and normalize(span) in normalize(chunk)
    at = chunk.casefold().find(collapse(span).casefold()) if span else -1
    if at < 0:
        return present, chunk[:FALLBACK_CHUNK_CHARS]
    start = max(0, at - CONTEXT_CHARS)
    end = min(len(chunk), at + len(collapse(span)) + CONTEXT_CHARS)
    return present, chunk[start:end]


def citations_by_link(payload: dict | None) -> dict[str, list[dict]]:
    """Group a payload's passage and table citations by atomic link id.

    Args:
        payload: An ``AnswerPayload`` dict, or ``None``.

    Returns:
        Link id mapped to its citation dicts.
    """

    grouped: dict[str, list[dict]] = {}
    if not payload:
        return grouped
    for citation in list(payload.get("citations") or []) + list(
        payload.get("table_citations") or []
    ):
        grouped.setdefault(str(citation.get("atomic_link_id")), []).append(citation)
    return grouped


def review_question(
    connection: psycopg.Connection, serde: JsonPlusSerializer, qid: str, row: dict
) -> tuple[list[str], dict[str, dict[str, str]]]:
    """Render one question's released claims and their review entries.

    Args:
        connection: Operator connection.
        serde: LangGraph serializer.
        qid: Question id.
        row: The question's ``answers.json`` row.

    Returns:
        Sheet lines and ``claim_key -> review entry`` for this question.
    """

    writes = node_writes(connection, serde, str(row.get("conversation_id") or ""))
    verification = last_write(writes, "verify_answer", "verification")
    generated = last_write(writes, "generate_answer", "answer")
    if verification is None:
        return [
            f"===== {qid} status={row.get('status')} released_claims=0 (no verify_answer write)",
            "",
        ], {}
    released = verification.get("answer") or {}
    links = list(released.get("atomic_links") or [])
    conclusion = released.get("composed_conclusion")
    kept = citations_by_link(released)
    early = citations_by_link(generated)
    wanted = {
        str(item.get("chunk_id"))
        for group in (kept, early)
        for items in group.values()
        for item in items
        if item.get("chunk_id")
    }
    texts = chunk_texts(connection, wanted)
    lines = [
        f"===== {qid} status={row.get('status')} verification={verification.get('status')} "
        f"released_claims={len(links) + (1 if conclusion else 0)}",
        f"  ANSWER: {collapse(row.get('answer_text'))}",
    ]
    entries: dict[str, dict[str, str]] = {}
    for link in links:
        link_id = str(link.get("link_id"))
        cites = kept.get(link_id, [])
        marker = "CITED"
        if not cites and early.get(link_id):
            cites, marker = early[link_id], "CITATION_DROPPED_BEFORE_RELEASE"
        elif not cites:
            marker = "NO_CITATION"
        key = f"{qid}:{link_id}"
        entries[key] = {"verdict": "UNREVIEWED", "marker": marker, "note": ""}
        lines.append(
            f"  --- claim {key} kind={link.get('kind')} marker={marker} citations={len(cites)}"
        )
        lines.append(f"      CLAIM: {collapse(link.get('claim'))}")
        for cite in cites:
            chunk_id = str(cite.get("chunk_id") or "")
            span = collapse(cite.get("span"))
            if chunk_id:
                present, around = context(texts.get(chunk_id, ""), span)
                lines.append(
                    f"      CITE chunk={chunk_id} span_in_chunk={'yes' if present else 'no'}"
                )
                lines.append(f"        SPAN: {span}")
                lines.append(f"        CONTEXT: {around}")
            else:
                lines.append(
                    f"      CITE table={cite.get('table_id')} span_in_chunk=n/a"
                )
                lines.append(f"        SPAN: {span}")
    if isinstance(conclusion, dict):
        key = f"{qid}:conclusion"
        entries[key] = {"verdict": "UNREVIEWED", "marker": "CONCLUSION", "note": ""}
        joined = ",".join(str(link_id) for link_id in conclusion.get("link_ids") or [])
        lines.append(f"  --- claim {key} kind=inference links={joined or '-'}")
        lines.append(f"      CLAIM: {collapse(conclusion.get('text'))}")
    lines.append("")
    return lines, entries


def main(argv: list[str] | None = None) -> int:
    """Write the sheet and the skeleton review file.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 on success, 1 when the review file already exists.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    args = parser.parse_args(argv)
    out, review = require_private(args.out), require_private(args.review)
    if review.exists():
        print(f"ERROR {review} exists; it holds verdicts and is never overwritten")
        return 1
    answers = json.loads(args.answers.read_text(encoding="utf-8"))
    serde = JsonPlusSerializer()
    lines: list[str] = []
    entries: dict[str, dict[str, str]] = {}
    with connect() as connection:
        for qid in sorted(answers):
            block, found = review_question(connection, serde, qid, answers[qid])
            lines.extend(block)
            entries.update(found)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    review.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    markers: dict[str, int] = {}
    for entry in entries.values():
        markers[entry["marker"]] = markers.get(entry["marker"], 0) + 1
    questions = {key.split(":", 1)[0] for key in entries}
    print(
        f"claims={len(entries)} questions_with_claims={len(questions)} markers={markers}"
    )
    print(f"wrote {out}")
    print(f"wrote {review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### `.private-eval/gold_subset.py` (exact code)

```python
"""Write a filtered copy of a private gold file for a subset run.

Private helper for packet A9 of the answer-loss repair plan. It replaces
the PowerShell ``ConvertTo-Json | Set-Content -Encoding utf8`` recipe, which
on Windows PowerShell 5.1 writes a UTF-8 byte-order mark (the runner's JSON
loader rejects it) and turns a one-item list into a bare object. This script
writes a JSON array in UTF-8 without a BOM and keeps the input item order.

Example:
    ``.venv/Scripts/python.exe .private-eval/gold_subset.py
    --gold .private-eval/known-answer-smoke-v1.json --ids ka-12
    --out .private-eval/runs/a9-negative/gold.json``
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Filter the gold file by id and write the subset.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 on success, 1 when an id is unknown.

    Raises:
        SystemExit: If ``--out`` is outside ``.private-eval``.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--ids", required=True, help="comma-separated question ids")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if ".private-eval" not in args.out.resolve().parts:
        raise SystemExit(f"refusing to write outside .private-eval: {args.out}")
    wanted = [part.strip() for part in args.ids.split(",") if part.strip()]
    items = json.loads(args.gold.read_text(encoding="utf-8"))
    known = {item["id"] for item in items}
    unknown = [qid for qid in wanted if qid not in known]
    if unknown:
        print(f"ERROR unknown ids: {','.join(unknown)}")
        return 1
    subset = [item for item in items if item["id"] in set(wanted)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(subset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out} questions={len(subset)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Step 3 - Rebuild the image, probe, and check the book version

1. Rebuild and check health exactly as 00-rules **Docker rebuild before
   any live run** says. `health/ready` must contain `"query_ready": true`.
2. Run the 00-rules probe one-liner unchanged. All seven lines must print
   `present`. A `ModuleNotFoundError` or any `MISSING` means a packet is
   not in the image: stop and report.
3. Record the image and commit:

   ```powershell
   git rev-parse --short HEAD
   docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml images api
   ```

4. A8 has no probe. Check the book's parser version read-only:

   ```powershell
   $env:PYTHONIOENCODING = "utf-8"
   .venv\Scripts\python.exe .private-eval/a9_metrics.py version
   ```

   It must end with `version_check=pass`. That means exactly one live
   document has reflow-parsed chunks, every chunk of its current version
   has `parser_v1_pdf_reflow_v4`, that version is not `e119bf87-...`, the
   old version row still exists (`row=live` or `row=soft_deleted`), and 4
   documents are live. Copy `book_document_id=` and `book_version_id=`,
   then set the variable the later steps use (a new shell needs it set
   again):

   ```powershell
   $newVersion = "<the book_version_id value>"
   ```

   On `version_check=fail`, stop and report the whole output.

## Step 4 - Run the diagnosed set

```powershell
New-Item -ItemType Directory -Force .private-eval/runs/a9-answer50 | Out-Null
git rev-parse HEAD | Set-Content -Encoding ascii .private-eval/runs/a9-answer50/head.txt
uv run python scripts/run_company_ask.py `
  --gold .private-eval/answer50-v1.json `
  --out .private-eval/runs/a9-answer50/summary.json `
  --credentials .private-eval/eval-credentials.json `
  --progress .private-eval/runs/a9-answer50/progress.json `
  --answers-out .private-eval/runs/a9-answer50/answers.json `
  --stage-export .private-eval/runs/a9-answer50/stages.json `
  --verbose
.venv\Scripts\python.exe .private-eval/a9_metrics.py run --summary .private-eval/runs/a9-answer50/summary.json --answers .private-eval/runs/a9-answer50/answers.json
```

About 50 minutes. Give the runner a timeout of at least 75 minutes, or
run it in the background and read
`.private-eval/runs/a9-answer50/progress.json` every 10 minutes. If it
stops early, run the same command again (it resumes). The last console
line starts `questions=50 strict_pass=`. If `a9_metrics.py run` prints
`rerank_fallback=missing:50`, the stage export changed shape; stop and
report.

## Step 5 - Run the unseen set

The unseen answers may be read from this step on. Nothing learned from
them may change code, prompts, or gold.

```powershell
.venv\Scripts\python.exe .private-eval/unseen50_validate.py --hash-only
New-Item -ItemType Directory -Force .private-eval/runs/a9-unseen50 | Out-Null
git rev-parse HEAD | Set-Content -Encoding ascii .private-eval/runs/a9-unseen50/head.txt
uv run python scripts/run_company_ask.py `
  --gold .private-eval/unseen50-v1.json `
  --out .private-eval/runs/a9-unseen50/summary.json `
  --credentials .private-eval/eval-credentials.json `
  --progress .private-eval/runs/a9-unseen50/progress.json `
  --answers-out .private-eval/runs/a9-unseen50/answers.json `
  --stage-export .private-eval/runs/a9-unseen50/stages.json `
  --verbose
.venv\Scripts\python.exe .private-eval/a9_metrics.py run --summary .private-eval/runs/a9-unseen50/summary.json --answers .private-eval/runs/a9-unseen50/answers.json
.venv\Scripts\python.exe .private-eval/unseen50_validate.py --version-id $newVersion
```

`--hash-only` must print `seal_match=yes` before the run. The last
command is information only. It checks whether each unseen fact is still
on its page in the re-ingested version. Record `valid=` and every
`FAIL u<nn>:<code>` line in the report. Do not change anything because of
it.

## Step 6 - Run the negative question

```powershell
.venv\Scripts\python.exe .private-eval/gold_subset.py --gold .private-eval/known-answer-smoke-v1.json --ids ka-12 --out .private-eval/runs/a9-negative/gold.json
git rev-parse HEAD | Set-Content -Encoding ascii .private-eval/runs/a9-negative/head.txt
uv run python scripts/run_company_ask.py `
  --gold .private-eval/runs/a9-negative/gold.json `
  --out .private-eval/runs/a9-negative/summary.json `
  --credentials .private-eval/eval-credentials.json `
  --progress .private-eval/runs/a9-negative/progress.json `
  --answers-out .private-eval/runs/a9-negative/answers.json `
  --stage-export .private-eval/runs/a9-negative/stages.json `
  --verbose
.venv\Scripts\python.exe .private-eval/a9_metrics.py negative --answers .private-eval/runs/a9-negative/answers.json
```

`gold_subset.py` must print `questions=1`. The target passes when the
last line is `negative_target=pass`: status `insufficient_evidence` or
`refused`, and no web or general-knowledge origin. `status=error` is not
a refusal.

## Step 7 - Adjudicate the three runs

Write one reading sheet per run. The A0 baseline ran on the old book
version, so its sheet uses the old version id:

```powershell
.venv\Scripts\python.exe .private-eval/a9_preview.py --gold .private-eval/answer50-v1.json --answers .private-eval/runs/a9-answer50/answers.json --summary .private-eval/runs/a9-answer50/summary.json --out .private-eval/runs/a9-answer50/preview.txt --version-id $newVersion
.venv\Scripts\python.exe .private-eval/a9_preview.py --gold .private-eval/unseen50-v1.json --answers .private-eval/runs/a9-unseen50/answers.json --summary .private-eval/runs/a9-unseen50/summary.json --out .private-eval/runs/a9-unseen50/preview.txt --version-id $newVersion
.venv\Scripts\python.exe .private-eval/a9_preview.py --gold .private-eval/unseen50-v1.json --answers .private-eval/runs/a0-unseen-baseline/answers.json --summary .private-eval/runs/a0-unseen-baseline/summary.json --out .private-eval/runs/a0-unseen-baseline/preview.txt --version-id e119bf87-1c70-4e10-abb1-5666c4f728c4
```

Each prints `strict_right=`, `adjudicate=`, `not_right=` with ids. If
the A0 sheet has no `PAGE leaf` lines under its `ADJUDICATE` rows (the
old version's chunks were deleted), rerun that command with
`--version-id $newVersion`.

Open each `preview.txt` with your file-read tool. Judge only the
`label=ADJUDICATE` rows, using these rules. They follow how
`ANSWER_ONLY_50_2026-09-24.md` counted its two extra right answers.

1. `STRICT_RIGHT` is right. `NOT_RIGHT` (refusal, deadline, error, empty)
   is never right; do not adjudicate it.
2. Read the question, the `FACT`, the answer `A`, and the `PAGE leaf`
   lines. The page decides, not outside knowledge.
3. **Right in other words** only when the answer states the same fact the
   gold phrase names, as the page states it, in different wording: a
   synonym, another inflection, reordered words, a spelled-out
   abbreviation, digits versus number words, or hyphen versus space. A
   short fact also counts when its key words appear in the sentence that
   answers the question.
4. **Wrong** when the answer names a different fact, even a nearby one on
   the same topic; hedges between candidates; gives the fact only as one
   item of a list without saying it answers the question; contradicts
   the page on the asked point; or only says the evidence does not
   answer.
5. When unsure, mark it wrong.

Write the verdicts to `adjudication.json` in the same run folder, one
entry per `ADJUDICATE` id and no other ids:

```json
{
  "u07": {"verdict": "right_other_words", "reason": "states the same term as the page with a synonym"},
  "u12": {"verdict": "wrong", "reason": "names a different component from the same section"}
}
```

`verdict` is `right_other_words` or `wrong`. `reason` is one private line.
It stays in `.private-eval/`; never copy it into a tracked file. Write the
file with your file-write tool (UTF-8, no BOM), not with PowerShell
redirection. Then count:

```powershell
.venv\Scripts\python.exe .private-eval/a9_metrics.py right --gold .private-eval/answer50-v1.json --summary .private-eval/runs/a9-answer50/summary.json --answers .private-eval/runs/a9-answer50/answers.json --adjudication .private-eval/runs/a9-answer50/adjudication.json
.venv\Scripts\python.exe .private-eval/a9_metrics.py right --gold .private-eval/unseen50-v1.json --summary .private-eval/runs/a9-unseen50/summary.json --answers .private-eval/runs/a9-unseen50/answers.json --adjudication .private-eval/runs/a9-unseen50/adjudication.json
.venv\Scripts\python.exe .private-eval/a9_metrics.py right --gold .private-eval/unseen50-v1.json --summary .private-eval/runs/a0-unseen-baseline/summary.json --answers .private-eval/runs/a0-unseen-baseline/answers.json --adjudication .private-eval/runs/a0-unseen-baseline/adjudication.json
```

Each must exit 0 with no `ERROR` line. `right_total=` is the "right"
count. If a run has `adjudicate=0`, no `adjudication.json` is needed.

## Step 8 - Diagnostics on the diagnosed set

First confirm that A8 gave the two diagnostic scripts the flags this step
uses:

```powershell
Select-String -Path .private-eval/answer50_stage_trace.py -SimpleMatch -Pattern "--version-id","--answers","--summary","--gold"
Select-String -Path .private-eval/answer50_checkpoint_dump.py -SimpleMatch -Pattern "--version-id","--answers","--summary","--gold"
```

- `answer50_stage_trace.py` must contain both `--version-id` and
  `--answers`. `answer50_checkpoint_dump.py` must contain `--answers`. If
  either is missing, stop and report; do not edit A8's scripts.
- Add `--version-id $newVersion` to the checkpoint dump only if its
  source contains `--version-id`. Add
  `--summary .private-eval/runs/a9-answer50/summary.json` and
  `--gold .private-eval/answer50-v1.json` to a script only if its source
  contains that flag. Without `--summary`, the trace's outcome column
  comes from the 2026-09-24 baseline; `a9_metrics.py` does not read that
  column.

Run them. The base invocations follow; add the optional flags per the rule
above:

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = ".private-eval"
$run = ".private-eval/runs/a9-answer50"
.venv\Scripts\python.exe .private-eval/answer50_stage_trace.py --version-id $newVersion --answers "$run/answers.json" | Out-File -Encoding utf8 "$run/trace.txt"
.venv\Scripts\python.exe .private-eval/answer50_checkpoint_dump.py summary --answers "$run/answers.json" | Out-File -Encoding utf8 "$run/dump.txt"
.venv\Scripts\python.exe .private-eval/latency_probe.py stages "$run/answers.json" | Out-File -Encoding utf8 "$run/latency.txt"
.venv\Scripts\python.exe .private-eval/latency_probe.py stages .private-eval/runs/a9-unseen50/answers.json | Out-File -Encoding utf8 .private-eval/runs/a9-unseen50/latency.txt
```

Each script must exit 0. An exit code of 2 is an argparse usage error: the
flag order or name differs from A8's. Stop and report the usage text. The
first line of `trace.txt` must name `version $newVersion`.

Then compute:

```powershell
.venv\Scripts\python.exe .private-eval/a9_metrics.py killed --dump-output "$run/dump.txt" --summary "$run/summary.json"
.venv\Scripts\python.exe .private-eval/a9_metrics.py evidence --trace-output "$run/trace.txt"
.venv\Scripts\python.exe .private-eval/a9_metrics.py latency --probe-output "$run/latency.txt"
.venv\Scripts\python.exe .private-eval/a9_metrics.py latency --probe-output .private-eval/runs/a9-unseen50/latency.txt
.venv\Scripts\python.exe .private-eval/a9_metrics.py waterfall --gold .private-eval/answer50-v1.json --summary "$run/summary.json" --answers "$run/answers.json" --adjudication "$run/adjudication.json" --trace-output "$run/trace.txt" --dump-output "$run/dump.txt"
```

The `waterfall` output ends with a complete `mermaid` block; you paste it
into the evidence doc unchanged. `latency` exits 1 if a run is missing from
`app.run_events` (`runs=` below 50). Report that as a measurement gap; do
not rerun questions to fill it.

## Step 8b - Latency report from the latency packets (report only)

The combined plan also ran latency packets L0-L4 (L0 added
`scripts/eval_latency_report.py` and `scripts/probe_latency_image.py`).
These numbers are reported, not gated; the gated latency targets are the
ADR rows in Step 11 (no deadlines, p90 at most 45 s).

1. Probe the latency packets on the same image as Step 3:

   ```powershell
   Get-Content scripts/probe_latency_image.py -Raw | docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml exec -T api python -
   ```

   Required: `L0` to `L3` print `present`; `L4` prints `present` only if
   L4 was committed (it is conditional); `L5` prints `present` because A3
   ships `rerank_v2`; `L6` and `L7` print `MISSING` (not in this plan).
   `rerank_prompt_version=rerank_v2`. Anything else: stop and report.
2. Build the report for both runs:

   ```powershell
   uv run python scripts/eval_latency_report.py report --answers .private-eval/runs/a9-answer50/answers.json --stages .private-eval/runs/a9-answer50/stages.json --label a9-answer50 --out .private-eval/runs/a9-answer50/latency-report.json
   uv run python scripts/eval_latency_report.py report --answers .private-eval/runs/a9-unseen50/answers.json --stages .private-eval/runs/a9-unseen50/stages.json --label a9-unseen50 --out .private-eval/runs/a9-unseen50/latency-report.json
   ```

3. In the Step 12 evidence doc, add a section `## Latency (report only)`
   directly after the acceptance table. Paste the printed
   `server_total_s`, `wall_seconds`, and `deadline_exhausted` lines of
   both reports in a `text` block, and one sentence: "L6 (pooled query
   connections) and L7 (shorter answers) were not part of this plan."

## Step 9 - Safety review

1. Invented-expansion regression, verifier, and release tests:

   ```powershell
   uv run python -m pytest "tests/unit/test_answer_verifier.py::test_wrong_mcp_expansion_in_link_is_rejected_despite_mock_verifier" "tests/unit/test_answer_verifier.py::test_free_prose_mcp_expansion_cannot_stay_verified" "tests/unit/test_answer_verifier.py::test_verify_node_rejects_ungrounded_mcp_expansion" -q
   uv run python -m pytest tests/unit/test_answer_verifier.py tests/unit/test_answer_citations_persist.py -q
   ```

   The first command must report `3 passed`. If pytest says a test is not
   found, an earlier packet removed or renamed it, which 00-rules rule 5
   forbids: stop and report.

2. Released-claim review on the unseen set:

   ```powershell
   .venv\Scripts\python.exe .private-eval/a9_claim_review.py --answers .private-eval/runs/a9-unseen50/answers.json --out .private-eval/runs/a9-unseen50/claim-sheet.txt --review .private-eval/runs/a9-unseen50/claim-review.json
   ```

   Sanity check: `questions_with_claims` must equal the number of unseen
   answers whose status is not `insufficient_evidence`, `refused`,
   `deadline_exhausted`, `error`, `failed`, or `timeout` (read `statuses=`
   from Step 5). On the baseline those numbers were 39 and 39. If they
   differ, or `claims=0` while answers were released, the checkpoint shape
   changed: stop and report.

   Open `claim-sheet.txt` and `claim-review.json`. For every entry, set
   `verdict` to `supported` or `unsupported` and fill `note` (required for
   `unsupported`, one private line):

   - `supported`: every part of the claim is stated by, or follows directly
     from, its cited `SPAN` (use `CONTEXT` only to read the span in place).
   - `unsupported`: any part of the claim is missing from the span or
     contradicts it; or `span_in_chunk=no`; or the marker is `NO_CITATION`.
   - `CITATION_DROPPED_BEFORE_RELEASE`: judge it against the spans shown
     (the generator's citations for that claim). The user saw the claim
     without that citation, so the evidence doc reports how many there
     were.
   - `CONCLUSION`: `supported` only if it follows from the released claims'
     spans without adding a new fact.

   Then count:

   ```powershell
   .venv\Scripts\python.exe .private-eval/a9_metrics.py claims --review .private-eval/runs/a9-unseen50/claim-review.json
   ```

   It must exit 0. The target passes on `claims_target=pass`.
3. The negative question is Step 6.

## Step 10 - Freeze

```powershell
uv run python -m pytest tests/unit/test_phase4_freeze.py -q
uv run python -m pytest tests/unit/test_answer_verifier.py tests/unit/test_answer_paragraph_citations.py tests/unit/test_hybrid_rerank.py tests/unit/test_graph_mapping_hybrid.py tests/unit/test_long_document_profile.py tests/unit/test_pdf_hybrid_overlay.py tests/unit/test_prompt_registry.py -q
git fetch origin main
git diff --exit-code --stat origin/main -- apps/agents/src/smart_rag_agents/prompts/answer_v1.md apps/agents/src/smart_rag_agents/prompts/answer_v2.md apps/agents/src/smart_rag_agents/prompts/answer_v3.md apps/agents/src/smart_rag_agents/prompts/verifier_v1.md apps/agents/src/smart_rag_agents/prompts/verifier_v2.md apps/agents/src/smart_rag_agents/prompts/rerank_v1.md packages/core/src/smart_rag_core/retrieval/frozen/hybrid_default_v1.json packages/core/src/smart_rag_core/retrieval/frozen/hybrid_long_document_v1.json packages/core/src/smart_rag_core/retrieval/frozen/hybrid_long_document_v2.json
```

All three exit 0, and the `git diff` prints nothing. The freeze row
passes only when all three pass.

## Step 11 - Fill the acceptance table

Targets are the ADR text, approved 2026-09-24. The ADR places the
deadline and p90 targets under **Rerun of this set**, so they apply to the
diagnosed set. Report the unseen values as information.

| Row | Target (ADR) | Set | Source | Pass when |
| --- | --- | --- | --- | --- |
| 1 | At least 40 of 50 right | unseen | `right` on `a9-unseen50` | `right_total` >= 40 |
| 2 | At least 40 of 50 right | diagnosed | `right` on `a9-answer50` | `right_total` >= 40 |
| 3 | No generated right answer is removed by bookkeeping | diagnosed | `killed` | `bookkeeping_kills=0` |
| 4 | Rerank completes, fully or partially, on at least 45 of 50 | diagnosed | `run` on `a9-answer50` | `rerank_completed` >= 45 |
| 5 | The fact chunk reaches final evidence on at least 43 of 50 | diagnosed | `evidence` | `fact_chunk_in_final_evidence` >= 43 |
| 6 | No deadlines | diagnosed | `run` `deadlines=` and `latency` `deadline_status=` | both 0 |
| 7 | The p90 run total is at most 45 s | diagnosed | `latency` on `a9-answer50` | `p90` <= 45.0 |
| 8 | The invented-expansion regression from the live-RAG ADR still refuses | tests | Step 9.1 first command | `3 passed` |
| 9 | Verifier and release tests still pass | tests | Step 9.1 second command | exit 0 |
| 10 | A manual review of every released claim on the unseen set finds none unsupported by its cited span | unseen | `claims` | `claims_target=pass` |
| 11 | Out-of-scope negative questions still refuse | negative | `negative` | `negative_target=pass` |
| 12 | The existing freeze tests prove the v1 and v2 profile digests and the `answer_v1`-`answer_v3`, `verifier_v2`, and `rerank_v1` bytes are unchanged | freeze | Step 10 | all three exit 0 |

## Step 12 - Write the evidence doc

Create `docs/evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md` from this
template. Replace every `<...>` with a measured value, and keep it under
300 lines. It may contain counts, question ids, chunk-free tokens, and
hashes. It must not contain questions, gold phrases, answer text,
adjudication reasons, claim text, or page text.

````markdown
---
title: Answer-loss repair evidence (A9)
owner: engineering-lead
status: draft
last-reviewed: <YYYY-MM-DD of this run>
audience: engineering, reviewers
---

# Answer-loss repair evidence (2026-09)

Decision record:
[ADR-retrieved-answer-loss-repair.md](../adr/ADR-retrieved-answer-loss-repair.md).
Diagnosis this repair targets:
[ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md](./ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md).
Baseline score:
[ANSWER_ONLY_50_2026-09-24.md](./ANSWER_ONLY_50_2026-09-24.md).

This record holds counts and question IDs only. Questions, gold phrases,
answers, and book text stay in the gitignored `.private-eval/` folder.

## Verdict

**<Pass or Fail>.** <One or two sentences: unseen right <U>/50, diagnosed
right <D>/50, and the names of any failed rows.>

## Provenance

| Pin | Value |
| --- | --- |
| Branch | `fix/answer-loss-repair` |
| Commit measured | `<short sha from Step 3>` |
| `api` image | `<IMAGE ID>`, created `<CREATED>` |
| Probe | A1 to A7 `present` |
| Health | `query_ready: true` |
| Book | document `<book_document_id>`, version `<book_version_id>`, `parser_v1_pdf_reflow_v4` |
| Previous book version | `e119bf87-1c70-4e10-abb1-5666c4f728c4`, row `<live or soft_deleted>` |
| Diagnosed set | `answer50-v1.json`, 50 questions, diagnosed 2026-09-24 |
| Unseen set | `unseen50-v1.json`, 50 questions, sealed in A0, SHA-256 `<hash>` |
| Scorer | `dual_metric.py` unchanged since the A0 commit |

## Scoring

A question is right when the scorer's strict pass is true, or when a
reviewer read the answer against the gold page and it states the same fact
in other words. A refusal or a deadline is never right. A nearby topic
that names a different fact is wrong. The same rules scored the unseen
baseline from A0 and both A9 runs.

## Acceptance

| Target (ADR, approved 2026-09-24) | Set | Baseline | A9 | Pass |
| --- | --- | ---: | ---: | --- |
| At least 40 of 50 right | unseen | <A0 right>/50 | <U>/50 | <yes or no> |
| At least 40 of 50 right | diagnosed | 21/50 | <D>/50 | <yes or no> |
| No generated right answer removed by bookkeeping | diagnosed | 7 | <n> | <yes or no> |
| Rerank completes, fully or partially, on at least 45 of 50 | diagnosed | 14/50 | <n>/50 | <yes or no> |
| Fact chunk reaches final evidence on at least 43 of 50 | diagnosed | 35/50 | <n>/50 | <yes or no> |
| No deadlines | diagnosed | 3 | <n> | <yes or no> |
| p90 run total at most 45 s | diagnosed | 49.9 s | <x> s | <yes or no> |
| Invented-expansion regression still refuses | tests | pass | <3 passed or fail> | <yes or no> |
| Verifier and release tests still pass | tests | pass | <pass or fail> | <yes or no> |
| No released unseen claim unsupported by its cited span | unseen | not reviewed | <u> of <c> claims unsupported | <yes or no> |
| Out-of-scope negative question refuses (`ka-12`) | negative | not measured | <status> | <yes or no> |
| Frozen profile digests and prompt bytes unchanged | freeze | pass | <pass or fail> | <yes or no> |

Diagnosed-set baselines come from the root-cause doc and were recomputed
with the same scripts. The baseline bookkeeping kills are a02, a09, a10,
a17, a34, a38, and a45.

## Comparison with the baselines

| Set | Run | Strict | Right in other words | Right | Deadlines |
| --- | --- | ---: | ---: | ---: | ---: |
| Diagnosed | 2026-09-24 baseline | 19 | 2 | 21 | 3 |
| Diagnosed | A9 | <s> | <o> | <r> | <d> |
| Unseen | A0 baseline, before any fix | <s> | <o> | <r> | <d> |
| Unseen | A9 | <s> | <o> | <r> | <d> |

Right in other words: diagnosed <ids or none>; unseen <ids or none>.
Unseen-set information without a target: rerank completed <n>/50, p90
run total <x> s, deadlines <n>. Unseen facts still on their page in the
re-ingested version: <valid=yes, or the failing ids and codes>.

## Loss waterfall (diagnosed set)

<paste the mermaid block printed by a9_metrics.py waterfall, unchanged>

<One sentence per bucket naming its question ids, from the bucket= lines.>

## Stage survival (diagnosed set)

| Stage | 2026-09-24 | A9 |
| --- | ---: | ---: |
| Stored chunk text holds the fact | 50 | <n> |
| Dense list | 50 | <n> |
| Fused list | 48 | <n> |
| Rerank pool | 44 | <n> |
| Final evidence | 35 | <n> |
| Generated answer states the fact | 28 | <n> |
| Right | 21 | <n> |

## Safety review

- Invented-expansion regression: the three MCP expansion tests in
  `tests/unit/test_answer_verifier.py` <passed or failed>.
- Verifier and release tests: `test_answer_verifier.py` and
  `test_answer_citations_persist.py` <passed or failed>.
- Released-claim review on the unseen set: <c> claims on <q> answered
  questions. Markers: <markers= line>. Unsupported: <u> <keys or none>.
  <k> claims reached the user after their citation was dropped before
  release; they were judged against the generator's spans.
- Out-of-scope negative `ka-12`: status `<status>`, origin `<origin>`.

## Freeze

| Check | Result |
| --- | --- |
| `tests/unit/test_phase4_freeze.py` | <n passed> |
| Prompt and profile pin tests (7 files) | <n passed> |
| Frozen prompt and profile bytes versus `origin/main` | <no diff> |

## Commands

| Command | Exit |
| --- | ---: |
| Docker rebuild and `health/ready` | 0 |
| 00-rules probe | 0 |
| `a9_metrics.py version` | <0> |
| `run_company_ask.py` diagnosed set | <0> |
| `run_company_ask.py` unseen set | <0> |
| `run_company_ask.py` negative `ka-12` | <0> |
| `answer50_stage_trace.py` | <0> |
| `answer50_checkpoint_dump.py summary` | <0> |
| `latency_probe.py stages` (both runs) | <0> |
| Safety tests | <0> |
| Freeze tests and byte diff | <0> |
| `scripts/check.py --tier docs` | <0> |

## Limits

- Right-in-other-words verdicts and the released-claim review are manual
  readings against the book page; one reviewer made them.
- One run per set. Model output varies between runs, so a count can move
  by a few questions on a rerun.
- The stage trace matches the gold phrase with a simple normalizer. A
  fact written differently in the new parse can be missed.
- The run total is the time from the first to the last `app.run_events`
  row of each run.
- The diagnosed set shaped the fixes, so only the unseen set shows how
  well they generalize.

## Reproduce

Requires `OPERATOR_SUPABASE_DB_URL` in `.env` or `.env.compose`, the
private gold files, and the A9 run folders under `.private-eval/runs/`.

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = ".private-eval"
.venv\Scripts\python.exe .private-eval/a9_metrics.py version
.venv\Scripts\python.exe .private-eval/a9_metrics.py run --summary .private-eval/runs/a9-answer50/summary.json --answers .private-eval/runs/a9-answer50/answers.json
.venv\Scripts\python.exe .private-eval/a9_metrics.py latency --probe-output .private-eval/runs/a9-answer50/latency.txt
.venv\Scripts\python.exe .private-eval/a9_metrics.py claims --review .private-eval/runs/a9-unseen50/claim-review.json
```

[docs index](../README.md)
````

Before you commit, paste in the real output of the waterfall block, not
the placeholder. If a value is not available (for example `latency`
exited 1), write `not measured` and explain it under **Limits**.

## Step 13 - Index and reciprocal links

1. `docs/README.md`: add this row directly below the
   `evaluation/ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md` row, and set the
   front matter `last-reviewed:` to the run date:

   ```markdown
   | [evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md](./evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md) | engineering-lead | draft | <YYYY-MM-DD> | eng, reviewers |
   ```

2. `docs/evaluation/ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md`: insert this
   line, followed by one blank line, directly above the final
   `[docs index](../README.md)` line:

   ```markdown
   Repair outcome: [ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md](./ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md).
   ```

3. `docs/adr/ADR-retrieved-answer-loss-repair.md`: append this bullet as
   the last item of the `## Links` list. Change nothing else in the ADR.

   ```markdown
   - [ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md](../evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md)
   ```

## Step 14 - Checks before commit

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe .private-eval/gold_leak_check.py docs/evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md docs/README.md docs/evaluation/ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md docs/adr/ADR-retrieved-answer-loss-repair.md
uv run python scripts/check.py --tier docs
```

The leak check must exit 0: no `FAIL` line, and so no `set=unseen50`
hit (any unseen hit is a `FAIL`). The three existing docs printed `PASS`
or `WARN` with one or two generic-term hits when A0 checked them. A `WARN`
on the evidence doc is allowed only if every matched phrase (look up the
listed ids in that gold file) is a generic word the template already
contains, such as a stage name. If a hit comes from text you took from a
private sheet, remove that text and rerun. Report every `WARN` line. The
docs tier must exit 0. It takes about 6 minutes.

## Step 15 - Commit, push, and stop if any target failed

Follow 00-rules **At the end of every code packet (A1 to A9)**. The paths
to add, one by one:

```powershell
git add docs/evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md
git add docs/README.md
git add docs/evaluation/ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md
git add docs/adr/ADR-retrieved-answer-loss-repair.md
```

Commit message (fill in the two counts):

```text
docs(eval): answer-loss repair evidence - <U>/50 unseen, <D>/50 diagnosed (A9)
```

Then `git push` and `gh pr checks --watch --fail-fast` exactly as 00-rules
says.

If any acceptance row is `no`: the doc says **Fail**, and it is still
committed, because the evidence is honest either way. Then stop and ask
the user how to proceed. Do not change code, prompts, profiles, gold, or
adjudication verdicts to move a number. Do not rerun the unseen set to
"try again". Do not start A10.

## Step 16 - Report

Paste the 00-rules **Reporting template** with `Packet: A9`. Add:

```text
Seal: sha256=<hash> seal_match=yes (equals the A0 report)
Image: <IMAGE ID> at <short sha>; probe A1..A7 present; version_check=pass (<book_version_id>)
Diagnosed: right_total=<D> (strict <s>, other words <o>); bookkeeping_kills=<n>; rerank_completed=<n>; final evidence=<n>; deadlines=<n>; p90=<x>
Unseen: right_total=<U> (strict <s>, other words <o>); A0 baseline right_total=<r>; claims=<c> unsupported=<u>
Negative ka-12: <status> negative_target=<pass|fail>
Freeze: <pass|fail>
Acceptance: <all pass | failed rows by number>
Scorer diff since A0: none | <stat>
```

No question, phrase, answer, reason, claim, or page text in the report.

## Done when

- [ ] Step 1 preconditions held: checks green, `seal_match=yes` with the
      A0 hash, scorer unchanged since A0.
- [ ] The four A9 helpers exist with the exact code above and are
      gitignored.
- [ ] The image was rebuilt from this branch head, the 00-rules probe
      printed `present` for A1 to A7, and `a9_metrics.py version` printed
      `version_check=pass`.
- [ ] `.private-eval/runs/a9-answer50/`, `.private-eval/runs/a9-unseen50/`, and
      `.private-eval/runs/a9-negative/` each hold `summary.json`,
      `answers.json`, and `head.txt` for this commit, with 50, 50, and 1
      outcomes.
- [ ] `adjudication.json` exists for every run with `adjudicate` > 0,
      and `a9_metrics.py right` exited 0 for all three runs.
- [ ] `trace.txt`, `dump.txt`, and `latency.txt` exist for the diagnosed
      run, and `killed`, `evidence`, `latency`, and `waterfall` ran.
- [ ] `claim-review.json` has a `supported` or `unsupported` verdict on
      every claim, and `a9_metrics.py claims` exited 0.
- [ ] The safety tests and the Step 10 freeze checks ran and their exit
      codes are recorded.
- [ ] `docs/evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md` exists with
      all twelve acceptance rows, the waterfall Mermaid block, and both
      baselines, and it has no private text.
- [ ] `docs/README.md`, the root-cause doc, and the ADR `## Links` list
      link to the evidence doc.
- [ ] The leak check exited 0 and `scripts/check.py --tier docs` exited 0.
- [ ] One commit `docs(eval): answer-loss repair evidence - <U>/50 unseen, <D>/50 diagnosed (A9)`
      is pushed, and `gh pr checks --watch --fail-fast` exited 0.
- [ ] If any row failed, the user was told and A10 was not started.

## Do not

- Do not change product code, tests, prompts, frozen files, or gold in
  this packet. A `fix(ci): ...` commit is allowed only for a CI failure
  caused by the evidence doc itself (for example a markdown lint rule).
- Do not tune anything on the unseen set, rerun it to improve a count, or
  edit `unseen50-v1.json` or its `.sha256` sidecar.
- Do not change an adjudication or claim verdict after seeing the totals.
- Do not copy questions, gold phrases, answers, adjudication reasons,
  claim text, or page text into the evidence doc, commit message, PR, or
  report.
- Do not use the 00-rules PowerShell subset recipe; use `gold_subset.py`.
- Do not edit `answer50_stage_trace.py`, `answer50_checkpoint_dump.py`, or
  `latency_probe.py`; stop if their flags differ from what Step 8 expects.
- Do not run any live eval against an image you did not rebuild in this
  run.
- Do not use `git add -A`, `git add .`, `--no-verify`, `--force`, or
  `--admin`, and do not start A10.
