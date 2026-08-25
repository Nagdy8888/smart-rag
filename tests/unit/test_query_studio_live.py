"""Unit tests for authenticated LangGraph Studio live admission."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import HumanMessage
from smart_rag_agents.query.graph import build_query_graph
from smart_rag_agents.query.live_runtime import QueryGraphProcessBindings
from smart_rag_agents.query.studio_live import (
    DETAIL_DISABLED,
    DETAIL_PROFILE,
    DETAIL_REVOKED,
    DETAIL_TOKEN_INVALID,
    DETAIL_TOKEN_MISSING,
    LIVE_ROUTE_FAMILY,
    STUDIO_LIVE_NAMESPACE,
    StudioLiveHooks,
    last_human_turn_ref,
    make_graph,
    open_studio_live_graph,
    run_studio_live_seed,
    seed_studio_live_unbound,
    studio_live_conversation_id,
    studio_live_idempotency_key,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import UserRole
from smart_rag_core.security.jwks import JwksVerificationError, VerifiedAccessToken
from smart_rag_core.security.profile_snapshot import ProfileSnapshot
from smart_rag_core.settings import AgentSettings, BackendSettings

CANARY = "studio-live-canary-token-9f3a"
_USER_ID = "11111111-1111-4111-8111-111111111111"
_REPO_ROOT = Path(__file__).resolve().parents[2]


class _IntrospectionRuntime:
    """Agent Server introspection stub. ``execution_runtime`` is None."""

    access_context = "assistants.read"
    user = None
    store = None

    @property
    def execution_runtime(self) -> None:
        """Return None so the factory opens no sockets.

        Returns:
            Always ``None``.
        """

        return None


class _ExecutionRuntime:
    """Agent Server execution stub."""

    access_context = "threads.create_run"
    user = None
    store = None
    context = None

    @property
    def execution_runtime(self) -> _ExecutionRuntime:
        """Return self as the execution runtime.

        Returns:
            This stub.
        """

        return self


class _FakeConnection:
    """Track close() without opening Postgres."""

    def __init__(self) -> None:
        """Create an open fake connection."""

        self.closed = False
        self.commit_count = 0

    def close(self) -> None:
        """Mark the connection closed."""

        self.closed = True

    def commit(self) -> None:
        """Count commits."""

        self.commit_count += 1

    def execute(self, *_args: object, **_kwargs: object) -> None:
        """No-op SQL execute.

        Args:
            *_args: Ignored.
            **_kwargs: Ignored.
        """

        return None


class _DummyHybrid:
    """Truthy Hybrid that must not retrieve in these tests."""

    def retrieve(self, **kwargs: object) -> object:
        """Refuse retrieve.

        Args:
            **kwargs: Ignored.

        Raises:
            AssertionError: Always.
        """

        del kwargs
        raise AssertionError("hybrid retrieve must not run in this test")


def _verified_token(*, subject: str = _USER_ID) -> VerifiedAccessToken:
    """Return a verified JWT fixture.

    Args:
        subject: JWT subject.

    Returns:
        Frozen verified claims. The raw token is omitted.
    """

    return VerifiedAccessToken(
        subject=subject,
        audience="authenticated",
        issuer="http://127.0.0.1:54321/auth/v1",
        algorithm="ES256",
        key_id="unit-kid",
        session_id="session-live",
        authentication_methods=("password",),
        assurance_level="aal1",
        expires_at=2_000_000_000,
        issued_at=1_700_000_000,
        raw_claims={"sub": subject},
    )


def _snapshot(
    *,
    role: UserRole = UserRole.MEMBER,
    authorization_version: int = 1,
    disabled: bool = False,
) -> ProfileSnapshot:
    """Return a live profile fixture.

    Args:
        role: Authoritative role.
        authorization_version: Company snapshot.
        disabled: Disabled flag.

    Returns:
        Frozen profile snapshot.
    """

    return ProfileSnapshot(
        user_id=_USER_ID,
        role=role,
        authorization_version=authorization_version,
        disabled=disabled,
        upload_enabled=False,
        mfa_enrolled=False,
        session_revoked_at=None,
    )


def _admitted_context(
    *,
    payload_hash: str,
    conversation_id: UUID,
) -> AuthorizedRuntimeContext:
    """Return a real (non-synthetic) admitted context.

    Args:
        payload_hash: Canonical hash.
        conversation_id: Live Studio conversation.

    Returns:
        Authorized runtime whose status is not ``studio_local``.
    """

    now = datetime.now(UTC)
    return AuthorizedRuntimeContext(
        user_id=UUID(_USER_ID),
        role=UserRole.MEMBER,
        authorization_version=1,
        session_id="session-live",
        conversation_id=conversation_id,
        run_id=uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=Phase6RouteFamily.COMPOSITE,
        deadline_at=now + timedelta(seconds=50),
        recursion_limit=24,
        correction_ceiling=1,
        subquestion_ceiling=3,
        model_call_ceiling=9,
        tool_ceiling=5,
        discovery_ceiling=1,
        manifest_ceiling=3,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("3.60"),
        remaining_usd=Decimal("3.60"),
        remaining_prompt_tokens=72000,
        remaining_completion_tokens=18000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash=payload_hash,
        status="pending",
    )


def _bindings() -> QueryGraphProcessBindings:
    """Return dummy process bindings that do not open sockets.

    Returns:
        Process bindings with a dummy Hybrid and gateway.
    """

    return QueryGraphProcessBindings(
        hybrid_retriever=_DummyHybrid(),
        model_gateway=object(),
        graph_retriever=None,
        table_executor=None,
        answer_prompt_text="answer",
        general_chat_prompt_text="general",
        verifier_prompt_text="verifier",
        supabase_dsn="postgresql://unit@127.0.0.1:1/postgres",
    )


def _hooks(
    *,
    enabled: bool = True,
    token: str | None = CANARY,
    verify: object | None = None,
    profile: ProfileSnapshot | str | None = "ok",
    revoked: bool = False,
    admit: object | None = None,
    open_connection: object | None = None,
    build_bindings: object | None = None,
    export_ok: bool = True,
) -> StudioLiveHooks:
    """Build injectable live hooks.

    Args:
        enabled: Live flag.
        token: Access token returned by the getter.
        verify: Optional verify replacement.
        profile: Snapshot, ``None``, or ``ok`` for the default snapshot.
        revoked: Whether ``is_revoked`` returns true.
        admit: Optional admit replacement.
        open_connection: Optional opener.
        build_bindings: Optional bindings factory.
        export_ok: Whether the LangSmith gate passes.

    Returns:
        Hooks that record no token on returned state.
    """

    snapshot = _snapshot() if profile == "ok" else profile

    def token_getter() -> str | None:
        """Return the fixture token.

        Returns:
            Token or ``None``.
        """

        return token

    def verify_access_token(raw: str) -> VerifiedAccessToken:
        """Verify or raise.

        Args:
            raw: Token. Must not be stored on state.

        Returns:
            Verified claims.

        Raises:
            JwksVerificationError: When ``verify`` is that error.
        """

        _ = raw
        if isinstance(verify, JwksVerificationError):
            raise verify
        if callable(verify):
            return verify(raw)
        return _verified_token()

    def load_profile(user_id: str) -> ProfileSnapshot | None:
        """Return the fixture snapshot.

        Args:
            user_id: Verified subject.

        Returns:
            Snapshot or ``None``.
        """

        _ = user_id
        if snapshot == "ok":
            return _snapshot()
        return snapshot  # type: ignore[return-value]

    def is_revoked(
        verified: VerifiedAccessToken,
        loaded: ProfileSnapshot,
    ) -> bool:
        """Return the fixture revocation flag.

        Args:
            verified: Verified token.
            loaded: Live profile.

        Returns:
            Revocation flag.
        """

        _ = (verified, loaded)
        return revoked

    def default_admit(**kwargs: object) -> AuthorizedRuntimeContext:
        """Return a non-synthetic admitted context.

        Args:
            **kwargs: Admit fields.

        Returns:
            Authorized runtime context.
        """

        conversation_id = kwargs["conversation_id"]
        payload_hash = str(kwargs["payload_hash"])
        assert isinstance(conversation_id, UUID)
        return _admitted_context(
            payload_hash=payload_hash,
            conversation_id=conversation_id,
        )

    def default_open() -> _FakeConnection:
        """Refuse accidental factory open in seed-only tests.

        Raises:
            AssertionError: Seed must not open the per-run connection.
        """

        raise AssertionError("open_connection must not run in this test")

    def export_gate() -> None:
        """No-op or raise for the governance gate.

        Raises:
            PermissionError: When ``export_ok`` is false. Tests that need the
                typed error should pass a custom hook.
        """

        if not export_ok:
            from smart_rag_core.observability.governance_gate import (
                ExternalFlowBlockedError,
            )

            raise ExternalFlowBlockedError("langsmith_real_content_unverified")

    return StudioLiveHooks(
        enabled=enabled,
        token_getter=token_getter,
        verify_access_token=verify_access_token,
        load_profile=load_profile,
        is_revoked=is_revoked,
        admit=admit if callable(admit) else default_admit,
        assert_export_permitted=export_gate,
        open_connection=open_connection if callable(open_connection) else default_open,
        build_bindings=build_bindings if callable(build_bindings) else _bindings,
    )


def _config(thread_id: str = "thread-live-a") -> dict[str, object]:
    """Return a Studio runnable config.

    Args:
        thread_id: Thread identifier.

    Returns:
        Config mapping without an access token.
    """

    return {"configurable": {"thread_id": thread_id}}


def test_agent_settings_do_not_inherit_backend_and_redact_token() -> None:
    """Live token is a secret on AgentSettings, not BackendSettings."""

    assert not issubclass(AgentSettings, BackendSettings)
    settings = AgentSettings(
        langgraph_studio_live_enabled=True,
        langgraph_studio_access_token=CANARY,
    )
    assert settings.langgraph_studio_live_enabled is True
    assert settings.langgraph_studio_access_token is not None
    assert settings.langgraph_studio_access_token.get_secret_value() == CANARY
    assert CANARY not in repr(settings)
    assert "service_role" not in AgentSettings.model_fields


def test_unbound_seed_rejects_without_synthetic_admit() -> None:
    """Disabled/unbound live seed never mints ``studio_local``."""

    result = seed_studio_live_unbound(
        {"user_query": "What is the status of INV-SR-1001?"},
        _config(),  # type: ignore[arg-type]
    )
    assert result["status"] == "admission_rejected"
    assert result["detail"] == DETAIL_DISABLED
    assert result["authorized_runtime"] is None


def test_disabled_and_missing_token_reject_before_verify() -> None:
    """Disabled mode and a missing token never call JWT/profile/admit."""

    calls: list[str] = []

    def verify(raw: str) -> VerifiedAccessToken:
        """Record an unexpected verify.

        Args:
            raw: Token.

        Returns:
            Verified claims.
        """

        calls.append(f"verify:{raw}")
        return _verified_token()

    disabled = run_studio_live_seed(
        {"user_query": "hello"},
        _config(),  # type: ignore[arg-type]
        _hooks(enabled=False, verify=verify),
    )
    assert disabled["status"] == "admission_rejected"
    assert disabled["authorized_runtime"] is None
    missing = run_studio_live_seed(
        {"user_query": "hello"},
        _config(),  # type: ignore[arg-type]
        _hooks(token=None, verify=verify),
    )
    assert missing["detail"] == DETAIL_TOKEN_MISSING
    assert calls == []


def test_invalid_token_rejects_before_profile_or_admit() -> None:
    """Expired/invalid JWT must not load profile or admit."""

    calls: list[str] = []

    def load_profile(user_id: str) -> ProfileSnapshot | None:
        """Record an unexpected profile read.

        Args:
            user_id: Subject.

        Returns:
            Never.
        """

        calls.append(f"profile:{user_id}")
        return _snapshot()

    hooks = _hooks(verify=JwksVerificationError("expired"))
    hooks.load_profile = load_profile
    result = run_studio_live_seed(
        {"user_query": "hello", "messages": [HumanMessage(content="hello", id="m1")]},
        _config(),  # type: ignore[arg-type]
        hooks,
    )
    assert result["status"] == "admission_rejected"
    assert result["detail"] == DETAIL_TOKEN_INVALID
    assert result["authorized_runtime"] is None
    assert calls == []
    dumped = json.dumps(result, default=str)
    assert CANARY not in dumped


def test_revoked_and_disabled_profile_reject_before_admit() -> None:
    """Revoked or disabled membership rejects without durable admit."""

    calls: list[str] = []

    def admit(**kwargs: object) -> AuthorizedRuntimeContext:
        """Record an unexpected admit.

        Args:
            **kwargs: Admit fields.

        Returns:
            Never.
        """

        calls.append("admit")
        raise AssertionError(kwargs)

    revoked = run_studio_live_seed(
        {"user_query": "hello"},
        _config(),  # type: ignore[arg-type]
        _hooks(revoked=True, admit=admit),
    )
    assert revoked["detail"] == DETAIL_REVOKED
    disabled = run_studio_live_seed(
        {"user_query": "hello"},
        _config(),  # type: ignore[arg-type]
        _hooks(profile=_snapshot(disabled=True), admit=admit),
    )
    assert disabled["detail"] == DETAIL_PROFILE
    missing = run_studio_live_seed(
        {"user_query": "hello"},
        _config(),  # type: ignore[arg-type]
        _hooks(profile=None, admit=admit),
    )
    assert missing["detail"] == DETAIL_PROFILE
    assert calls == []


def test_valid_mocked_admit_is_never_studio_local() -> None:
    """A mocked JWT/profile/admit returns a real Composite context."""

    result = run_studio_live_seed(
        {
            "user_query": "What is the status of INV-SR-1001?",
            "messages": [
                HumanMessage(content="What is the status of INV-SR-1001?", id="turn-1")
            ],
        },
        _config("thread-live-a"),  # type: ignore[arg-type]
        _hooks(),
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
        return _admitted_context(
            payload_hash=str(kwargs["payload_hash"]),
            conversation_id=conversation_id,
        )

    state = {
        "user_query": "same question",
        "messages": [HumanMessage(content="same question", id="stable-msg")],
    }
    hooks = _hooks(admit=admit)
    first = run_studio_live_seed(state, _config("thread-retry"), hooks)  # type: ignore[arg-type]
    second = run_studio_live_seed(state, _config("thread-retry"), hooks)  # type: ignore[arg-type]
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
        return _admitted_context(
            payload_hash=str(kwargs["payload_hash"]),
            conversation_id=conversation_id,
        )

    hooks = _hooks(admit=admit)
    run_studio_live_seed(
        {"messages": [HumanMessage(content="same text", id="turn-1")]},
        _config("thread-new"),  # type: ignore[arg-type]
        hooks,
    )
    run_studio_live_seed(
        {
            "messages": [
                HumanMessage(content="same text", id="turn-1"),
                HumanMessage(content="same text", id="turn-2"),
            ]
        },
        _config("thread-new"),  # type: ignore[arg-type]
        hooks,
    )
    assert keys[0] != keys[1]
    assert last_human_turn_ref(
        {"messages": [HumanMessage(content="same text", id="turn-2")]}
    ) == "turn-2"


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
        return _snapshot(
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
        return _admitted_context(
            payload_hash=str(kwargs["payload_hash"]),
            conversation_id=conversation_id,
        )

    hooks = _hooks(admit=admit)
    hooks.load_profile = load_profile
    run_studio_live_seed({"user_query": "first"}, _config(), hooks)  # type: ignore[arg-type]
    current["role"] = UserRole.ADMIN
    current["version"] = 4
    run_studio_live_seed({"user_query": "second"}, _config(), hooks)  # type: ignore[arg-type]
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


def test_build_query_graph_rejects_both_studio_modes() -> None:
    """Local and live Studio flags are mutually exclusive."""

    with pytest.raises(ValueError, match="mutually exclusive"):
        build_query_graph(studio_local=True, studio_live=True)


def test_introspection_opens_zero_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Schema/graph introspection must not open DB or model sockets."""

    def boom(*_args: object, **_kwargs: object) -> None:
        """Fail if any connect-like helper is used.

        Args:
            *_args: Ignored.
            **_kwargs: Ignored.

        Raises:
            AssertionError: Always.
        """

        raise AssertionError("introspection opened a socket")

    monkeypatch.setattr("psycopg.connect", boom)
    monkeypatch.setattr(
        "smart_rag_core.security.profile_snapshot.psycopg.connect",
        boom,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.live_runtime.psycopg.connect",
        boom,
    )
    monkeypatch.setattr(
        "smart_rag_core.security.jwks.httpx.Client",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("jwks")),
    )

    async def _run() -> None:
        """Compile the introspection graph and inspect topology."""

        async with make_graph(_IntrospectionRuntime()) as graph:  # type: ignore[arg-type]
            nodes = set(graph.get_graph().nodes)
            assert "seed_studio_live_runtime" in nodes
            assert "emit_studio_response" in nodes
            schema = json.dumps(graph.get_input_jsonschema())
            assert CANARY not in schema

    asyncio.run(_run())


