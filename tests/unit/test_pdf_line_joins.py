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

    assert PDF_PARSER_VERSION == "parser_v1_pdf_reflow_v5"
