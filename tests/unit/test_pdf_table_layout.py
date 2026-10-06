"""Captioned PDF tables become Markdown pipe tables (reflow v5)."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.ingestion.parser.adapters import parse_file
from smart_rag_core.ingestion.parser.helpers import (
    PdfTextBlock,
    detect_pdf_tables,
    join_pdf_lines,
)
from smart_rag_core.text_constants import PARAGRAPH_DELIMITER

from tests.fixtures.parser import build_pdf_layout_fixture

COLUMNS = (75.6, 150.0, 250.0)
TABLE_PIPE = (
    "| Name | Kind | Cost |\n| --- | --- | --- |\n"
    "| alpha | tool | low |\n| beta | agent | high |"
)
TABLE_PLAIN = "Name Kind Cost\nalpha tool low\nbeta agent high"
TABLE = f"{TABLE_PIPE}{PARAGRAPH_DELIMITER}{TABLE_PLAIN}"


def _line(
    text: str, x0: float, y0: float, *, size: float = 9.0, mono: bool = False
) -> PdfTextBlock:
    """Build one page line with 5-point characters.

    Args:
        text: Line text.
        x0: Left x.
        y0: Top y.
        size: Font size.
        mono: Monospace flag.

    Returns:
        Text block.
    """

    return PdfTextBlock(
        text=text,
        bbox=(x0, y0, x0 + 5.0 * len(text), y0 + 8.0),
        max_size=size,
        bold=False,
        block_index=0,
        monospace=mono,
    )


def _grid(
    rows: list[tuple[float, tuple[str, ...]]], *, mono: bool = False
) -> list[PdfTextBlock]:
    """Build table cell lines at the shared column positions.

    Args:
        rows: ``(top y, cell texts)`` per row band.
        mono: Monospace flag for every cell.

    Returns:
        Cell lines in reading order.
    """

    return [
        _line(text, x0, y0, mono=mono)
        for y0, cells in rows
        for x0, text in zip(COLUMNS, cells, strict=False)
    ]


CAPTION = _line("Table 2-1. Sample costs", 72.0, 40.0, size=10.0)
GRID = [
    (60.0, ("Name", "Kind", "Cost")),
    (73.0, ("alpha", "tool", "low")),
    (86.0, ("beta", "agent", "high")),
]


def test_captioned_table_becomes_pipe_table() -> None:
    """Caption plus three aligned row bands yields one table."""

    lines = tuple([CAPTION, *_grid(GRID)])
    tables = detect_pdf_tables(lines)
    assert len(tables) == 1
    assert tables[0].block.text == TABLE
    assert tables[0].block.table is True
    assert tables[0].members == frozenset(range(1, 10))


def test_uncaptioned_columns_are_not_tables() -> None:
    """Two-column text or an index without a caption stays prose."""

    assert detect_pdf_tables(tuple(_grid(GRID))) == ()


def test_continued_table_needs_matching_columns() -> None:
    """A captionless region continues the previous page's table."""

    lines = tuple(_grid(GRID))
    assert len(detect_pdf_tables(lines, previous_columns=COLUMNS)) == 1
    assert detect_pdf_tables(lines, previous_columns=(75.6, 200.0, 250.0)) == ()


def test_wrapped_cell_line_joins_its_cell() -> None:
    """A lone aligned line with a small gap continues the cell above."""

    rows = [
        (60.0, ("Name", "Kind", "Cost")),
        (73.0, ("alpha", "tool", "low")),
        (96.0, ("beta", "agent", "high")),
    ]
    lines = tuple([CAPTION, *_grid(rows), _line("fast", 150.0, 83.0)])
    text = detect_pdf_tables(lines)[0].block.text
    assert "| alpha | tool fast | low |" in text
    assert "| beta | agent | high |" in text


def test_uniform_tight_rows_stay_separate() -> None:
    """Equal gaps below the wrap ratio are rows, not wrapped lines."""

    rows = [
        (60.0, ("Name", "Kind", "Cost")),
        (70.8, ("alpha", "tool", "low")),
        (81.6, ("beta", "agent", "high")),
    ]
    assert detect_pdf_tables(tuple([CAPTION, *_grid(rows)]))[0].block.text == TABLE


def test_monospace_columns_are_not_tables() -> None:
    """Aligned code lines never become a table."""

    assert detect_pdf_tables(tuple([CAPTION, *_grid(GRID, mono=True)])) == ()


def test_pipe_in_cell_is_escaped_and_table_is_own_paragraph() -> None:
    """Literal pipes are escaped; a table never joins prose with a space."""

    rows = [(60.0, ("Name", "Kind", "Cost")), (73.0, ("a|b", "tool", "low"))]
    table = detect_pdf_tables(tuple([CAPTION, *_grid(rows)]))[0].block
    assert "| a\\|b | tool | low |" in table.text
    assert (
        join_pdf_lines(CAPTION, table)
        == f"{CAPTION.text}{PARAGRAPH_DELIMITER}{table.text}"
    )


def test_pdf_fixture_keeps_table_and_code_layout(tmp_path: Path) -> None:
    """The real adapter path emits the pipe table and the indented code."""

    payload, digest = build_pdf_layout_fixture()
    path = tmp_path / "layout.pdf"
    path.write_bytes(payload)
    texts = [
        element.text
        for element in parse_file(path, digest, "pdf").elements
        if element.text
    ]
    joined = "\n\n".join(texts)
    assert f"Table 2-1. Sample costs{PARAGRAPH_DELIMITER}{TABLE}" in joined
    assert "def f(x):\n    return x" in joined
    assert "Body text after the table and the code." in joined
