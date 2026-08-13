"""Unit contracts for isolated Supabase Auth Admin HTTP boundaries."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable

import httpx
import pytest
from smart_rag_api.auth_admin import invitations, mfa_recovery, offboarding
from smart_rag_api.auth_admin.settings import (
    PrivilegedAuthSettings,
    load_privileged_auth_settings,
)


@pytest.fixture
def privileged_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> PrivilegedAuthSettings:
    """Build isolated settings with an ephemeral test credential."""

    monkeypatch.setenv("SUPABASE_URL", "https://project.invalid")
    monkeypatch.setenv(
        "SUPABASE_AUTH_ADMIN_SECRET",
        secrets.token_urlsafe(48),
    )
    return load_privileged_auth_settings()


def _install_mock_client(
    monkeypatch: pytest.MonkeyPatch,
    module_httpx: object,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Patch one boundary module to construct a mock-transport client."""

    real_client = httpx.Client

    def client_factory(
        *,
        timeout: float,
        headers: dict[str, str] | None = None,
    ) -> httpx.Client:
        """Return a real client backed by the deterministic mock transport."""

        return real_client(
            timeout=timeout,
            headers=headers,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(module_httpx, "Client", client_factory)


def test_mfa_recovery_uses_current_factor_and_global_logout_endpoints(
    privileged_settings: PrivilegedAuthSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovery lists/deletes every factor before one global session logout."""

    user_id = uuid.uuid4()
    verified_factor = uuid.uuid4()
    unverified_factor = uuid.uuid4()
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve deterministic GoTrue factor and logout responses."""

        requests.append((request.method, request.url.path))
        assert request.headers["authorization"].startswith("Bearer ")
        assert request.headers["apikey"]
        if request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {"id": str(verified_factor), "status": "verified"},
                    {"id": str(unverified_factor), "status": "unverified"},
                ],
            )
        return httpx.Response(200, json={})

    _install_mock_client(monkeypatch, mfa_recovery.httpx, handler)
    removed = mfa_recovery.reset_mfa_and_sessions_via_auth_admin(
        privileged_settings,
        user_id,
    )

    base = f"/auth/v1/admin/users/{user_id}"
    assert removed == 2
    assert requests == [
        ("GET", f"{base}/factors"),
        ("DELETE", f"{base}/factors/{verified_factor}"),
        ("DELETE", f"{base}/factors/{unverified_factor}"),
        ("POST", f"{base}/logout"),
    ]


def test_mfa_recovery_without_verified_factor_fails_before_mutation(
    privileged_settings: PrivilegedAuthSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed lost-factor request cannot become a reset operation."""

    user_id = uuid.uuid4()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return an inventory containing only an unverified factor."""

        requests.append(request.method)
        return httpx.Response(
            200,
            json=[{"id": str(uuid.uuid4()), "status": "unverified"}],
        )

    _install_mock_client(monkeypatch, mfa_recovery.httpx, handler)
    with pytest.raises(
        mfa_recovery.MfaRecoveryError,
        match="no verified factor",
    ):
        mfa_recovery.reset_mfa_and_sessions_via_auth_admin(
            privileged_settings,
            user_id,
        )
    assert requests == ["GET"]


def test_offboarding_uses_global_logout_and_fails_on_provider_error(
    privileged_settings: PrivilegedAuthSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offboarding owns one bounded global logout with no fallback success."""

    user_id = uuid.uuid4()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Capture the request and simulate provider unavailability."""

        requests.append(request)
        return httpx.Response(503, json={"message": "unavailable"})

    _install_mock_client(monkeypatch, offboarding.httpx, handler)
    with pytest.raises(
        offboarding.OffboardingError,
        match="provider session revocation failed",
    ):
        offboarding.revoke_provider_sessions(privileged_settings, user_id)
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == f"/auth/v1/admin/users/{user_id}/logout"


def test_invitation_provider_rejection_is_not_treated_as_success(
    privileged_settings: PrivilegedAuthSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every provider 4xx response triggers application-token compensation."""

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return the previously special-cased provider validation status."""

        requests.append(request)
        return httpx.Response(422, json={"message": "invalid invitation"})

    _install_mock_client(monkeypatch, invitations.httpx, handler)
    with pytest.raises(
        invitations.InvitationServiceError,
        match="auth admin invite call failed",
    ):
        invitations.send_provider_invite_email(
            privileged_settings,
            email="fixture@example.com",
            raw_token=secrets.token_urlsafe(32),
        )
    assert len(requests) == 1
    assert requests[0].url.path == "/auth/v1/invite"
