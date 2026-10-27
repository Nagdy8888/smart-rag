"""Operational answer failures must not claim the corpus lacks evidence."""

from smart_rag_agents.query.nodes.answer import company_model_failure_payload

from tests.support.answer_verifier import verifier_fusion


def test_answer_timeout_copy_identifies_operational_failure() -> None:
    """A provider timeout is not an evidence-coverage judgment."""
    payload, _ = company_model_failure_payload(
        verifier_fusion(),
        user_query="Compare the agent archetypes",
        reason="timeout_after_send",
    )
    assert payload.answer_text == "The answer service timed out. Please try again."
    assert payload.citations == ()
