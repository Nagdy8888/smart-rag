"""Unit tests for requested code-fence and pipe-table answer formatting."""

from __future__ import annotations

from smart_rag_core.query_answer.format_shape import (
    answer_has_code_fence,
    answer_has_markdown_pipe_table,
    ensure_fenced_code,
    ensure_markdown_pipe_table,
    format_requested_answer_shape,
    requested_answer_shape,
    strip_markdown_fences_for_literal_guard,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.release import drop_ungrounded_literals

from tests.support.answer_verifier import (
    verifier_fusion,
    verifier_passage,
    verifier_uid,
)


def _payload(text: str, *, chunk_n: int = 1) -> AnswerPayload:
    """Build a one-claim company payload for format tests."""

    chunk_id = verifier_uid(chunk_n)
    link = AtomicLink(
        link_id="link-1",
        claim=text,
        chunk_ids=(chunk_id,),
        kind="fact",
        priority=10,
    )
    return AnswerPayload(
        answer_text=text,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=text, link_ids=("link-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span=text[:200],
                atomic_link_id="link-1",
                paragraph_index=0,
            ),
        ),
        atomic_links=(link,),
        status="complete",
    )


def test_requested_shape_detects_fence_and_pipe() -> None:
    """Detect fenced-code and Markdown-pipe asks without false positives."""

    assert (
        requested_answer_shape(
            "reproduce the top_router function as a fenced Python code block"
        )
        == "code_fence"
    )
    assert (
        requested_answer_shape(
            "render Table 7-1 as a Markdown pipe table with Method columns"
        )
        == "pipe_table"
    )
    assert requested_answer_shape("What is Manual Assist Auto?") == "none"
    assert (
        requested_answer_shape(
            "in Table 3-1 GUI examples, what exact phrase names Cursor "
            "among AI coding assistants? Give the exact wording from the page."
        )
        == "none"
    )


def test_ensure_fenced_code_idempotent() -> None:
    """Bare code becomes fenced; already-fenced bodies are not double-wrapped."""

    bare = "def top_router(state):\n    return 'billing'"
    once = ensure_fenced_code(bare)
    assert once.startswith("```python\n")
    assert once.endswith("\n```")
    assert "def top_router" in once
    assert ensure_fenced_code(once) == once
    assert answer_has_code_fence(once)


def test_ensure_pipe_table_from_aligned_columns_and_compact() -> None:
    """Aligned column gaps become a pipe table; unpaired lines stay in order."""

    aligned = (
        "Table 7-1. Primary methods\n"
        "Method    How it works\n"
        "SFT       Ground truth examples\n"
        "Vision    Image-label pairs"
    )
    table = ensure_markdown_pipe_table(aligned)
    assert answer_has_markdown_pipe_table(table)
    assert "Table 7-1" in table
    assert "| Method | How it works |" in table
    assert "| SFT | Ground truth examples |" in table
    assert "Item" not in table
    assert "Detail" not in table

    unpaired = (
        "Table 7-1. Primary methods\n"
        "First header line without column gaps\n"
        "Second body line stays on its own\n"
        "Third body line stays on its own"
    )
    kept = ensure_markdown_pipe_table(unpaired)
    assert kept == unpaired
    assert "Row 1" not in kept
    assert "Item" not in kept

    compact = (
        "| Strategy | Description | | --- | --- | "
        "| Lean models | Use simpler models | "
        "| Cloud-based resources | pay-as-you-go |"
    )
    normalized = ensure_markdown_pipe_table(compact)
    assert answer_has_markdown_pipe_table(normalized)


def test_format_requested_keeps_citation_span_exact() -> None:
    """Display wrap must not rewrite citation spans."""

    body = "def billing_router(state):\n    return 'invoice'"
    span = "def billing_router(state):"
    payload = _payload(body)
    payload = payload.model_copy(
        update={
            "citations": (
                AnswerCitation(
                    chunk_id=verifier_uid(1),
                    span=span,
                    atomic_link_id="link-1",
                    paragraph_index=0,
                ),
            )
        }
    )
    formatted = format_requested_answer_shape(
        payload,
        user_query=(
            "reproduce the billing_router function as a fenced Python code block"
        ),
    )
    assert answer_has_code_fence(formatted.answer_text)
    assert formatted.citations[0].span == span
    assert "```" not in (formatted.citations[0].span or "")


def test_format_skips_when_not_requested() -> None:
    """Ordinary prose asks are left unchanged."""

    payload = _payload("Boundary testing evaluates edge cases.")
    same = format_requested_answer_shape(
        payload, user_query="What does Boundary testing evaluate?"
    )
    assert same.answer_text == payload.answer_text


def test_fenced_claim_survives_drop_ungrounded_literals() -> None:
    """Fence wrappers must not make grounded code literals fail the guard."""

    source = (
        "def track_shipments(origin: str = None, **kwargs) -> str:\n"
        '    return "shipment_tracking_updated"'
    )
    claim = (
        "```python\n"
        "def track_shipments(origin: str = None, **kwargs) -> str:\n"
        '    return "shipment_tracking_updated"\n'
        "```"
    )
    payload = _payload(claim)
    fusion = verifier_fusion(verifier_passage(1, text=source))
    kept = drop_ungrounded_literals(payload, fusion=fusion, tables=())
    assert kept.atomic_links
    assert "track_shipments" in kept.atomic_links[0].claim
    stripped = strip_markdown_fences_for_literal_guard(claim)
    assert "shipment_tracking_updated" in stripped
    assert "```" not in stripped
