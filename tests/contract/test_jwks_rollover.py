"""JWKS provider rollover gate (Phase 2 Packet 4).

Real standby→active→retired rollover requires Supabase Management API access.
"""

from __future__ import annotations

import httpx
import pytest

from tests.contract.integration_support import read_process_env

MANAGED_PROJECT_REF = "qsjivtwtmlmtksufqjik"
MANAGED_JWKS_URL = (
    f"https://{MANAGED_PROJECT_REF}.supabase.co/auth/v1/.well-known/jwks.json"
)
ROLLOVER_BLOCKER = (
    "SUPABASE_ACCESS_TOKEN not available; cannot invoke Management API key rotate"
)


@pytest.mark.skip(reason=ROLLOVER_BLOCKER)
def test_provider_key_rollover_lifecycle() -> None:
    """Requires managed Auth signing-key rotate API — blocked in local Packet 4."""

    access_token = read_process_env("SUPABASE_ACCESS_TOKEN")
    assert access_token is not None


def test_managed_jwks_publishes_es256_key() -> None:
    """Read-only probe: managed JWKS exposes asymmetric ES256 (rollover still blocked)."""

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(MANAGED_JWKS_URL)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        pytest.skip(f"Managed JWKS unreachable: {exc}")

    keys = payload.get("keys", [])
    assert keys, "managed JWKS must publish at least one key"
    algorithms = {key.get("alg") for key in keys}
    assert "ES256" in algorithms
    assert "HS256" not in algorithms
