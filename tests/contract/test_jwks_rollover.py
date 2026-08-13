"""JWKS provider rollover gate (Phase 2 Packet 4).

Full standby→in_use→revoked lifecycle was executed against managed project
``qsjivtwtmlmtksufqjik`` (see phase evidence). CI asserts durable postconditions
via Management API + public JWKS rather than rotating keys on every run.
"""

from __future__ import annotations

import httpx
import pytest

from tests.contract.integration_support import read_process_env

MANAGED_PROJECT_REF = "qsjivtwtmlmtksufqjik"
MANAGED_JWKS_URL = (
    f"https://{MANAGED_PROJECT_REF}.supabase.co/auth/v1/.well-known/jwks.json"
)
MANAGEMENT_SIGNING_KEYS_URL = f"https://api.supabase.com/v1/projects/{MANAGED_PROJECT_REF}/config/auth/signing-keys"

# Proven rollover pair (standby created → rotated → prior revoked).
PROVEN_IN_USE_KID = "caa0e22b-cd04-4ee8-9701-a75aa682da78"
PROVEN_REVOKED_KID = "37b8d1b0-4217-4feb-becd-a986437dc994"


def test_managed_jwks_publishes_es256_key() -> None:
    """Read-only probe: managed JWKS exposes asymmetric ES256 only."""

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


def test_provider_key_rollover_postconditions() -> None:
    """Assert managed signing-key rollover postconditions after live proof.

    Requires ``SUPABASE_ACCESS_TOKEN``. Does not create or rotate keys.
    """

    access_token = read_process_env("SUPABASE_ACCESS_TOKEN")
    if access_token is None:
        pytest.skip("SUPABASE_ACCESS_TOKEN not set in process env")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    with httpx.Client(timeout=30.0) as client:
        keys_response = client.get(MANAGEMENT_SIGNING_KEYS_URL, headers=headers)
        keys_response.raise_for_status()
        keys = keys_response.json().get("keys", [])
        jwks_response = client.get(MANAGED_JWKS_URL)
        jwks_response.raise_for_status()
        jwks_payload = jwks_response.json()

    jwks_kids = {
        str(item.get("kid")) for item in jwks_payload.get("keys", []) if item.get("kid")
    }
    by_id = {str(item["id"]): item for item in keys}
    assert PROVEN_IN_USE_KID in by_id
    assert PROVEN_REVOKED_KID in by_id
    assert by_id[PROVEN_IN_USE_KID]["status"] == "in_use"
    assert by_id[PROVEN_IN_USE_KID]["algorithm"] == "ES256"
    assert by_id[PROVEN_REVOKED_KID]["status"] == "revoked"
    assert by_id[PROVEN_REVOKED_KID]["algorithm"] == "ES256"

    in_use_ids = {
        str(item["id"])
        for item in keys
        if item.get("status") == "in_use" and item.get("algorithm") == "ES256"
    }
    assert PROVEN_IN_USE_KID in in_use_ids
    assert PROVEN_IN_USE_KID in jwks_kids
    assert PROVEN_REVOKED_KID not in jwks_kids
    assert "HS256" not in {item.get("alg") for item in jwks_payload.get("keys", [])}
