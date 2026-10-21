"""A dedented native page continuation must not produce an invalid function."""

import ast
import re

import pytest
from smart_rag_core.query_answer.code_continuation import restore_code_continuation
from smart_rag_core.query_answer.format_shape import format_requested_answer_shape
from smart_rag_core.query_answer.generate_code_salvage import (
    extractive_block_already_released,
    salvage_named_code_definition,
)
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.native_blocks import attach_native_evidence
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.retrieval.rerank import code_definition_gold_pattern

from tests.support.answer_verifier import verifier_fusion, verifier_passage

QUERY = "Reproduce build_widget_graph, keeping the original Python function."
SIGNATURE = "def build_widget_graph():"
BODY = "graph = build_graph()\nif ready:\n    graph.add_step()\nreturn graph.compile()"


def test_code_body_tail_cannot_change_behind_matching_short_anchors() -> None:
    """Original implementation requests compare every displayed statement."""
    body = (
        "def build_widget_graph():\n"
        + "    value = value + 1\n" * 25
        + "    return 'original'"
    )
    changed = body.replace("return 'original'", "return 'changed'")
    payload = AnswerPayload(answer_text=changed, status="complete")
    assert not extractive_block_already_released(payload, body)


def _fusion() -> FusionResult:
    """Return source fragments plus a parent proving their page-break order."""
    head = verifier_passage(701, text="def other_helper():\n   return 1\n" + SIGNATURE)
    head = head.model_copy(
        update={
            "content_kind": "code",
            "page_number": 8,
            "section_path": ("Factories",),
        }
    )
    shared = {
        "document_id": head.document_id,
        "version_id": head.version_id,
        "section_path": head.section_path,
    }
    tail = verifier_passage(702, text=BODY).model_copy(
        update={**shared, "content_kind": "code", "page_number": 9}
    )
    parent = verifier_passage(
        703, text=SIGNATURE + "\n\nFactory Designs | 99\n\n" + BODY
    ).model_copy(update=shared)
    return verifier_fusion(head, tail, parent)


def test_adjacent_native_fragments_restore_only_the_function_base_indent() -> None:
    """Source statements/relative indentation survive and both pages are cited."""
    fusion = _fusion()
    draft = AnswerPayload(answer_text="Wrong draft", status="complete")
    result = salvage_named_code_definition(draft, fusion, user_query=QUERY)
    parsed = ast.parse(result.answer_text)
    function = parsed.body[0]
    assert isinstance(function, ast.FunctionDef)
    assert function.name == "build_widget_graph"
    assert len(parsed.body) == 1
    assert [
        line.removeprefix("   ") for line in result.answer_text.splitlines()[1:]
    ] == BODY.splitlines()
    assert len(result.citations) == 2
    sources = {s.chunk_id: s.citation_text for s in fusion.evidence}
    for citation in result.citations:
        assert citation.chunk_id is not None and citation.span is not None
        assert citation.span in sources[citation.chunk_id]
    assert {c.chunk_id for c in result.citations} == {
        s.chunk_id for s in fusion.evidence[:2]
    }
    shown = format_requested_answer_shape(result, user_query=QUERY)
    shown = attach_native_evidence(shown, fusion, user_query=QUERY)
    assert "other_helper" not in shown.answer_text
    code = re.search(r"```python\n(.*?)\n```", shown.answer_text, re.S)
    assert code is not None
    ast.parse(code.group(1))
    assert salvage_named_code_definition(shown, fusion, user_query=QUERY) is shown


@pytest.mark.parametrize(
    "failure",
    ["version", "document", "section", "page", "no_parent", "prose_gap", "harness"],
)
def test_unproven_or_unrelated_continuation_is_not_joined(failure: str) -> None:
    """Page proximity alone cannot move statements into a function."""
    fusion = _fusion()
    head, tail, parent = fusion.evidence
    if failure in {"version", "document"}:
        field = "version_id" if failure == "version" else "document_id"
        tail = tail.model_copy(update={field: "different"})
    elif failure == "section":
        tail = tail.model_copy(update={"section_path": ("Other",)})
    elif failure == "page":
        tail = tail.model_copy(update={"page_number": 10})
    elif failure == "prose_gap":
        parent = parent.model_copy(
            update={"citation_text": SIGNATURE + "\nUnrelated prose\n" + BODY}
        )
    elif failure == "harness":
        tail = tail.model_copy(
            update={"citation_text": BODY + "\nprint('outside function')"}
        )
    evidence = (head, tail) if failure == "no_parent" else (head, tail, parent)
    pattern = code_definition_gold_pattern(("build_widget_graph",))
    assert pattern is not None
    result = restore_code_continuation(
        AnswerPayload(answer_text="Draft", status="complete"),
        fusion.model_copy(update={"evidence": evidence}),
        pattern,
    )
    assert result is None


def test_conflicting_proven_continuations_fail_closed() -> None:
    """Two versions of a same-page body cannot be resolved by rank or length."""
    fusion = _fusion()
    head = fusion.evidence[0]
    body = "graph = different_graph()\nreturn graph.compile()"
    shared = {
        "document_id": head.document_id,
        "version_id": head.version_id,
        "section_path": head.section_path,
    }
    other = verifier_passage(704, text=body).model_copy(
        update={**shared, "content_kind": "code", "page_number": 9}
    )
    parent = verifier_passage(705, text=SIGNATURE + "\n" + body).model_copy(
        update=shared
    )
    pattern = code_definition_gold_pattern(("build_widget_graph",))
    assert pattern is not None
    assert (
        restore_code_continuation(
            AnswerPayload(answer_text="Draft", status="complete"),
            fusion.model_copy(update={"evidence": (*fusion.evidence, other, parent)}),
            pattern,
        )
        is None
    )
