"""Display-only Markdown fences and pipe tables for requested answer shapes.

Citation ``span`` values stay exact evidence substrings. Fences and pipe
separators are applied only to claim / paragraph / ``answer_text`` when the
user ask requests that shape.
"""

from __future__ import annotations

import re
from typing import Literal

from smart_rag_core.query_answer.models import (
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.paragraphs import with_derived_answer_text
from smart_rag_core.query_answer.stacked_table import (
    repair_missing_row_header,
    stacked_records_to_table,
)
from smart_rag_core.query_answer.versions import MAX_CLAIM_CHARS
from smart_rag_core.retrieval.rerank import (
    named_code_definition_ids,
    named_table_captions,
)

RequestedShape = Literal["code_fence", "pipe_table", "none"]

_FENCE_ASK = re.compile(
    r"(?i)\breproduce\b.{0,120}\b(?:code|fenced|python|@tool|\bdef\b)"
    r"|\bfenced\b.{0,80}\b(?:python|code|block)"
    r"|\bcode\s+block\b"
    r"|\bfenced\s+python\b"
    r"|```"
)
_PIPE_TABLE_ASK = re.compile(
    r"(?i)\breproduce\b.{0,120}\btable\b"
    r"|\btable\b.{0,80}\b(?:markdown|pipe)\b"
    r"|\bMarkdown\s+pipe\s+table\b"
    r"|\bpipe\s+table\b"
)
# Exact-phrase asks may name ``Table N-M`` as a locator without requesting
# a Markdown pipe reshape of a one-line gold span.
_EXACT_PHRASE_SHAPE_ASK = re.compile(
    r"(?i)\bexact\s+(?:wording|phrase|name|code\s+fragment)\b"
    r"|\bcode\s+fragment\s+from\s+the\s+page\b"
)
_FENCE_BLOCK = re.compile(
    r"^\s*```([a-zA-Z0-9_+-]*)[ \t]*\n([\s\S]*?)\n[ \t]*```[ \t]*\s*$"
)
_FENCE_ANY = re.compile(r"```([a-zA-Z0-9_+-]*)[ \t]*\n([\s\S]*?)\n[ \t]*```")
_MD_TABLE_ROW = re.compile(r"(?m)^\s*\|.+\|.+\|")
_MD_TABLE_SEP = re.compile(r"(?m)^\s*\|?\s*:?-{3,}")
_CODE_LOOKS = re.compile(
    r"(?m)^(?:@tool\b|(?:async\s+)?def\s+\w+|class\s+\w+|from\s+\w+|import\s+\w)"
)


def requested_answer_shape(user_query: str) -> RequestedShape:
    """Return the Markdown shape the user explicitly asked for.

    Args:
        user_query: Original user text. Untrusted.

    Returns:
        ``code_fence``, ``pipe_table``, or ``none``.
    """

    query = user_query or ""
    # Bare ``Table N-M`` (via named captions) is not enough: exact-phrase
    # asks locate a cell without requesting pipe-table display reshape.
    wants_table = bool(
        _PIPE_TABLE_ASK.search(query)
        or (
            named_table_captions(query)
            and _EXACT_PHRASE_SHAPE_ASK.search(query) is None
        )
    )
    wants_code = bool(_FENCE_ASK.search(query) or named_code_definition_ids(query))
    if wants_table and wants_code:
        if re.search(r"(?i)pipe\s+table|Markdown\s+pipe", query):
            return "pipe_table"
        if re.search(r"(?i)fenced|code\s+block|```", query):
            return "code_fence"
        return "pipe_table"
    if wants_table:
        return "pipe_table"
    if wants_code:
        return "code_fence"
    return "none"


def strip_markdown_fences_for_literal_guard(claim: str) -> str:
    """Remove outer Markdown fences so literal guards see only source body.

    Args:
        claim: Fact claim that may include a display fence.

    Returns:
        Claim text without outer `` ``` `` wrappers.
    """

    text = claim.replace("\r\n", "\n")
    match = _FENCE_BLOCK.match(text)
    if match is not None:
        return match.group(2).strip()
    match = _FENCE_ANY.search(text)
    if match is not None:
        return match.group(2).strip()
    return text


def answer_has_code_fence(text: str) -> bool:
    """Return whether ``text`` already contains a fenced code block.

    Args:
        text: Answer or claim body.

    Returns:
        True when a Markdown fence is present.
    """

    return _FENCE_ANY.search(text.replace("\r\n", "\n")) is not None


def answer_has_markdown_pipe_table(text: str) -> bool:
    """Return whether ``text`` already has a qualifying Markdown pipe table.

    Args:
        text: Answer or claim body.

    Returns:
        True when there are two pipe rows, or one pipe row plus a separator.
    """

    normalized = text.replace("\r\n", "\n")
    rows = _MD_TABLE_ROW.findall(normalized)
    if len(rows) >= 2:
        return True
    if len(rows) >= 1 and _MD_TABLE_SEP.search(normalized):
        return True
    return False


def ensure_fenced_code(display: str, *, language: str = "python") -> str:
    """Wrap ``display`` in a Markdown fence when it is not already fenced.

    Args:
        display: Bare or partially formatted code body.
        language: Fence language tag.

    Returns:
        Fenced block using only single newlines (no blank lines).
    """

    body = re.sub(r"\n{2,}", "\n", display.replace("\r\n", "\n")).strip()
    if not body:
        return display
    existing = _FENCE_BLOCK.match(body) or _FENCE_ANY.search(body)
    if existing is not None:
        inner = existing.group(2).strip()
        lang = (existing.group(1) or language).strip() or language
        block = f"```{lang}\n{inner}\n```"
        # One provider claim may contain an introduction, code and its
        # explanation. Finding a fence must never discard its surrounding text.
        return "\n".join(
            part
            for part in (
                body[: existing.start()].strip(),
                block,
                body[existing.end() :].strip(),
            )
            if part
        )
    if not _CODE_LOOKS.search(body) and "return " not in body:
        # Still wrap when the ask requested a fence; body may be dense OCR.
        pass
    lang = language.strip() or "python"
    return f"```{lang}\n{body}\n```"


def ensure_markdown_pipe_table(display: str) -> str:
    """Normalize or build a GFM pipe table from salvage/OCR table text.

    Args:
        display: Bare table dump, compacted pipes, or existing pipe table.

    Returns:
        Pipe table with header, separator, and at least one data row when
        conversion is possible; otherwise the original text.
    """

    text = re.sub(r"\n{2,}", "\n", display.replace("\r\n", "\n")).strip()
    if not text:
        return display
    normalized = _expand_compact_pipe_rows(text)
    if answer_has_markdown_pipe_table(normalized):
        return repair_missing_row_header(normalized)
    stacked = stacked_records_to_table(normalized)
    if stacked is not None:
        return stacked
    return _ocr_body_to_pipe_table(normalized)


def format_requested_answer_shape(
    payload: AnswerPayload,
    *,
    user_query: str,
) -> AnswerPayload:
    """Apply requested fence/pipe formatting to display fields only.

    Citation ``span`` values are left unchanged. Refused or empty answers
    are unchanged. Idempotent when the shape is already present.

    Args:
        payload: Released company answer.
        user_query: Original user text. Untrusted.

    Returns:
        Payload with formatted claim / paragraph / ``answer_text`` when
        the ask requested a shape; otherwise ``payload``.
    """

    shape = requested_answer_shape(user_query)
    if shape == "none":
        return payload
    if payload.status == "refused" and not payload.atomic_links:
        return payload
    if len(payload.paragraphs) > 1:
        # Shape artifacts individually. Formatting the joined answer used to
        # extract its first fence, dropping every explanation after the code
        # and collapsing citation ownership onto paragraph zero.
        paragraphs: list[AnswerParagraph] = []
        replacements: dict[str, str] = {}
        for paragraph in payload.paragraphs:
            text = paragraph.text
            artifact = (
                bool(_CODE_LOOKS.search(text) or _FENCE_ANY.search(text))
                if shape == "code_fence"
                else answer_has_markdown_pipe_table(text)
            )
            if artifact:
                formatted = (
                    ensure_fenced_code(text)
                    if shape == "code_fence"
                    else ensure_markdown_pipe_table(text)
                )
                if len(formatted) <= MAX_CLAIM_CHARS:
                    text = formatted
                    replacements.update(dict.fromkeys(paragraph.link_ids, text))
            paragraphs.append(paragraph.model_copy(update={"text": text}))
        return with_derived_answer_text(
            payload.model_copy(
                update={
                    "paragraphs": tuple(paragraphs),
                    "atomic_links": tuple(
                        link.model_copy(update={"claim": replacements[link.link_id]})
                        if link.link_id in replacements
                        else link
                        for link in payload.atomic_links
                    ),
                }
            )
        )
    body = (payload.answer_text or "").strip()
    if not body and payload.paragraphs:
        body = payload.paragraphs[0].text.strip()
    if not body and payload.atomic_links:
        body = payload.atomic_links[0].claim.strip()
    if not body:
        return payload

    if shape == "code_fence":
        if answer_has_code_fence(body) and _FENCE_BLOCK.match(
            body.replace("\r\n", "\n").strip()
        ):
            formatted = ensure_fenced_code(body)
        else:
            formatted = ensure_fenced_code(body)
    else:
        formatted = ensure_markdown_pipe_table(body)

    formatted = re.sub(r"\n{2,}", "\n", formatted).strip()
    if not formatted or formatted == body:
        if shape == "pipe_table" and answer_has_markdown_pipe_table(formatted):
            pass
        elif shape == "code_fence" and answer_has_code_fence(formatted):
            pass
        elif formatted == body:
            return payload

    if len(formatted) > MAX_CLAIM_CHARS:
        return payload.model_copy(update={"status": "partial"})
    claim_text = formatted
    paragraph_text = formatted
    link_ids = (
        payload.paragraphs[0].link_ids
        if payload.paragraphs
        else tuple(item.link_id for item in payload.atomic_links[:1])
    )
    if not link_ids and payload.atomic_links:
        link_ids = (payload.atomic_links[0].link_id,)
    paragraph = AnswerParagraph(
        paragraph_index=0,
        text=paragraph_text,
        link_ids=link_ids or (),
    )
    citations = tuple(
        item.model_copy(update={"paragraph_index": 0}) for item in payload.citations
    )
    links: list[AtomicLink] = []
    for index, link in enumerate(payload.atomic_links):
        if index == 0:
            links.append(link.model_copy(update={"claim": claim_text}))
        else:
            links.append(link)
    if not links and link_ids:
        # Keep paragraphs even when links were already emptied.
        pass
    updated = payload.model_copy(
        update={
            "paragraphs": (paragraph,),
            "citations": citations,
            "atomic_links": tuple(links) if links else payload.atomic_links,
            "answer_text": paragraph_text,
        }
    )
    return with_derived_answer_text(updated)


def _expand_compact_pipe_rows(text: str) -> str:
    """Insert newlines between compacted pipe header/separator/data segments.

    Args:
        text: Possibly single-line pipe table.

    Returns:
        Multiline pipe table candidate.
    """

    if "\n" in text and answer_has_markdown_pipe_table(text):
        return text
    if text.count("|") < 4:
        return text
    # Split after separator-like segments and between adjacent row starts.
    working = text
    working = re.sub(
        r"(\|[ \t]*:?-{3,}[^\n|]*\|(?:[ \t]*:?-{3,}[^\n|]*\|)*)",
        r"\n\1\n",
        working,
    )
    working = re.sub(r"\|\s*\|", "|\n|", working)
    lines = [line.strip() for line in working.splitlines() if line.strip()]
    if not lines:
        return text
    return "\n".join(lines)


_COLUMN_GAP = re.compile(r"[ \t]*\t[ \t]*| {2,}")


def _ocr_body_to_pipe_table(text: str) -> str:
    """Build a pipe table when every body line shares one column count.

    A tab or a run of two or more spaces is a column gap. The first aligned
    line becomes the header. Lines that do not share that structure are
    returned unchanged so adjacent cells are not zipped into a fake pair.

    Args:
        text: Non-pipe table body.

    Returns:
        GFM pipe table, or the original text when columns are not aligned.
    """

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return text
    caption = ""
    body_lines = lines
    if re.search(r"(?i)^Table\s+\d+-\d+", lines[0]):
        caption = lines[0]
        body_lines = lines[1:]
    if len(body_lines) < 2:
        return text
    parsed = [_split_aligned_cells(line) for line in body_lines]
    if any(row is None for row in parsed):
        return text
    rows = [row for row in parsed if row is not None]
    width = len(rows[0])
    if width < 2 or any(len(row) != width for row in rows):
        return text
    prefix = f"{caption}\n" if caption else ""
    header = rows[0]
    head = "| " + " | ".join(_cell(value) for value in header) + " |"
    separator = "| " + " | ".join("---" for _ in range(width)) + " |"
    data = "\n".join(
        "| " + " | ".join(_cell(value) for value in row) + " |" for row in rows[1:]
    )
    return f"{prefix}{head}\n{separator}\n{data}"


def _split_aligned_cells(line: str) -> list[str] | None:
    """Split one line on tab or multi-space column gaps.

    Args:
        line: Candidate table row.

    Returns:
        Cell strings when the line has at least two columns, else None.
    """

    parts = [part.strip() for part in _COLUMN_GAP.split(line.strip()) if part.strip()]
    if len(parts) < 2:
        return None
    return parts


def _cell(value: str) -> str:
    """Escape pipe characters for one table cell.

    Args:
        value: Raw cell text.

    Returns:
        Cell safe for a single pipe-table row.
    """

    return re.sub(r"\s+", " ", value.replace("|", "/")).strip()


__all__ = [
    "RequestedShape",
    "answer_has_code_fence",
    "answer_has_markdown_pipe_table",
    "ensure_fenced_code",
    "ensure_markdown_pipe_table",
    "format_requested_answer_shape",
    "requested_answer_shape",
    "strip_markdown_fences_for_literal_guard",
]
