"""Unit tests for local Docker JWT issuer aliases (Phase 9 P09-07-A)."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Mapping
from typing import cast

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm
from smart_rag_core.security.jwks import (
    FORBIDDEN_JWT_ROLES,
    LOCAL_DOCKER_INTERNAL_JWT_ISSUER,
    LOCAL_JWT_ISSUER_ALIASES,
    LOCAL_LOOPBACK_JWT_ISSUER,
    REQUIRED_JWT_ROLE,
    JwksVerificationError,
    JwksVerifier,
    resolved_jwt_issuers,
)

from tests.unit.test_settings import configure_hosted_backend_env

_KID = "unit-local-es256-kid"
_DOCKER_SUPABASE_URL = "http://host.docker.internal:54321"
_LOOPBACK_SUPABASE_URL = "http://127.0.0.1:54321"
_FOREIGN_ISSUER = "https://auth.evil.example/auth/v1"
_HS256_SECRET = "unit-test-hs256-secret-with-32-bytes"  # noqa: S105


def _public_jwk(private_key: ec.EllipticCurvePrivateKey) -> dict[str, object]:
    """Return a public ES256 JWK document for the generated key.

    Args:
        private_key: Ephemeral P-256 signing key used only in this module.

    Returns:
        String-keyed public JWK including ``kid`` and ``alg``.
    """

    raw = ECAlgorithm.to_jwk(private_key.public_key())
    jwk = cast(dict[str, object], json.loads(raw))
    jwk["kid"] = _KID
    jwk["alg"] = "ES256"
    jwk["use"] = "sig"
    return jwk


def _sign_es256(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    issuer: str,
    audience: str = "authenticated",
    role: str = "authenticated",
) -> str:
    """Sign one ES256 access token with required claims.

    Args:
        private_key: Ephemeral P-256 signing key.
        issuer: JWT ``iss`` claim.
        audience: JWT ``aud`` claim.
        role: JWT ``role`` claim. User tokens use ``authenticated``.

    Returns:
        Compact JWT string.
    """

    now = int(time.time())
    claims: dict[str, str | int] = {
        "sub": str(uuid.uuid4()),
        "aud": audience,
        "iss": issuer,
        "exp": now + 3600,
        "iat": now,
    }
    if role:
        claims["role"] = role
    return jwt.encode(
        claims,
        private_key,
        algorithm="ES256",
        headers={"kid": _KID, "typ": "JWT"},
    )


def _patch_jwks(
    monkeypatch: pytest.MonkeyPatch,
    jwk: Mapping[str, object],
) -> list[str]:
    """Serve a fixed JWKS document and record requested URLs.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        jwk: Public JWK object returned under ``keys``.

    Returns:
        Mutable list that receives every requested JWKS URL.
    """

    fetched: list[str] = []

    def _get(
        _client: httpx.Client,
        url: str | httpx.URL,
    ) -> httpx.Response:
        """Return the fixture JWKS payload.

        Args:
            _client: Patched HTTP client.
            url: Requested JWKS URL.

        Returns:
            HTTP 200 JWKS response.
        """

        fetched.append(str(url))
        request = httpx.Request("GET", url)
        return httpx.Response(200, json={"keys": [dict(jwk)]}, request=request)

    monkeypatch.setattr(httpx.Client, "get", _get)
    return fetched


def _require_jwks_verifier(application: object) -> JwksVerifier:
    """Return the lifespan JWKS verifier from a started FastAPI app.

    Args:
        application: FastAPI app after lifespan startup.

    Returns:
        The bound ``JwksVerifier``.

    Raises:
        AssertionError: If lifespan did not bind a verifier.
    """

    bound: object = getattr(application, "state", None)
    verifier: object = getattr(bound, "jwks_verifier", None)
    if not isinstance(verifier, JwksVerifier):
        raise AssertionError("jwks_verifier was not bound")
    return verifier


def test_packet4_issuer_constants_match_jwks_aliases() -> None:
    """Phase 9 freeze constants must stay identical to the JWKS alias pair."""

    from smart_rag_core.release.packet4 import (
        API_EXPECTED_JWT_ISSUER,
        LOCAL_GOTRUE_JWT_ISSUER,
    )

    assert API_EXPECTED_JWT_ISSUER == LOCAL_DOCKER_INTERNAL_JWT_ISSUER
    assert LOCAL_GOTRUE_JWT_ISSUER == LOCAL_LOOPBACK_JWT_ISSUER
    assert LOCAL_JWT_ISSUER_ALIASES == frozenset(
        {LOCAL_LOOPBACK_JWT_ISSUER, LOCAL_DOCKER_INTERNAL_JWT_ISSUER}
    )


def test_resolved_jwt_issuers_expand_only_for_local_alias_hosts() -> None:
    """Only APP_ENV=local on the documented pair expands both issuers."""

    docker_local = resolved_jwt_issuers(
        supabase_url=_DOCKER_SUPABASE_URL,
        app_env="local",
    )
    loopback_local = resolved_jwt_issuers(
        supabase_url=_LOOPBACK_SUPABASE_URL,
        app_env="local",
    )
    assert docker_local == (
        LOCAL_DOCKER_INTERNAL_JWT_ISSUER,
        LOCAL_LOOPBACK_JWT_ISSUER,
    )
    assert loopback_local == (
        LOCAL_LOOPBACK_JWT_ISSUER,
        LOCAL_DOCKER_INTERNAL_JWT_ISSUER,
    )
    assert resolved_jwt_issuers(
        supabase_url=_DOCKER_SUPABASE_URL,
        app_env="production",
    ) == (LOCAL_DOCKER_INTERNAL_JWT_ISSUER,)
    assert resolved_jwt_issuers(
        supabase_url=_DOCKER_SUPABASE_URL,
        app_env="staging",
    ) == (LOCAL_DOCKER_INTERNAL_JWT_ISSUER,)
    assert resolved_jwt_issuers(
        supabase_url=_DOCKER_SUPABASE_URL,
        app_env="test",
    ) == (LOCAL_DOCKER_INTERNAL_JWT_ISSUER,)
    assert resolved_jwt_issuers(
        supabase_url="https://example.supabase.co",
        app_env="local",
    ) == ("https://example.supabase.co/auth/v1",)


@pytest.mark.parametrize(
    ("supabase_url", "token_iss"),
    (
        (_DOCKER_SUPABASE_URL, LOCAL_LOOPBACK_JWT_ISSUER),
        (_DOCKER_SUPABASE_URL, LOCAL_DOCKER_INTERNAL_JWT_ISSUER),
        (_LOOPBACK_SUPABASE_URL, LOCAL_LOOPBACK_JWT_ISSUER),
        (_LOOPBACK_SUPABASE_URL, LOCAL_DOCKER_INTERNAL_JWT_ISSUER),
    ),
)
def test_local_alias_pair_verifies_against_configured_jwks(
    monkeypatch: pytest.MonkeyPatch,
    supabase_url: str,
    token_iss: str,
) -> None:
    """APP_ENV=local accepts either documented iss against SUPABASE_URL JWKS."""

    private_key = ec.generate_private_key(ec.SECP256R1())
    fetched = _patch_jwks(monkeypatch, _public_jwk(private_key))
    verifier = JwksVerifier(
        supabase_url=supabase_url,
        audience="authenticated",
        cache_seconds=600,
        app_env="local",
    )
    token = _sign_es256(private_key, issuer=token_iss)
    verified = verifier.verify_access_token(token)
    assert verified.algorithm == "ES256"
    assert verified.issuer == token_iss
    assert verified.key_id == _KID
    assert fetched == [verifier.jwks_url]
    assert verifier.jwks_url == f"{supabase_url}/auth/v1/.well-known/jwks.json"


def test_local_foreign_issuer_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_ENV=local still rejects an iss outside the documented alias pair."""

    private_key = ec.generate_private_key(ec.SECP256R1())
    _patch_jwks(monkeypatch, _public_jwk(private_key))
    verifier = JwksVerifier(
        supabase_url=_DOCKER_SUPABASE_URL,
        audience="authenticated",
        cache_seconds=600,
        app_env="local",
    )
    token = _sign_es256(private_key, issuer=_FOREIGN_ISSUER)
    with pytest.raises(JwksVerificationError, match="token verification failed"):
        verifier.verify_access_token(token)


