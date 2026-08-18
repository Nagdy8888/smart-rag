"""Unit tests for Phase 10 Packet 4 JWKS, origin, CDN, ParadeDB, and Valkey negatives."""

from __future__ import annotations

import json
import time
import uuid
from typing import cast

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm
from smart_rag_core.release.phase10_constants import (
    CDN_SSE_MIN_DURATION_SECONDS,
    CDN_SSE_VIA_CLOUDFRONT,
    ORIGIN_ROTATION_OVERLAP_MAX_MINUTES,
)
from smart_rag_core.release.phase10_packet1 import (
    LiveProviderProbe,
    packet1_checkbox_unchecked,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_packet2 import packet2_checkbox_unchecked
from smart_rag_core.release.phase10_packet3 import packet3_checkbox_unchecked
from smart_rag_core.release.phase10_packet4 import (
    CdnStreamEvidence,
    Phase10Packet4GateError,
    assert_caddy_dual_origin_values,
    assert_origin_overlap_minutes,
    assert_paradedb_projection_not_canonical,
    classify_p1004_a,
    classify_p1004_b,
    classify_p1004_c,
    classify_p1004_d,
    classify_p1004_e,
    packet4_checkbox_unchecked,
)
from smart_rag_core.security.jwks import (
    FORBIDDEN_ALGORITHMS,
    JwksVerificationError,
    JwksVerifier,
)

_KID_ACTIVE = "unit-packet4-active"
_KID_STANDBY = "unit-packet4-standby"
_ISSUER = "http://127.0.0.1:54321/auth/v1"
_HS256_SECRET = "unit-test-hs256-secret-with-32-bytes"  # noqa: S105

_GOOD_CADDY = """
:443 {
	@origin_current {
		header {$ORIGIN_HEADER_NAME} {$ORIGIN_HEADER_VALUE_CURRENT}
	}
	@origin_previous {
		header {$ORIGIN_HEADER_NAME} {$ORIGIN_HEADER_VALUE_PREVIOUS}
	}
	handle {
		respond "direct origin denied" 403
	}
}
"""


def _live_blocked() -> LiveProviderProbe:
    """Return a Blocked live-apply probe for classification tests.

    Returns:
        Frozen probe matching the current workstation constraint.
    """

    return LiveProviderProbe(
        terraform_installed=False,
        tofu_installed=False,
        aws_cli_installed=True,
        sts_ok=False,
        sts_detail="session expired",
        apply_state="Blocked",
        apply_reason="AWS session expired",
    )


def _public_jwk(private_key: ec.EllipticCurvePrivateKey, kid: str) -> dict[str, object]:
    """Return a public ES256 JWK document.

    Args:
        private_key: Ephemeral P-256 signing key used only in this module.
        kid: Key id placed on the JWK.

    Returns:
        String-keyed public JWK including ``kid`` and ``alg``.
    """

    raw = ECAlgorithm.to_jwk(private_key.public_key())
    jwk = cast(dict[str, object], json.loads(raw))
    jwk["kid"] = kid
    jwk["alg"] = "ES256"
    jwk["use"] = "sig"
    return jwk


def _sign_es256(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    kid: str,
) -> str:
    """Sign one ES256 access token.

    Args:
        private_key: Ephemeral P-256 signing key.
        kid: JWT header kid.

    Returns:
        Compact JWT string.
    """

    now = int(time.time())
    return jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "iss": _ISSUER,
            "exp": now + 3600,
            "iat": now,
            "role": "authenticated",
        },
        private_key,
        algorithm="ES256",
        headers={"kid": kid, "typ": "JWT"},
    )


