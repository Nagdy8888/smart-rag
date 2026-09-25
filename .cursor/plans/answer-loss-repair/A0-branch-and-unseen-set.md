# A0 - Branch, plan commit, and the sealed unseen answer-only 50 set

## Goal

Three things, in this order:

1. Create the `fix/answer-loss-repair` branch and commit the plan and the
   docs written before A0, exactly as `00-rules-and-commands.md` says.
2. Write a **new** private answer-only set of 50 questions,
   `.private-eval/unseen50-v1.json`, on pages that no earlier private set
   used. Validate it, record its SHA-256, and seal it. After sealing,
   nobody edits it again and nobody reads its answers until A9.
3. Run that set once on the **current** code (before any fix) and record
   aggregate counts only.

This packet changes no product code. The only commit is the plan/docs
commit from `00-rules-and-commands.md`. Everything else lives under the
gitignored `.private-eval/`.

## Depends on

Nothing. A0 is the first packet.

## Read first

- `00-rules-and-commands.md`: all of it. You need **Working rules**,
  **Repo facts**, **Docker rebuild before any live run**, **Live eval
  commands**, **Git workflow** (section "Once, at the start of A0"), and
  the **Reporting template**.
- [`docs/adr/ADR-retrieved-answer-loss-repair.md`](../../../docs/adr/ADR-retrieved-answer-loss-repair.md),
  section "Expected effect and acceptance", first bullet (**Unseen set**).
- Do **not** open `.private-eval/answer50-v1.json`,
  `.private-eval/known-answer-50-v1.json`, or `.private-eval/fresh50-v1.json`
  to copy wording. The scripts below read them for page numbers and
  duplicate checks; you do not need their text.

## Facts verified for this packet (2026-09-24, read-only)

| Fact | Value |
| --- | --- |
| Gold schema (all three earlier sets) | JSON list of 50 objects. Keys in this order: `id` (str), `page` (int), `kind` (str, always `"known_answer"`), `prompt` (str), `facts` (list). Each fact: `id` (str, `<qid>-f1`, ...), `canonical` (list with 1 str), `aliases` (list, empty). |
| Earlier-set ids | `a01`..`a50`, `k01`..`k50`, `f01`..`f50` |
| Earlier-set pages | 50 + 50 + 50, union 150. `used-pages.txt` has 100 pages (the known and fresh sets) |
| Book | document `95e6c763-24ca-444b-b667-cd075d4f40cd`, current version `e119bf87-1c70-4e10-abb1-5666c4f728c4`, 1016 chunks, all `parser_v1_pdf_reflow_v3` |
| Leaf chunk | `parent_chunk_id IS NOT NULL` (656 leaves). `page_number` is the 1-based PDF page |
| Structural pages excluded | 41: pages 1-22 (front matter; includes the table of contents on 7-13), glossary 337-340, index 341-353, back matter 354-355 |
| Excluded pages total | 184 (150 earlier-set pages plus 41 structural; 7 overlap) |
| Candidate pages | 141 body pages (23-336) that no earlier set used and that hold at least 800 characters of leaf text. 25 unused body pages have no leaf chunk and 5 have less than 800 characters |
| PR #17 | `OPEN`, draft, head `fix/ka50-accuracy-repair`, base `main` |
| Merge commits on `main` | GitHub default subject `Merge pull request #N from Nagdy8888/<branch>` |
| Plan index file | `.cursor/plans/answer_loss_repair_9c24e1a0.plan.md` exists (untracked) |
| Shell | Windows PowerShell 5.1. `>` writes UTF-16 and `Set-Content -Encoding utf8` writes a byte-order mark, so every script below writes its own UTF-8 file |

Known conflict you must surface (Step 2): `00-rules` rule 10 forbids gold
phrases in tracked files, but its A0 commit list includes two docs that
contain many gold phrases. The leak check in Step 2 detects this.

## Sealing rules (apply from Step 6 onward, and in every later packet)

1. The SHA-256 printed at sealing goes into the A0 report. The sidecar
   `.private-eval/unseen50-v1.sha256` holds the same value.
2. Never edit, rebuild, reformat, re-save, rename, or delete
   `.private-eval/unseen50-v1.json` or `.private-eval/unseen50-v1.sha256`.
   `build_unseen50.py` refuses to run once the sidecar exists.
3. Nobody reads the unseen answers until A9. Do not open
   `.private-eval/runs/a0-unseen-baseline/answers.json`, do not print any
   `answer_text` from it, and do not run any preview script on it. Only
   `run_counts.py` (Step 7) may read it; it prints counts and tokens only.
4. Never tune code, prompts, thresholds, profiles, or gold on unseen
   questions. Do not use unseen questions in any subset run before A9.
5. Never copy an unseen question, fact phrase, or page text into a
   tracked file, a commit message, a PR body, or the chat report.

## Step 1 - Write the five private helper scripts

These files are gitignored (`.gitignore` line 99 ignores `.private-eval/`),
so writing them changes no tracked file. Create each file with **exact
code** from this section. Then confirm they are ignored:

```powershell
git check-ignore -v .private-eval/unseen50_pages.py .private-eval/unseen50_validate.py .private-eval/build_unseen50.py .private-eval/gold_leak_check.py .private-eval/run_counts.py
```

Each of the five paths must print a `.gitignore:99:.private-eval/` line.

### `.private-eval/unseen50_pages.py` (exact code)

