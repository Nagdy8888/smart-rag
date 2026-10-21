"""Select complete canonical function bodies within existing answer limits."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.versions import MAX_CLAIM_CHARS
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage

_RUNNING_FOOTER = re.compile(r"(?m)^[A-Z][A-Za-z -]{3,}\s+\|\s+\d+[ \t]*$")

NEXT_CODE_DEF = re.compile(
    r"(?<![A-Za-z0-9_])(?:@tool\b|(?:async\s+)?def\s+\w+|class\s+\w+)"
)


CODE_SECTION_BREAK = re.compile(r"#\s*--\s*\d+")


_LLM_ASSIGN_LOOKBACK = re.compile(r"(?i)(?:llm\s*=\s*)?ChatOpenAI\s*\([^)]*\)\s*")


_AFTER_CODE_PROSE = re.compile(
    r"\n[ \t]*\n(?=[A-Z][A-Za-z -]{8,}\s(?:is|are|can|will|offers?|provides?)\s)"
)


def best_code_definition_match(
    fusion: FusionResult,
    pattern: re.Pattern[str],
    *,
    user_query: str | None = None,
) -> tuple[ScoredPassage, re.Match[str], str] | None:
    """Return the best definition hit and its extractable block.

    Prefers a definition with a body over a page-ending signature, then an
    earlier ``def`` offset (primary definition over a reprint), ``YOUR_*``
    placeholders, better hybrid rank, and longer bodies.

    Args:
        fusion: Fitted canonical evidence.
        pattern: Compiled ``def`` / ``@tool def`` pattern.
        user_query: Original user text for overlap ranking. Untrusted.

    Returns:
        Passage, match, and exact block, or ``None``.
    """

    ranked: list[tuple[int, int, int, int, ScoredPassage, re.Match[str], str]] = []
    for item in fusion.evidence:
        text = item.citation_text or ""
        match = pattern.search(text)
        if match is None:
            continue
        span = _extract_code_definition_block(text, match)
        if not span:
            continue
        ranked.append(
            (
                match.start(),
                1 if "YOUR_" in span else 0,
                item.hybrid_rank or 10_000,
                len(span),
                item,
                match,
                span,
            )
        )
    if not ranked:
        return None
    ranked.sort(
        key=lambda row: (
            not _has_code_body(row[6]),
            row[0],
            -row[1],
            row[2],
            -row[3],
            row[4].chunk_id,
        )
    )
    _offset, _your, _rank, _length, item, match, span = ranked[0]
    return item, match, span


def _has_code_body(span: str) -> bool:
    """Distinguish a complete fitting definition from a page-ending header.

    Args:
        span: Extracted canonical definition candidate.

    Returns:
        True for a one-line body or substantive lines after the signature.
    """
    lines = span.splitlines()
    if not lines:
        return False
    if re.search(r"\)\s*(?:->[^:]+)?\s*:\s*\S", lines[0]):
        return True
    return any(
        line.strip()
        and not line.lstrip().startswith("#")
        and not _RUNNING_FOOTER.match(line)
        for line in lines[1:]
    )


def _extract_code_definition_block(text: str, match: re.Match[str]) -> str:
    """Copy a bounded ``def`` / ``@tool`` block from ``text``.

    Continues through blank lines inside the body so docstring-separated
    assignments (for example ``YOUR_*`` placeholders) stay in the span.
    Stops before a sibling ``def`` / ``@tool`` / ``class`` even when OCR
    flattened the page onto one line, and before book section markers
    like ``# -- 2)``. When the definition is ``call_model``, includes a
    preceding ``ChatOpenAI(...)`` assignment in the lookback window.
    ``replace_with_extractive_block`` collapses blank lines for the
    paragraph contract while keeping this exact span for citations.

    Args:
        text: Passage citation text.
        match: Match for the definition line inside ``text``.

    Returns:
        Exact substring of ``text``, capped at ``MAX_CITATION_SPAN_CHARS``.
    """

    start = match.start()
    lookback = text[max(0, start - 40) : start]
    tool_at = lookback.rfind("@tool")
    if tool_at >= 0:
        start = max(0, start - 40) + tool_at
    # Include preceding ChatOpenAI assignment for call_model nodes.
    if re.search(r"(?i)def\s+call_model\s*\(", match.group(0)):
        prefix = text[max(0, start - 220) : start]
        llm = None
        for candidate in _LLM_ASSIGN_LOOKBACK.finditer(prefix):
            llm = candidate
        if llm is not None:
            start = max(0, start - 220) + llm.start()
    rest = text[match.end() :]
    end = match.end() + len(rest)
    next_def = NEXT_CODE_DEF.search(rest)
    if next_def is not None:
        end = min(end, match.end() + next_def.start())
    section = CODE_SECTION_BREAK.search(rest)
    if section is not None:
        end = min(end, match.end() + section.start())
    block = text[start:end].strip()
    if not block or block not in text:
        block = match.group(0).strip()
    if not block or block not in text:
        return ""
    lines = block.splitlines(keepends=True)
    header_index = next(
        (i for i, line in enumerate(lines) if re.match(r"(?:async\s+)?def\s", line)),
        None,
    )
    if header_index is not None:
        body = lines[header_index + 1 :]
        first = next((line for line in body if line.strip()), "")
        if first[:1].isspace():
            # With preserved indentation, a following module-level statement
            # belongs to the example harness, not the requested function.
            for index, line in enumerate(body):
                if line.strip() and not line[:1].isspace():
                    block = "".join(lines[: header_index + 1 + index]).rstrip()
                    break
    prose = _AFTER_CODE_PROSE.search(block)
    if prose is not None:
        block = block[: prose.start()].rstrip()
    # One extra character lets the release helper mark an over-cap function
    # partial instead of presenting a silently cut implementation as complete.
    return block[: MAX_CLAIM_CHARS - 19]
