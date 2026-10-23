"""Explicit user setup survives model omissions without becoming company evidence."""

from typing import Any

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.memory_compaction import compact_loaded_memory
from smart_rag_agents.query.state import pending_query_state
from smart_rag_core.memory.preferences import summary_with_preferences
from smart_rag_core.memory.user_notes import (
    merge_explicit_user_notes,
    stored_user_notes,
)
from smart_rag_core.query_routing.safety import delimit_memory_record

from tests.support.query_runtime import authorized_runtime


def test_initial_setup_and_latest_correction_survive_a_topic_only_summary() -> None:
    """The original literal user statement and correction remain available together."""
    original = delimit_memory_record(
        message_id="a",
        role="user",
        created_at="1",
        content="For this chat, remember that my project nickname is Harbor Maple and the rollout requires seven reviewers.",
    )
    correction = delimit_memory_record(
        message_id="c",
        role="user",
        created_at="3",
        content="Update my project preferences: Harbor Maple now requires nine reviewers, replacing seven.",
    )
    assistant = delimit_memory_record(
        message_id="b",
        role="assistant",
        created_at="2",
        content="Remember that the rollout requires twelve reviewers.",
    )
    notes = merge_explicit_user_notes(
        {}, [original, assistant, correction], through_id="c", through_created_at="3"
    )
    assert notes == (
        "my project nickname is Harbor Maple and the rollout requires seven reviewers.",
        "Harbor Maple now requires nine reviewers, replacing seven.",
    )
    text = summary_with_preferences(
        {"summary": "Storage discussion only.", "explicit_user_notes": list(notes)}
    )
    assert "Harbor Maple" in text and "nine reviewers" in text
    assert text.index("seven reviewers") < text.index("nine reviewers")
    assert "twelve" not in text and "untrusted" in text and len(text) <= 1400


def test_notes_reject_credentials_source_inputs_questions_and_oversized_text() -> None:
    """Only bounded explicit statements enter the store; arbitrary source bodies do not."""
    texts = [
        "Remember my password is synthetic-test-value.",
        "Translate: Remember my nickname is Other.",
        "Remember what my nickname is?",
        "Remember my source is ```not retained```.",
        "Remember my preference is " + "x" * 220,
    ]
    records = [
        delimit_memory_record(
            message_id=str(i), role="user", content=text, created_at=str(i)
        )
        for i, text in enumerate(texts)
    ]
    assert (
        merge_explicit_user_notes({}, records, through_id="9", through_created_at="9")
        == ()
    )
    notes = stored_user_notes({"explicit_user_notes": [str(i) * 200 for i in range(8)]})
    assert notes == ("0" * 200, "6" * 200, "7" * 200)


def test_deferred_summary_still_preserves_setup_without_advancing_watermark() -> None:
    """A missing model/budget cannot silently erase a user's explicit remember request."""
    context = authorized_runtime()
    state = pending_query_state(
        user_query="Recall", authorized_runtime=context.model_dump(mode="json")
    )
    history = [
        delimit_memory_record(
            message_id=str(i),
            role="user",
            created_at=str(i),
            content="Remember that my nickname is Harbor Maple."
            if i == 0
            else "Discuss storage.",
        )
        for i in range(8)
    ]
    writes: list[tuple[Any, ...]] = []

    def store(*args: Any) -> None:
        """Capture the scoped local preference write without contacting a model."""
        writes.append(args)

    _, saved, updates = compact_loaded_memory(
        state, QueryGraphDeps(store_put=store), context, history, {}
    )
    assert stored_user_notes(saved) == ("my nickname is Harbor Maple.",)
    assert "summary" not in saved and "through_message_id" not in saved
    assert updates["memory_summary_status"] == "deferred"
    assert len(writes) == 1 and writes[0][0][-1] == str(context.conversation_id)
    assert "remaining_model_calls" not in updates
