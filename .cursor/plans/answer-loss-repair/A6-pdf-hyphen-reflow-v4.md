# A6 - PDF line joins for U+2010 and U+00AD hyphens (`parser_v1_pdf_reflow_v4`)

Read [`00-rules-and-commands.md`](./00-rules-and-commands.md) first.
This packet is one commit on `fix/answer-loss-repair`.

**Depends on:** A5 (A1 to A5 are committed on the branch; this packet
does not use their code). **Probe symbol:**
`smart_rag_core.ingestion.parser.helpers.LINE_END_HYPHENS`.
**Live run:** none. The stored book changes only in A8 (re-ingest).

## Goal

The book hyphenates line ends with U+2010 HYPHEN. `join_pdf_lines`
removes a line-end hyphen only when it is ASCII `-`. Every other
same-block join inserts a space, so `com` + U+2010 at a line end plus
`plexity` on the next line is stored as `com`, U+2010, a space,
`plexity`. On the stored book (version `e119bf87`), 719 of 1,016 chunks
contain letter + U+2010 + space + letter (2,732 times). All 719 are
same-block joins; 0 are cross-block. In 7 chunks (8 occurrences) the
right fragment starts uppercase; those stay as they are after this fix.

Fix (ADR Fix 4 item 1): treat ASCII `-`, U+2010, and U+00AD SOFT HYPHEN
alike at a line end. Bump `PDF_PARSER_VERSION` to
`parser_v1_pdf_reflow_v4`.

## Why these choices (do not "improve" them)

- **Same condition as today, more characters.** The join still needs a
  letter before the hyphen and a lowercase first character on the next
  line. An uppercase or digit start keeps the hyphen and uses the normal
  space or `PARAGRAPH_DELIMITER` join, so nothing new is inserted.
- **U+2011 NON-BREAKING HYPHEN is excluded.** A line never breaks after
  it, so a line-end U+2011 is part of the text.
- **No other hyphen code points** (U+2012 to U+2015 are dashes, not
  word-break hyphens).
- **Known trade-off (accepted in the ADR):** a real compound broken at
  its own hyphen at a line end loses the hyphen, exactly as the ASCII
  rule already does. Hyphens inside a line are never touched.
- **Version bump is required.** `PDF_PARSER_VERSION` feeds the PDF
  parser config hash and every PDF chunk ID, so old and new chunks never
  share an ID.

## Read first (confirm each quote exists; line numbers may drift a few lines)

`packages/core/src/smart_rag_core/ingestion/parser/helpers.py` lines
18-23 (constants):

```python
# PyMuPDF 1.25.5 span ``flags`` bit 4 (``TEXT_FONT_BOLD``).
PDF_TEXT_FONT_BOLD = 1 << 4
PDF_HEADING_MAX_WORDS = 12
PDF_HEADING_MAX_CHARS = 80
PDF_HEADING_SIZE_RATIO = 1.2
PDF_HEADING_MIN_SIZE = 11.0
```

Same file, lines 69-96 (`join_pdf_lines`):

```python
def join_pdf_lines(pending: PdfTextBlock, block: PdfTextBlock) -> str:
    """Join two paragraph lines without a mid-word break or a mid-block newline.

    A trailing hyphen after a letter is removed when the next line starts with
    a lowercase letter. Lines from the same PyMuPDF block are separated by a
    space. Lines from different blocks use ``PARAGRAPH_DELIMITER`` so citation
    spans can still see paragraph boundaries.

    Args:
        pending: Paragraph accumulated so far.
        block: Next paragraph line in reading order.

    Returns:
        Joined text. Neither input is mutated.
    """

    left = pending.text
    right = block.text
    if (
        len(left) >= 2
        and left.endswith("-")
        and left[-2].isalpha()
        and right[:1].islower()
    ):
        return f"{left[:-1]}{right}"
    if pending.block_index == block.block_index:
        return f"{left} {right}"
    return f"{left}{PARAGRAPH_DELIMITER}{right}"
```