def test_disabled_execution_never_synthetic_admits() -> None:
    """Enabled-off execution rejects and does not mint ``studio_local``."""

    hooks = _hooks(enabled=False)

    async def _run() -> object:
        """Invoke the disabled live graph.

        Returns:
            Terminal state.
        """

        async with open_studio_live_graph(_ExecutionRuntime(), hooks=hooks) as graph:  # type: ignore[arg-type]
            return await graph.ainvoke({"user_query": "hello"})

    result = asyncio.run(_run())
    assert result["status"] == "admission_rejected"
    assert result["authorized_runtime"] is None
    assert DETAIL_DISABLED in str(result["detail"])
    messages = result.get("messages") or []
    assert messages
    assert CANARY not in json.dumps(result, default=str)


def test_invalid_token_execution_does_not_open_connection() -> None:
    """Invalid JWT execution rejects before the per-run connection."""

    opened = {"count": 0}

    def open_connection() -> _FakeConnection:
        """Record an unexpected open.

        Returns:
            Never.
        """

        opened["count"] += 1
        raise AssertionError("opened")

    hooks = _hooks(
        verify=JwksVerificationError("invalid"),
        open_connection=open_connection,
    )

    async def _run() -> object:
        """Invoke the invalid-token live graph.

        Returns:
            Terminal state.
        """

        async with open_studio_live_graph(_ExecutionRuntime(), hooks=hooks) as graph:  # type: ignore[arg-type]
            return await graph.ainvoke({"user_query": "hello"})

    result = asyncio.run(_run())
    assert result["detail"] == DETAIL_TOKEN_INVALID
    assert opened["count"] == 0


