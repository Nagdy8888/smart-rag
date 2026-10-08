"""Grounded company-document generation and extractive mock answers."""

from __future__ import annotations

from smart_rag_core.query_answer.generate_anchor_salvage import (
    salvage_anchor_claim_fill,
    salvage_named_page_claim_fill,
)
from smart_rag_core.query_answer.generate_code_salvage import (
    salvage_named_code_definition,
    salvage_named_table_block,
)
from smart_rag_core.query_answer.generate_company import (
    generate_grounded_answer,
    mock_answer_payload,
)
from smart_rag_core.query_answer.generate_literals import (
    distinctive_query_literals,
    distinctive_query_names,
    significant_query_terms,
)

__all__ = [
    "distinctive_query_literals",
    "distinctive_query_names",
    "generate_grounded_answer",
    "mock_answer_payload",
    "salvage_anchor_claim_fill",
    "salvage_named_code_definition",
    "salvage_named_page_claim_fill",
    "salvage_named_table_block",
    "significant_query_terms",
]
