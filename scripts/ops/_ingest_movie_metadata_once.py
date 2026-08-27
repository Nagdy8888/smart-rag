"""One-shot Hybrid-only ingest of the movie metadata demo CSV.

Creates an MFA-satisfied local uploader, reserves/uploads/finalizes through
FastAPI + Storage, marks the scan job synthetic (so it never goes to LightRAG),
and polls until a terminal public status.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import cast

import httpx
import psycopg

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tests.contract.rfc6238_totp import totp_window  # noqa: E402

CSV_PATH = REPO / "docs" / "datasets" / "MovieSummaries" / "movie.metadata.demo.csv"
API_URL = "http://127.0.0.1:8000"
DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
ATTESTATION_POLICY_VERSION = "2026-08-13"
PASSWORD = "LocalDemo-Upload-1!"  # noqa: S105
TERMINAL = frozenset(
    {"graph_ineligible", "hybrid_ready", "graph_pending", "graph_ready", "failed"}
)


def _supabase_status() -> dict[str, str]:
    """Return Auth URL and keys from the environment or local CLI status."""

    env_url = os.environ.get("SMART_RAG_AUTH_URL", "").strip()
    env_anon = os.environ.get("SMART_RAG_ANON_KEY", "").strip()
    env_service = os.environ.get("SMART_RAG_SERVICE_ROLE_KEY", "").strip()
    if env_url and env_anon and env_service:
        return {
            "API_URL": env_url,
            "ANON_KEY": env_anon,
            "SERVICE_ROLE_KEY": env_service,
        }
    raise RuntimeError(
        "set SMART_RAG_AUTH_URL, SMART_RAG_ANON_KEY, and SMART_RAG_SERVICE_ROLE_KEY"
    )


def _json_object(payload: object, source: str) -> dict[str, object]:
    """Require a JSON object."""

    if not isinstance(payload, dict):
        raise RuntimeError(f"{source} was not a JSON object")
    return cast(dict[str, object], payload)


def _create_uploader(status: dict[str, str]) -> tuple[str, str, str]:
    """Create a confirmed Auth user, enroll TOTP, and enable upload.

    Returns:
        Tuple of aal2 access token, user id, and Auth API origin.
    """

    auth_url = status["API_URL"].rstrip("/")
    anon = status["ANON_KEY"]
    service = status["SERVICE_ROLE_KEY"]
    email = f"hybrid-demo-{uuid.uuid4().hex[:12]}@localhost"
    with httpx.Client(timeout=30.0) as client:
        created = client.post(
            f"{auth_url}/auth/v1/admin/users",
            headers={"Authorization": f"Bearer {service}", "apikey": service},
            json={"email": email, "password": PASSWORD, "email_confirm": True},
        )
        created.raise_for_status()
        user_id = str(_json_object(created.json(), "admin create").get("id", ""))
        if not user_id:
            raise RuntimeError("auth admin create omitted user id")
        token_response = client.post(
            f"{auth_url}/auth/v1/token?grant_type=password",
            headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            json={"email": email, "password": PASSWORD},
        )
        token_response.raise_for_status()
        access = str(
            _json_object(token_response.json(), "password grant").get(
                "access_token", ""
            )
        )
        if not access:
            raise RuntimeError("password grant omitted access_token")
        aal2 = _enroll_totp(client, auth_url=auth_url, anon=anon, access_token=access)
    _upsert_profile(user_id)
    return aal2, user_id, auth_url


def _enroll_totp(
    client: httpx.Client,
    *,
    auth_url: str,
    anon: str,
    access_token: str,
) -> str:
    """Enroll and verify TOTP; return the aal2 access token."""

    headers = {
        "Authorization": f"Bearer {access_token}",
        "apikey": anon,
        "Content-Type": "application/json",
    }
    enroll = client.post(
        f"{auth_url}/auth/v1/factors",
        headers=headers,
        json={"factor_type": "totp", "friendly_name": "hybrid-demo"},
    )
    enroll.raise_for_status()
    body = _json_object(enroll.json(), "totp enroll")
    totp = body.get("totp")
    if not isinstance(totp, dict):
        raise RuntimeError("GoTrue enroll omitted totp")
    totp_obj = cast(dict[str, object], totp)
    secret = str(totp_obj.get("secret", ""))
    factor_id = str(body.get("id", ""))
    challenge = client.post(
        f"{auth_url}/auth/v1/factors/{factor_id}/challenge",
        headers=headers,
        json={},
    )
    challenge.raise_for_status()
    challenge_id = str(_json_object(challenge.json(), "totp challenge").get("id", ""))
    last = "verify failed"
    for code in totp_window(secret):
        verified = client.post(
            f"{auth_url}/auth/v1/factors/{factor_id}/verify",
            headers=headers,
            json={"challenge_id": challenge_id, "code": code},
        )
        if verified.status_code < 400:
            token = str(
                _json_object(verified.json(), "totp verify").get("access_token", "")
            )
            if token:
                return token
        last = f"{verified.status_code} {verified.text[:200]}"
    raise RuntimeError(f"TOTP verify failed: {last}")


def _upsert_profile(user_id: str) -> None:
    """Enable upload on a member profile with MFA recorded as enrolled."""

    with psycopg.connect(DB_URL, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.profiles (
                  user_id, role, upload_enabled, mfa_enrolled, monthly_llm_budget_usd
                )
                VALUES (%s, 'member'::app.user_role, true, true, 100)
                ON CONFLICT (user_id) DO UPDATE
                  SET upload_enabled = true,
                      mfa_enrolled = true,
                      role = 'member'::app.user_role
                """,
                (user_id,),
            )
        connection.commit()