Its only caller is `merge_consecutive_pdf_paragraphs` (same file, line
~125: `text=join_pdf_lines(pending, block),`). Do not change the caller.

`packages/core/src/smart_rag_core/ingestion/parser/limits.py` line 6:

```python
PDF_PARSER_VERSION = "parser_v1_pdf_reflow_v3"  # PDF-only; other formats stay parser_v1
```

`tests/unit/test_pdf_heading_extraction.py`: read
`test_hyphenated_lines_join_across_blocks` (line ~108) and the
`PdfTextBlock(...)` fixture shape (bbox `(0.0, 0.0, 100.0, 12.0)`,
`max_size=11.0`, `bold=False`). Those tests must pass unchanged.

## Reader audit for `PDF_PARSER_VERSION` (done while writing this packet)

| Reader | Uses | Action |
| --- | --- | --- |
| `ingestion/parser/__init__.py` lines 11, 24 | re-export | none |
| `ingestion/parser/adapters/pdf_adapter.py` line 38 (import), 238 (`stable_config_hash(PDF_PARSER_VERSION, CLEANING_POLICY_VERSION)`), 244 (`parser_version=`) | config hash and stored parser version | none; the bump flows through |
| `tests/unit/test_pdf_heading_extraction.py` lines 15, 133, 178 | the symbol, not the string | none |
| `docs/ingestion/INGESTION_LIMITS.md` line 145 | the string | update (Docs) |
| `docs/development/phase-06/p06-post-fix-v2-acceptance-2026-09-22.md` lines 19, 97 | historical v3 record | **leave unchanged** |

Nothing else in `packages/`, `apps/`, `scripts/`, or `tests/` pins
`parser_v1_pdf_reflow_v3`. Check once:
`rg -n "reflow_v3" packages apps scripts tests` must print only
`limits.py` before your edit and nothing after it.

No product code strips U+00AD today (`chunking/normalize.py`
`normalize_for_dedup` uses NFKC, which keeps it). The stored book has 0
chunks containing U+00AD; the soft-hyphen join is for other PDFs.

## Steps

### 1. Constant in `helpers.py` (exact code)

Replace the line `PDF_HEADING_MIN_SIZE = 11.0` with:

```python
PDF_HEADING_MIN_SIZE = 11.0
LINE_END_HYPHENS = ("-", "\u2010", "\u00ad")
"""Line-end characters removed when they split one word across two lines.

ASCII hyphen-minus, U+2010 HYPHEN (the hyphen typeset books use), and
U+00AD SOFT HYPHEN. U+2011 NON-BREAKING HYPHEN is not listed: a line never
breaks after it, so a line-end U+2011 belongs to the text.
"""
```

Keep the `\u2010` and `\u00ad` escapes. A literal hyphen character
fails Ruff `RUF001`.

### 2. `join_pdf_lines` in `helpers.py` (exact edits)

In the docstring, replace these four lines:

```text
    A trailing hyphen after a letter is removed when the next line starts with
    a lowercase letter. Lines from the same PyMuPDF block are separated by a
    space. Lines from different blocks use ``PARAGRAPH_DELIMITER`` so citation
    spans can still see paragraph boundaries.
```

with:

```text
    A trailing hyphen from ``LINE_END_HYPHENS`` after a letter is removed
    when the next line starts with a lowercase letter, so ``com`` + U+2010 +
    ``plexity`` becomes ``complexity``. A real compound broken at its own
    hyphen at a line end loses that hyphen; hyphens inside a line are never
    touched. When the next line starts with anything else, the hyphen stays
    and the normal join applies. Lines from the same PyMuPDF block are
    separated by a space. Lines from different blocks use
    ``PARAGRAPH_DELIMITER`` so citation spans can still see paragraph
    boundaries.
```

In the body, replace `        and left.endswith("-")` with:

```python
        and left.endswith(LINE_END_HYPHENS)
```

