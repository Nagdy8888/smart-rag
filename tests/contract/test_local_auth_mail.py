"""Local Auth, OAuth configuration, and SMTP delivery contracts."""

from __future__ import annotations

import smtplib
import time
import tomllib
import uuid
from collections.abc import Iterator
from email.message import EmailMessage
from pathlib import Path
from typing import cast

import httpx
import psycopg
import pytest
from smart_rag_api.auth_admin.invitations import create_invitation
from smart_rag_api.auth_admin.settings import PrivilegedAuthSettings

from tests.contract.integration_support import (
    local_supabase_status,
    resolve_supabase_db_url,
    try_connect,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SUPABASE_CONFIG = REPO_ROOT / "supabase" / "config.toml"


@pytest.fixture
def postgres_url() -> Iterator[str]:
    """Yield the local database URL or skip when the stack is unavailable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.close()
    yield url


def _string_object(value: object, *, label: str) -> dict[str, object]:
    """Narrow an untrusted JSON/TOML value to a string-keyed object."""

    if not isinstance(value, dict):
        raise AssertionError(f"{label} is not an object")
    untyped = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in untyped):
        raise AssertionError(f"{label} contains a non-string key")
    return cast(dict[str, object], untyped)


def _insert_invitation_actor(
    postgres_url: str,
    *,
    actor_id: uuid.UUID,
    email: str,
    allowed_domain: str,
) -> None:
    """Persist one active admin and one authoritative invitation domain."""

    with psycopg.connect(postgres_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth.users (
                  id, instance_id, aud, role, email, encrypted_password,
                  email_confirmed_at, created_at, updated_at
                )
                VALUES (
                  %s,
                  '00000000-0000-0000-0000-000000000000'::uuid,
                  'authenticated',
                  'authenticated',
                  %s,
                  crypt('test-password', gen_salt('bf')),
                  timezone('utc', now()),
                  timezone('utc', now()),
                  timezone('utc', now())
                )
                """,
                (actor_id, email),
            )
            cursor.execute(
                """
                INSERT INTO app.profiles (
                  user_id, role, mfa_enrolled
                )
                VALUES (%s, 'admin', true)
                """,
                (actor_id,),
            )
            cursor.execute(
                """
                INSERT INTO app.allowed_email_domains (domain)
                VALUES (%s)
                """,
                (allowed_domain,),
            )
        connection.commit()


def _mail_count(mailpit_url: str, recipient: str) -> int:
    """Return Mailpit's count for one exact recipient search."""

    response = httpx.get(
        f"{mailpit_url.rstrip('/')}/api/v1/search",
        params={"query": f"to:{recipient}"},
        timeout=5.0,
    )
    response.raise_for_status()
    payload = _string_object(response.json(), label="Mailpit search response")
    total = payload.get("total")
    if not isinstance(total, int):
        raise AssertionError("Mailpit search response has no integer total")
    return total


def await_mail(mailpit_url: str, recipient: str) -> None:
    """Wait at most five seconds for local SMTP delivery."""

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if _mail_count(mailpit_url, recipient) > 0:
            return
        time.sleep(0.2)
    raise AssertionError(f"local mail was not delivered to {recipient}")


def _send_local_admin_alert(recipient: str) -> None:
    """Send one metadata-only admin alert through the exposed local SMTP port."""

    message = EmailMessage()
    message["From"] = "admin@example.com"
    message["To"] = recipient
    message["Subject"] = "Smart RAG local admin alert"
    message.set_content("kind=quarantine_accumulation severity=warning fixture=true")
    with smtplib.SMTP("127.0.0.1", 54325, timeout=5.0) as client:
        client.send_message(message)