def test_connection_closes_on_success_error_and_cancel() -> None:
    """The per-run connection closes after success, error, and cancel."""

    success = _FakeConnection()
    hooks = _hooks(
        open_connection=lambda: success,
        build_bindings=_bindings,
    )

    async def _success() -> None:
        """Open then close the success-path connection."""

        async with open_studio_live_graph(_ExecutionRuntime(), hooks=hooks) as graph:  # type: ignore[arg-type]
            assert not success.closed
            nodes = set(graph.get_graph().nodes)
            assert "seed_studio_live_runtime" in nodes

    asyncio.run(_success())
    assert success.closed

    errored = _FakeConnection()

    def boom_bindings() -> QueryGraphProcessBindings:
        """Fail after the connection is open.

        Raises:
            OSError: Simulated bind failure.
        """

        raise OSError("bind failed")

    error_hooks = _hooks(open_connection=lambda: errored, build_bindings=boom_bindings)

    async def _error() -> object:
        """Compile the error-path reject graph.

        Returns:
            Terminal state.
        """

        async with open_studio_live_graph(_ExecutionRuntime(), hooks=error_hooks) as graph:  # type: ignore[arg-type]
            return await graph.ainvoke({"user_query": "hello"})

    result = asyncio.run(_error())
    assert result["status"] == "admission_rejected"
    assert errored.closed

    cancelled = _FakeConnection()
    cancel_hooks = _hooks(open_connection=lambda: cancelled, build_bindings=_bindings)

    async def _cancel() -> None:
        """Cancel while the live graph is yielded."""

        async with open_studio_live_graph(_ExecutionRuntime(), hooks=cancel_hooks) as graph:  # type: ignore[arg-type]
            assert graph is not None
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_cancel())
    assert cancelled.closed


def test_live_modules_do_not_import_backend_or_print_token() -> None:
    """Agents live modules stay import-safe and do not mention service_role."""

    paths = [
        _REPO_ROOT / "apps/agents/src/smart_rag_agents/query/studio_live.py",
        _REPO_ROOT / "apps/agents/src/smart_rag_agents/query/live_runtime.py",
        _REPO_ROOT / "packages/core/src/smart_rag_core/security/profile_snapshot.py",
    ]
    haystack = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "from smart_rag_api" not in haystack
    assert "import smart_rag_api" not in haystack
    assert "from fastapi" not in haystack
    assert "import fastapi" not in haystack
    assert "service_role" not in haystack
    assert "print(" not in haystack


def test_query_studio_registration_unchanged() -> None:
    """The unbound Studio graph entry must stay on ``studio.py:graph``."""

    payload = json.loads(
        (_REPO_ROOT / "apps/agents/langgraph.json").read_text(encoding="utf-8")
    )
    assert payload["graphs"]["query_studio"] == "./src/smart_rag_agents/query/studio.py:graph"
    assert (
        payload["graphs"]["query_studio_live"]
        == "./src/smart_rag_agents/query/studio_live.py:make_graph"
    )
