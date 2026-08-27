"""Studio live admission, idempotency, and conversation namespace."""

from __future__ import annotations

import json
from uuid import UUID

from langchain_core.messages import HumanMessage
from smart_rag_agents.query.studio_live import (
    LIVE_ROUTE_FAMILY,
    STUDIO_LIVE_NAMESPACE,
    last_human_turn_ref,
    run_studio_live_seed,
    studio_live_conversation_id,
    studio_live_idempotency_key,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.security.identity import UserRole
from smart_rag_core.security.profile_snapshot import ProfileSnapshot

from tests.support.studio_live import (
    CANARY,
    admitted_studio_context,
    studio_config,
    studio_hooks,
    studio_query_state,
    studio_snapshot,
)


def test_valid_mocked_admit_is_never_studio_local() -> None:
    """A mocked JWT/profile/admit returns a real Composite context."""

    result = run_studio_live_seed(
        studio_query_state(
            "What is the status of INV-SR-1001?",
            messages=[
                HumanMessage(content="What is the status of INV-SR-1001?", id="turn-1")
            ],
        ),
        studio_config("thread-live-a"),  # type: ignore[arg-type]
        studio_hooks(),
    )
    assert result["status"] == "pending"
    runtime = result["authorized_runtime"]
    assert isinstance(runtime, dict)
    assert runtime["status"] != "studio_local"
    assert runtime["route_family"] == LIVE_ROUTE_FAMILY.value
    assert runtime["model_call_ceiling"] == 9
    dumped = json.dumps(result, default=str)
    assert CANARY not in dumped


def test_same_human_message_reuses_idempotency_key() -> None:
    """Retrying the same human message reuses the admit idempotency key."""

    keys: list[UUID] = []

    def admit(**kwargs: object) -> AuthorizedRuntimeContext:
        """Capture the idempotency key.

        Args:
            **kwargs: Admit fields.

        Returns:
            Admitted context.
        """

        key = kwargs["idempotency_key"]
        assert isinstance(key, UUID)
        keys.append(key)
        conversation_id = kwargs["conversation_id"]
        assert isinstance(conversation_id, UUID)
        return admitted_studio_context(
            payload_hash=str(kwargs["payload_hash"]),
            conversation_id=conversation_id,
        )

    state = {
        "user_query": "same question",
        "messages": [HumanMessage(content="same question", id="stable-msg")],
    }
    hooks = studio_hooks(admit=admit)
    first = run_studio_live_seed(state, studio_config("thread-retry"), hooks)  # type: ignore[arg-type]
    second = run_studio_live_seed(state, studio_config("thread-retry"), hooks)  # type: ignore[arg-type]
    assert first["authorized_runtime"] is not None
    assert second["authorized_runtime"] is not None
    assert keys[0] == keys[1]
    expected = studio_live_idempotency_key(
        thread_id="thread-retry",
        turn_ref="stable-msg",
        payload_hash=hash_query_admission_payload(
            conversation_id=studio_live_conversation_id("thread-retry"),
            route_family=LIVE_ROUTE_FAMILY,
            message="same question",
        ),
    )
    assert keys[0] == expected


def test_new_turn_gets_a_different_idempotency_key() -> None:
    """A new human turn, even with identical text, uses a new key."""

    keys: list[UUID] = []

    def admit(**kwargs: object) -> AuthorizedRuntimeContext:
        """Capture keys.

        Args:
            **kwargs: Admit fields.

        Returns:
            Admitted context.
        """

        key = kwargs["idempotency_key"]
        assert isinstance(key, UUID)
        keys.append(key)
        conversation_id = kwargs["conversation_id"]
        assert isinstance(conversation_id, UUID)
        return admitted_studio_context(
            payload_hash=str(kwargs["payload_hash"]),
            conversation_id=conversation_id,
        )

    hooks = studio_hooks(admit=admit)
    run_studio_live_seed(
        studio_query_state(
            "",
            messages=[HumanMessage(content="same text", id="turn-1")],
        ),
        studio_config("thread-new"),  # type: ignore[arg-type]
        hooks,
    )
    run_studio_live_seed(
        studio_query_state(
            "",
            messages=[
                HumanMessage(content="same text", id="turn-1"),
                HumanMessage(content="same text", id="turn-2"),
            ],
        ),
        studio_config("thread-new"),  # type: ignore[arg-type]
        hooks,
    )
    assert keys[0] != keys[1]
    assert (
        last_human_turn_ref(
            {"messages": [HumanMessage(content="same text", id="turn-2")]}
        )
        == "turn-2"
    )


def test_role_and_version_are_rechecked_each_turn() -> None:
    """Each seed reloads the live role and authorization version."""

    seen: list[tuple[UserRole, int]] = []
    current = {"role": UserRole.MEMBER, "version": 1}

    def load_profile(user_id: str) -> ProfileSnapshot:
        """Return the mutable live profile.

        Args:
            user_id: Subject.

        Returns:
            Current snapshot.
        """

        _ = user_id
        return studio_snapshot(
            role=current["role"],  # type: ignore[arg-type]
            authorization_version=int(current["version"]),
        )

    def admit(**kwargs: object) -> AuthorizedRuntimeContext:
        """Record the caller snapshot used for admit.

        Args:
            **kwargs: Admit fields.

        Returns:
            Admitted context.
        """

        caller = kwargs["caller"]
        seen.append((caller.role, caller.authorization_version))  # type: ignore[attr-defined]
        conversation_id = kwargs["conversation_id"]
        assert isinstance(conversation_id, UUID)
        return admitted_studio_context(
            payload_hash=str(kwargs["payload_hash"]),
            conversation_id=conversation_id,
        )

    hooks = studio_hooks(admit=admit)
    hooks.load_profile = load_profile
    run_studio_live_seed(studio_query_state("first"), studio_config(), hooks)  # type: ignore[arg-type]
    current["role"] = UserRole.ADMIN
    current["version"] = 4
    run_studio_live_seed(studio_query_state("second"), studio_config(), hooks)  # type: ignore[arg-type]
    assert seen == [(UserRole.MEMBER, 1), (UserRole.ADMIN, 4)]


def test_conversation_id_uses_live_namespace() -> None:
    """Live conversation ids must not reuse the local Studio namespace."""

    from smart_rag_agents.query.studio import STUDIO_NAMESPACE

    thread_id = "thread-live-a"
    live_id = studio_live_conversation_id(thread_id)
    local_id = UUID(int=0)
    from uuid import uuid5

    local_id = uuid5(STUDIO_NAMESPACE, f"conversation:{thread_id}")
    assert live_id != local_id
    assert live_id == uuid5(STUDIO_LIVE_NAMESPACE, thread_id)