def _mark_scan_job_synthetic(job_id: str) -> None:
    """Set scan-job payload so promotion is allowed without LightRAG indexing."""

    with psycopg.connect(DB_URL, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.ingestion_jobs
                SET payload_ref = COALESCE(payload_ref, '{}'::jsonb)
                  || jsonb_build_object(
                       'content_class', 'synthetic',
                       'review_approved', true
                     )
                WHERE id = %s::uuid
                """,
                (job_id,),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"scan job {job_id} not updated")
        connection.commit()


def _version_jobs(version_id: str) -> list[dict[str, object]]:
    """List ingestion jobs for a version."""

    with psycopg.connect(DB_URL, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, job_kind, status::text, last_error, attempt_count
                FROM app.ingestion_jobs
                WHERE version_id = %s::uuid
                ORDER BY created_at
                """,
                (version_id,),
            )
            rows = cursor.fetchall()
    return [
        {
            "id": row[0],
            "job_kind": row[1],
            "status": row[2],
            "last_error": row[3],
            "attempt_count": row[4],
        }
        for row in rows
    ]


def _mark_version_jobs_synthetic(version_id: str) -> None:
    """Keep later hybrid_index jobs synthetic as well."""

    with psycopg.connect(DB_URL, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.ingestion_jobs
                SET payload_ref = COALESCE(payload_ref, '{}'::jsonb)
                  || jsonb_build_object(
                       'content_class', 'synthetic',
                       'review_approved', true
                     )
                WHERE version_id = %s::uuid
                """,
                (version_id,),
            )
        connection.commit()


def main() -> int:
    """Upload and poll the demo CSV."""

    if not CSV_PATH.is_file():
        print(f"missing {CSV_PATH}", file=sys.stderr, flush=True)
        return 2
    payload = CSV_PATH.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    print(f"loaded csv bytes={len(payload)}", flush=True)
    status = _supabase_status()
    print("creating uploader", flush=True)
    token, _user_id, auth_url = _create_uploader(status)
    print("uploader ready", flush=True)
    anon = status["ANON_KEY"]
    idempotency_key = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Client-Version": "0.1.0",
        "Idempotency-Key": idempotency_key,
    }
    with httpx.Client(timeout=60.0) as client:
        me = client.get(f"{API_URL}/me", headers={"Authorization": f"Bearer {token}"})
        print(f"GET /me {me.status_code}", flush=True)
        me.raise_for_status()
        reserved = client.post(
            f"{API_URL}/documents/uploads",
            headers=headers,
            json={"declared_bytes": len(payload), "idempotency_key": idempotency_key},
        )
        print(f"POST /documents/uploads {reserved.status_code}", flush=True)
        reserved.raise_for_status()
        body = _json_object(reserved.json(), "reserve")
        reservation_id = str(body["reservation_id"])
        bucket = str(body["storage_bucket"])
        prefix = str(body["storage_path"]).rstrip("/")
        object_name = f"{prefix}/{CSV_PATH.name}"
        uploaded = client.post(
            f"{auth_url}/storage/v1/object/{bucket}/{object_name}",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": anon,
                "Content-Type": "text/csv",
                "x-upsert": "false",
            },
            content=payload,
        )
        if uploaded.status_code not in {200, 201}:
            print(uploaded.text[:500], file=sys.stderr)
            uploaded.raise_for_status()
        finalized = client.post(
            f"{API_URL}/documents/uploads/finalize",
            headers=headers,
            json={
                "reservation_id": reservation_id,
                "object_name": object_name,
                "content_hash": digest,
                "actual_bytes": len(payload),
                "media_type": "text/csv",
                "declared_category": "allowed",
                "attestation_policy_version": ATTESTATION_POLICY_VERSION,
                "idempotency_key": idempotency_key,
                "document_title": "CMU movie metadata (Hybrid demo)",
            },
        )
        if finalized.status_code >= 400:
            print(finalized.text[:800], file=sys.stderr)
        finalized.raise_for_status()
        fin = _json_object(finalized.json(), "finalize")
        document_id = str(fin["document_id"])
        version_id = str(fin["version_id"])
        job_id = str(fin["job_id"])
        _mark_scan_job_synthetic(job_id)
        print(
            json.dumps(
                {
                    "document_id": document_id,
                    "version_id": version_id,
                    "job_id": job_id,
                    "bytes": len(payload),
                    "rows": 500,
                },
                indent=2,
            ),
            flush=True,
        )
        deadline = time.time() + 900
        last_status = ""
        while time.time() < deadline:
            _mark_version_jobs_synthetic(version_id)
            response = client.get(
                f"{API_URL}/ingestion/versions/{version_id}/status",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            payload_status = _json_object(response.json(), "status")
            version = payload_status.get("version")
            if isinstance(version, dict):
                public_status = str(cast(dict[str, object], version).get("status", ""))
            else:
                public_status = str(payload_status.get("status", ""))
            jobs = _version_jobs(version_id)
            if public_status != last_status:
                print(
                    json.dumps(
                        {"status": public_status, "jobs": jobs},
                        default=str,
                    ),
                    flush=True,
                )
                last_status = public_status
            if public_status in TERMINAL:
                if public_status == "graph_ineligible":
                    print("ingestion complete: graph_ineligible (Hybrid only)")
                    return 0
                if public_status == "graph_pending":
                    print(
                        "unexpected graph_pending; LightRAG handoff was created",
                        file=sys.stderr,
                    )
                    return 3
                print(f"ingestion stopped at {public_status}", file=sys.stderr)
                print(json.dumps({"jobs": jobs}, default=str), file=sys.stderr)
                return 4
            time.sleep(5)
    print("timed out waiting for Hybrid Ready / graph_ineligible", file=sys.stderr)
    print(json.dumps(_version_jobs(version_id), default=str), file=sys.stderr)
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
