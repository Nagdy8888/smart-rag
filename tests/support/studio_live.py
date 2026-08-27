"""Shared LangGraph Studio live hooks, tokens, and runtime stubs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from smart_rag_agents.query.live_runtime import QueryGraphProcessBindings
from smart_rag_agents.query.studio import StudioQueryState
from smart_rag_agents.query.studio_live import (
    StudioLiveHooks,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import UserRole
from smart_rag_core.security.jwks import JwksVerificationError, VerifiedAccessToken
from smart_rag_core.security.profile_snapshot import ProfileSnapshot

from tests.support.query_runtime import RefusingHybridRetriever

CANARY = "studio-live-canary-token-9f3a"

_USER_ID = "11111111-1111-4111-8111-111111111111"

STUDIO_REPO_ROOT = Path(__file__).resolve().parents[2]


def studio_query_state(
    user_query: str,
    *,
    messages: object | None = None,
) -> StudioQueryState:
    """Build a partial Studio seed mapping accepted by live seed helpers.

    Args:
        user_query: Original user text.
        messages: Optional LangChain messages channel.

    Returns:
        Mapping widened to ``StudioQueryState``. Tests seed only ``user_query``
        and messages; remaining TypedDict keys are filled by the seed path.
    """

    payload: dict[str, object] = {"user_query": user_query}
    if messages is not None:
        payload["messages"] = messages
    return cast(StudioQueryState, payload)


class IntrospectionRuntime:
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


class ExecutionRuntime:
    """Agent Server execution stub."""

    access_context = "threads.create_run"
    user = None
    store = None
    context = None

    @property
    def execution_runtime(self) -> ExecutionRuntime:
        """Return self as the execution runtime.

        Returns:
            This stub.
        """

        return self


class FakeConnection:
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


def studio_verified_token(*, subject: str = _USER_ID) -> VerifiedAccessToken:
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


def studio_snapshot(
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


def admitted_studio_context(
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


def studio_bindings() -> QueryGraphProcessBindings:
    """Return dummy process bindings that do not open sockets.

    Returns:
        Process bindings with a dummy Hybrid and gateway.
    """

    return QueryGraphProcessBindings(
        hybrid_retriever=RefusingHybridRetriever(),
        model_gateway=object(),
        graph_retriever=None,
        table_executor=None,
        answer_prompt_text="answer",
        general_chat_prompt_text="general",
        verifier_prompt_text="verifier",
        query_profile_prompt_text="query_profile",
        profile_model_id="gpt-4o-mini",
        supabase_dsn="postgresql://unit@127.0.0.1:1/postgres",
    )


def studio_hooks(
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

    snapshot = studio_snapshot() if profile == "ok" else profile

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
            verified = verify(raw)
            if not isinstance(verified, VerifiedAccessToken):
                raise TypeError("verified_token_required")
            return verified
        return studio_verified_token()

    def load_profile(user_id: str) -> ProfileSnapshot | None:
        """Return the fixture snapshot.

        Args:
            user_id: Verified subject.

        Returns:
            Snapshot or ``None``.
        """

        _ = user_id
        if snapshot == "ok":
            return studio_snapshot()
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
        return admitted_studio_context(
            payload_hash=payload_hash,
            conversation_id=conversation_id,
        )

    def default_open() -> FakeConnection:
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
        build_bindings=(
            cast(Callable[[], QueryGraphProcessBindings], build_bindings)
            if callable(build_bindings)
            else studio_bindings
        ),
    )


def studio_config(thread_id: str = "thread-live-a") -> dict[str, object]:
    """Return a Studio runnable config.

    Args:
        thread_id: Thread identifier.

    Returns:
        Config mapping without an access token.
    """

    return {"configurable": {"thread_id": thread_id}}
