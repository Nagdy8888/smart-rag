"""Literal native artifacts need no generative answer call, but still need verification."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.format_shape import format_requested_answer_shape
from smart_rag_core.query_answer.generate_code_salvage import (
    salvage_named_code_definition,
    salvage_named_table_block,
)
from smart_rag_core.query_answer.language import requested_answer_language
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope


def canonical_reproduction_payload(
    fusion: FusionResult, query: str
) -> AnswerPayload | None:
    """Copy only explicit English code/table requests without transformations or analysis."""
    if (
        requested_answer_language(query) != "en"
        or not re.search(r"(?i)\b(?:reproduce|copy|show|render)\b", query)
        or not re.search(r"(?i)\b(?:markdown|pipe table|fenced|verbatim)\b", query)
        or re.search(
            r"(?i)\b(?:and|explain|describe|how|why|compare|translate|calculate|filter|sort|only|excluding|difference|sum|average|total)\b",
            query,
        )
    ):
        return None
    empty = AnswerPayload(
        answer_text="Insufficient authorized evidence.", status="refused"
    )
    payload = salvage_named_code_definition(empty, fusion, user_query=query)
    payload = salvage_named_table_block(payload, fusion, user_query=query)
    if not payload.atomic_links:
        return None
    return format_requested_answer_shape(payload, user_query=query).model_copy(
        update={"answer_origin": KnowledgeScope.COMPANY_DOCUMENTS}
    )
