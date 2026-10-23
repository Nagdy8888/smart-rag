"""Restore a function's base indentation across a proven native PDF page break."""

from __future__ import annotations

import ast
import re
import textwrap

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage

_SIGNATURE = re.compile(
    r"(?:@tool\s+)?(?:async\s+)?def\s+\w+\([^\n]*\)\s*(?:->[^:\n]+)?\s*:"
)
_FOOTER = re.compile(
    r"(?:[A-Za-z][A-Za-z -]+\s*\|\s*\d+|\d+\s*\|\s*Chapter\s+\d+[^\n]*|\d+)"
)


def restore_code_continuation(
    payload: AnswerPayload, fusion: FusionResult, pattern: re.Pattern[str]
) -> AnswerPayload | None:
    """Join adjacent native fragments only when a parent proves their order.

    Args:
        payload: Current company answer; never used as reconstruction evidence.
        fusion: Already authorized fitted canonical sources.
        pattern: The function explicitly named by the user.

    Returns:
        Exact source statements with a restored function-level indentation and
        two exact source citations, or None for absent/ambiguous continuity.
        No source text, inner indentation, token, or statement is rewritten.
    """
    candidates: dict[str, tuple[str, ScoredPassage, str, ScoredPassage, str]] = {}
    for head in fusion.evidence:
        match = pattern.search(head.citation_text)
        if head.content_kind != "code" or head.page_number is None or match is None:
            continue
        signature = head.citation_text[match.start() :].strip()
        if not _SIGNATURE.fullmatch(signature) or len(signature) > 1000:
            continue
        # Parent expansion can retain the entire canonical section while its
        # second native child falls outside the fitted evidence budget.
        for parent in fusion.evidence:
            if parent.chunk_id != head.parent_chunk_id:
                continue
            if (
                parent.document_id != head.document_id
                or parent.version_id != head.version_id
            ):
                continue
            if parent.citation_text.count(signature) != 1:
                continue
            rest = parent.citation_text.split(signature, 1)[1].strip("\r\n")
            blocks = rest.split("\n\n")
            if len(blocks) < 2 or not _FOOTER.fullmatch(blocks[0].strip()):
                continue
            body = blocks[1].strip("\r\n")
            display = signature + "\n" + textwrap.indent(body, "    ")
            if _eligible_body(body) and len(display) <= 1980 and _one_function(display):
                candidates.setdefault(
                    signature + "\n" + body, (display, head, signature, parent, body)
                )
        for tail in fusion.evidence:
            body = tail.citation_text.strip("\r\n")
            if not _adjacent(head, tail) or not _eligible_body(body):
                continue
            shared_parent = bool(
                head.parent_chunk_id and head.parent_chunk_id == tail.parent_chunk_id
            )
            if not shared_parent and not _parent_proves_join(
                fusion, head, signature, body
            ):
                continue
            steps = re.findall(
                r"(?m)^(?:async\s+)?def[^\n]+:\n([ \t]+)\S", head.citation_text
            )
            indent = steps[-1] if steps else "    "
            display = signature + "\n" + textwrap.indent(body, indent)
            if len(display) > 1980 or not _one_function(display):
                continue
            candidates.setdefault(
                signature + "\n" + body, (display, head, signature, tail, body)
            )
    if len(candidates) != 1:
        return None
    display, head, signature, tail, body = next(iter(candidates.values()))
    if display in payload.answer_text:
        return payload
    link_id = "code-def-1"
    return payload.model_copy(
        update={
            "answer_text": display,
            "paragraphs": (
                AnswerParagraph(paragraph_index=0, text=display, link_ids=(link_id,)),
            ),
            "atomic_links": (
                AtomicLink(
                    link_id=link_id,
                    claim=display,
                    chunk_ids=(head.chunk_id, tail.chunk_id),
                    kind="fact",
                    priority=10,
                ),
            ),
            "citations": tuple(
                AnswerCitation(
                    chunk_id=source.chunk_id,
                    span=span,
                    atomic_link_id=link_id,
                    paragraph_index=0,
                )
                for source, span in ((head, signature), (tail, body))
            ),
            "table_citations": (),
            "composed_conclusion": None,
            "refused_links": (),
            "status": "complete",
        }
    )


def _adjacent(head: ScoredPassage, tail: ScoredPassage) -> bool:
    """Require the same document version, section, and next physical page."""
    return bool(
        tail.content_kind == "code"
        and head.document_id == tail.document_id
        and head.version_id == tail.version_id
        and head.section_path
        and head.section_path == tail.section_path
        and head.page_number is not None
        and tail.page_number == head.page_number + 1
    )


def _eligible_body(body: str) -> bool:
    """A dedented continuation must finish with a function-level return."""
    lines = [line for line in body.splitlines() if line.strip()]
    return bool(
        lines
        and len(body) <= 1000
        and not lines[0][:1].isspace()
        and re.match(r"return\b", lines[-1])
        and not re.search(r"(?m)^(?:@|(?:async\s+)?def\b|class\b)", body)
    )


def _parent_proves_join(
    fusion: FusionResult, head: ScoredPassage, signature: str, body: str
) -> bool:
    """The full exact fragments must be separated only by blank/footer lines."""
    for parent in fusion.evidence:
        if (parent.document_id, parent.version_id) != (
            head.document_id,
            head.version_id,
        ):
            continue
        start = parent.citation_text.find(signature)
        if start < 0:
            continue
        end = start + len(signature)
        at = parent.citation_text.find(body, end)
        if at < 0:
            continue
        gap = parent.citation_text[end:at]
        if len(gap) <= 300 and all(
            not line.strip() or _FOOTER.fullmatch(line.strip())
            for line in gap.splitlines()
        ):
            return True
    return False


def _one_function(display: str) -> bool:
    """Parse syntax without executing, importing, or repairing any statements."""
    try:
        tree = ast.parse(display)
    except (SyntaxError, ValueError):
        return False
    definitions = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return len(tree.body) == 1 and len(definitions) == 1