def test_hs256_is_rejected_without_auth_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HS256 tokens fail closed and never become a JWKS signing path."""

    assert "HS256" in FORBIDDEN_ALGORITHMS
    private_key = ec.generate_private_key(ec.SECP256R1())
    jwk = _public_jwk(private_key, _KID_ACTIVE)

    def _get(_client: httpx.Client, url: str | httpx.URL) -> httpx.Response:
        """Serve one ES256 JWK.

        Args:
            _client: Patched HTTP client.
            url: Requested JWKS URL.

        Returns:
            HTTP 200 JWKS response.
        """

        request = httpx.Request("GET", url)
        return httpx.Response(200, json={"keys": [jwk]}, request=request)

    monkeypatch.setattr(httpx.Client, "get", _get)
    verifier = JwksVerifier(
        supabase_url="http://127.0.0.1:54321",
        audience="authenticated",
        cache_seconds=600,
        app_env="local",
    )
    valid = _sign_es256(private_key, kid=_KID_ACTIVE)
    assert verifier.verify_access_token(valid).algorithm == "ES256"
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "iss": _ISSUER,
            "exp": int(time.time()) + 3600,
            "role": "authenticated",
        },
        _HS256_SECRET,
        algorithm="HS256",
        headers={"kid": _KID_ACTIVE},
    )
    with pytest.raises(JwksVerificationError, match="forbidden symmetric"):
        verifier.verify_access_token(forged)


def test_jwks_rollover_keeps_valid_and_rejects_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standby then active overlap verifies; unknown and retired kids fail."""

    active = ec.generate_private_key(ec.SECP256R1())
    standby = ec.generate_private_key(ec.SECP256R1())
    keys = [
        _public_jwk(active, _KID_ACTIVE),
        _public_jwk(standby, _KID_STANDBY),
    ]

    def _get(_client: httpx.Client, url: str | httpx.URL) -> httpx.Response:
        """Serve the current JWKS snapshot.

        Args:
            _client: Patched HTTP client.
            url: Requested JWKS URL.

        Returns:
            HTTP 200 JWKS response.
        """

        request = httpx.Request("GET", url)
        return httpx.Response(200, json={"keys": list(keys)}, request=request)

    monkeypatch.setattr(httpx.Client, "get", _get)
    verifier = JwksVerifier(
        supabase_url="http://127.0.0.1:54321",
        audience="authenticated",
        cache_seconds=600,
        app_env="local",
    )
    old_token = _sign_es256(active, kid=_KID_ACTIVE)
    new_token = _sign_es256(standby, kid=_KID_STANDBY)
    assert verifier.verify_access_token(old_token).key_id == _KID_ACTIVE
    assert verifier.verify_access_token(new_token).key_id == _KID_STANDBY
    keys[:] = [_public_jwk(standby, _KID_STANDBY)]
    verifier_retired = JwksVerifier(
        supabase_url="http://127.0.0.1:54321",
        audience="authenticated",
        cache_seconds=600,
        app_env="local",
    )
    with pytest.raises(JwksVerificationError, match="unknown kid"):
        verifier_retired.verify_access_token(old_token)
    unknown = _sign_es256(standby, kid="00000000-0000-0000-0000-000000000000")
    with pytest.raises(JwksVerificationError, match="unknown kid"):
        verifier_retired.verify_access_token(unknown)


def test_origin_overlap_over_15_is_rejected() -> None:
    """Overlap longer than 15 minutes fails closed."""

    assert ORIGIN_ROTATION_OVERLAP_MAX_MINUTES == 15
    assert_origin_overlap_minutes(15)
    with pytest.raises(Phase10Packet4GateError, match="15"):
        assert_origin_overlap_minutes(16)


def test_missing_previous_origin_value_is_rejected() -> None:
    """Caddy without PREVIOUS cannot satisfy dual rotation."""

    assert_caddy_dual_origin_values(_GOOD_CADDY)
    missing = _GOOD_CADDY.replace(
        "{$ORIGIN_HEADER_VALUE_PREVIOUS}", "{$ORIGIN_HEADER_VALUE_CURRENT}"
    ).replace("ORIGIN_HEADER_VALUE_PREVIOUS", "ORIGIN_HEADER_VALUE_CURRENT")
    with pytest.raises(Phase10Packet4GateError, match="previous origin"):
        assert_caddy_dual_origin_values(missing)


