"""Prove managed Supabase JWT signing-key standby→in_use→revoked rollover.

Requires process env:
  SUPABASE_ACCESS_TOKEN, SUPABASE_PROJECT_REF, SUPABASE_MANAGED_URL,
  SUPABASE_ANON_KEY. Fetches service_role via Management API (not persisted).

Side effects: creates a temporary Auth user; creates/rotates/revokes signing keys.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import jwt
from smart_rag_core.security.jwks import JwksVerificationError, JwksVerifier

ROOT = Path(__file__).resolve().parents[2]
MANAGEMENT = "https://api.supabase.com/v1"
STATE_PATH = ROOT / ".tmp-jwks-rollover-state.json"


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing required env {name}")
    return value


def _mgmt_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _list_keys(client: httpx.Client, ref: str, token: str) -> list[dict[str, Any]]:
    response = client.get(
        f"{MANAGEMENT}/projects/{ref}/config/auth/signing-keys",
        headers=_mgmt_headers(token),
    )
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("keys", []))


def _jwks_kids(client: httpx.Client, managed_url: str) -> set[str]:
    response = client.get(f"{managed_url.rstrip('/')}/auth/v1/.well-known/jwks.json")
    response.raise_for_status()
    return {
        str(key.get("kid")) for key in response.json().get("keys", []) if key.get("kid")
    }


def _decode_header(token: str) -> dict[str, Any]:
    return dict(jwt.get_unverified_header(token))


def main() -> int:
    """Execute managed standby to in_use to revoked JWKS rollover proof.

    Returns:
        Process exit code ``0`` on success.
    """

    access_token = _require("SUPABASE_ACCESS_TOKEN")
    ref = _require("SUPABASE_PROJECT_REF")
    managed_url = _require("SUPABASE_MANAGED_URL").rstrip("/")
    anon_key = _require("SUPABASE_ANON_KEY")

    with httpx.Client(timeout=30.0) as client:
        keys = _list_keys(client, ref, access_token)
        in_use = next((k for k in keys if k.get("status") == "in_use"), None)
        standby = next((k for k in keys if k.get("status") == "standby"), None)
        if in_use is None:
            raise SystemExit("no in_use signing key")
        if standby is None:
            created = client.post(
                f"{MANAGEMENT}/projects/{ref}/config/auth/signing-keys",
                headers=_mgmt_headers(access_token),
                json={"algorithm": "ES256"},
            )
            created.raise_for_status()
            standby = created.json()
            print(f"created_standby={standby['id']}")
            # Platform throttles signing-key state changes (~5 minutes).
            print("waiting_300s_before_rotate")
            time.sleep(300)
        else:
            print(f"reuse_standby={standby['id']}")

        old_id = str(in_use["id"])
        new_id = str(standby["id"])
        kids_before = _jwks_kids(client, managed_url)
        print(f"jwks_before={sorted(kids_before)}")
        if old_id not in kids_before or new_id not in kids_before:
            # Wait for edge cache to publish standby.
            for _ in range(60):
                time.sleep(10)
                kids_before = _jwks_kids(client, managed_url)
                if old_id in kids_before and new_id in kids_before:
                    break
            else:
                raise SystemExit(
                    f"standby not published in JWKS: {sorted(kids_before)}"
                )

        api_keys = client.get(
            f"{MANAGEMENT}/projects/{ref}/api-keys",
            headers=_mgmt_headers(access_token),
        )
        api_keys.raise_for_status()
        service_role = next(
            (
                item["api_key"]
                for item in api_keys.json()
                if item.get("name") == "service_role" and item.get("type") == "legacy"
            ),
            None,
        )
        if not service_role:
            raise SystemExit("service_role api key unavailable")

        email = f"jwks.rollover.{int(time.time())}@example.com"
        password = f"Aa1!{os.urandom(8).hex()}"
        admin_headers = {
            "apikey": service_role,
            "Authorization": f"Bearer {service_role}",
            "Content-Type": "application/json",
        }
        created_user = client.post(
            f"{managed_url}/auth/v1/admin/users",
            headers=admin_headers,
            json={"email": email, "password": password, "email_confirm": True},
        )
        created_user.raise_for_status()
        user_id = created_user.json()["id"]
        print(f"user_id={user_id}")

        login_headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json",
        }
        pre = client.post(
            f"{managed_url}/auth/v1/token?grant_type=password",
            headers=login_headers,
            json={"email": email, "password": password},
        )
        pre.raise_for_status()
        old_token = pre.json()["access_token"]
        old_header = _decode_header(old_token)
        print(f"pre_rotate_kid={old_header.get('kid')}")
        if old_header.get("kid") != old_id:
            raise SystemExit("pre-rotate token not signed by in_use key")

        rotate = client.patch(
            f"{MANAGEMENT}/projects/{ref}/config/auth/signing-keys/{new_id}",
            headers=_mgmt_headers(access_token),
            json={"status": "in_use"},
        )
        if rotate.status_code == 429:
            print("rotate_throttled_waiting_300s")
            time.sleep(300)
            rotate = client.patch(
                f"{MANAGEMENT}/projects/{ref}/config/auth/signing-keys/{new_id}",
                headers=_mgmt_headers(access_token),
                json={"status": "in_use"},
            )
        rotate.raise_for_status()
        print(f"rotated_in_use={new_id}")

        post = client.post(
            f"{managed_url}/auth/v1/token?grant_type=password",
            headers=login_headers,
            json={"email": email, "password": password},
        )
        post.raise_for_status()
        new_token = post.json()["access_token"]
        new_header = _decode_header(new_token)
        print(f"post_rotate_kid={new_header.get('kid')}")
        if new_header.get("kid") != new_id:
            raise SystemExit("post-rotate token not signed by new key")

        verifier = JwksVerifier(
            supabase_url=managed_url,
            audience="authenticated",
            cache_seconds=1,
        )
        verifier.verify_access_token(old_token)
        verifier.verify_access_token(new_token)
        print("overlap_verify_ok")

        # Throttle before revoke.
        print("waiting_300s_before_revoke")
        time.sleep(300)
        revoke = client.patch(
            f"{MANAGEMENT}/projects/{ref}/config/auth/signing-keys/{old_id}",
            headers=_mgmt_headers(access_token),
            json={"status": "revoked"},
        )
        if revoke.status_code == 429:
            print("revoke_throttled_waiting_300s")
            time.sleep(300)
            revoke = client.patch(
                f"{MANAGEMENT}/projects/{ref}/config/auth/signing-keys/{old_id}",
                headers=_mgmt_headers(access_token),
                json={"status": "revoked"},
            )
        revoke.raise_for_status()
        print(f"revoked={old_id}")

        # Edge caches JWKS for ~10 minutes; poll until old kid disappears.
        for attempt in range(90):
            kids = _jwks_kids(client, managed_url)
            if old_id not in kids and new_id in kids:
                print(f"jwks_after_revoke={sorted(kids)} attempts={attempt + 1}")
                break
            time.sleep(10)
        else:
            raise SystemExit(f"old kid still in JWKS after revoke wait: {sorted(kids)}")

        verifier = JwksVerifier(
            supabase_url=managed_url,
            audience="authenticated",
            cache_seconds=1,
        )
        try:
            verifier.verify_access_token(old_token)
            raise SystemExit("old token unexpectedly verified after revoke")
        except JwksVerificationError:
            print("old_token_fail_closed_ok")
        verifier.verify_access_token(new_token)
        print("new_token_still_valid_ok")

        # Cleanup test user (best effort).
        client.delete(
            f"{managed_url}/auth/v1/admin/users/{user_id}",
            headers=admin_headers,
        )
        STATE_PATH.write_text(
            json.dumps(
                {
                    "old_id": old_id,
                    "new_id": new_id,
                    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "result": "standby_in_use_revoked_proven",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("ROLLOVER_PROOF_OK")
        return 0


if __name__ == "__main__":
    sys.exit(main())
