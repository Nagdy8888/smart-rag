"""Studio live authentication, revocation, and settings redaction."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage
from smart_rag_agents.query.studio_live import (
    DETAIL_DISABLED,
    DETAIL_PROFILE,
    DETAIL_REVOKED,
    DETAIL_TOKEN_INVALID,
    DETAIL_TOKEN_MISSING,
    run_studio_live_seed,
    seed_studio_live_unbound,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.security.jwks import JwksVerificationError, VerifiedAccessToken
from smart_rag_core.security.profile_snapshot import ProfileSnapshot
from smart_rag_core.settings import AgentSettings, BackendSettings

from tests.support.studio_live import (
    CANARY,
    _config,
    _hooks,
    _snapshot,
    _verified_token,
)


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
