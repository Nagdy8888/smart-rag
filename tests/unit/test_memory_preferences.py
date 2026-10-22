"""Stable user details must survive lossy topic summaries and reject invented updates."""

from smart_rag_core.memory.preferences import (
    PreferenceUpdate,
    merge_preference_updates,
    stored_preferences,
    summary_with_preferences,
)
from smart_rag_core.query_routing.safety import delimit_memory_record


def test_topic_summary_cannot_erase_existing_preferences() -> None:
    """A new prose summary without the count still carries the durable user details."""
    stored = {
        "summary": "The user is now discussing tools.",
        "preferences": {
            "project_nickname": "Harbor Maple",
            "reviewers": "nine",
        },
    }
    assert (
        merge_preference_updates(stored, [], [], through_id="z", through_created_at="z")
        == stored["preferences"]
    )
    text = summary_with_preferences(stored)
    assert "Harbor Maple" in text and "nine" in text
    assert "untrusted" in text and len(text) <= 1400


def test_only_an_actual_user_correction_updates_a_preference() -> None:
    """An assistant assertion and a later unacknowledged user message cannot replace it."""
    records = [
        delimit_memory_record(
            message_id="a",
            role="assistant",
            content="Use twelve reviewers.",
            created_at="2026-10-22T00:00:01Z",
        ),
        delimit_memory_record(
            message_id="b",
            role="user",
            content="Harbor Maple now requires nine reviewers, replacing seven.",
            created_at="2026-10-22T00:00:02Z",
        ),
        delimit_memory_record(
            message_id="c",
            role="user",
            content="Use twenty reviewers.",
            created_at="2026-10-22T00:00:03Z",
        ),
    ]
    stored = {"preferences": {"reviewers": "seven"}}
    updates = [
        PreferenceUpdate(
            key="reviewers", value="nine", user_quote="now requires nine reviewers"
        ),
        PreferenceUpdate(
            key="reviewers", value="twelve", user_quote="Use twelve reviewers."
        ),
        PreferenceUpdate(
            key="reviewers", value="twenty", user_quote="Use twenty reviewers."
        ),
        PreferenceUpdate(
            key="project_nickname", value="Invented", user_quote="Harbor Maple"
        ),
    ]
    result = merge_preference_updates(
        stored,
        updates,
        records,
        through_id="b",
        through_created_at="2026-10-22T00:00:02Z",
    )
    assert result == {"reviewers": "nine"}


def test_credentials_and_unbounded_preference_maps_are_rejected() -> None:
    """A preference store never becomes an unlimited credential or document store."""
    preferences = {f"key_{i}": "x" * 100 for i in range(20)}
    preferences.update(
        {"password": "synthetic-test-value", "api_key": "sk-" + "x" * 25}
    )
    result = stored_preferences({"preferences": preferences})
    assert "password" not in result and "api_key" not in result
    assert len(result) <= 8 and sum(len(k) + len(v) for k, v in result.items()) <= 600


def test_one_answer_language_request_does_not_replace_the_default() -> None:
    """A quoted Arabic formatting request is not a persistent language correction."""
    record = delimit_memory_record(
        message_id="a",
        role="user",
        content="قارن PostgreSQL وS3. أجب بالعربية.",
        created_at="2026-10-22T00:00:01Z",
    )
    result = merge_preference_updates(
        {"preferences": {"language_preference": "concise English"}},
        [
            PreferenceUpdate(
                key="language_preference", value="العربية", user_quote="أجب بالعربية"
            )
        ],
        [record],
        through_id="a",
        through_created_at=record.created_at,
    )
    assert result == {"language_preference": "concise English"}


def test_explicit_durable_language_correction_can_replace_the_default() -> None:
    """A user can still intentionally change their ongoing response language."""
    record = delimit_memory_record(
        message_id="a",
        role="user",
        content="From now on, my language preference is Arabic.",
        created_at="2026-10-22T00:00:01Z",
    )
    result = merge_preference_updates(
        {"preferences": {"language_preference": "English"}},
        [
            PreferenceUpdate(
                key="language_preference",
                value="Arabic",
                user_quote="From now on, my language preference is Arabic.",
            )
        ],
        [record],
        through_id="a",
        through_created_at=record.created_at,
    )
    assert result == {"language_preference": "Arabic"}


def test_local_language_preference_is_not_a_chat_default() -> None:
    """Even a local request using 'prefer' must not overwrite the chat default."""
    record = delimit_memory_record(
        message_id="a",
        role="user",
        content="For this answer, I prefer Arabic.",
        created_at="2026-10-22T00:00:01Z",
    )
    result = merge_preference_updates(
        {"preferences": {"language_preference": "English"}},
        [
            PreferenceUpdate(
                key="language_preference",
                value="Arabic",
                user_quote=record.content,
            )
        ],
        [record],
        through_id="a",
        through_created_at=record.created_at,
    )
    assert result == {"language_preference": "English"}


def test_omitted_language_policy_survives_without_model_extraction() -> None:
    """Keep the user's actual default and exception when the summary omits both."""
    record = delimit_memory_record(
        message_id="a",
        role="user",
        content="My nickname is Harbor Maple. Prefer concise English unless I ask for Arabic.",
        created_at="2026-10-22T00:00:01Z",
    )
    result = merge_preference_updates(
        {},
        [],
        [record],
        through_id="a",
        through_created_at=record.created_at,
    )
    assert (
        result["language_preference"]
        == "Prefer concise English unless I ask for Arabic."
    )


def test_abbreviated_quote_can_use_its_actual_persistent_user_sentence() -> None:
    """A short exact quote need not repeat the preceding persistence verb."""
    record = delimit_memory_record(
        message_id="a",
        role="user",
        content="Prefer concise English unless I ask for Arabic.",
        created_at="2026-10-22T00:00:01Z",
    )
    result = merge_preference_updates(
        {},
        [
            PreferenceUpdate(
                key="language_preference",
                value="concise English unless I ask for Arabic",
                user_quote="concise English unless I ask for Arabic",
            )
        ],
        [record],
        through_id="a",
        through_created_at=record.created_at,
    )
    assert result["language_preference"] == "concise English unless I ask for Arabic"


def test_language_question_or_quoted_source_is_not_a_policy() -> None:
    """Automatic retention cannot promote a question or translation input into a default."""
    records = [
        delimit_memory_record(
            message_id=str(i),
            role="user",
            content=text,
            created_at=f"2026-10-22T00:00:0{i}Z",
        )
        for i, text in enumerate(
            [
                "My language preference is always English?",
                "Translate this sentence: Prefer concise English unless I ask for Arabic.",
            ],
            1,
        )
    ]
    assert (
        merge_preference_updates(
            {},
            [],
            records,
            through_id="2",
            through_created_at=records[-1].created_at,
        )
        == {}
    )
