"""Monospace PDF lines keep line breaks and indentation (reflow v5)."""

from __future__ import annotations

from smart_rag_core.ingestion.parser.helpers import (
    PdfTextBlock,
    extract_pdf_text_blocks,
    indent_pdf_code_lines,
    join_pdf_lines,
    merge_consecutive_pdf_paragraphs,
)
from smart_rag_core.ingestion.parser.types import ElementKind
from smart_rag_core.text_constants import PARAGRAPH_DELIMITER

P = ElementKind.PARAGRAPH


def _span(
    text: str, *, font: str, flags: int = 0, size: float = 8.5
) -> dict[str, object]:
    """Build one vendor span.

    Args:
        text: Span text.
        font: Font name.
        flags: PyMuPDF flags.
        size: Font size.

    Returns:
        Span mapping.
    """

    return {"text": text, "font": font, "flags": flags, "size": size}


def _page(
    *lines: tuple[tuple[float, float], list[dict[str, object]]],
) -> dict[str, object]:
    """Build a one-block ``get_text('dict')`` page.

    Args:
        lines: ``((x0, x1), spans)`` per line.

    Returns:
        Vendor page mapping.
    """

    return {
        "blocks": [
            {
                "type": 0,
                "bbox": [0.0, 0.0, 400.0, 400.0],
                "lines": [
                    {"bbox": [x0, 10.0 * i, x1, 10.0 * i + 9.0], "spans": spans}
                    for i, ((x0, x1), spans) in enumerate(lines)
                ],
            }
        ]
    }


def _code(text: str, x0: float, block: int = 0) -> PdfTextBlock:
    """Build one monospace line with 5-point characters.

    Args:
        text: Visible line text.
        x0: X of the first visible character.
        block: Block index.

    Returns:
        Monospace text block.
    """

    return PdfTextBlock(
        text=text,
        bbox=(x0, 0.0, x0 + 5.0 * len(text), 9.0),
        max_size=8.5,
        bold=False,
        block_index=block,
        monospace=True,
        text_x0=x0,
        char_width=5.0,
    )


def _prose(text: str, block: int = 0) -> PdfTextBlock:
    """Build one body line.

    Args:
        text: Line text.
        block: Block index.

    Returns:
        Proportional-font text block.
    """

    return PdfTextBlock(
        text=text,
        bbox=(72.0, 0.0, 300.0, 12.0),
        max_size=10.0,
        bold=False,
        block_index=block,
    )


def test_monospace_detected_by_flag_or_font_name() -> None:
    """Flag bit 3 or a monospace font name marks the line; mixed lines do not."""

    blocks, _sizes = extract_pdf_text_blocks(
        _page(
            ((89.0, 134.0), [_span("def f(x):", font="AnyFont", flags=8)]),
            ((89.0, 129.0), [_span("x = 1", font="UbuntuMono-Regular")]),
            (
                (72.0, 300.0),
                [_span("Call ", font="MinionPro"), _span("f()", font="UbuntuMono")],
            ),
        )
    )
    assert [block.monospace for block in blocks] == [True, True, False]


def test_leading_spaces_move_text_x0() -> None:
    """Leading spaces in span text shift the visible start, not the text."""

    blocks, _sizes = extract_pdf_text_blocks(
        _page(((89.0, 149.0), [_span("    return x", font="Courier")]))
    )
    assert blocks[0].text == "return x"
    assert blocks[0].char_width == 5.0
    assert blocks[0].text_x0 == 109.0


def test_indent_rebuilt_from_x_offset() -> None:
    """A line 20 points right of the run start gets four spaces."""

    lines = ((P, _code("def f(x):", 89.0)), (P, _code("return x", 109.0)))
    indented = indent_pdf_code_lines(lines)
    assert [block.text for _kind, block in indented] == ["def f(x):", "    return x"]


def test_code_lines_join_with_newline_and_keep_hyphens() -> None:
    """Indented code joins with a newline; the hyphen rule never applies."""

    assert join_pdf_lines(_code("a = b -", 89.0), _code("    c", 109.0)) == (
        "a = b -\n    c"
    )
    assert join_pdf_lines(_code("x = 1", 89.0), _code("y = 2", 89.0, block=1)) == (
        "x = 1 y = 2"
    )


def test_indented_code_keeps_line_breaks() -> None:
    """A dedent or indented body line starts a new layout line."""

    assert join_pdf_lines(_code("def f(x):", 89.0), _code("    return x", 109.0)) == (
        "def f(x):\n    return x"
    )
    assert join_pdf_lines(_code("    return x", 109.0), _code("y = 2", 89.0)) == (
        "    return x\ny = 2"
    )


def test_prose_code_switch_uses_paragraph_delimiter() -> None:
    """Prose followed by code, or code followed by prose, splits paragraphs."""

    assert join_pdf_lines(_prose("Example:"), _code("x = 1", 89.0)) == (
        f"Example:{PARAGRAPH_DELIMITER}x = 1"
    )
    assert join_pdf_lines(_code("x = 1", 89.0), _prose("Next we")) == (
        f"x = 1{PARAGRAPH_DELIMITER}Next we"
    )


def test_merge_keeps_function_layout() -> None:
    """A three-line function survives indentation plus merge."""

    lines = (
        (P, _prose("The helper is:")),
        (P, _code("def f(x):", 89.0)),
        (P, _code("y = x + 1", 109.0)),
        (P, _code("return y", 109.0)),
    )
    merged = merge_consecutive_pdf_paragraphs(indent_pdf_code_lines(lines))
    assert len(merged) == 1
    assert merged[0][1].text == (
        f"The helper is:{PARAGRAPH_DELIMITER}def f(x):\n    y = x + 1\n    return y"
    )


def test_prose_lines_unchanged() -> None:
    """Non-monospace lines keep the existing space join."""

    assert join_pdf_lines(_prose("one"), _prose("two")) == "one two"