```python
"""List, read, and check candidate pages for the unseen answer-only 50 set.

Private helper for packet A0 of the answer-loss repair plan. Database access
is read-only: it runs SELECT statements through ``latency_probe.connect()``,
which reads ``OPERATOR_SUPABASE_DB_URL`` from ``.env`` and ``.env.compose``
and switches to the ``postgres`` role. It writes only private working files
under ``.private-eval/``. Run it from the repository root.

Subcommands:
    status: Print the book's current version and its chunk parser versions.
    candidates: Print excluded-page counts, every candidate body page, and an
        evenly spaced pick of 50 pages; optionally save the pick.
    replace: Swap one rejected page in the saved pick for the nearest unused
        candidate page.
    text: Write the leaf-chunk text of the picked pages to a private file.
    check: Report whether one fact phrase is on one page and in how many
        chunks of the version it appears.

Example:
    ``.venv/Scripts/python.exe .private-eval/unseen50_pages.py candidates``
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import unicodedata
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from latency_probe import connect

PRIVATE_DIR = Path(".private-eval")
DOCUMENT_ID = "95e6c763-24ca-444b-b667-cd075d4f40cd"
VERSION_ID = "e119bf87-1c70-4e10-abb1-5666c4f728c4"
EARLIER_GOLD_FILES = (
    "answer50-v1.json",
    "known-answer-50-v1.json",
    "fresh50-v1.json",
)
USED_PAGES_FILE = "used-pages.txt"
DEFAULT_PICKS_FILE = PRIVATE_DIR / "unseen50-pages.txt"
DEFAULT_REJECTED_FILE = PRIVATE_DIR / "unseen50-rejected.txt"
DEFAULT_TEXT_FILE = PRIVATE_DIR / "unseen50-page-text.txt"
FRONT_MATTER_PAGES = frozenset(range(1, 23))
TABLE_OF_CONTENTS_PAGES = frozenset(range(7, 14))
GLOSSARY_PAGES = frozenset(range(337, 341))
BACK_INDEX_PAGES = frozenset(range(341, 354))
BACK_MATTER_PAGES = frozenset(range(354, 356))
BODY_FIRST_PAGE = 23
BODY_LAST_PAGE = 336
MIN_LEAF_CHARS = 800
MIN_FACT_CHARS = 4
MAX_FACT_CHARS = 80
MAX_FACT_WORDS = 8
MAX_CHUNK_MATCHES = 3
SET_SIZE = 50
FORBIDDEN_FACT_CHARS = {
    "\u2010": "unicode_hyphen",
    "\u2011": "unicode_hyphen",
    "\u00ad": "soft_hyphen",
    "\u2013": "dash",
    "\u2014": "dash",
    "\u2018": "curly_quote",
    "\u2019": "curly_quote",
    "\u201c": "curly_quote",
    "\u201d": "curly_quote",
    "'": "apostrophe",
    '"': "double_quote",
    "<": "angle_bracket",
    ">": "angle_bracket",
}
ChunkRow = tuple[int | None, bool, str]


def normalize(text: str) -> str:
    """Normalize text the way the eval scorer compares phrases.

    Mirrors ``smart_rag_core.evaluation.dual_metric`` (HTML unescape, NFKC,
    casefold) and also collapses whitespace runs so line breaks inside a
    page do not hide a phrase.

    Args:
        text: Raw chunk, answer, or phrase text.

    Returns:
        Normalized text for substring matching.
    """

    folded = unicodedata.normalize("NFKC", html.unescape(text)).casefold()
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


def read_page_list(path: Path) -> list[int]:
    """Read a comma- or newline-separated list of page numbers.

    Args:
        path: Text file with page numbers.

    Returns:
        Page numbers in file order; empty when the file is missing.

    Raises:
        ValueError: If an entry is not an integer.
    """

    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8-sig").replace("\n", ",")
    return [int(part) for part in text.split(",") if part.strip()]


def write_page_list(path: Path, pages: list[int]) -> None:
    """Write page numbers as one comma-separated UTF-8 line.

    Args:
        path: Private output file.
        pages: Page numbers to store.
    """

    require_private(path).parent.mkdir(parents=True, exist_ok=True)
    path.write_text(",".join(str(page) for page in pages) + "\n", encoding="utf-8")


def read_gold(name: str) -> list[dict]:
    """Load one earlier private gold file.

    Args:
        name: File name inside ``.private-eval``.

    Returns:
        The gold items.
    """

    return json.loads((PRIVATE_DIR / name).read_text(encoding="utf-8"))


def excluded_pages() -> tuple[set[int], dict[str, int]]:
    """Collect every page an earlier private set already used.

    Returns:
        The union of pages from ``used-pages.txt`` and the three earlier gold
        files, and the page count per source plus ``union``.
    """

    sources: dict[str, set[int]] = {
        USED_PAGES_FILE: set(read_page_list(PRIVATE_DIR / USED_PAGES_FILE))
    }
    for name in EARLIER_GOLD_FILES:
        sources[name] = {int(item["page"]) for item in read_gold(name)}
    union: set[int] = set().union(*sources.values())
    counts = {name: len(pages) for name, pages in sources.items()}
    counts["union"] = len(union)
    return union, counts


def structural_pages() -> set[int]:
    """Return pages that can never hold an unseen question.

    Returns:
        Front matter pages 1-22 (they include the table of contents on
        pages 7-13), glossary pages 337-340, index pages 341-353, and back
        matter pages 354-355.
    """

    return set(
        FRONT_MATTER_PAGES
        | TABLE_OF_CONTENTS_PAGES
        | GLOSSARY_PAGES
        | BACK_INDEX_PAGES
        | BACK_MATTER_PAGES
    )


def earlier_phrases() -> set[str]:
    """Return the normalized canonical phrases of the three earlier sets.

    Returns:
        Normalized phrases, used to reject a repeat of an earlier fact.
    """

    phrases: set[str] = set()
    for name in EARLIER_GOLD_FILES:
        for item in read_gold(name):
            for fact in item["facts"]:
                phrases.update(normalize(str(phrase)) for phrase in fact["canonical"])
    return phrases


def phrase_problems(phrase: str) -> list[str]:
    """List reasons a fact phrase is unsafe for strict scoring.

    The book prints hyphens as U+2010 and apostrophes as U+2019. The scorer's
    NFKC step does not map them to ASCII, so a phrase that contains either
    can miss a correct answer.

    Args:
        phrase: Candidate fact phrase exactly as it will be stored.

    Returns:
        Problem codes; empty when the phrase is usable.
    """

    problems = sorted(
        {code for char, code in FORBIDDEN_FACT_CHARS.items() if char in phrase}
    )
    normalized = normalize(phrase)
    if phrase != phrase.strip() or "  " in phrase or "\n" in phrase or "\t" in phrase:
        problems.append("untrimmed_whitespace")
    if "- " in phrase:
        problems.append("broken_line_hyphen")
    if len(normalized) < MIN_FACT_CHARS:
        problems.append("too_short")
    if len(normalized) > MAX_FACT_CHARS or len(normalized.split()) > MAX_FACT_WORDS:
        problems.append("too_long")
    return problems


def version_chunks(connection: psycopg.Connection, version_id: str) -> list[ChunkRow]:
    """Load every live chunk of one document version.

    Args:
        connection: Operator connection from ``latency_probe.connect()``.
        version_id: Document version UUID.

    Returns:
        ``(page_number, is_leaf, normalized_text)`` per chunk. A leaf chunk
        has a parent chunk.
    """

    rows = connection.execute(
        """
        SELECT page_number, parent_chunk_id IS NOT NULL, raw_text
        FROM app.document_chunks
        WHERE version_id = %s::uuid AND deleted_at IS NULL
        """,
        (version_id,),
    ).fetchall()
    return [
        (page, bool(is_leaf), normalize(str(text or "")))
        for page, is_leaf, text in rows
    ]


def leaf_stats(chunks: list[ChunkRow]) -> dict[int, tuple[int, int]]:
    """Summarize leaf chunks per page.

    Args:
        chunks: Rows from :func:`version_chunks`.

    Returns:
        Page number mapped to ``(leaf_count, leaf_characters)``.
    """

    stats: dict[int, tuple[int, int]] = {}
    for page, is_leaf, text in chunks:
        if not is_leaf or page is None:
            continue
        count, chars = stats.get(page, (0, 0))
        stats[page] = (count + 1, chars + len(text))
    return stats


def candidate_pages(chunks: list[ChunkRow]) -> list[int]:
    """Return body pages no earlier set used that carry enough leaf text.

    Args:
        chunks: Rows from :func:`version_chunks`.

    Returns:
        Sorted candidate page numbers.
    """

    earlier, _ = excluded_pages()
    blocked = earlier | structural_pages()
    stats = leaf_stats(chunks)
    return [
        page
        for page in range(BODY_FIRST_PAGE, BODY_LAST_PAGE + 1)
        if page not in blocked and stats.get(page, (0, 0))[1] >= MIN_LEAF_CHARS
    ]


def spread(pages: list[int], size: int) -> list[int]:
    """Pick ``size`` pages spaced evenly across a sorted list.

    Uses round-half-up so the picks stay strictly increasing.

    Args:
        pages: Sorted candidate pages.
        size: Number of pages to pick.

    Returns:
        ``size`` distinct pages; the first and last candidates are included.

    Raises:
        ValueError: If fewer than ``size`` pages are available.
    """

    if len(pages) < size:
        raise ValueError(f"only {len(pages)} candidate pages for {size} questions")
    if size == 1:
        return [pages[0]]
    step = (len(pages) - 1) / (size - 1)
    return [pages[int(index * step + 0.5)] for index in range(size)]


def nearest_unused(pages: list[int], blocked: set[int], wanted: int) -> int | None:
    """Return the candidate page closest to ``wanted`` that is not blocked.

    Args:
        pages: Sorted candidate pages.
        blocked: Pages already picked or already rejected.
        wanted: The rejected page to replace.

    Returns:
        The closest free candidate; on a tie the higher page wins. ``None``
        when no candidate is free.
    """

    free = [page for page in pages if page not in blocked]
    if not free:
        return None
    return min(free, key=lambda page: (abs(page - wanted), -page))


def book_status(
    connection: psycopg.Connection,
) -> tuple[str | None, list[tuple[str, int]]]:
    """Read the book's current version and chunk parser versions.

    Args:
        connection: Operator connection.

    Returns:
        The current version id (``None`` when the book is missing or
        deleted) and ``(parser_version, chunk_count)`` pairs for it.
    """

    row = connection.execute(
        """
        SELECT current_version_id::text FROM app.documents
        WHERE id = %s::uuid AND deleted_at IS NULL
        """,
        (DOCUMENT_ID,),
    ).fetchone()
    current = row[0] if row else None
    if current is None:
        return None, []
    parsers = connection.execute(
        """
        SELECT coalesce(provenance->>'parser_version', '<none>'), count(*)
        FROM app.document_chunks
        WHERE version_id = %s::uuid AND deleted_at IS NULL
        GROUP BY 1 ORDER BY 1
        """,
        (current,),
    ).fetchall()
    return current, [(str(name), int(count)) for name, count in parsers]


def cmd_status(_: argparse.Namespace) -> int:
    """Print the book's current version and whether it is the pinned one.

    Args:
        _: Parsed arguments (unused).

    Returns:
        0 when the current version equals ``VERSION_ID``, else 1.
    """

    with connect() as connection:
        current, parsers = book_status(connection)
    print(f"document_id={DOCUMENT_ID}")
    print(f"current_version_id={current}")
    print(f"expected_version_id={VERSION_ID}")
    print(f"version_match={'yes' if current == VERSION_ID else 'no'}")
    print("parser_versions=" + ",".join(f"{name}:{count}" for name, count in parsers))
    return 0 if current == VERSION_ID else 1


def cmd_candidates(args: argparse.Namespace) -> int:
    """Print excluded-page counts, candidate pages, and a 50-page pick.

    Args:
        args: Parsed arguments with ``version_id``, ``write_picks``, and
            ``picks_file``.

    Returns:
        0 on success, 1 when fewer than 50 candidates exist or the picks
        file already exists.
    """

    earlier, counts = excluded_pages()
    structural = structural_pages()
    with connect() as connection:
        chunks = version_chunks(connection, args.version_id)
    stats = leaf_stats(chunks)
    body = list(range(BODY_FIRST_PAGE, BODY_LAST_PAGE + 1))
    unused_body = [page for page in body if page not in earlier]
    no_leaf = [page for page in unused_body if page not in stats]
    thin = [
        page
        for page in unused_body
        if page in stats and stats[page][1] < MIN_LEAF_CHARS
    ]
    candidates = candidate_pages(chunks)
    for name, count in counts.items():
        print(f"pages[{name}]={count}")
    print(f"structural_pages={len(structural)}")
    print(f"excluded_pages_total={len(earlier | structural)}")
    print(f"body_pages={len(body)} range={BODY_FIRST_PAGE}-{BODY_LAST_PAGE}")
    print(f"body_pages_used_by_earlier_sets={len(body) - len(unused_body)}")
    print(f"unused_body_pages_without_leaf_chunk={len(no_leaf)} pages={no_leaf}")
    print(
        f"unused_body_pages_below_{MIN_LEAF_CHARS}_leaf_chars={len(thin)} pages={thin}"
    )
    print(f"candidates={len(candidates)}")
    print("candidate_pages=" + ",".join(str(page) for page in candidates))
    if len(candidates) < SET_SIZE:
        print(f"ERROR only {len(candidates)} candidates; need {SET_SIZE}")
        return 1
    picks = spread(candidates, SET_SIZE)
    print(f"spread_{SET_SIZE}=" + ",".join(str(page) for page in picks))
    if args.write_picks:
        if args.picks_file.exists():
            print(f"ERROR picks file already exists: {args.picks_file}")
            return 1
        write_page_list(args.picks_file, picks)
        print(f"wrote {args.picks_file}")
    return 0


def cmd_replace(args: argparse.Namespace) -> int:
    """Replace one rejected page in the saved pick.

    Args:
        args: Parsed arguments with ``page``, ``version_id``, ``picks_file``,
            and ``rejected_file``.

    Returns:
        0 on success, 1 when the page is not picked or no candidate is free.
    """

    picks = read_page_list(args.picks_file)
    if args.page not in picks:
        print(f"ERROR page {args.page} is not in {args.picks_file}")
        return 1
    rejected = read_page_list(args.rejected_file)
    with connect() as connection:
        candidates = candidate_pages(version_chunks(connection, args.version_id))
    blocked = set(picks) | set(rejected) | {args.page}
    replacement = nearest_unused(candidates, blocked, args.page)
    if replacement is None:
        print("ERROR no free candidate page left")
        return 1
    picks[picks.index(args.page)] = replacement
    write_page_list(args.picks_file, sorted(picks))
    write_page_list(args.rejected_file, sorted(set(rejected) | {args.page}))
    print(f"replaced {args.page} -> {replacement}")
    print(f"picks={len(picks)} rejected={len(set(rejected) | {args.page})}")
    return 0


def cmd_text(args: argparse.Namespace) -> int:
    """Write the leaf-chunk text of chosen pages to a private file.

    Args:
        args: Parsed arguments with ``pages`` or ``picks_file``,
            ``version_id``, and ``out``.

    Returns:
        0 on success, 1 when no pages were given.
    """

    if args.pages:
        pages = [int(part) for part in args.pages.split(",") if part.strip()]
    else:
        pages = read_page_list(args.picks_file)
    if not pages:
        print("ERROR no pages given")
        return 1
    out = require_private(args.out)
    blocks: list[str] = []
    with connect() as connection:
        for page in pages:
            rows = connection.execute(
                """
                SELECT raw_text FROM app.document_chunks
                WHERE version_id = %s::uuid AND deleted_at IS NULL
                  AND parent_chunk_id IS NOT NULL AND page_number = %s
                ORDER BY chunk_index
                """,
                (args.version_id, page),
            ).fetchall()
            texts = [" ".join(str(text or "").split()) for (text,) in rows]
            blocks.append(f"=== page {page} leaves={len(texts)}")
            blocks.extend(
                f"--- leaf {index}\n{text}" for index, text in enumerate(texts, 1)
            )
            blocks.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(blocks), encoding="utf-8")
    print(f"wrote {out} pages={len(pages)}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Check one fact phrase against one page and the whole version.

    Args:
        args: Parsed arguments with ``page``, ``phrase``, and ``version_id``.

    Returns:
        0 when the verdict is OK, else 1.
    """

    earlier, _ = excluded_pages()
    allowed = (
        BODY_FIRST_PAGE <= args.page <= BODY_LAST_PAGE
        and args.page not in earlier
        and args.page not in structural_pages()
    )
    with connect() as connection:
        chunks = version_chunks(connection, args.version_id)
    needle = normalize(args.phrase)
    on_page = any(
        needle in text
        for page, is_leaf, text in chunks
        if is_leaf and page == args.page
    )
    matches = sum(1 for _, _, text in chunks if needle in text)
    duplicate = needle in earlier_phrases()
    problems = phrase_problems(args.phrase)
    ok = (
        allowed
        and on_page
        and 1 <= matches <= MAX_CHUNK_MATCHES
        and not duplicate
        and not problems
    )
    print(
        f"page={args.page} page_allowed={'yes' if allowed else 'no'} "
        f"on_page_leaf={'yes' if on_page else 'no'} chunk_matches={matches} "
        f"earlier_duplicate={'yes' if duplicate else 'no'} "
        f"problems={','.join(problems) or 'none'} verdict={'OK' if ok else 'REJECT'}"
    )
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Parser with the five subcommands.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="book version and parser")
    status.set_defaults(handler=cmd_status)
    for name, handler in (
        ("candidates", cmd_candidates),
        ("replace", cmd_replace),
        ("text", cmd_text),
        ("check", cmd_check),
    ):
        command = sub.add_parser(name)
        command.add_argument("--version-id", default=VERSION_ID)
        command.set_defaults(handler=handler)
        if name == "candidates":
            command.add_argument("--write-picks", action="store_true")
            command.add_argument("--picks-file", type=Path, default=DEFAULT_PICKS_FILE)
        if name == "replace":
            command.add_argument("page", type=int)
            command.add_argument("--picks-file", type=Path, default=DEFAULT_PICKS_FILE)
            command.add_argument(
                "--rejected-file", type=Path, default=DEFAULT_REJECTED_FILE
            )
        if name == "text":
            command.add_argument("--pages", default="")
            command.add_argument("--picks-file", type=Path, default=DEFAULT_PICKS_FILE)
            command.add_argument("--out", type=Path, default=DEFAULT_TEXT_FILE)
        if name == "check":
            command.add_argument("page", type=int)
            command.add_argument("phrase")
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
```