Change nothing else in the function. `left[:-1]` stays correct because
every entry in `LINE_END_HYPHENS` is one character.

### 3. `limits.py` (exact code)

Replace line 6 with:

```python
PDF_PARSER_VERSION = "parser_v1_pdf_reflow_v4"  # PDF-only; other formats stay parser_v1
```

### 4. New test file `tests/unit/test_pdf_line_joins.py` (exact code)

```python
"""PDF line joins for ASCII, U+2010, and U+00AD line-end hyphens (A6)."""

from __future__ import annotations

import pytest
from smart_rag_core.ingestion.parser.helpers import (
    LINE_END_HYPHENS,
    PdfTextBlock,
    join_pdf_lines,
)
from smart_rag_core.ingestion.parser.limits import PDF_PARSER_VERSION
from smart_rag_core.text_constants import PARAGRAPH_DELIMITER

U2010 = "\u2010"
SOFT = "\u00ad"


def _line(text: str, block_index: int) -> PdfTextBlock:
    """Build one body-size PDF line.

    Args:
        text: Line text.
        block_index: PyMuPDF block position; equal values mean the same block.

    Returns:
        A non-bold 11 pt line.
    """

    return PdfTextBlock(
        text=text,
        bbox=(0.0, 0.0, 100.0, 12.0),
        max_size=11.0,
        bold=False,
        block_index=block_index,
    )


def test_line_end_hyphens_cover_ascii_u2010_and_soft_hyphen() -> None:
    """The probe constant lists exactly the three joinable hyphens."""

    assert LINE_END_HYPHENS == ("-", U2010, SOFT)


def test_u2010_split_joins_without_hyphen_or_space() -> None:
    """A U+2010 line break inside a word is removed."""

    assert join_pdf_lines(_line(f"com{U2010}", 0), _line("plexity", 0)) == "complexity"


def test_soft_hyphen_split_joins_without_hyphen_or_space() -> None:
    """A U+00AD line break inside a word is removed."""

    assert join_pdf_lines(_line(f"com{SOFT}", 0), _line("plexity", 0)) == "complexity"


@pytest.mark.parametrize("hyphen", LINE_END_HYPHENS)
@pytest.mark.parametrize("right_block", [0, 1])
def test_every_line_end_hyphen_joins_within_and_across_blocks(
    hyphen: str, right_block: int
) -> None:
    """All three hyphens behave alike, in the same block and across blocks.

    Args:
        hyphen: Line-end hyphen under test.
        right_block: Block index of the right line (0 is the same block).
    """

    joined = join_pdf_lines(
        _line(f"The reason{hyphen}", 0), _line("ing step", right_block)
    )
    assert joined == "The reasoning step"


def test_ascii_hyphen_behavior_is_unchanged() -> None:
    """The existing ASCII rule and both fallback joins are unchanged."""

    assert join_pdf_lines(_line("multi-", 0), _line("agent", 0)) == "multiagent"
    assert join_pdf_lines(_line("see page 4-", 0), _line("5", 0)) == "see page 4- 5"
    assert join_pdf_lines(_line("Plan A-", 0), _line("Team", 0)) == "Plan A- Team"
    assert (
        join_pdf_lines(_line("end.", 0), _line("next", 1))
        == f"end.{PARAGRAPH_DELIMITER}next"
    )


@pytest.mark.parametrize("hyphen", [U2010, SOFT])
def test_uppercase_right_fragment_keeps_hyphen_and_adds_nothing(hyphen: str) -> None:
    """An uppercase right fragment keeps the hyphen and uses the normal join.

    Args:
        hyphen: Unicode line-end hyphen under test.
    """

    left = f"Chain{hyphen}"
    assert (
        join_pdf_lines(_line(left, 0), _line("Of Thought", 0)) == f"{left} Of Thought"
    )
    assert (
        join_pdf_lines(_line(left, 0), _line("Of Thought", 1))
        == f"{left}{PARAGRAPH_DELIMITER}Of Thought"
    )


@pytest.mark.parametrize("hyphen", LINE_END_HYPHENS)
def test_hyphen_after_non_letter_or_alone_is_kept(hyphen: str) -> None:
    """A hyphen after a digit, or a line that is only a hyphen, is kept.

    Args:
        hyphen: Line-end hyphen under test.
    """

    assert (
        join_pdf_lines(_line(f"version 2{hyphen}", 0), _line("beta", 0))
        == f"version 2{hyphen} beta"
    )
    assert join_pdf_lines(_line(hyphen, 0), _line("item", 0)) == f"{hyphen} item"


def test_inline_u2010_compound_is_untouched() -> None:
    """Only the line-end hyphen is removed; an inline compound keeps its hyphen."""

    joined = join_pdf_lines(
        _line(f"multi{U2010}agent co{U2010}", 0), _line("ordination", 0)
    )
    assert joined == f"multi{U2010}agent coordination"


def test_pdf_parser_version_is_reflow_v4() -> None:
    """The line-join change carries a new PDF parser version identity."""

    assert PDF_PARSER_VERSION == "parser_v1_pdf_reflow_v4"
```

