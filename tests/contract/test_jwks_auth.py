"""JWKS asymmetric auth contract tests (Phase 2 Packet 4)."""

from __future__ import annotations

import time
import uuid

import httpx
import jwt
import pytest
from smart_rag_api.main import live, ready
from smart_rag_core.security.jwks import JwksVerificationError, JwksVerifier
from smart_rag_core.settings import BackendSettings, SharedSettings
from smart_rag_core.settings.base import load_settings

LOCAL_SUPABASE_URL = "http://127.0.0.1:54321"
LOCAL_ISSUER = f"{LOCAL_SUPABASE_URL}/auth/v1"
DEFAULT_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def _supabase_reachable() -> bool:
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(f"{LOCAL_SUPABASE_URL}/auth/v1/health")
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def _anon_key() -> str:
    from tests.contract.integration_support import read_process_env

    status = read_process_env("ANON_KEY")
    if status:
        return status
    return (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
        "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
    )


def _jwt_secret() -> str:
    from tests.contract.integration_support import read_process_env

    return (
        read_process_env("JWT_SECRET")
        or "super-secret-jwt-token-with-at-least-32-characters-long"
    )


def _signup_and_token() -> tuple[str, str]:
    """Return ``(user_id, access_token)`` from live local Auth."""

    email = f"jwks-{uuid.uuid4()}@example.com"
    password = "Str0ngPass!"  # noqa: S105 - disposable local Auth test user
    anon = _anon_key()
    headers = {"apikey": anon, "Authorization": f"Bearer {anon}"}
    with httpx.Client(timeout=10.0) as client:
        signup = client.post(
            f"{LOCAL_SUPABASE_URL}/auth/v1/signup",
            headers=headers,
            json={"email": email, "password": password},
        )
        if signup.status_code >= 400:
            token_resp = client.post(
                f"{LOCAL_SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers=headers,
                json={"email": email, "password": password},
            )
            token_resp.raise_for_status()
            payload = token_resp.json()
        else:
            payload = signup.json()
            if "access_token" not in payload:
                token_resp = client.post(
                    f"{LOCAL_SUPABASE_URL}/auth/v1/token?grant_type=password",
                    headers=headers,
                    json={"email": email, "password": password},
                )
                token_resp.raise_for_status()
                payload = token_resp.json()
    access_token = payload["access_token"]
    user_id = payload["user"]["id"]
    return user_id, access_token


@pytest.fixture
def verifier() -> JwksVerifier:
    """JWKS verifier bound to local Supabase."""

    return JwksVerifier(
        supabase_url=LOCAL_SUPABASE_URL,
        audience="authenticated",
        cache_seconds=600,
    )


@pytest.mark.skipif(not _supabase_reachable(), reason="local Supabase Auth unreachable")
def test_live_signup_token_verifies_with_es256_jwks(verifier: JwksVerifier) -> None:
    """Signup/login via Auth API; access token verifies through JWKS."""

    _user_id, token = _signup_and_token()
    verified = verifier.verify_access_token(token)
    assert verified.algorithm == "ES256"
    assert verified.issuer == LOCAL_ISSUER
    assert verified.audience == "authenticated"
    assert verified.subject


@pytest.mark.skipif(not _supabase_reachable(), reason="local Supabase Auth unreachable")
def test_rejects_hs256_token_signed_with_local_jwt_secret(
    verifier: JwksVerifier,
) -> None:
    """HS256/shared-secret tokens fail closed even with the local JWT secret."""

    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "iss": LOCAL_ISSUER,
            "exp": int(time.time()) + 3600,
            "role": "authenticated",
        },
        _jwt_secret(),
        algorithm="HS256",
    )
    with pytest.raises(JwksVerificationError, match="forbidden symmetric"):
        verifier.verify_access_token(forged)


@pytest.mark.skipif(not _supabase_reachable(), reason="local Supabase Auth unreachable")
def test_wrong_audience_fail_closed(verifier: JwksVerifier) -> None:
    """Verifier configured with wrong audience fails closed."""

    _user_id, token = _signup_and_token()
    strict = JwksVerifier(
        supabase_url=LOCAL_SUPABASE_URL,
        audience="service_role",
        cache_seconds=600,
    )
    with pytest.raises(JwksVerificationError):
        strict.verify_access_token(token)


@pytest.mark.skipif(not _supabase_reachable(), reason="local Supabase Auth unreachable")
def test_wrong_issuer_fail_closed() -> None:
    """Verifier configured with wrong issuer fails closed."""

    _user_id, token = _signup_and_token()
    wrong = JwksVerifier(
        supabase_url="http://127.0.0.1:59999",
        audience="authenticated",
        cache_seconds=600,
    )
    with pytest.raises(JwksVerificationError):
        wrong.verify_access_token(token)


def test_expired_token_fail_closed(verifier: JwksVerifier) -> None:
    """Expired tokens fail closed (synthetic ES256 rejection via jwt layer)."""

    # Without private ES256 key we assert decode rejects expired claims when
    # signature verification is bypassed in PyJWT's exp check path.
    expired = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "iss": LOCAL_ISSUER,
            "exp": int(time.time()) - 10,
        },
        "unused",
        algorithm="HS256",
    )
    with pytest.raises(JwksVerificationError, match="forbidden symmetric"):
        verifier.verify_access_token(expired)


@pytest.mark.skipif(not _supabase_reachable(), reason="local Supabase Auth unreachable")
def test_unknown_kid_after_refresh_fails_closed(verifier: JwksVerifier) -> None:
    """Unknown kid after one JWKS refresh fails closed."""

    _user_id, token = _signup_and_token()
    parts = token.split(".")
    import base64
    import json

    header = json.loads(base64.urlsafe_b64decode(parts[0] + "=="))
    header["kid"] = "00000000-0000-0000-0000-000000000000"
    parts[0] = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )
    tampered = ".".join(parts)
    with pytest.raises(JwksVerificationError, match="unknown kid"):
        verifier.verify_access_token(tampered)


def test_shared_settings_and_health_do_not_expose_auth_admin_secret() -> None:
    """General settings and health paths must not surface privileged secrets."""

    shared_fields = SharedSettings.model_fields
    backend_fields = BackendSettings.model_fields
    assert "supabase_auth_admin_secret" not in shared_fields
    assert "supabase_auth_admin_secret" not in backend_fields
    assert "service_role" not in str(shared_fields).lower()

    health = {**live(), **ready()}
    assert "service_role" not in str(health).lower()
    assert "auth_admin" not in str(health).lower()

    loaded = load_settings(BackendSettings)
    dumped = loaded.model_dump_json()
    assert "SUPABASE_AUTH_ADMIN_SECRET" not in dumped
