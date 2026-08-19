"""Live thin-developer-UI HTTP contract against local FastAPI and Auth."""

from __future__ import annotations

import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import cast
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from smart_rag_core.memory.reaper import search_conversation_lingering_ids

from tests.contract.integration_support import (
    DEFAULT_SUPABASE_DB_URL,
    local_supabase_status,
    try_connect,
)
from tests.contract.rfc6238_totp import totp_window

_FASTAPI_URL = "http://127.0.0.1:8000"
_PASSWORD = "Phase6Ui9x"  # noqa: S105 - disposable local Auth user
_CLIENT_VERSION = "0.1.0"
_XSS_MESSAGE = "<script>alert(1)</script>"


def _fastapi_live() -> bool:
    """Return whether local FastAPI answers liveness.

    Returns:
        True when ``GET /health/live`` is HTTP 200.
    """

    try:
        response = httpx.get(f"{_FASTAPI_URL}/health/live", timeout=3.0)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def _event_names(buffer: str) -> list[str]:
    """Parse SSE ``event:`` names from a concatenated buffer.

    Args:
        buffer: Raw EventSource text.

    Returns:
        Event type names in order.
    """

    names: list[str] = []
    for block in buffer.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("event:"):
                names.append(line.split(":", 1)[1].strip())
    return names


def _json_object(value: object) -> dict[str, object]:
    """Narrow decoded JSON to a string-keyed object.

    Args:
        value: Decoded JSON.

    Returns:
        Mapping.

    Raises:
        AssertionError: If the value is not an object.
    """

    if not isinstance(value, dict):
        raise AssertionError("expected JSON object")
    return cast(dict[str, object], value)


def _access_token_from_auth_json(body: dict[str, object]) -> str:
    """Extract an access token from a GoTrue JSON object.

    Args:
        body: Decoded Auth JSON.

    Returns:
        Token string, or empty when absent.
    """

    token = str(body.get("access_token", ""))
    if token:
        return token
    nested = body.get("data")
    if isinstance(nested, dict):
        nested_body = _json_object(cast(object, nested))
        return str(nested_body.get("access_token", ""))
    return ""


def _jwt_aal(token: str) -> str:
    """Read the ``aal`` claim without verifying the signature.

    Args:
        token: Compact JWT.

    Returns:
        Assurance level string, defaulting to ``aal1``.
    """

    parts = token.split(".")
    if len(parts) < 2:
        return "aal1"
    padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    if not isinstance(payload, dict):
        return "aal1"
    claims = _json_object(cast(object, payload))
    return str(claims.get("aal", "aal1"))


