"""``hybrid_seed_terms`` returns only identifiers the user typed."""

from __future__ import annotations

import pytest
from smart_rag_core.retrieval.rerank import hybrid_seed_terms, literal_anchor_ask

QUERIES = (
    "Reproduce the parse_invoice function as a fenced Python code block.",
    "Show def load_rows(path) and the RowCache class as fenced Python code.",
    "Reproduce Table 3-2 (Storage options) as a Markdown pipe table.",
    "What does the document say about retry budgets?",
    "Reproduce the ChatClient constructor call as a fenced code block.",
)


@pytest.mark.parametrize("query", QUERIES)
def test_every_seed_term_occurs_in_the_query(query: str) -> None:
    """No seed term is invented from document-side vocabulary."""

    lowered = query.casefold()
    for term in hybrid_seed_terms(query):
        assert term.casefold() in lowered


def test_code_identifier_is_seeded() -> None:
    """A snake_case identifier in a code ask is seeded."""

    assert "parse_invoice" in hybrid_seed_terms(QUERIES[0])


def test_plain_question_has_no_seeds() -> None:
    """A prose question gets no seed terms."""

    assert hybrid_seed_terms(QUERIES[3]) == ()


def test_literal_anchor_ask_is_code_or_table_only() -> None:
    """Only code-reproduce and table-reproduce asks trigger fused reloads."""

    assert literal_anchor_ask(QUERIES[0])
    assert literal_anchor_ask(QUERIES[2])
    assert not literal_anchor_ask(QUERIES[3])