def test_auth_oauth_and_local_smtp_configuration_is_explicit() -> None:
    """Pinned config uses exact redirects, env-backed OAuth, and local SMTP."""

    with SUPABASE_CONFIG.open("rb") as handle:
        config = _string_object(tomllib.load(handle), label="Supabase config")

    auth = _string_object(config["auth"], label="auth")
    redirects = auth["additional_redirect_urls"]
    assert redirects == [
        "http://localhost:3000",
        "http://127.0.0.1:3000/auth/callback",
        "http://localhost:3000/auth/callback",
    ]
    assert all("*" not in str(url) for url in cast(list[object], redirects))
    assert auth["site_url"] == "http://127.0.0.1:3000"
    assert auth["jwt_expiry"] == 3600
    assert auth["minimum_password_length"] == 8
    assert auth["password_requirements"] == "lower_upper_letters_digits"  # noqa: S105

    local_smtp = _string_object(config["local_smtp"], label="local_smtp")
    assert local_smtp["enabled"] is True
    assert local_smtp["port"] == 54324
    assert local_smtp["smtp_port"] == 54325
    assert "inbucket" not in config

    external = _string_object(auth["external"], label="auth.external")
    google = _string_object(external["google"], label="auth.external.google")
    assert google == {
        "enabled": False,
        "client_id": "env(SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID)",
        "secret": "env(SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET)",
        "redirect_uri": "",
        "skip_nonce_check": False,
        "email_optional": False,
    }


def test_local_email_password_sign_in_and_failure() -> None:
    """The local Auth API accepts configured passwords and rejects a mismatch."""

    status = local_supabase_status()
    api_url = status["API_URL"].rstrip("/")
    anon_key = status["ANON_KEY"]
    email = f"password-proof-{uuid.uuid4()}@example.com"
    password = f"LocalProof7{uuid.uuid4().hex}"
    headers = {"apikey": anon_key}

    signup = httpx.post(
        f"{api_url}/auth/v1/signup",
        headers=headers,
        json={"email": email, "password": password},
        timeout=10.0,
    )
    signup.raise_for_status()

    sign_in = httpx.post(
        f"{api_url}/auth/v1/token",
        params={"grant_type": "password"},
        headers=headers,
        json={"email": email, "password": password},
        timeout=10.0,
    )
    sign_in.raise_for_status()
    sign_in_payload = _string_object(sign_in.json(), label="sign-in response")
    assert isinstance(sign_in_payload.get("access_token"), str)
    assert isinstance(sign_in_payload.get("refresh_token"), str)

    rejected = httpx.post(
        f"{api_url}/auth/v1/token",
        params={"grant_type": "password"},
        headers=headers,
        json={"email": email, "password": f"{password}-wrong"},
        timeout=10.0,
    )
    assert rejected.status_code in {400, 401}


def test_invitation_and_admin_alert_reach_local_mailpit(
    postgres_url: str,
) -> None:
    """Provider invitations and metadata-only admin alerts traverse local SMTP."""

    status = local_supabase_status()
    api_url = status["API_URL"]
    mailpit_url = status["MAILPIT_URL"]
    actor_id = uuid.uuid4()
    domain = f"mail-proof-{uuid.uuid4().hex}.example"
    recipient = f"invitee@{domain}"
    admin_recipient = f"admin-alert-{uuid.uuid4()}@example.com"
    _insert_invitation_actor(
        postgres_url,
        actor_id=actor_id,
        email=f"mail-admin-{actor_id}@example.com",
        allowed_domain=domain,
    )
    settings = PrivilegedAuthSettings.model_validate(
        {
            "SUPABASE_URL": api_url,
            "SUPABASE_AUTH_ADMIN_SECRET": status["SERVICE_ROLE_KEY"],
        }
    )

    created = create_invitation(
        settings,
        postgres_url=postgres_url,
        email=recipient,
        role="member",
        invited_by=actor_id,
        upload_enabled=True,
    )
    await_mail(mailpit_url, recipient)

    with psycopg.connect(postgres_url) as connection:
        metadata_row = connection.execute(
            """
            SELECT raw_user_meta_data
            FROM auth.users
            WHERE email = %s
            """,
            (recipient,),
        ).fetchone()
    assert metadata_row is not None
    metadata = _string_object(metadata_row[0], label="invite user metadata")
    assert metadata["invitation_token"] == created.raw_token

    _send_local_admin_alert(admin_recipient)
    await_mail(mailpit_url, admin_recipient)
