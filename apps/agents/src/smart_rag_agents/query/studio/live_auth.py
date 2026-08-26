"""JWT, profile, revocation, and settings hooks for live Studio."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from smart_rag_core.observability.governance_gate import (
    assert_langsmith_export_permitted,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.external_processing import ContentClass
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.security.jwks import JwksVerifier, VerifiedAccessToken
from smart_rag_core.security.profile_snapshot import (
    ProfileSnapshot,
    is_session_revoked,
    load_profile_snapshot,
)
from smart_rag_core.settings import load_agent_settings, load_backend_settings

from smart_rag_agents.query.live_runtime import (
    QueryGraphProcessBindings,
    QueryGraphRuntimeError,
    build_query_process_bindings,
    open_run_app_api_connection,
)


@dataclass(slots=True)
class StudioLiveHooks:
    """Injectable live-Studio boundaries. The token is never stored here.

    Attributes:
        enabled: Whether authenticated live execution is allowed.
        token_getter: Returns the bearer JWT or ``None``. Never logged.
        verify_access_token: JWKS verification. Must not persist the token.
        load_profile: Live profile reload for the verified subject.
        is_revoked: Session revocation check.
        admit: Durable admit that returns a real authorized context.
        assert_export_permitted: LangSmith company-content gate.
        open_connection: Per-run ``app_api`` opener.
        build_bindings: Process Hybrid/gateway/table factory.
        postgres_url: Optional DSN for identity/revocation only.
    """

    enabled: bool
    token_getter: Callable[[], str | None]
    verify_access_token: Callable[[str], VerifiedAccessToken]
    load_profile: Callable[[str], ProfileSnapshot | None]
    is_revoked: Callable[[VerifiedAccessToken, ProfileSnapshot], bool]
    admit: Callable[..., object]
    assert_export_permitted: Callable[[], None]
    open_connection: Callable[[], object]
    build_bindings: Callable[[], QueryGraphProcessBindings]
    postgres_url: str | None = None


def secret_text(value: object) -> str | None:
    """Return a secret string without logging it.

    Args:
        value: ``SecretStr`` or ``None``.

    Returns:
        Plaintext secret, or ``None``.
    """

    if value is None:
        return None
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        raw = getter()
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def load_production_hooks() -> StudioLiveHooks:
    """Build live hooks from ``AgentSettings`` plus separate ``BackendSettings``.

    Returns:
        Hooks that verify JWT, reload profile, and admit. The token is read
        through a getter and never assigned to a hook field.

    Raises:
        SettingsValidationError: When agent or backend settings are invalid.
        QueryGraphRuntimeError: When the identity DSN is missing.
    """

    agent = load_agent_settings()
    backend = load_backend_settings()
    token = secret_text(agent.langgraph_studio_access_token)
    dsn = secret_text(getattr(backend, "supabase_db_url", None))
    supabase_url = str(backend.supabase_url)

    def token_getter() -> str | None:
        """Return the configured access token.

        Returns:
            Bearer JWT, or ``None``.
        """

        return token

    def verify_access_token(raw_token: str) -> VerifiedAccessToken:
        """Verify the bearer JWT against hosted JWKS.

        Args:
            raw_token: Access token. Never logged.

        Returns:
            Verified claims.

        Raises:
            JwksVerificationError: Signature, audience, issuer, or expiry.
        """

        verifier = JwksVerifier(
            supabase_url=supabase_url,
            audience=backend.supabase_jwt_audience,
            cache_seconds=backend.jwks_cache_seconds,
            app_env=backend.app_env.value,
        )
        return verifier.verify_access_token(raw_token)

    def load_profile(user_id: str) -> ProfileSnapshot | None:
        """Reload the authoritative profile.

        Args:
            user_id: Verified subject.

        Returns:
            Snapshot, or ``None`` when missing.
        """

        if dsn is None:
            return None
        return load_profile_snapshot(dsn, user_id=user_id)

    def revoked(verified: VerifiedAccessToken, snapshot: ProfileSnapshot) -> bool:
        """Return whether the session is revoked.

        Args:
            verified: Verified token claims.
            snapshot: Live profile.

        Returns:
            ``True`` when the session must be rejected.
        """

        if dsn is None:
            return True
        return is_session_revoked(
            dsn,
            session_id=verified.session_id,
            issued_at=verified.issued_at,
            session_revoked_at=snapshot.session_revoked_at,
        )

    def export_gate() -> None:
        """Block company-content LangSmith export when unverified.

        Raises:
            ExternalFlowBlockedError: When tracing would leak company text.
        """

        assert_langsmith_export_permitted(
            tracing_enabled=agent.langsmith_tracing,
            content_class=ContentClass.REAL_COMPANY,
            provider_settings_verified=agent.subprocessor_matrix_verified,
            local_unsigned_waiver=agent.allows_unsigned_local_live_providers(),
        )

    def open_connection() -> object:
        """Open the per-run ``app_api`` connection.

        Returns:
            Open connection.

        Raises:
            QueryGraphRuntimeError: When the DSN is missing or connect fails.
        """

        if dsn is None:
            raise QueryGraphRuntimeError("app_api_connection_unbound")
        return open_run_app_api_connection(dsn)

    def bindings() -> QueryGraphProcessBindings:
        """Build process Hybrid/gateway/table bindings.

        Returns:
            Process bindings. Does not import FastAPI.
        """

        return build_query_process_bindings(settings=backend, app_state=None)

    def admit(**kwargs: object) -> object:
        """Admit using the connection captured later by the factory.

        Args:
            **kwargs: Admit fields plus optional ``connection``.

        Returns:
            Authorized runtime context.

        Raises:
            QueryAdmissionError: When admit cannot run.
        """

        connection = kwargs.get("connection")
        if not isinstance(connection, psycopg.Connection):
            raise QueryAdmissionError("database_rejected")
        from smart_rag_agents.query.studio.live_admission import production_admit

        return production_admit(
            connection=connection,  # pyright: ignore[reportUnknownArgumentType]
            caller=cast(CallerContext, kwargs["caller"]),
            conversation_id=cast(UUID, kwargs["conversation_id"]),
            idempotency_key=cast(UUID, kwargs["idempotency_key"]),
            payload_hash=cast(str, kwargs["payload_hash"]),
            message=cast(str, kwargs["message"]),
            token_issued_at=cast(datetime | None, kwargs.get("token_issued_at")),
        )

    return StudioLiveHooks(
        enabled=agent.langgraph_studio_live_enabled,
        token_getter=token_getter,
        verify_access_token=verify_access_token,
        load_profile=load_profile,
        is_revoked=revoked,
        admit=admit,
        assert_export_permitted=export_gate,
        open_connection=open_connection,
        build_bindings=bindings,
        postgres_url=None,
    )