### `.private-eval/unseen50_validate.py` (exact code)

```python
"""Validate, hash, and seal the private unseen answer-only 50 gold file.

Private helper for packets A0 and A9 of the answer-loss repair plan. It
reads the gold file and runs SELECT statements only. Output lists question
ids, pages, counts, check codes, and the file hash; it never prints question
or fact text. ``--seal`` writes the hash to a sidecar file next to the gold
file and refuses to overwrite a different hash.

Example:
    ``.venv/Scripts/python.exe .private-eval/unseen50_validate.py --seal``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from latency_probe import connect
from unseen50_pages import (
    BODY_FIRST_PAGE,
    BODY_LAST_PAGE,
    MAX_CHUNK_MATCHES,
    SET_SIZE,
    VERSION_ID,
    ChunkRow,
    earlier_phrases,
    excluded_pages,
    normalize,
    phrase_problems,
    structural_pages,
    version_chunks,
)

DEFAULT_GOLD = Path(".private-eval/unseen50-v1.json")
ITEM_KEYS = ["id", "page", "kind", "prompt", "facts"]
FACT_KEYS = ["id", "canonical", "aliases"]
KIND = "known_answer"
EXPECTED_IDS = [f"u{number:02d}" for number in range(1, SET_SIZE + 1)]
MIN_PROMPT_WORDS = 8
MAX_PROMPT_WORDS = 30
LOCATION_WORDS = re.compile(r"\b(page|pages|chapter|chapters)\b", re.IGNORECASE)


def sha256_of(path: Path) -> str:
    """Hash a file's exact bytes.

    Args:
        path: File to hash.

    Returns:
        Lowercase hex SHA-256 digest.
    """

    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal_path(gold: Path) -> Path:
    """Return the sidecar file that stores the sealed hash.

    Args:
        gold: Gold file path.

    Returns:
        ``<gold stem>.sha256`` in the same directory.
    """

    return gold.with_suffix(".sha256")


def read_seal(gold: Path) -> str | None:
    """Read the sealed hash, if the set was sealed.

    Args:
        gold: Gold file path.

    Returns:
        The stored digest, or ``None`` when no sidecar exists.
    """

    path = seal_path(gold)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").split()[0]


def schema_failures(payload: object) -> list[str]:
    """Check the shape, key order, and value types of the gold file.

    Args:
        payload: Parsed JSON.

    Returns:
        Failure codes such as ``u07:fact_keys``; empty when the shape is
        valid.
    """

    if not isinstance(payload, list):
        return ["top_level_not_list"]
    failures: list[str] = []
    if len(payload) != SET_SIZE:
        failures.append(f"item_count_{len(payload)}")
    ids = [item.get("id") if isinstance(item, dict) else None for item in payload]
    if ids != EXPECTED_IDS:
        failures.append("ids_not_u01_to_u50_in_order")
    for index, item in enumerate(payload):
        qid = ids[index] if isinstance(ids[index], str) else f"item{index}"
        if not isinstance(item, dict) or list(item) != ITEM_KEYS:
            failures.append(f"{qid}:item_keys")
            continue
        if isinstance(item["page"], bool) or not isinstance(item["page"], int):
            failures.append(f"{qid}:page_type")
        if item["kind"] != KIND:
            failures.append(f"{qid}:kind")
        if not isinstance(item["prompt"], str) or not item["prompt"].strip():
            failures.append(f"{qid}:prompt_type")
        facts = item["facts"]
        if not isinstance(facts, list) or len(facts) != 1:
            failures.append(f"{qid}:fact_count")
            continue
        fact = facts[0]
        if not isinstance(fact, dict) or list(fact) != FACT_KEYS:
            failures.append(f"{qid}:fact_keys")
            continue
        if fact["id"] != f"{qid}-f1":
            failures.append(f"{qid}:fact_id")
        canonical = fact["canonical"]
        if (
            not isinstance(canonical, list)
            or len(canonical) != 1
            or not isinstance(canonical[0], str)
            or not canonical[0].strip()
        ):
            failures.append(f"{qid}:canonical")
        if fact["aliases"] != []:
            failures.append(f"{qid}:aliases_not_empty")
    return failures


def content_failures(
    items: list[dict], chunks: list[ChunkRow]
) -> tuple[list[str], list[str]]:
    """Check pages, prompts, and fact phrases against the book version.

    Args:
        items: Schema-valid gold items.
        chunks: Rows from ``unseen50_pages.version_chunks``.

    Returns:
        Failure codes and one status line per question (ids and counts
        only).
    """

    earlier, _ = excluded_pages()
    blocked = earlier | structural_pages()
    known = earlier_phrases()
    failures: list[str] = []
    lines: list[str] = []
    pages = [item["page"] for item in items]
    if len(set(pages)) != len(pages):
        failures.append("duplicate_pages")
    phrases = [normalize(item["facts"][0]["canonical"][0]) for item in items]
    if len(set(phrases)) != len(phrases):
        failures.append("duplicate_facts")
    prompts = [normalize(item["prompt"]) for item in items]
    if len(set(prompts)) != len(prompts):
        failures.append("duplicate_prompts")
    for item, needle, prompt in zip(items, phrases, prompts, strict=True):
        qid, page = item["id"], item["page"]
        codes: list[str] = []
        if not BODY_FIRST_PAGE <= page <= BODY_LAST_PAGE:
            codes.append("page_outside_body")
        if page in blocked:
            codes.append("page_excluded")
        words = len(item["prompt"].split())
        if not MIN_PROMPT_WORDS <= words <= MAX_PROMPT_WORDS:
            codes.append("prompt_length")
        if not item["prompt"].rstrip().endswith("?"):
            codes.append("prompt_not_question")
        if LOCATION_WORDS.search(item["prompt"]):
            codes.append("prompt_location_word")
        if needle in prompt:
            codes.append("prompt_contains_fact")
        codes.extend(
            f"fact_{code}" for code in phrase_problems(item["facts"][0]["canonical"][0])
        )
        if needle in known:
            codes.append("fact_repeats_earlier_set")
        on_page = any(
            needle in text
            for chunk_page, is_leaf, text in chunks
            if is_leaf and chunk_page == page
        )
        matches = sum(1 for _, _, text in chunks if needle in text)
        if not on_page:
            codes.append("fact_not_on_page_leaf")
        if not 1 <= matches <= MAX_CHUNK_MATCHES:
            codes.append("fact_chunk_matches")
        failures.extend(f"{qid}:{code}" for code in codes)
        lines.append(
            f"{qid} page={page} on_page_leaf={'yes' if on_page else 'no'} "
            f"chunk_matches={matches} ok={'yes' if not codes else 'no'}"
        )
    return failures, lines


def runner_failures(gold: Path) -> list[str]:
    """Load the file with the eval runner's own loader.

    Args:
        gold: Gold file path.

    Returns:
        ``[]`` when ``load_private_gold`` accepts 50 questions, else one
        failure code.
    """

    from smart_rag_core.evaluation.company_ask_regression import load_private_gold

    try:
        loaded = load_private_gold(gold)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [f"runner_loader_{type(exc).__name__}"]
    return [] if len(loaded) == SET_SIZE else [f"runner_loader_count_{len(loaded)}"]


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Parser for ``--gold``, ``--version-id``, ``--seal``, and
        ``--hash-only``.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--version-id", default=VERSION_ID)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--seal", action="store_true", help="write the hash sidecar")
    mode.add_argument(
        "--hash-only", action="store_true", help="compare hash to the seal"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate the gold file, print its hash, and optionally seal it.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 when every check passes (and the seal matches), else 1; 2 when
        the gold file is missing.
    """

    args = build_parser().parse_args(argv)
    gold: Path = args.gold
    if not gold.is_file():
        print(f"ERROR gold file missing: {gold}")
        return 2
    digest = sha256_of(gold)
    sealed = read_seal(gold)
    if args.hash_only:
        print(f"sha256={digest}")
        print(f"sealed_sha256={sealed or 'missing'}")
        print(f"seal_match={'yes' if sealed == digest else 'no'}")
        return 0 if sealed == digest else 1
    payload = json.loads(gold.read_text(encoding="utf-8"))
    failures = schema_failures(payload)
    lines: list[str] = []
    if not failures:
        with connect() as connection:
            chunks = version_chunks(connection, args.version_id)
        content, lines = content_failures(payload, chunks)
        failures.extend(content)
        failures.extend(runner_failures(gold))
    for line in lines:
        print(line)
    for failure in failures:
        print(f"FAIL {failure}")
    count = len(payload) if isinstance(payload, list) else 0
    print(
        f"questions={count} failures={len(failures)} valid={'yes' if not failures else 'no'}"
    )
    print(f"sha256={digest}")
    if not args.seal:
        return 0 if not failures else 1
    if failures:
        print("seal=refused_invalid")
        return 1
    if sealed is None:
        seal_path(gold).write_text(f"{digest}  {gold.name}\n", encoding="utf-8")
        print(f"seal=written file={seal_path(gold)}")
        return 0
    if sealed == digest:
        print("seal=unchanged")
        return 0
    print(f"seal=MISMATCH sealed_sha256={sealed}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

### `.private-eval/build_unseen50.py` (exact code, then you fill the table)

Copy this file exactly. In Step 5 you replace only the line
`QUESTIONS: tuple[tuple[str, int, str, str, str], ...] = ()` with the
filled 50-row table. Change nothing else in the file.

```python
"""Build the private unseen answer-only 50 gold file from a reviewed table.

Private helper for packet A0 of the answer-loss repair plan. The question
table below is private: it lives only in ``.private-eval/`` (gitignored) and
must never be copied into a tracked file. The output uses the same schema as
``answer50-v1.json``. The script refuses to run once the set is sealed, so the
sealed file can never be regenerated or edited through it.

Example:
    ``.venv/Scripts/python.exe .private-eval/build_unseen50.py``
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

OUT = Path(".private-eval/unseen50-v1.json")
SEAL = Path(".private-eval/unseen50-v1.sha256")
KIND = "known_answer"
SET_SIZE = 50
TYPE_MINIMUMS = {
    "term": 8,
    "named_entity": 6,
    "number": 3,
    "attribute": 6,
    "purpose": 6,
    "risk": 4,
}
TYPE_MAXIMUM = 15

# (question_id, page, question_type, prompt, fact_phrase)
QUESTIONS: tuple[tuple[str, int, str, str, str], ...] = ()


def table_problems() -> list[str]:
    """Check ids, row shape, and the question-type mix of the table.

    Returns:
        Problem messages without question or fact text; empty when the
        table can be written.
    """

    problems: list[str] = []
    expected = [f"u{number:02d}" for number in range(1, SET_SIZE + 1)]
    if [row[0] for row in QUESTIONS] != expected:
        problems.append(
            f"ids must be u01..u{SET_SIZE:02d} in order (found {len(QUESTIONS)} rows)"
        )
    for row in QUESTIONS:
        if len(row) != 5 or not isinstance(row[1], int) or isinstance(row[1], bool):
            problems.append(
                f"{row[0]}: row must be (id, int page, type, prompt, phrase)"
            )
    types = Counter(row[2] for row in QUESTIONS)
    for name in sorted(set(types) - set(TYPE_MINIMUMS)):
        problems.append(f"unknown question type {name}")
    for name, minimum in TYPE_MINIMUMS.items():
        if types[name] < minimum:
            problems.append(f"type {name} has {types[name]}; needs at least {minimum}")
    for name, count in sorted(types.items()):
        if count > TYPE_MAXIMUM:
            problems.append(f"type {name} has {count}; at most {TYPE_MAXIMUM}")
    return problems


def build_items() -> list[dict[str, object]]:
    """Convert the table to gold items in the ``answer50-v1.json`` schema.

    Returns:
        Items with keys ``id``, ``page``, ``kind``, ``prompt``, ``facts``;
        one fact per item with ``id``, ``canonical``, ``aliases``.
    """

    return [
        {
            "id": qid,
            "page": page,
            "kind": KIND,
            "prompt": prompt,
            "facts": [{"id": f"{qid}-f1", "canonical": [phrase], "aliases": []}],
        }
        for qid, page, _, prompt, phrase in QUESTIONS
    ]


def main() -> int:
    """Write the gold file unless the set is sealed or the table is invalid.

    Returns:
        0 when the file was written, else 1.
    """

    if SEAL.exists():
        print(f"ERROR {SEAL} exists: the set is sealed and must never be rebuilt")
        return 1
    problems = table_problems()
    for problem in problems:
        print(f"ERROR {problem}")
    if problems:
        return 1
    OUT.write_text(
        json.dumps(build_items(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    types = Counter(row[2] for row in QUESTIONS)
    print(f"wrote {OUT} questions={len(QUESTIONS)} types={dict(sorted(types.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### `.private-eval/gold_leak_check.py` (exact code)

```python
"""Scan files for private gold text before they are committed.