def test_local_hs256_is_rejected_even_with_alias_iss() -> None:
    """HS256 stays forbidden when iss is a documented local alias."""

    verifier = JwksVerifier(
        supabase_url=_DOCKER_SUPABASE_URL,
        audience="authenticated",
        cache_seconds=600,
        app_env="local",
    )
    now = int(time.time())
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "iss": LOCAL_LOOPBACK_JWT_ISSUER,
            "exp": now + 3600,
            "role": "authenticated",
        },
        _HS256_SECRET,
        algorithm="HS256",
        headers={"kid": _KID},
    )
    with pytest.raises(JwksVerificationError, match="forbidden symmetric"):
        verifier.verify_access_token(forged)


def test_production_does_not_accept_loopback_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-local environments require iss to match SUPABASE_URL exactly."""

    private_key = ec.generate_private_key(ec.SECP256R1())
    _patch_jwks(monkeypatch, _public_jwk(private_key))
    verifier = JwksVerifier(
        supabase_url=_DOCKER_SUPABASE_URL,
        audience="authenticated",
        cache_seconds=600,
        app_env="production",
    )
    token = _sign_es256(private_key, issuer=LOCAL_LOOPBACK_JWT_ISSUER)
    with pytest.raises(JwksVerificationError, match="token verification failed"):
        verifier.verify_access_token(token)
    assert verifier.allowed_issuers == (LOCAL_DOCKER_INTERNAL_JWT_ISSUER,)


def test_backend_lifespan_wires_local_issuer_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compose APP_ENV=local plus docker SUPABASE_URL enables the alias pair."""

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("SUPABASE_URL", _DOCKER_SUPABASE_URL)
    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    from fastapi.testclient import TestClient
    from smart_rag_api.main import create_app

    application = create_app()
    with TestClient(application):
        verifier = _require_jwks_verifier(application)
        assert verifier.jwks_url == (
            f"{_DOCKER_SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        )
        assert verifier.allowed_issuers == (
            LOCAL_DOCKER_INTERNAL_JWT_ISSUER,
            LOCAL_LOOPBACK_JWT_ISSUER,
        )


def test_backend_lifespan_production_keeps_single_issuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production lifespan does not expand the local Docker iss pair."""

    configure_hosted_backend_env(monkeypatch, app_env="production")
    monkeypatch.setenv("SUPABASE_URL", _DOCKER_SUPABASE_URL)
    from fastapi.testclient import TestClient
    from smart_rag_api.main import create_app

    application = create_app()
    with TestClient(application):
        verifier = _require_jwks_verifier(application)
        assert verifier.allowed_issuers == (LOCAL_DOCKER_INTERNAL_JWT_ISSUER,)


@pytest.mark.parametrize("role", sorted(FORBIDDEN_JWT_ROLES))
def test_jwks_rejects_service_role_and_anon(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    """ES256 tokens with ``service_role`` or ``anon`` fail closed."""

    private_key = ec.generate_private_key(ec.SECP256R1())
    _patch_jwks(monkeypatch, _public_jwk(private_key))
    verifier = JwksVerifier(
        supabase_url=_LOOPBACK_SUPABASE_URL,
        audience="authenticated",
        cache_seconds=600,
        app_env="local",
    )
    token = _sign_es256(
        private_key,
        issuer=LOCAL_LOOPBACK_JWT_ISSUER,
        role=role,
    )
    with pytest.raises(JwksVerificationError, match="forbidden role"):
        verifier.verify_access_token(token)


def test_jwks_rejects_missing_role_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    """User JWTs must carry ``role=authenticated``."""

    private_key = ec.generate_private_key(ec.SECP256R1())
    _patch_jwks(monkeypatch, _public_jwk(private_key))
    verifier = JwksVerifier(
        supabase_url=_LOOPBACK_SUPABASE_URL,
        audience="authenticated",
        cache_seconds=600,
        app_env="local",
    )
    token = _sign_es256(
        private_key,
        issuer=LOCAL_LOOPBACK_JWT_ISSUER,
        role="",
    )
    with pytest.raises(JwksVerificationError, match="forbidden role"):
        verifier.verify_access_token(token)


def test_jwks_accepts_authenticated_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local user JWTs with ``role=authenticated`` still verify."""

    private_key = ec.generate_private_key(ec.SECP256R1())
    _patch_jwks(monkeypatch, _public_jwk(private_key))
    verifier = JwksVerifier(
        supabase_url=_LOOPBACK_SUPABASE_URL,
        audience="authenticated",
        cache_seconds=600,
        app_env="local",
    )
    token = _sign_es256(
        private_key,
        issuer=LOCAL_LOOPBACK_JWT_ISSUER,
        role=REQUIRED_JWT_ROLE,
    )
    verified = verifier.verify_access_token(token)
    assert verified.raw_claims.get("role") == REQUIRED_JWT_ROLE