This file passes `ruff check` and `ruff format` as written (checked
while writing this packet). It collects **17** tests.

## Docs (exact edits)

Set the date once and use it for every `<RUN_DATE>` below:

```powershell
$runDate = Get-Date -Format yyyy-MM-dd; $runDate
```

1. `docs/ingestion/INGESTION_LIMITS.md` line 145. Replace the row:

   ```text
   | PDF parser version | text | `parser_v1_pdf_reflow_v3` | — | Ask evidence repair | PDF adapter | new version identity | Heading classification or line-join change |
   ```

   with:

   ```text
   | PDF parser version | text | `parser_v1_pdf_reflow_v4` | — | Answer-loss repair (U+2010 and U+00AD line joins) | PDF adapter | new version identity | Heading classification or line-join change |
   ```

   and set the front matter `last-reviewed: 2026-09-16` to
   `last-reviewed: <RUN_DATE>`.

2. `docs/ingestion/CHUNKING_CONTRACT.md`. After the line that ends
   `treat `page_label` as the displayed page.` (end of the PDF paragraph,
   line ~47) and before the blank line and `## Atomicity`, insert one
   blank line and this paragraph:

   ```markdown
   PDF line joins (`parser_v1_pdf_reflow_v4`, `join_pdf_lines` in
   `ingestion/parser/helpers.py`): lines of one PyMuPDF block join with a
   space, and lines of different blocks join with `PARAGRAPH_DELIMITER`
   (`\n\n`). When a line ends in a letter plus ASCII `-`, U+2010 HYPHEN,
   or U+00AD SOFT HYPHEN (`LINE_END_HYPHENS`) and the next line starts
   lowercase, the two join with no hyphen and no space. Before v4 only
   ASCII `-` joined, so typeset books stored letter + U+2010 + space +
   letter splits (719 of 1,016 chunks of the private PDF above). Limits:
   a real compound broken at its own hyphen at a line end loses the
   hyphen, and a suspended hyphen at a line end is joined to the next
   word. Hyphens inside a line are untouched. Any change to this rule
   changes `PDF_PARSER_VERSION`, the parser config hash, and every PDF
   chunk ID, so the stored document needs a re-ingest.
   ```

   In the **Verification** block, replace
   `uv run pytest tests/unit/test_chunking_service.py tests/unit/test_chunking_dedup.py`
   with
   `uv run pytest tests/unit/test_pdf_line_joins.py tests/unit/test_chunking_service.py tests/unit/test_chunking_dedup.py`
   (the rest of the command line stays). Set the front matter
   `last-reviewed: 2026-09-15` to `last-reviewed: <RUN_DATE>`.

