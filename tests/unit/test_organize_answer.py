"""The compatibility organizer cannot alter already checked answer state."""

from __future__ import annotations

from typing import Literal

import pytest
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.organize import organize_answer_node
from smart_rag_agents.query.state import pending_query_state


@pytest.mark.parametrize(
    "status", ["verified", "verified_partial", "refused", "insufficient_evidence"]
)
def test_organize_is_an_immutable_release_stage(
    status: Literal["verified", "verified_partial", "refused", "insufficient_evidence"],
) -> None:
    """Keep the complete checked state, including existing metadata and usage."""
    state = pending_query_state(user_query="How does the process run?")
    state["status"] = status
    state["answer"] = {"answer_text": "Exact checked answer."}
    state["verification"] = {"status": status}
    assert organize_answer_node(state, QueryGraphDeps()) is state


def test_organize_does_not_append_uncited_fusion_figures() -> None:
    """A release stage cannot append a retrieved figure after citation checks."""
    state = pending_query_state(user_query="Show the diagram.")
    state["status"] = "verified"
    state["answer"] = {"answer_text": "Exact checked answer."}
    state["fusion"] = {"evidence": [{"figure_id": "abc123"}]}
    result = organize_answer_node(state, QueryGraphDeps())
    assert result["answer"] == {"answer_text": "Exact checked answer."}
