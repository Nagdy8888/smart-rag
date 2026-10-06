"""Code and table paragraphs keep their lines when prose is split (chunking_v3)."""

from __future__ import annotations

from smart_rag_core.ingestion.chunking.limits import (
    LINE_STRUCTURED_MAX_TOKENS,
    PASSAGE_HARD_MAX_TOKENS,
    PASSAGE_TARGET_MAX_TOKENS,
)
from smart_rag_core.ingestion.chunking.splitter import (
    ProseSegment,
    split_prose_segments,
)
from smart_rag_core.ingestion.chunking.tokenizer import count_tokens

HEADER = "| Name | Value |\n| --- | --- |"


def _code_text(min_tokens: int) -> str:
    """Build a function whose token count first exceeds ``min_tokens``.

    Args:
        min_tokens: Threshold to pass.

    Returns:
        Multi-line indented code.
    """

    lines = ["def build(x):"]
    index = 0
    while count_tokens("\n".join(lines)) <= min_tokens:
        lines.append(f"    value_{index} = compute(x, {index})")
        index += 1
    return "\n".join(lines)


def _table_text(min_tokens: int) -> str:
    """Build a pipe table whose token count first exceeds ``min_tokens``.

    Args:
        min_tokens: Threshold to pass.

    Returns:
        Header, separator, and body rows.
    """

    rows = [HEADER]
    index = 0
    while count_tokens("\n".join(rows)) <= min_tokens:
        rows.append(f"| item {index} | value {index} |")
        index += 1
    return "\n".join(rows)


def _split(text: str) -> list[str]:
    """Split one paragraph through the public prose splitter.

    Args:
        text: Paragraph text.

    Returns:
        Passage texts.
    """

    segment = ProseSegment(text=text, element_ids=("e1",), locators=({"page": 1},))
    return [passage.text for passage in split_prose_segments([segment])]


def _body(text: str, index: int) -> str:
    """Drop the overlap prefix that later passages start with.

    Args:
        text: Passage text.
        index: Passage position.

    Returns:
        Passage text without the prefix.
    """

    return text.split("\n\n", 1)[-1] if index > 0 else text


def test_code_over_target_but_under_keep_limit_stays_whole() -> None:
    """A 401-536 token listing is one passage with its newlines."""

    code = _code_text(PASSAGE_TARGET_MAX_TOKENS)
    assert PASSAGE_TARGET_MAX_TOKENS < count_tokens(code) <= LINE_STRUCTURED_MAX_TOKENS
    assert _split(code) == [code]


def test_long_code_splits_only_at_line_ends() -> None:
    """Every passage body is made of whole original lines."""

    code = _code_text(LINE_STRUCTURED_MAX_TOKENS)
    original = set(code.split("\n"))
    passages = _split(code)
    assert len(passages) >= 2
    for index, passage in enumerate(passages):
        assert count_tokens(passage) <= PASSAGE_HARD_MAX_TOKENS
        assert set(_body(passage, index).split("\n")) <= original


def test_long_table_repeats_header_in_every_fragment() -> None:
    """Each passage body starts with the header and separator rows."""

    passages = _split(_table_text(LINE_STRUCTURED_MAX_TOKENS))
    assert len(passages) >= 2
    for index, passage in enumerate(passages):
        assert _body(passage, index).startswith(HEADER + "\n| item ")


def test_single_oversized_line_still_bounded() -> None:
    """A line longer than the keep limit falls back to token windows."""

    text = "short line\n" + " ".join(f"w{index}" for index in range(900))
    for passage in _split(text):
        assert count_tokens(passage) <= PASSAGE_HARD_MAX_TOKENS