def test_claiming_local_stream_as_cdn_is_not_passed() -> None:
    """Local EventSource duration cannot classify P10-04-C Passed."""

    blocked = classify_p1004_c(
        timeout_policy_passed=True,
        stream=CdnStreamEvidence(),
    )
    assert blocked == "Blocked"
    fake_local = classify_p1004_c(
        timeout_policy_passed=True,
        stream=CdnStreamEvidence(
            duration_seconds=float(CDN_SSE_MIN_DURATION_SECONDS),
            via="local",
            paid_runs=1,
        ),
    )
    assert fake_local == "Failed"
    cloudfront = classify_p1004_c(
        timeout_policy_passed=True,
        stream=CdnStreamEvidence(
            duration_seconds=float(CDN_SSE_MIN_DURATION_SECONDS),
            via=CDN_SSE_VIA_CLOUDFRONT,
            paid_runs=1,
        ),
    )
    assert cloudfront == "Passed"


def test_stale_bm25_snapshot_as_canonical_fails() -> None:
    """ParadeDB snapshots cannot be recorded as canonical recovery evidence."""

    assert_paradedb_projection_not_canonical({"paradedb_used_as_canonical": False})
    with pytest.raises(Phase10Packet4GateError, match="canonical"):
        assert_paradedb_projection_not_canonical({"paradedb_used_as_canonical": True})
    assert (
        classify_p1004_d(
            app_degrade_ok=True,
            rebuild_parity_ok=True,
            snapshot_as_canonical=True,
            live_kill_passed=False,
        )
        == "Failed"
    )


def test_classifications_fail_closed_and_keep_live_blocked() -> None:
    """Policy misses fail; missing CDN/managed JWKS/EC2 kill stay honest."""

    assert (
        classify_p1004_a(
            app_jwks_collected=True,
            app_jwks_passed=True,
            hs256_forbidden=True,
            managed_jwks_passed=False,
        )
        == "Passed"
    )
    assert (
        classify_p1004_a(
            app_jwks_collected=False,
            app_jwks_passed=False,
            hs256_forbidden=True,
            managed_jwks_passed=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1004_a(
            app_jwks_collected=True,
            app_jwks_passed=True,
            hs256_forbidden=False,
            managed_jwks_passed=False,
        )
        == "Failed"
    )
    assert (
        classify_p1004_b(
            origin_policy_passed=True,
            live_rotation_state="Blocked",
            live_rotation_passed=False,
        )
        == "Blocked"
    )
    assert (
        classify_p1004_b(
            origin_policy_passed=False,
            live_rotation_state="Blocked",
            live_rotation_passed=False,
        )
        == "Failed"
    )
    assert (
        classify_p1004_e(
            app_fail_closed_ok=True,
            live_valkey_kill_passed=False,
        )
        == "Passed"
    )
    assert (
        classify_p1004_d(
            app_degrade_ok=True,
            rebuild_parity_ok=True,
            snapshot_as_canonical=False,
            live_kill_passed=False,
        )
        == "Passed"
    )
    blocked = _live_blocked()
    assert blocked.apply_state == "Blocked"
    wrapper = """---
status: pending
---
1. [ ] [Provision isolated managed Supabase
2. [ ] [Implement GitHub OIDC, protected immutable expand/contract
3. [ ] [Prove direct-origin rejection, provider/crawl/parser egress
4. [ ] [Exercise asymmetric JWKS rollover, dual origin-secret rotation
"""
    assert wrapper_status_pending(wrapper) is True
    assert packet1_checkbox_unchecked(wrapper) is True
    assert packet2_checkbox_unchecked(wrapper) is True
    assert packet3_checkbox_unchecked(wrapper) is True
    assert packet4_checkbox_unchecked(wrapper) is True