Private helper for packets A0 and A9 of the answer-loss repair plan. It loads
every private gold set that exists under ``.private-eval/``, normalizes the
fact phrases and prompts, and searches each given file. It prints file
paths, set names, question ids, and counts only, never the matched text.

A file fails when it contains any prompt opening (first eight words), any
unseen-set phrase, or at least five phrases from one earlier set. One to four
phrase hits from an earlier set are reported as a warning: short generic
terms can appear in normal prose.

Example:
    ``.venv/Scripts/python.exe .private-eval/gold_leak_check.py docs/README.md``
"""

from __future__ import annotations

import argparse
import html
import json
import unicodedata
from pathlib import Path

PRIVATE_DIR = Path(".private-eval")
GOLD_FILES = {
    "answer50": "answer50-v1.json",
    "known50": "known-answer-50-v1.json",
    "fresh50": "fresh50-v1.json",
    "smoke12": "known-answer-smoke-v1.json",
    "unseen50": "unseen50-v1.json",
}
SEALED_SETS = frozenset({"unseen50"})
MIN_PHRASE_CHARS = 8
PHRASE_HIT_LIMIT = 5
PROMPT_OPENING_WORDS = 8


def normalize(text: str) -> str:
    """Apply HTML unescape, NFKC, casefold, and whitespace collapse.

    Args:
        text: File, phrase, or prompt text.

    Returns:
        Normalized text for substring search.
    """

    folded = unicodedata.normalize("NFKC", html.unescape(text)).casefold()
    return " ".join(folded.split())


def load_sets() -> dict[str, list[tuple[str, list[str], str]]]:
    """Load every private gold set that exists.

    Returns:
        Set name mapped to ``(question_id, phrases, prompt_opening)`` rows.
        Phrases shorter than eight normalized characters are skipped.
    """

    sets: dict[str, list[tuple[str, list[str], str]]] = {}
    for name, file_name in GOLD_FILES.items():
        path = PRIVATE_DIR / file_name
        if not path.is_file():
            continue
        rows: list[tuple[str, list[str], str]] = []
        for item in json.loads(path.read_text(encoding="utf-8")):
            phrases: list[str] = []
            for fact in item.get("facts") or []:
                for phrase in list(fact.get("canonical") or []) + list(
                    fact.get("aliases") or []
                ):
                    normalized = normalize(str(phrase))
                    if len(normalized) >= MIN_PHRASE_CHARS:
                        phrases.append(normalized)
            prompt = normalize(str(item.get("prompt") or item.get("question") or ""))
            opening = " ".join(prompt.split()[:PROMPT_OPENING_WORDS])
            rows.append((str(item["id"]), phrases, opening))
        sets[name] = rows
    return sets


def scan(
    path: Path, sets: dict[str, list[tuple[str, list[str], str]]]
) -> tuple[str, list[str]]:
    """Scan one file and decide its verdict.

    Args:
        path: File to scan.
        sets: Output of :func:`load_sets`.

    Returns:
        ``PASS``, ``WARN``, or ``FAIL`` and report lines (ids and counts).
    """

    text = normalize(path.read_text(encoding="utf-8-sig", errors="replace"))
    verdict = "PASS"
    lines: list[str] = []
    for name, rows in sets.items():
        phrase_ids = [
            qid for qid, phrases, _ in rows if any(p in text for p in phrases)
        ]
        prompt_ids = [qid for qid, _, opening in rows if opening and opening in text]
        if not phrase_ids and not prompt_ids:
            continue
        failed = (
            bool(prompt_ids)
            or len(phrase_ids) >= PHRASE_HIT_LIMIT
            or (name in SEALED_SETS and bool(phrase_ids))
        )
        level = "FAIL" if failed else "WARN"
        if level == "FAIL" or verdict == "PASS":
            verdict = level
        lines.append(
            f"  {level} set={name} phrase_hits={len(phrase_ids)} ids={','.join(phrase_ids) or '-'} "
            f"prompt_hits={len(prompt_ids)} ids={','.join(prompt_ids) or '-'}"
        )
    return verdict, lines


def main(argv: list[str] | None = None) -> int:
    """Scan every file given on the command line.

    Args:
        argv: File paths; ``None`` reads ``sys.argv``.

    Returns:
        0 when no file fails, 1 when any file fails, 2 when a file is
        missing or no gold set was found.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    sets = load_sets()
    if not sets:
        print("ERROR no gold sets found under .private-eval")
        return 2
    print("sets=" + ",".join(f"{name}:{len(rows)}" for name, rows in sets.items()))
    worst = 0
    for path in args.paths:
        if not path.is_file():
            print(f"MISSING {path}")
            worst = max(worst, 2)
            continue
        verdict, lines = scan(path, sets)
        print(f"{verdict} {path.as_posix()}")
        for line in lines:
            print(line)
        if verdict == "FAIL":
            worst = max(worst, 1)
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
```

### `.private-eval/run_counts.py` (exact code)

```python
"""Print aggregate counts for one eval run without any answer text.

Private helper for packets A0 and A9 of the answer-loss repair plan. It reads
the runner's redacted ``summary.json`` and the private ``answers.json`` and
prints counts and token histograms only: never answer text, question text,
or gold phrases. Safe to run on the sealed unseen set before A9.

Example:
    ``.venv/Scripts/python.exe .private-eval/run_counts.py
    --summary .private-eval/runs/a0-unseen-baseline/summary.json
    --answers .private-eval/runs/a0-unseen-baseline/answers.json``
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

RERANK_COMPLETED = frozenset({"none", "rerank_partial"})
SUMMARY_KEYS = (
    "questions",
    "strict_pass",
    "grounded_fact_pass",
    "deadline_failures",
    "verifier_refusal_after_fusion",
    "empty_retrieval",
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


def rerank_completed(stages: dict[str, object]) -> bool:
    """Decide whether rerank finished fully or partially for one question.

    Args:
        stages: The ``stages`` mapping of one answers row.

    Returns:
        True when the fallback token is ``none`` or ``rerank_partial`` and
        at least one rerank call was recorded.
    """

    calls = stages.get("rerank_call_count")
    return (
        stages.get("rerank_fallback") in RERANK_COMPLETED
        and isinstance(calls, int)
        and calls >= 1
    )


def main(argv: list[str] | None = None) -> int:
    """Print the aggregate counts.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 on success, 1 when the two files disagree on question ids.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    answers = json.loads(args.answers.read_text(encoding="utf-8"))
    block = summary["summary"]
    outcomes = summary["outcomes"]
    print(" ".join(f"{key}={block.get(key)}" for key in SUMMARY_KEYS))
    print("outcomes=" + histogram(row["outcome"] for row in outcomes))
    print("statuses=" + histogram(row.get("status") for row in answers.values()))
    stages = [row.get("stages") or {} for row in answers.values()]
    print(
        "rerank_fallback=" + histogram(stage.get("rerank_fallback") for stage in stages)
    )
    print(
        "rerank_call_count="
        + histogram(stage.get("rerank_call_count") for stage in stages)
    )
    print(f"rerank_completed={sum(1 for stage in stages if rerank_completed(stage))}")
    print(
        "retrieval_profile_id="
        + histogram(stage.get("retrieval_profile_id") for stage in stages)
    )
    summary_ids = {row["question_id"] for row in outcomes}
    if summary_ids != set(answers):
        print(f"ERROR id mismatch summary={len(summary_ids)} answers={len(answers)}")
        return 1
    print(f"rows={len(answers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Step 2 - Preflight and user decisions (ask everything at once)

Run these read-only checks from the repo root:

```powershell
git status --short
git branch --show-current
Test-Path .cursor/plans/answer_loss_repair_9c24e1a0.plan.md
gh pr view 17 --json state,mergedAt
git branch --list fix/answer-loss-repair
git ls-remote --heads origin fix/answer-loss-repair
```

Then run the leak check on every file the 00-rules A0 commit will add:

```powershell
$env:PYTHONIOENCODING = "utf-8"
$files = @(
  ".cursor/plans/answer_loss_repair_9c24e1a0.plan.md",
  ".cursor/plans/query_latency_repair_3f9c2a61.plan.md",
  "docs/adr/ADR-retrieved-answer-loss-repair.md",
  "docs/adr/README.md",
  "docs/README.md",
  "docs/evaluation/ANSWER_ONLY_50_2026-09-24.md",
  "docs/evaluation/ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md",
  "docs/evaluation/FRESH_KNOWN_ANSWER_50_2026-09-23.md",
  "docs/evaluation/KNOWN_ANSWER_50_REPAIR_EVIDENCE_2026-09-22.md"
) + (Get-ChildItem .cursor/plans/answer-loss-repair -Filter *.md).FullName + (Get-ChildItem .cursor/plans/query-latency-repair -Filter *.md).FullName
.venv\Scripts\python.exe .private-eval/gold_leak_check.py @files
```

Verified result before Step 2b on 2026-09-24 (yours should match unless the docs
changed): exit code 1, with
`FAIL docs/evaluation/ANSWER_ONLY_50_2026-09-24.md` (`answer50`
phrase_hits=45) and `FAIL docs/evaluation/FRESH_KNOWN_ANSWER_50_2026-09-23.md`
(`fresh50` phrase_hits=15). The other files print `PASS` or `WARN` with one
or two generic-term hits. `WARN` is not a blocker.

Stop conditions. If **any** of these hold, stop and send the user **one**
message that asks every applicable question, then wait:

1. `Test-Path` printed `False`: the plan index file that 00-rules stashes
   and commits is missing. Ask whether to continue without it (the
   `git stash` and `git add` pathspecs would fail) or wait for it.
2. PR #17 `state` is `OPEN`: ask "Ship PR #17 first, or stack
   `fix/answer-loss-repair` on `fix/ka50-accuracy-repair`?" (00-rules).
3. The leak check prints `FAIL` for any file **other than**
   `docs/evaluation/ANSWER_ONLY_50_2026-09-24.md` and
   `docs/evaluation/FRESH_KNOWN_ANSWER_50_2026-09-23.md`: report the
   leak-check output (paths, ids, counts only) and stop. The two eval
   docs are expected to fail here; Step 2b redacts them (decision D4 in
   the plan index is "redact").

Record every answer verbatim in the report under **Deviations**.

## Step 2b - Redact the two eval docs (decision D4 = redact)

The user chose to remove the expected-answer and answer-text columns
before commit. Do it with this private helper, not by hand.

1. Create `.private-eval/drop_table_columns.py` with exactly this code
   (verified on copies of both docs on 2026-09-24):

   ```python
   """Drop named columns from Markdown tables in one file.

   Private helper for packet A0 of the answer-loss repair plan (decision D4).
   It removes expected-answer and answer-text columns from the evaluation docs
   before they are committed. It prints line numbers, row counts, and column
   names only, never cell text.

   Example:
       ``.venv/Scripts/python.exe .private-eval/drop_table_columns.py
       docs/evaluation/ANSWER_ONLY_50_2026-09-24.md "Asked fact"``
   """

   from __future__ import annotations

   import argparse
   import re
   from pathlib import Path

   _PIPE = re.compile(r"(?<!\\)\|")
   _SEPARATOR_CELL = re.compile(r"\s*:?-{3,}:?\s*")


   def split_row(line: str) -> list[str] | None:
       """Split one Markdown table row into cells.

       Args:
           line: One line of the file without its newline.

       Returns:
           The cells without the outer pipes, or ``None`` when the line is not
           a table row.
       """

       stripped = line.strip()
       if len(stripped) < 2 or not (stripped.startswith("|") and stripped.endswith("|")):
           return None
       return _PIPE.split(stripped[1:-1])


   def drop_columns(lines: list[str], names: set[str]) -> tuple[list[str], list[str]]:
       """Remove the named columns from every table whose header has them.

       Args:
           lines: File lines without newlines.
           names: Header names to drop, compared after stripping spaces.

       Returns:
           The new lines and one report line per changed table.

       Raises:
           SystemExit: If a row in a changed table has a different cell count
               from its header (for example an unescaped pipe inside a cell).
       """

       out: list[str] = []
       report: list[str] = []
       index = 0
       while index < len(lines):
           header = split_row(lines[index])
           separator = split_row(lines[index + 1]) if index + 1 < len(lines) else None
           is_table = (
               header is not None
               and separator is not None
               and len(separator) == len(header)
               and all(_SEPARATOR_CELL.fullmatch(cell) for cell in separator)
           )
           if not is_table or header is None:
               out.append(lines[index])
               index += 1
               continue
           drop = {i for i, cell in enumerate(header) if cell.strip() in names}
           end = index
           while end < len(lines) and split_row(lines[end]) is not None:
               end += 1
           if not drop:
               out.extend(lines[index:end])
               index = end
               continue
           for row_number in range(index, end):
               cells = split_row(lines[row_number]) or []
               if len(cells) != len(header):
                   raise SystemExit(
                       f"cell count mismatch at line {row_number + 1}: "
                       f"{len(cells)} != {len(header)}"
                   )
               kept = [cell for i, cell in enumerate(cells) if i not in drop]
               out.append("|" + "|".join(kept) + "|")
           dropped = ",".join(header[i].strip() for i in sorted(drop))
           report.append(f"table at line {index + 1}: rows={end - index - 2} dropped={dropped}")
           index = end
       return out, report


   def main(argv: list[str] | None = None) -> int:
       """Rewrite one file with the named columns removed.

       Args:
           argv: The file path, then one or more column names; ``None`` reads
               ``sys.argv``.

       Returns:
           0 when at least one table changed, 1 when none did.
       """

       parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
       parser.add_argument("path", type=Path)
       parser.add_argument("names", nargs="+")
       args = parser.parse_args(argv)
       text = args.path.read_text(encoding="utf-8")
       newline = "\r\n" if "\r\n" in text else "\n"
       new_lines, report = drop_columns(text.splitlines(), set(args.names))
       for line in report:
           print(line)
       if not report:
           print(f"no table in {args.path.as_posix()} has the named columns")
           return 1
       args.path.write_text(newline.join(new_lines) + newline, encoding="utf-8", newline="")
       print(f"wrote {args.path.as_posix()} tables={len(report)}")
       return 0


   if __name__ == "__main__":
       raise SystemExit(main())
   ```

   Confirm it is ignored: `git check-ignore -v .private-eval/drop_table_columns.py`
   must print a `.gitignore` rule.

2. Run both commands:

   ```powershell
   .venv\Scripts\python.exe .private-eval/drop_table_columns.py docs/evaluation/ANSWER_ONLY_50_2026-09-24.md "Asked fact" "What the answer said" "Fact on the page" "What the RAG said" "Fact the page supports"
   .venv\Scripts\python.exe .private-eval/drop_table_columns.py docs/evaluation/FRESH_KNOWN_ANSWER_50_2026-09-23.md "What the answer did" "What happened" "What the answer used instead" "Answer the run stored" "Failure"
   ```

   Expected output (verified on copies on 2026-09-24):

   ```text
   table at line 46: rows=2 dropped=Asked fact,What the answer said
   table at line 53: rows=18 dropped=Fact on the page,What the RAG said
   table at line 83: rows=50 dropped=Fact the page supports
   wrote docs/evaluation/ANSWER_ONLY_50_2026-09-24.md tables=3
   table at line 100: rows=6 dropped=What the answer did
   table at line 114: rows=6 dropped=What happened
   table at line 132: rows=14 dropped=What the answer used instead
   table at line 156: rows=6 dropped=Answer the run stored
   table at line 201: rows=50 dropped=Failure
   wrote docs/evaluation/FRESH_KNOWN_ANSWER_50_2026-09-23.md tables=5
   ```

   Any `cell count mismatch` or a different table list: stop and report
   the printed lines. (On a mismatch the script exits before writing, so
   the file is unchanged.)

3. Add one sentence to each doc so readers know why the columns are gone.
   In `docs/evaluation/ANSWER_ONLY_50_2026-09-24.md`, find

   ```text
   question file is `.private-eval/answer50-v1.json`.
   ```

   and replace it with

   ```text
   question file is `.private-eval/answer50-v1.json`. Expected-answer and
   answer-text columns were removed before commit (plan decision D4); the
   private run files keep them.
   ```

   In `docs/evaluation/FRESH_KNOWN_ANSWER_50_2026-09-23.md`, find

   ```text
   [ANSWER_ONLY_50_2026-09-24.md](./ANSWER_ONLY_50_2026-09-24.md).

   ## Result
   ```

   and replace it with

   ```text
   [ANSWER_ONLY_50_2026-09-24.md](./ANSWER_ONLY_50_2026-09-24.md).
   Expected-answer and answer-text columns were removed before commit
   (plan decision D4); the private run files keep them.

   ## Result
   ```

4. Rerun the Step 2 leak-check command unchanged. Required: exit code 0,
   and neither eval doc prints `FAIL`. Verified on redacted copies on
   2026-09-24: `ANSWER_ONLY_50_2026-09-24.md` prints `WARN` (answer50
   `phrase_hits=1`) and `FRESH_KNOWN_ANSWER_50_2026-09-23.md` prints
   `WARN` (answer50 1, fresh50 3, smoke12 1). `WARN` is not a blocker.
   Any `FAIL`: stop and report the leak-check output.
5. Run `pnpm exec markdownlint-cli2 docs/evaluation/ANSWER_ONLY_50_2026-09-24.md docs/evaluation/FRESH_KNOWN_ANSWER_50_2026-09-23.md`.
   Required: `Summary: 0 issues in 0 files` (verified on the redacted copies).

## Step 3 - Branch and plan commit

Follow `00-rules-and-commands.md`, section **Git workflow**, subsection
"Once, at the start of A0", exactly. Do not copy commands from memory;
run the ones printed there. The checks for this step:

- [ ] If `fix/answer-loss-repair` already exists locally or on `origin`,
      use the 00-rules "If the branch already exists" line instead, then
      confirm the plan commit is there:
      `git log --oneline -5 --grep "docs(plan): answer-loss repair"`.
      If it is, skip to Step 4.
- [ ] MERGED path: `git stash push` printed `Saved working directory`,
      and `git stash pop` finished without a conflict. On a conflict,
      stop and report `git status --short`; do not resolve it by guessing.
- [ ] STACK path (only if the user said stack): the new branch was cut
      from an up-to-date `fix/ka50-accuracy-repair`, and `gh pr create`
      used `--base fix/ka50-accuracy-repair`.
- [ ] Before `git commit`, the staged list is exactly the 00-rules paths
      (adjusted only by the user's Step 2 answer):

      ```powershell
      git diff --cached --name-only
      ```

      It must not list anything under `.private-eval/` or any `.env*`
      file. It **must** list
      `.cursor/plans/query_latency_repair_3f9c2a61.plan.md` and the files
      under `.cursor/plans/query-latency-repair/` (the combined plan
      commits them in A0).
- [ ] Commit message is exactly
      `docs(plan): answer-loss repair ADR, root causes, and plan A0-A10`.
- [ ] `git push -u origin fix/answer-loss-repair` succeeded, and the
      draft PR exists:

      ```powershell
      gh pr view --json number,url,state,isDraft,baseRefName,headRefName
      ```

      Required: `"state": "OPEN"`, `"isDraft": true`,
      `"headRefName": "fix/answer-loss-repair"`, and `baseRefName` equal
      to `main` (or `fix/ka50-accuracy-repair` on the stack path).
- [ ] `gh pr checks --watch --fail-fast` exits 0. On red, follow 00-rules
      (`gh run view <run-id> --log-failed`, fix as `fix(ci): <what>`).
      If the failure is in a doc you were told not to edit, stop and ask.

## Step 4 - Pick the 50 pages

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe .private-eval/unseen50_pages.py status
.venv\Scripts\python.exe .private-eval/unseen50_pages.py candidates --write-picks
```

`status` must print `version_match=yes` and
`parser_versions=parser_v1_pdf_reflow_v3:1016`. If not, the book was
re-ingested after this packet was written; stop and report.

`candidates` must print these lines (verified 2026-09-24):

```text
pages[used-pages.txt]=100
pages[answer50-v1.json]=50
pages[known-answer-50-v1.json]=50
pages[fresh50-v1.json]=50
pages[union]=150
structural_pages=41
excluded_pages_total=184
body_pages=314 range=23-336
body_pages_used_by_earlier_sets=143
unused_body_pages_without_leaf_chunk=25 pages=[38, 44, 62, 92, 136, 151, 156, 178, 179, 189, 190, 191, 196, 197, 198, 209, 220, 225, 226, 244, 264, 271, 291, 292, 317]
unused_body_pages_below_800_leaf_chars=5 pages=[184, 199, 214, 243, 336]
candidates=141
spread_50=24,31,39,46,51,55,61,68,73,79,87,91,97,104,109,115,121,124,126,131,137,144,153,159,164,166,173,185,193,203,213,221,229,235,245,255,261,268,276,280,286,296,304,308,313,319,322,327,332,335
wrote .private-eval\unseen50-pages.txt
```

If any count differs, stop and report the output. If
`ERROR picks file already exists` appears, a previous run already picked
pages; keep that file and continue.

## Step 5 - Read the pages and write the 50 questions

1. Write the page text to a private file and open it with your file-read
   tool. Never paste it into chat, a tracked file, or the report.

   ```powershell
   .venv\Scripts\python.exe .private-eval/unseen50_pages.py text
   ```

   Output: `.private-eval/unseen50-page-text.txt`, one
   `=== page <n> leaves=<k>` block per picked page.

2. Go through the pages in ascending order. Question ids follow page
   order: the lowest page is `u01`, the highest is `u50`.

3. For each page choose **one** fact phrase:
   - Copy it character for character from that page's text, 1 to 5
     words preferred (at most 8 words, 4 to 80 characters).
   - It must be the thing a correct answer has to say: a term, a name, a
     number with its unit noun, a named component, a stated purpose, or a
     named risk. Not a generic word, a running header, or a figure label.
   - It must not contain a hyphen or dash character of any kind, a quote,
     an apostrophe, `<`, or `>`, and it must not span a line-break
     hyphen (`word- word`). The `check` command rejects these.
4. Check the phrase before you use it:

   ```powershell
   .venv\Scripts\python.exe .private-eval/unseen50_pages.py check <page> "<phrase>"
   ```

   The line must end in `verdict=OK` (`page_allowed=yes`,
   `on_page_leaf=yes`, `chunk_matches` 1 to 3, `earlier_duplicate=no`,
   `problems=none`). A leaf and its parent usually both hold the phrase,
   so `chunk_matches=2` is normal. If `chunk_matches` is above 3, add
   one neighbouring word from the page or pick another fact on the same
   page.
5. Replacement rule: if three different facts on one page are all
   `REJECT`, or the page is mostly a figure, list, or reference block,
   replace the page. Never choose a replacement by hand:

   ```powershell
   .venv\Scripts\python.exe .private-eval/unseen50_pages.py replace <page>
   .venv\Scripts\python.exe .private-eval/unseen50_pages.py text --pages <new page> --out .private-eval/unseen50-page-text-extra.txt
   ```

   `replace` takes the nearest unused candidate page (on a tie, the
   higher page), records the rejected page in
   `.private-eval/unseen50-rejected.txt`, and rewrites the pick file.
   Re-number the ids in page order afterwards.
6. Write the question:
   - 8 to 30 words, one sentence, ending with `?`. Earlier sets mostly
     start with "What" or "Which" and often say "the book"; do the same.
   - It must be answerable from that page alone, have exactly one
     correct answer, and that answer must contain the fact phrase. Do
     not ask "name one of ..." when the page lists several items.
   - It must not contain the fact phrase or the words `page`, `pages`,
     `chapter`, or `chapters`, and must not quote the page's sentences.
7. Give each row one type. Definitions:
   - `term`: the page names or defines a concept; the fact is that name.
   - `named_entity`: a named product, tool, framework, protocol,
     standard, organization, or person.
   - `number`: a count, percentage, year, or size, written with its
     unit or noun.
   - `attribute`: a property, part, step, or characteristic of something
     the page describes.
   - `purpose`: what something is for or what it enables.
   - `risk`: a risk, failure mode, limitation, or challenge the page
     names.

   Mix: at least 8 `term`, 6 `named_entity`, 3 `number`, 6 `attribute`,
   6 `purpose`, 4 `risk`, and no type above 15. To meet the mix, pick a
   different fact on a page; do not change pages for it.
8. Put the 50 rows into `.private-eval/build_unseen50.py` in place of the
   empty `QUESTIONS` line, one tuple per line in id order:
   `("u01", <page>, "<type>", "<question>", "<fact phrase>"),`.

## Step 6 - Build, validate, and seal

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe .private-eval/build_unseen50.py
.venv\Scripts\python.exe .private-eval/unseen50_validate.py
```

`build_unseen50.py` prints `wrote .private-eval\unseen50-v1.json
questions=50 types={...}`. The validator prints one line per question and
must end with `questions=50 failures=0 valid=yes` and `sha256=<hex>`. For
every `FAIL u<nn>:<code>` line, fix that row in the `QUESTIONS` table
(never the JSON file) and run both commands again:

| Code | Fix |
| --- | --- |
| `page_excluded`, `page_outside_body` | Use `replace` (Step 5.5) |
| `fact_not_on_page_leaf` | Copy the phrase again from that page's leaf text |
| `fact_chunk_matches` | Make the phrase more specific, or pick another fact |
| `fact_<problem>` | Remove the flagged character or shorten the phrase |
| `fact_repeats_earlier_set` | Pick another fact on the page |
| `prompt_length`, `prompt_not_question`, `prompt_location_word`, `prompt_contains_fact` | Rewrite the question |
| `duplicate_pages`, `duplicate_facts`, `duplicate_prompts` | Make every row unique |
| `runner_loader_*` | Stop and report; the schema is wrong |

When `valid=yes`, seal it and confirm:

```powershell
.venv\Scripts\python.exe .private-eval/unseen50_validate.py --seal
.venv\Scripts\python.exe .private-eval/unseen50_validate.py --hash-only
.venv\Scripts\python.exe .private-eval/build_unseen50.py
```

Expected: `seal=written file=...unseen50-v1.sha256`, then
`seal_match=yes`, then the builder refuses with
`ERROR .private-eval\unseen50-v1.sha256 exists: ...` (exit code 1). That
refusal is the proof the seal holds. From here on the **Sealing rules**
apply.

Confirm no plan file leaks the new set (all lines `PASS` or `WARN`, none
naming `set=unseen50`):

```powershell
.venv\Scripts\python.exe .private-eval/gold_leak_check.py (Get-ChildItem .cursor/plans/answer-loss-repair -Filter *.md).FullName
```

## Step 7 - Baseline run on the current code

1. Rebuild the `api` image and check health exactly as 00-rules
   **Docker rebuild before any live run** says. `health/ready` must
   contain `"query_ready": true`.
2. Probe. No packet is committed yet, so all seven entries must print
   `MISSING`. The 00-rules one-liner stops with `ModuleNotFoundError` at
   A1, and 00-rules says to probe per entry in that case. This command
   probes every entry separately in one call:

   ```powershell
   docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml exec -T api python -c "import importlib, importlib.util; checks={'A1':('smart_rag_core.query_answer.claims','claims_to_answer_payload'),'A2':('smart_rag_core.retrieval.rerank','RerankPayloadError'),'A3':('smart_rag_core.retrieval.rerank_versions','RERANK_LABEL_PREFIX'),'A4':('smart_rag_core.retrieval.frozen_profile','LONG_DOCUMENT_V3_PROFILE_ID'),'A5':('smart_rag_core.retrieval.profiles','CHANNEL_PHASE_RESERVE_SECONDS'),'A6':('smart_rag_core.ingestion.parser.helpers','LINE_END_HYPHENS'),'A7':('smart_rag_core.ingestion.chunking.navigation','is_navigation_chunk')}; [print(k, 'present' if importlib.util.find_spec(m) is not None and hasattr(importlib.import_module(m), a) else 'MISSING') for k,(m,a) in checks.items()]"
   ```

   Any `present` line means the image is not the pre-fix code; stop and
   report.
3. Run all 50 with the 00-rules **Full answer-only run** command, using
   run name `a0-unseen-baseline` and `--gold .private-eval/unseen50-v1.json`:

   ```powershell
   New-Item -ItemType Directory -Force .private-eval/runs/a0-unseen-baseline | Out-Null
   uv run python scripts/run_company_ask.py `
     --gold .private-eval/unseen50-v1.json `
     --out .private-eval/runs/a0-unseen-baseline/summary.json `
     --credentials .private-eval/eval-credentials.json `
     --progress .private-eval/runs/a0-unseen-baseline/progress.json `
     --answers-out .private-eval/runs/a0-unseen-baseline/answers.json `
     --stage-export .private-eval/runs/a0-unseen-baseline/stages.json `
     --verbose
   ```

   It takes about 50 minutes. Give the command a timeout of at least
   75 minutes, or start it in the background and read
   `.private-eval/runs/a0-unseen-baseline/progress.json` (keys
   `progress`, `last_id`, `last_terminal`; tokens only) every 10
   minutes. If it stops early, run the same command again; it resumes
   from `answers.json`. The console lines (progress, `DIAG ...`,
   `drop_histogram=`, `questions=... strict_pass=...`) hold tokens and
   ids only and are safe to read.
4. Record aggregate counts only:

   ```powershell
   .venv\Scripts\python.exe .private-eval/run_counts.py --summary .private-eval/runs/a0-unseen-baseline/summary.json --answers .private-eval/runs/a0-unseen-baseline/answers.json
   .venv\Scripts\python.exe .private-eval/unseen50_validate.py --hash-only
   ```

   Copy these lines into the report: the first line
   (`questions=50 strict_pass=...`), `outcomes=`, `statuses=`,
   `rerank_fallback=`, `rerank_completed=`, and `rows=50`. The hash check
   must print `seal_match=yes`.
5. `git status --short` must show no new tracked or untracked path
   outside `.private-eval/` compared with Step 3.

## Step 8 - Report

Paste the 00-rules **Reporting template**. Use `Packet: A0`,
`Tests added/updated: none`, and in **Files changed** list only the
tracked paths of the plan/docs commit. Then add this block:

```text
Unseen set:
  file: .private-eval/unseen50-v1.json (gitignored)
  sha256: <64 hex characters from --seal>
  seal sidecar: .private-eval/unseen50-v1.sha256, builder refusal confirmed
  pages: excluded=184 candidates=141 replaced=<n> rejected=<page list or none>
  types: <the types={...} dict printed by build_unseen50.py>
Baseline on current code (A0):
  image rebuilt at <git rev-parse --short HEAD>; probe A1..A7 MISSING
  <run_counts.py lines>
  seal_match=yes after the run
Decisions from Step 2: <PR #17 answer; leak-check answer; or "none needed">
PR: <url> (draft, base <base>)
```

Do not put question text, fact phrases, page text, or answer text in the
report.

## Done when

- [ ] The five private helpers exist with the exact code above, and
      `git check-ignore -v` lists all five.
- [ ] Every Step 2 stop condition was either absent or answered by the
      user, and the answers are in the report.
- [ ] Branch `fix/answer-loss-repair` exists on `origin` with exactly one
      new commit, `docs(plan): answer-loss repair ADR, root causes, and plan A0-A10`,
      whose files match the 00-rules list (adjusted only by the user's
      answer).
- [ ] A draft PR from `fix/answer-loss-repair` exists, and
      `gh pr checks --watch --fail-fast` exited 0.
- [ ] `unseen50_pages.py candidates` printed `excluded_pages_total=184`
      and `candidates=141`.
- [ ] `unseen50_validate.py` printed `questions=50 failures=0 valid=yes`.
- [ ] `unseen50_validate.py --seal` printed `seal=written`,
      `--hash-only` printed `seal_match=yes`, and the builder then
      refused with exit code 1.
- [ ] The baseline ran on an `api` image rebuilt from this branch; the
      probe printed `MISSING` for all of A1..A7.
- [ ] `.private-eval/runs/a0-unseen-baseline/summary.json` has 50
      outcomes, and `run_counts.py` printed `rows=50`.
- [ ] The report holds the SHA-256, the aggregate counts, and no private
      text.

## Do not

- Do not open, print, or preview `.private-eval/runs/a0-unseen-baseline/answers.json`
  or any unseen answer text. Only `run_counts.py` reads it.
- Do not edit, rebuild, reformat, or delete `.private-eval/unseen50-v1.json`
  or `.private-eval/unseen50-v1.sha256` after sealing.
- Do not copy unseen questions, fact phrases, or page text into any
  tracked file, commit message, PR body, or the chat report.
- Do not use the unseen set to tune anything, and do not run unseen
  questions in any subset run.
- Do not change product code, tests, prompts, or docs in this packet. The
  only commit is the 00-rules plan/docs commit.
- Do not edit `00-rules-and-commands.md`, the ADR, or the docs the leak
  check flags.
- Do not `git add` anything under `.private-eval/` or any `.env*` file;
  never `git add -A`, `git add .`, `--no-verify`, `--force`, or `--admin`.
- Do not pick or replace pages by hand; use `candidates` and `replace`.
- Do not run the baseline against an image you did not rebuild in this
  run, or continue after any stop condition without the user's answer.
