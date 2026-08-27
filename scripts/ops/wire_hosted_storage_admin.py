"""Fetch hosted service_role via Management API into gitignored Compose env.

The laptop Storage Admin JWT is the local ``supabase-demo`` key and hosted
Storage returns 400 for it. This writes the hosted legacy service_role into
``.env.compose`` as ``SUPABASE_STORAGE_ADMIN_SECRET``. Does not print the
key. Restart the host ingest worker after running.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from smart_rag_core.release.io import as_json_list, as_json_object

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ensure_app_runtime_role import parse_env, upsert_env

REPO = Path(__file__).resolve().parents[2]
MANAGEMENT = "https://api.supabase.com/v1"


def _jwt_claims(token: str) -> dict[str, object]:
    """Decode JWT payload claims without verifying the signature.

    Args:
        token: Compact JWS.

    Returns:
        Selected public claims only.
    """

    payload = token.split(".")[1]
    pad = "=" * (-len(payload) % 4)
    data = json.loads(base64.urlsafe_b64decode(payload + pad))
    return {key: data.get(key) for key in ("role", "iss", "ref")}


def _project_ref(env: dict[str, str]) -> str:
    """Return the hosted project ref from env.

    Args:
        env: Parsed env mapping.

    Returns:
        Project ref.

    Raises:
        RuntimeError: When the ref cannot be derived.
    """

    explicit = env.get("SUPABASE_PROJECT_REF", "").strip()
    if explicit:
        return explicit
    url = env.get("SUPABASE_URL") or env.get("SUPABASE_MANAGED_URL") or ""
    host = urlparse(url).hostname or ""
    if host.endswith(".supabase.co"):
        return host.split(".", 1)[0]
    raise RuntimeError("missing_project_ref")


def _fetch_service_role(*, access_token: str, project_ref: str) -> str:
    """Return the hosted legacy service_role JWT.

    Args:
        access_token: Supabase Management PAT.
        project_ref: Project ref.

    Returns:
        service_role JWT.

    Raises:
        RuntimeError: When the key is missing.
        httpx.HTTPStatusError: When management GET fails.
    """

    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{MANAGEMENT}/projects/{project_ref}/api-keys",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            params={"reveal": "true"},
        )
        if response.status_code >= 400:
            response = client.get(
                f"{MANAGEMENT}/projects/{project_ref}/api-keys",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
        response.raise_for_status()
        payload: object = response.json()
        try:
            items = as_json_list(payload)
        except ValueError:
            mapped_payload = as_json_object(payload)
            keys_raw: object = mapped_payload.get("keys", [])
            try:
                items = as_json_list(keys_raw)
            except ValueError:
                items = []
        for item in items:
            try:
                mapped = as_json_object(item)
            except ValueError:
                continue
            if mapped.get("name") == "service_role" and mapped.get("type") == "legacy":
                key = str(mapped.get("api_key") or mapped.get("key") or "")
                if key.startswith("eyJ"):
                    return key
    raise RuntimeError("hosted_service_role_unavailable")


def main() -> int:
    """Write hosted Storage Admin into ``.env.compose``.

    Returns:
        Process exit code.
    """

    env = parse_env(REPO / ".env")
    env.update(parse_env(REPO / ".env.compose"))
    access_token = env.get("SUPABASE_ACCESS_TOKEN", "").strip()
    if not access_token:
        print("missing_SUPABASE_ACCESS_TOKEN", file=sys.stderr)
        return 2
    project_ref = _project_ref(env)
    service_role = _fetch_service_role(
        access_token=access_token, project_ref=project_ref
    )
    claims = _jwt_claims(service_role)
    print(f"project_ref={project_ref}", flush=True)
    print(f"service_role_claims={claims}", flush=True)
    print(f"service_role_len={len(service_role)}", flush=True)
    compose = REPO / ".env.compose"
    upsert_env(compose, "SUPABASE_STORAGE_ADMIN_SECRET", service_role)
    upsert_env(compose, "SUPABASE_SERVICE_ROLE_KEY", service_role)
    print("wrote_hosted_storage_admin=.env.compose", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
