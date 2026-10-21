"""Source syntax errors stay visible without executing or silently fixing code."""

import pytest
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.verify import verify_answer_node
from smart_rag_api.services.sse.mapping.verified import emit_verified_events
from smart_rag_core.query_answer.generate_code_salvage import (
    salvage_named_code_definition,
)
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.source_syntax import (
    SOURCE_CODE_SYNTAX_INVALID,
    has_source_code_syntax_issue,
)

from tests.support.answer_verifier import (
    verified_answer_state,
    verifier_fusion,
    verifier_passage,
)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("def quote_widget():\n    return 'ok'", False),
        ("def quote_widget():\nreturn 'bad indent'", True),
        ('def quote_widget():\n    return "missing quote', True),
        ("raise RuntimeError('must not execute')", False),
    ],
)
def test_syntax_check_never_executes_source(code: str, expected: bool) -> None:
    """A valid raise statement is only compiled, not run."""
    payload = AnswerPayload(
        answer_text="```python\n" + code + "\n```", status="complete"
    )
    assert (
        has_source_code_syntax_issue(
            payload, user_query="Reproduce quote_widget Python function."
        )
        is expected
    )


def test_verified_source_typo_is_partial_and_surfaces_a_signed_warning() -> None:
    """Grounded reproduction is distinct from a syntactically valid example."""
    query = "Reproduce quote_widget Python function, keeping its original code."
    text = 'def quote_widget():\n    return "missing quote'
    fusion = verifier_fusion(verifier_passage(811, text=text))
    answer = salvage_named_code_definition(
        AnswerPayload(answer_text="Draft", status="complete"), fusion, user_query=query
    )
    state = verified_answer_state()
    state.update(
        {
            "user_query": query,
            "answer": answer.model_dump(mode="json"),
            "fusion": fusion.model_dump(mode="json"),
        }
    )
    result = verify_answer_node(state, QueryGraphDeps())
    assert result["status"] == "verified_partial"
    assert result["detail"] == SOURCE_CODE_SYNTAX_INVALID
    released = AnswerPayload.model_validate(result["answer"])
    assert text in released.answer_text
    events, emitted, _ = emit_verified_events(released, dict(result))
    assert emitted
    assert ("limitation", {"code": SOURCE_CODE_SYNTAX_INVALID}) in events
    assert ("partial", {"reason": SOURCE_CODE_SYNTAX_INVALID}) in events
    assert not any(name == "completed" for name, _ in events)
