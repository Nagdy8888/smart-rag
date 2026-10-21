"""Syntax-only diagnostics for faithfully reproduced named Python examples."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.retrieval.rerank import named_code_definition_ids

SOURCE_CODE_SYNTAX_INVALID = "source_code_syntax_invalid"
_PYTHON = re.compile(r"```(?:python|py)[ \t]*\n(.*?)\n[ \t]*```", re.S | re.I)


def missing_requested_definition(payload: AnswerPayload, *, user_query: str) -> bool:
    """Reject unrelated fenced prose as the answer to a named-function request.

    This structural identity check does not certify source correctness or syntax.
    The original source may have syntax errors after a real matching definition.
    """
    names = named_code_definition_ids(user_query)
    if not names or payload.status == "refused":
        return False
    blocks = _PYTHON.findall(payload.answer_text)
    return any(
        not any(
            re.search(rf"(?m)^\s*(?:async\s+)?def\s+{re.escape(name)}\s*\(", block)
            for block in blocks
        )
        for name in names
    )


def has_source_code_syntax_issue(payload: AnswerPayload, *, user_query: str) -> bool:
    """Compile quoted Python without executing, importing, or fixing its code.

    Args:
        payload: Grounded, formatted company answer after verification.
        user_query: Original question, which must name a requested function.

    Returns:
        True when a requested Python example fails syntax compilation. This is
        a source-quality limitation, not a new support verdict or a code fix.
    """
    if payload.status == "refused" or not named_code_definition_ids(user_query):
        return False
    for block in _PYTHON.findall(payload.answer_text):
        try:
            compile(block, "<cited-source-example>", "exec")
        except (SyntaxError, ValueError):
            return True
    return False
