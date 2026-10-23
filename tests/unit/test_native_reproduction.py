"""Native copies preserve source ownership and do not swallow additional user requests."""

from smart_rag_agents.query.nodes.answer import company_model_failure_payload
from smart_rag_core.query_answer.reproduction import canonical_reproduction_payload

from tests.support.answer_verifier import verifier_fusion, verifier_passage


def test_table_reproduction_and_timeout_recovery_use_exact_canonical_rows() -> None:
    """A provider timeout is not a reason to refuse an already fitted native table."""
    text = "Table 8-1. Storage approaches\n| Approach | Pros |\n| --- | --- |\n| SQL | Queryable |\n| Objects | Durable |"
    fusion = verifier_fusion(verifier_passage(1, text=text))
    query = "Reproduce Table 8-1 as a Markdown table."
    native = canonical_reproduction_payload(fusion, query)
    assert native is not None
    assert "| SQL | Queryable |" in native.answer_text
    assert native.citations and all(c.span and c.span in text for c in native.citations)
    recovered, status = company_model_failure_payload(
        fusion, user_query=query, reason="answer_timeout"
    )
    assert status == "answered" and recovered.atomic_links


def test_transformations_and_code_explanations_still_require_generation() -> None:
    """Native copying must not replace a translation, calculation, or explanation."""
    fusion = verifier_fusion(verifier_passage(1, text="def widget():\n    return 1"))
    for query in (
        "Show widget as a fenced Python block and explain it.",
        "Reproduce Table 8-1 as Markdown and calculate the total.",
        "Show Table 8-1 as a Markdown table in Arabic.",
    ):
        assert canonical_reproduction_payload(fusion, query) is None


def test_unrelated_native_content_does_not_satisfy_a_named_artifact() -> None:
    """Copying is gated by the requested identifier, not any available code block."""
    fusion = verifier_fusion(verifier_passage(1, text="def unrelated():\n    return 1"))
    assert (
        canonical_reproduction_payload(
            fusion, "Reproduce widget as a fenced Python block."
        )
        is None
    )
