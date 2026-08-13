"""Asymmetric Supabase JWT verification through JWKS (ES256/RS256 only)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import cast

import httpx
import jwt
from cryptography.exceptions import UnsupportedAlgorithm
from jwt import PyJWK, PyJWKSet

LOGGER = logging.getLogger(__name__)

ALLOWED_ALGORITHMS = frozenset({"ES256", "RS256"})
FORBIDDEN_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})


class JwksVerificationError(Exception):
    """Raised when a bearer token fails asymmetric verification."""


@dataclass(frozen=True, slots=True)
class VerifiedAccessToken:
    """Claims extracted from a verified Supabase access token."""

    subject: str
    audience: str
    issuer: str
    algorithm: str
    key_id: str
    session_id: str | None
    authentication_methods: tuple[str, ...]
    assurance_level: str | None
    expires_at: int
    issued_at: int | None
    raw_claims: dict[str, object]


@dataclass
class _JwksCache:
    """In-memory JWKS snapshot with bounded TTL."""

    jwks: PyJWKSet
    fetched_at: float


def _string_keyed_object(value: object, *, error_message: str) -> dict[str, object]:
    """Validate and narrow one decoded JSON object.

    Args:
        value: Untrusted value returned by a JSON or JWT decoder.
        error_message: Sanitized verification error for an invalid shape.

    Returns:
        A mapping whose keys are all strings.

    Raises:
        JwksVerificationError: If ``value`` is not a string-keyed object.
    """

    if not isinstance(value, dict):
        raise JwksVerificationError(error_message)
    untyped = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in untyped):
        raise JwksVerificationError(error_message)
    return cast(dict[str, object], untyped)


def _jwks_document(value: object) -> dict[str, object]:
    """Validate the object and key-list shape required by ``PyJWKSet``.

    Args:
        value: Untrusted JSON value returned by the JWKS endpoint.

    Returns:
        A string-keyed JWKS object containing string-keyed key objects.

    Raises:
        JwksVerificationError: If the document shape is invalid.
    """

    document = _string_keyed_object(value, error_message="invalid jwks payload")
    raw_keys = document.get("keys")
    if not isinstance(raw_keys, list):
        raise JwksVerificationError("invalid jwks payload")
    key_values = cast(list[object], raw_keys)
    keys = [
        _string_keyed_object(item, error_message="invalid jwks payload")
        for item in key_values
    ]
    narrowed = dict(document)
    narrowed["keys"] = keys
    return narrowed


def _numeric_date(value: object, *, claim: str) -> int:
    """Convert one already-verified JWT NumericDate claim to an integer.

    Args:
        value: Decoded JSON value accepted by PyJWT's NumericDate validation.
        claim: Claim name used only in the sanitized failure message.

    Returns:
        Integer epoch seconds.

    Raises:
        JwksVerificationError: If the decoded value is not numeric.
    """

    if not isinstance(value, str | int | float):
        raise JwksVerificationError(f"invalid {claim}")
    try:
        return int(value)
    except ValueError as exc:
        raise JwksVerificationError(f"invalid {claim}") from exc


class JwksVerifier:
    """Fetch and cache Supabase JWKS; verify access tokens fail-closed."""

    def __init__(
        self,
        *,
        supabase_url: str,
        audience: str = "authenticated",
        cache_seconds: int = 600,
        http_timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize verifier endpoints and cache bounds.

        Args:
            supabase_url: Supabase project URL without trailing slash.
            audience: Required JWT ``aud`` claim. Defaults to ``authenticated``.
            cache_seconds: JWKS cache TTL; must not exceed 600 seconds.
            http_timeout_seconds: Network timeout for JWKS fetch.

        Raises:
            ValueError: When ``cache_seconds`` exceeds 600.
        """

        if cache_seconds < 1 or cache_seconds > 600:
            raise ValueError("jwks_cache_seconds must be between 1 and 600")

        normalized = supabase_url.rstrip("/")
        self._issuer = f"{normalized}/auth/v1"
        self._jwks_url = f"{self._issuer}/.well-known/jwks.json"
        self._audience = audience
        self._cache_seconds = cache_seconds
        self._http_timeout_seconds = http_timeout_seconds
        self._cache: _JwksCache | None = None

    @property
    def issuer(self) -> str:
        """Return the expected JWT issuer."""

        return self._issuer

    @property
    def jwks_url(self) -> str:
        """Return the JWKS discovery URL."""

        return self._jwks_url

    def verify_access_token(self, token: str) -> VerifiedAccessToken:
        """Verify one bearer access token against cached JWKS.

        Args:
            token: Raw JWT string without the ``Bearer`` prefix.

        Returns:
            Parsed claims for an asymmetrically signed Supabase access token.

        Raises:
            JwksVerificationError: On malformed tokens, forbidden algorithms,
                issuer/audience/exp/kid failures, or JWKS fetch errors.
        """

        if not token or not token.strip():
            raise JwksVerificationError("missing token")

        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise JwksVerificationError("invalid token header") from exc

        algorithm = str(header.get("alg", ""))
        if algorithm in FORBIDDEN_ALGORITHMS:
            raise JwksVerificationError("forbidden symmetric algorithm")
        if algorithm not in ALLOWED_ALGORITHMS:
            raise JwksVerificationError("unsupported algorithm")

        key_id = header.get("kid")
        if not isinstance(key_id, str) or not key_id.strip():
            raise JwksVerificationError("missing kid")

        signing_key = self._resolve_signing_key(key_id)
        if signing_key is None:
            raise JwksVerificationError("unknown kid after refresh")

        try:
            decoded_claims: object = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": ["exp", "sub", "iss", "aud"],
                    "verify_signature": True,
                },
            )
        except jwt.PyJWTError as exc:
            raise JwksVerificationError("token verification failed") from exc
        claims = _string_keyed_object(
            decoded_claims,
            error_message="invalid token claims",
        )

        subject = str(claims.get("sub", ""))
        if not subject:
            raise JwksVerificationError("missing sub")

        session_id = claims.get("session_id")
        session_text = str(session_id) if session_id is not None else None

        amr_raw = claims.get("amr")
        methods: tuple[str, ...]
        if isinstance(amr_raw, list):
            methods = tuple(str(item) for item in cast(list[object], amr_raw))
        else:
            methods = ()

        aal = claims.get("aal")
        assurance = str(aal) if aal is not None else None

        return VerifiedAccessToken(
            subject=subject,
            audience=str(claims["aud"]),
            issuer=str(claims["iss"]),
            algorithm=algorithm,
            key_id=key_id,
            session_id=session_text,
            authentication_methods=methods,
            assurance_level=assurance,
            expires_at=_numeric_date(claims["exp"], claim="exp"),
            issued_at=(
                _numeric_date(claims["iat"], claim="iat") if "iat" in claims else None
            ),
            raw_claims=claims,
        )

    def _resolve_signing_key(self, key_id: str) -> PyJWK | None:
        """Return a signing key, refreshing JWKS once on unknown ``kid``."""

        cached = self._get_cached_jwks()
        key = self._lookup_key(cached.jwks, key_id)
        if key is not None:
            return key

        refreshed = self._fetch_jwks(force=True)
        return self._lookup_key(refreshed, key_id)

    def _get_cached_jwks(self) -> _JwksCache:
        """Return cached JWKS, fetching when missing or expired."""

        now = time.monotonic()
        if self._cache is None or now - self._cache.fetched_at >= self._cache_seconds:
            jwks = self._fetch_jwks(force=True)
            return _JwksCache(jwks=jwks, fetched_at=now)
        return self._cache

    def _fetch_jwks(self, *, force: bool) -> PyJWKSet:
        """Download JWKS from Supabase Auth."""

        del force  # single refresh path; kept for clarity in callers
        try:
            with httpx.Client(timeout=self._http_timeout_seconds) as client:
                response = client.get(self._jwks_url)
                response.raise_for_status()
                decoded_payload: object = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.warning(
                "JWKS fetch failed",
                extra={"event": "jwks.fetch.failed", "jwks_url": self._jwks_url},
            )
            raise JwksVerificationError("jwks fetch failed") from exc

        payload = _jwks_document(decoded_payload)
        try:
            jwks = PyJWKSet.from_dict(payload)
        except (TypeError, ValueError, jwt.PyJWTError, UnsupportedAlgorithm) as exc:
            raise JwksVerificationError("invalid jwks payload") from exc

        for jwk in jwks.keys:
            if jwk.algorithm_name in FORBIDDEN_ALGORITHMS:
                raise JwksVerificationError("jwks contains forbidden symmetric key")

        self._cache = _JwksCache(jwks=jwks, fetched_at=time.monotonic())
        return jwks

    @staticmethod
    def _lookup_key(jwks: PyJWKSet, key_id: str) -> PyJWK | None:
        """Find one JWK by ``kid``."""

        for jwk in jwks.keys:
            if jwk.key_id == key_id:
                if jwk.algorithm_name in FORBIDDEN_ALGORITHMS:
                    return None
                if jwk.algorithm_name not in ALLOWED_ALGORITHMS:
                    return None
                return jwk
        return None