def _upsert_profile(
    user_id: str,
    *,
    upload_enabled: bool,
    mfa_enrolled: bool,
) -> None:
    """Write the local ``app.profiles`` row used by FastAPI identity.

    Args:
        user_id: Auth user UUID.
        upload_enabled: Upload capability flag.
        mfa_enrolled: Application MFA enrollment flag.
    """

    with psycopg.connect(DEFAULT_SUPABASE_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.profiles (
                  user_id, role, upload_enabled, mfa_enrolled, monthly_llm_budget_usd
                )
                VALUES (%s, 'member'::app.user_role, %s, %s, 100)
                ON CONFLICT (user_id) DO UPDATE
                  SET role = 'member'::app.user_role,
                      upload_enabled = EXCLUDED.upload_enabled,
                      mfa_enrolled = EXCLUDED.mfa_enrolled,
                      monthly_llm_budget_usd = EXCLUDED.monthly_llm_budget_usd
                """,
                (user_id, upload_enabled, mfa_enrolled),
            )
        connection.commit()


def _create_password_user(live_stack: dict[str, str]) -> dict[str, str]:
    """Create a confirmed local Auth user and return a password-grant JWT.

    Args:
        live_stack: Module fixture with Auth URLs and keys.

    Returns:
        ``access_token``, ``user_id``, ``fastapi_url``, ``anon_key``, and
        ``auth_url``.
    """

    email = f"phase6-ui-{uuid4().hex}@example.com"
    auth_url = live_stack["API_URL"].rstrip("/")
    anon = live_stack["ANON_KEY"]
    service = live_stack["SERVICE_ROLE_KEY"]
    with httpx.Client(timeout=15.0) as client:
        created = client.post(
            f"{auth_url}/auth/v1/admin/users",
            headers={
                "Authorization": f"Bearer {service}",
                "apikey": service,
            },
            json={
                "email": email,
                "password": _PASSWORD,
                "email_confirm": True,
            },
        )
        if created.status_code >= 400:
            pytest.fail(f"local Auth admin create failed: {created.status_code}")
        user_payload = _json_object(created.json())
        user_id = str(user_payload.get("id", ""))
        if user_id == "":
            pytest.fail("local Auth admin create omitted user id")
        token_response = client.post(
            f"{auth_url}/auth/v1/token?grant_type=password",
            headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            json={"email": email, "password": _PASSWORD},
        )
        token_response.raise_for_status()
        token_payload = _json_object(token_response.json())
        access_token = str(token_payload.get("access_token", ""))
        if access_token == "":
            pytest.fail("password grant omitted access_token")
    return {
        "access_token": access_token,
        "user_id": user_id,
        "fastapi_url": live_stack["fastapi_url"],
        "anon_key": anon,
        "auth_url": auth_url,
    }


def _enroll_and_verify_totp(
    *,
    auth_url: str,
    anon: str,
    access_token: str,
) -> str:
    """Enroll TOTP on the current session and return an aal2 access token.

    Args:
        auth_url: Local GoTrue origin.
        anon: Anon API key.
        access_token: aal1 password JWT.

    Returns:
        Access token after successful challenge/verify.

    Raises:
        pytest.skip.Exception: When local TOTP enroll is disabled until Auth
            restarts with ``[auth.mfa.totp]``.
    """

    headers = {
        "Authorization": f"Bearer {access_token}",
        "apikey": anon,
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=15.0) as client:
        enroll = client.post(
            f"{auth_url}/auth/v1/factors",
            headers=headers,
            json={"factor_type": "totp", "friendly_name": "phase6-ui"},
        )
        if enroll.status_code >= 400:
            pytest.skip(
                "local TOTP enroll is unavailable; restart Auth after "
                f"[auth.mfa.totp] ({enroll.status_code})"
            )
        enroll_body = _json_object(enroll.json())
        totp = enroll_body.get("totp")
        if not isinstance(totp, dict):
            pytest.skip("GoTrue enroll omitted totp.secret")
        totp_body = _json_object(cast(object, totp))
        secret = str(totp_body.get("secret", ""))
        factor_id = str(enroll_body.get("id", ""))
        if secret == "" or factor_id == "":
            pytest.skip("GoTrue enroll omitted factor id or secret")
        challenge = client.post(
            f"{auth_url}/auth/v1/factors/{factor_id}/challenge",
            headers=headers,
            json={},
        )
        if challenge.status_code >= 400:
            pytest.skip(f"GoTrue TOTP challenge failed ({challenge.status_code})")
        challenge_id = str(_json_object(challenge.json()).get("id", ""))
        if challenge_id == "":
            pytest.skip("GoTrue challenge omitted id")
        last_error = "verify failed"
        for code in totp_window(secret):
            verified = client.post(
                f"{auth_url}/auth/v1/factors/{factor_id}/verify",
                headers=headers,
                json={"challenge_id": challenge_id, "code": code},
            )
            if verified.status_code < 400:
                body = _json_object(verified.json())
                next_token = _access_token_from_auth_json(body)
                if next_token == "":
                    pytest.fail("TOTP verify omitted access_token")
                return next_token
            last_error = f"{verified.status_code}"
        pytest.fail(f"TOTP verify rejected codes in the skew window ({last_error})")


def _ready_dependencies(api: str) -> dict[str, str]:
    """Return named probes from public ``GET /health/ready``.

    After PRD-M-014 the public body omits ``dependencies``, so this map is
    empty unless the API regresses and leaks names.

    Args:
        api: FastAPI origin.

    Returns:
        Status map. Empty when the payload has no ``dependencies`` list.
    """

    response = httpx.get(f"{api}/health/ready", timeout=5.0)
    payload = _json_object(response.json())
    raw = payload.get("dependencies")
    if not isinstance(raw, list):
        return {}
    out: dict[str, str] = {}
    for raw_item in cast(list[object], raw):
        if not isinstance(raw_item, dict):
            continue
        row = _json_object(cast(object, raw_item))
        name = str(row.get("name", ""))
        if name:
            out[name] = str(row.get("status", ""))
    return out


@pytest.fixture(scope="module")
def live_stack() -> dict[str, str]:
    """Yield local Auth status plus FastAPI origin, or skip.

    Returns:
        Status keys from the pinned Supabase CLI plus ``fastapi_url``.
        Callers must never print credential values.
    """

    if not _fastapi_live():
        pytest.skip("local FastAPI is unreachable at 127.0.0.1:8000")
    postgres = try_connect(DEFAULT_SUPABASE_DB_URL)
    if postgres is None:
        pytest.skip("local Supabase Postgres is unreachable")
    postgres.close()
    status = local_supabase_status()
    status = {**status, "fastapi_url": _FASTAPI_URL}
    return status


@pytest.fixture
def live_member(live_stack: dict[str, str]) -> dict[str, str]:
    """Create one local Auth user with an application profile.

    Args:
        live_stack: Module fixture with Auth URLs and keys.

    Returns:
        ``access_token``, ``user_id``, ``fastapi_url``, and ``anon_key``.
    """

    created = _create_password_user(live_stack)
    _upsert_profile(
        created["user_id"],
        upload_enabled=False,
        mfa_enrolled=False,
    )
    return created


def _paid_headers(
    token: str,
    *,
    idempotency_key: str | None = None,
    client_version: str | None = _CLIENT_VERSION,
) -> dict[str, str]:
    """Build headers matching the thin UI paid POST.

    Args:
        token: Bearer access token.
        idempotency_key: Optional Idempotency-Key UUID.
        client_version: Handshake header, or None to omit.

    Returns:
        Header mapping.
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if client_version is not None:
        headers["X-Client-Version"] = client_version
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _consume_sse(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    *,
    timeout_seconds: float = 60.0,
) -> tuple[str, str]:
    """Read one EventSource body until a terminal event or timeout.

    Args:
        client: Shared HTTP client.
        url: ``GET /runs/{id}/events`` URL.
        headers: Bearer resume headers.
        timeout_seconds: Maximum read time.

    Returns:
        Content-Type and raw body.
    """

    resume = {
        "Authorization": headers["Authorization"],
        "Accept": "text/event-stream",
    }
    buffer = ""
    content_type = ""
    deadline = time.monotonic() + timeout_seconds
    with client.stream("GET", url, headers=resume, timeout=timeout_seconds) as response:
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        for chunk in response.iter_text():
            buffer += chunk
            names = _event_names(buffer)
            if any(
                name in {"completed", "cancelled", "error", "partial"} for name in names
            ):
                break
            if time.monotonic() > deadline:
                break
    return content_type, buffer


def test_live_meta_handshake_is_public(live_stack: dict[str, str]) -> None:
    """``GET /api/meta`` publishes versions without a session."""

    response = httpx.get(f"{live_stack['fastapi_url']}/api/meta", timeout=5.0)
    assert response.status_code == 200
    payload = _json_object(response.json())
    assert payload.get("min_client_version") == _CLIENT_VERSION
    assert payload.get("sse_schema_version") == "1"


def test_thin_ui_live_jwt_chat_idempotency_delete_upload(
    live_member: dict[str, str],
) -> None:
    """Prove the UI HTTP contract: JWT, 426, one paid run, SSE, delete, upload."""

    api = live_member["fastapi_url"]
    token = live_member["access_token"]
    with httpx.Client(timeout=30.0) as client:
        me = client.get(f"{api}/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        me_body = _json_object(me.json())
        assert me_body.get("user_id") == live_member["user_id"]
        assert me_body.get("upload_enabled") is False
        assert me_body.get("role") == "member"

        created = client.post(
            f"{api}/conversations",
            headers=_paid_headers(token),
            json={"title": "thin-ui-live"},
        )
        assert created.status_code == 201, created.text
        conversation_id = str(_json_object(created.json())["conversation_id"])

        missing_version = client.post(
            f"{api}/conversations/{conversation_id}/messages",
            headers=_paid_headers(token, client_version=None),
            json={"message": "hello", "idempotency_key": str(uuid4())},
        )
        assert missing_version.status_code == 426
        upgrade = _json_object(missing_version.json())
        assert upgrade.get("min_client_version") == _CLIENT_VERSION

        key = str(uuid4())
        first = client.post(
            f"{api}/conversations/{conversation_id}/messages",
            headers=_paid_headers(token, idempotency_key=key),
            json={"message": _XSS_MESSAGE, "idempotency_key": key},
        )
        assert first.status_code == 202, first.text
        first_body = _json_object(first.json())
        run_id = str(first_body["run_id"])
        stream_path = str(first_body["stream_path"])
        assert stream_path.endswith(f"/runs/{run_id}/events")

        second = client.post(
            f"{api}/conversations/{conversation_id}/messages",
            headers=_paid_headers(token, idempotency_key=key),
            json={"message": _XSS_MESSAGE, "idempotency_key": key},
        )
        assert second.status_code == 202, second.text
        assert str(_json_object(second.json())["run_id"]) == run_id

        content_type, body = _consume_sse(
            client,
            f"{api}{stream_path}?after=0",
            _paid_headers(token),
        )
        assert content_type.startswith("text/event-stream")
        assert "text/html" not in content_type
        assert "<html" not in body.lower()
        names = _event_names(body)
        assert "schema" in names
        assert any(
            name in {"completed", "cancelled", "error", "partial"} for name in names
        )

        upload_key = f"upload-{uuid4()}"
        reserved = client.post(
            f"{api}/documents/uploads",
            headers=_paid_headers(token, idempotency_key=upload_key),
            json={"declared_bytes": 1024, "idempotency_key": upload_key},
        )
        assert reserved.status_code == 403
        assert _json_object(reserved.json()).get("detail") == "forbidden"

        deleted = client.delete(
            f"{api}/conversations/{conversation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert deleted.status_code == 204

        missing = client.get(
            f"{api}/conversations/{conversation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert missing.status_code == 404

        resume = client.get(
            f"{api}/runs/{run_id}/events?after=0",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "text/event-stream",
            },
        )
        assert resume.status_code == 404

    with psycopg.connect(DEFAULT_SUPABASE_DB_URL) as connection:
        connection.execute("SET ROLE app_api")
        lingering = search_conversation_lingering_ids(
            connection,
            conversation_id=UUID(conversation_id),
        )
    assert lingering
    assert all(count == 0 for count in lingering.values())


def test_thin_ui_live_five_composite_streams(live_member: dict[str, str]) -> None:
    """Admit five Composite runs then hold five concurrent EventSource reads."""

    api = live_member["fastapi_url"]
    token = live_member["access_token"]
    with httpx.Client(timeout=30.0) as client:
        created = client.post(
            f"{api}/conversations",
            headers=_paid_headers(token),
            json={"title": "thin-ui-five-stream"},
        )
        assert created.status_code == 201, created.text
        conversation_id = str(_json_object(created.json())["conversation_id"])
        run_ids: list[str] = []
        for index in range(5):
            key = str(uuid4())
            admitted = client.post(
                f"{api}/conversations/{conversation_id}/messages",
                headers=_paid_headers(token, idempotency_key=key),
                json={
                    "message": f"composite-stream-{index}",
                    "idempotency_key": key,
                },
            )
            assert admitted.status_code == 202, admitted.text
            run_ids.append(str(_json_object(admitted.json())["run_id"]))
        assert len(set(run_ids)) == 5

        def _one(run_id: str) -> tuple[str, str]:
            """Consume one live EventSource until terminal.

            Args:
                run_id: Admitted run.

            Returns:
                Content-Type and body.
            """

            with httpx.Client(timeout=60.0) as stream_client:
                return _consume_sse(
                    stream_client,
                    f"{api}/runs/{run_id}/events?after=0",
                    _paid_headers(token),
                )

        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(_one, run_ids))
        for content_type, body in results:
            assert content_type.startswith("text/event-stream")
            names = _event_names(body)
            assert "schema" in names
            assert any(
                name in {"completed", "cancelled", "error", "partial"} for name in names
            )


def test_upload_enabled_aal1_is_mfa_required(live_stack: dict[str, str]) -> None:
    """Upload-enabled password JWTs stay aal1 and must not look like success."""

    created = _create_password_user(live_stack)
    assert _jwt_aal(created["access_token"]) == "aal1"
    _upsert_profile(created["user_id"], upload_enabled=True, mfa_enrolled=True)
    api = created["fastapi_url"]
    token = created["access_token"]
    with httpx.Client(timeout=15.0) as client:
        me = client.get(f"{api}/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 403
        assert _json_object(me.json()).get("detail") == "MFA required"
        upload_key = f"upload-{uuid4()}"
        reserved = client.post(
            f"{api}/documents/uploads",
            headers=_paid_headers(token, idempotency_key=upload_key),
            json={"declared_bytes": 1024, "idempotency_key": upload_key},
        )
        assert reserved.status_code == 403
        assert _json_object(reserved.json()).get("detail") == "MFA required"


def test_mfa_aal2_upload_reserve_signed_url_is_null(
    live_stack: dict[str, str],
) -> None:
    """Verified TOTP (aal2) plus upload_enabled reserves with signed_url null.

    After reserve, the same user JWT can POST the object to Storage. That is
    the local ``supabase_storage_jwt`` path; FastAPI still returns
    ``signed_url=None``.
    """

    created = _create_password_user(live_stack)
    _upsert_profile(created["user_id"], upload_enabled=False, mfa_enrolled=False)
    aal2_token = _enroll_and_verify_totp(
        auth_url=created["auth_url"],
        anon=created["anon_key"],
        access_token=created["access_token"],
    )
    assert _jwt_aal(aal2_token) == "aal2"
    _upsert_profile(created["user_id"], upload_enabled=True, mfa_enrolled=True)
    api = created["fastapi_url"]
    upload_key = f"upload-{uuid4()}"
    with httpx.Client(timeout=15.0) as client:
        me = client.get(
            f"{api}/me",
            headers={"Authorization": f"Bearer {aal2_token}"},
        )
        assert me.status_code == 200, me.text
        me_body = _json_object(me.json())
        assert me_body.get("upload_enabled") is True
        reserved = client.post(
            f"{api}/documents/uploads",
            headers=_paid_headers(aal2_token, idempotency_key=upload_key),
            json={"declared_bytes": 1024, "idempotency_key": upload_key},
        )
        assert reserved.status_code == 200, reserved.text
        body = _json_object(reserved.json())
        assert body.get("signed_url") is None
        assert body.get("upload_method") == "supabase_storage_jwt"
        assert body.get("reservation_id")
        bucket = str(body.get("storage_bucket", ""))
        prefix = str(body.get("storage_path", "")).rstrip("/")
        if bucket == "" or prefix == "":
            pytest.fail("aal2 reserve omitted storage_bucket or storage_path")
        object_name = f"{prefix}/phase8-live.bin"
        uploaded = client.post(
            f"{created['auth_url'].rstrip('/')}/storage/v1/object/{bucket}/{object_name}",
            headers={
                "Authorization": f"Bearer {aal2_token}",
                "apikey": created["anon_key"],
                "Content-Type": "text/plain",
                "x-upsert": "false",
            },
            content=b"phase8-storage-jwt",
        )
        assert uploaded.status_code in {200, 201}, uploaded.text


def test_live_public_ready_omits_named_dependencies(live_stack: dict[str, str]) -> None:
    """Public GET /health/ready must not leak ParadeDB/Valkey/LightRAG names.

    Named probes are owner/admin ``GET /ops/ready``. Host uvicorn without
    those URLs reports unconfigured. That is honest, not a mock success.
    """

    api = live_stack["fastapi_url"]
    origin = httpx.get(
        f"{api}/health/ready",
        headers={"Origin": "http://127.0.0.1:3010"},
        timeout=5.0,
    )
    assert origin.status_code == 200
    assert origin.headers.get("access-control-allow-origin") == (
        "http://127.0.0.1:3010"
    )
    payload = _json_object(origin.json())
    assert payload.get("query_ready") is False
    assert "dependencies" not in payload
    assert _ready_dependencies(api) == {}