3. `docs/README.md`: in the rows for
   `ingestion/CHUNKING_CONTRACT.md` (line ~165, date `2026-09-15`) and
   `ingestion/INGESTION_LIMITS.md` (line ~166, date `2026-09-22`),
   replace only the date cell with `<RUN_DATE>`. Set the front matter
   `last-reviewed:` to `<RUN_DATE>` if it is older.

No new doc file, so no new `docs/README.md` row.

## Commands (run in this order; all must exit 0)

```powershell
uv run python -m ruff format packages/core/src/smart_rag_core/ingestion/parser/helpers.py packages/core/src/smart_rag_core/ingestion/parser/limits.py tests/unit/test_pdf_line_joins.py
uv run python -m pytest tests/unit/test_pdf_line_joins.py -q
uv run python -m pytest tests/unit/test_pdf_heading_extraction.py tests/unit/test_chunking_service.py -q
rg -n "reflow_v3" packages apps scripts tests
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier format
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier docs
```

Expected: the first pytest prints `17 passed`. The `rg` line prints
nothing and exits 1; that exit code is the pass condition for that line
only. No contract test changes, so the contract tier is not required.

Local-only sanity check (not evidence for A8; do not paste chunk text):

```powershell
uv run python -c "from smart_rag_core.ingestion.parser.helpers import LINE_END_HYPHENS; from smart_rag_core.ingestion.parser.limits import PDF_PARSER_VERSION; print(PDF_PARSER_VERSION, len(LINE_END_HYPHENS))"
```

It must print `parser_v1_pdf_reflow_v4 3`.

## Live proof

None in this packet. Do not rebuild images, upload, or re-ingest. A8
applies this parser to the stored book.

## Done when

- [ ] `LINE_END_HYPHENS` exists in `helpers.py` with its docstring and
      `\u` escapes; `join_pdf_lines` uses it and its docstring is updated.
- [ ] `PDF_PARSER_VERSION == "parser_v1_pdf_reflow_v4"`.
- [ ] `tests/unit/test_pdf_line_joins.py` exists as above; `17 passed`.
- [ ] `test_pdf_heading_extraction.py` and `test_chunking_service.py`
      pass unchanged.
- [ ] `rg -n "reflow_v3" packages apps scripts tests` prints nothing.
- [ ] `lint`, `types`, `format`, `unit`, and `docs` tiers exit 0.
- [ ] `INGESTION_LIMITS.md`, `CHUNKING_CONTRACT.md`, and `docs/README.md`
      updated as above; the phase-06 history doc is unchanged.
- [ ] Commit pushed; `gh pr checks --watch --fail-fast` exits 0.

## Commit

```text
fix(ingestion): join U+2010 and U+00AD line-end hyphens; parser_v1_pdf_reflow_v4 (A6)
```

Files to `git add`, one by one:

```text
packages/core/src/smart_rag_core/ingestion/parser/helpers.py
packages/core/src/smart_rag_core/ingestion/parser/limits.py
tests/unit/test_pdf_line_joins.py
docs/ingestion/INGESTION_LIMITS.md
docs/ingestion/CHUNKING_CONTRACT.md
docs/README.md
```

(Six paths. If `git status --short` shows any other changed tracked
file, stop and explain it before committing.)

## Do not

- Do not add U+2011, U+2012 to U+2015, or any other character to
  `LINE_END_HYPHENS`.
- Do not change the lowercase-next-line condition, the letter-before-
  hyphen condition, or the space and `PARAGRAPH_DELIMITER` joins.
- Do not strip hyphens inside a line, and do not add U+00AD removal to
  `normalize.py`, `arabic_normalize.py`, or any search normalizer.
- Do not bump `PARSER_CONFIG_VERSION`, `CLEANING_POLICY_VERSION`, or
  `CHUNKING_POLICY_VERSION`; only `PDF_PARSER_VERSION` changes.
- Do not edit the phase-06 acceptance doc; it records v3 history.
- Do not rebuild images, upload, re-ingest, or run a live eval.
- Do not put book text, question text, or gold phrases in any tracked
  file.
