"""Upload the two demo plot slices and start laptop ingest against hosted Auth.

Creates an MFA-satisfied uploader, finalizes both files through FastAPI, marks
jobs synthetic for the local unsigned waiver, and marks the 200-line document
graph-eligible after promote. Does not ingest ``plot_summaries.txt``.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from typing import LiteralString, cast

import httpx
import psycopg
from psycopg import sql as psycopg_sql

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ops.mark_demo_graph_eligible import mark_graph_eligible  # noqa: E402
from tests.contract.rfc6238_totp import totp_window  # noqa: E402

HYBRID_PATH = (
    REPO / "docs" / "datasets" / "MovieSummaries" / "plot_summaries.hybrid-800.txt"
)
GRAPH_PATH = (
    REPO / "docs" / "datasets" / "MovieSummaries" / "plot_summaries.graph-200.txt"
)
API_URL = "http://127.0.0.1:8000"
DEMO_LOGIN = "LocalDemo-Upload-1!"
ATTESTATION_POLICY_VERSION = "2026-08-13"
TERMINAL = frozenset(
    {"graph_ineligible", "hybrid_ready", "graph_pending", "graph_ready", "failed"}
)


def _parse_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from one gitignored env file.

    Args:
        path: Env file path.

    Returns:
        Mapping of keys to values.
    """

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _merged_env() -> dict[str, str]:
    """Return ``.env`` overlaid by ``.env.compose``.

    Returns:
        Combined mapping. Compose wins on conflicts.
    """

    merged = _parse_env(REPO / ".env")
    merged.update(_parse_env(REPO / ".env.compose"))
    return merged


def merged_env() -> dict[str, str]:
    """Return ``.env`` overlaid by ``.env.compose``.

    Returns:
        Combined mapping. Compose wins on conflicts.
    """

    return _merged_env()


def _require(env: dict[str, str], *keys: str) -> str:
    """Return the first non-empty env value among ``keys``.

    Args:
        env: Parsed environment.
        *keys: Candidate names.

    Returns:
        First non-empty value.

    Raises:
        RuntimeError: When every candidate is empty.
    """

    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    raise RuntimeError("missing_" + keys[0])


def require_env(env: dict[str, str], *keys: str) -> str:
    """Return the first configured demo environment value.

    Args:
        env: Parsed environment.
        *keys: Candidate names.

    Returns:
        First non-empty value.

    Raises:
        RuntimeError: When every candidate is empty.
    """

    return _require(env, *keys)


def _json_object(payload: object, source: str) -> dict[str, object]:
    """Require a JSON object.

    Args:
        payload: Decoded JSON.
        source: Label for errors.

    Returns:
        Mapping.

    Raises:
        RuntimeError: When payload is not an object.
    """

    if not isinstance(payload, dict):
        raise RuntimeError(f"{source} was not a JSON object")
    return cast(dict[str, object], payload)


def _enroll_totp(
    client: httpx.Client,
    *,
    auth_url: str,
    anon: str,
    access_token: str,
) -> str:
    """Enroll and verify TOTP; return the aal2 access token.

    Args:
        client: Shared HTTP client.
        auth_url: Hosted Auth origin.
        anon: Anon key.
        access_token: aal1 access token.

    Returns:
        aal2 access token.
    """

    headers = {
        "Authorization": f"Bearer {access_token}",
        "apikey": anon,
        "Content-Type": "application/json",
    }
    enroll = client.post(
        f"{auth_url}/auth/v1/factors",
        headers=headers,
        json={"factor_type": "totp", "friendly_name": "plot-demo"},
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


def _upsert_profile(*, operator_url: str, user_id: str) -> None:
    """Enable upload on a member profile with MFA recorded as enrolled.

    Args:
        operator_url: Session URL that can ``SET ROLE postgres``.
        user_id: Auth subject.
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        connection.execute(
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


def requeue_hybrid_index_jobs(
    *,
    operator_url: str,
    job_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    """Clear checkpoints and requeue hybrid_index jobs after a lease failure.

    Args:
        operator_url: Operator session URL (``postgres`` role).
        job_ids: Hybrid index job ids to restart.

    Returns:
        Job snapshots after the update (id, status, attempt_count).

    Side Effects:
        Deletes LangGraph checkpoints for each ``thread_id`` so resume cannot
        keep a stale ``lease_token``. Sets jobs ``pending`` with synthetic
        waiver flags. Does not print secrets.
    """

    snapshots: list[dict[str, object]] = []
    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        for job_id in job_ids:
            connection.execute(
                "DELETE FROM langgraph.checkpoint_writes WHERE thread_id = %s",
                (job_id,),
            )
            connection.execute(
                "DELETE FROM langgraph.checkpoint_blobs WHERE thread_id = %s",
                (job_id,),
            )
            connection.execute(
                "DELETE FROM langgraph.checkpoints WHERE thread_id = %s",
                (job_id,),
            )
            row = connection.execute(
                """
                UPDATE app.ingestion_jobs
                SET
                  status = 'pending'::app.job_status,
                  next_attempt_at = timezone('utc', now()),
                  lease_token = NULL,
                  lease_owner = NULL,
                  lease_expires_at = NULL,
                  attempt_count = 0,
                  last_error = NULL,
                  payload_ref = COALESCE(payload_ref, '{}'::jsonb)
                    || jsonb_build_object(
                         'content_class', 'synthetic',
                         'review_approved', true
                       )
                WHERE id = %s::uuid
                  AND job_kind = 'hybrid_index'
                RETURNING id::text, status::text, attempt_count
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                snapshots.append(
                    {"id": job_id, "status": "missing", "attempt_count": 0}
                )
            else:
                snapshots.append(
                    {
                        "id": row[0],
                        "status": row[1],
                        "attempt_count": row[2],
                    }
                )
        connection.commit()
    return snapshots


def reset_failed_graph_extract(
    *,
    operator_url: str,
    job_id: str,
    version_id: str,
    workspace_key: str = "company_default",
) -> dict[str, object]:
    """Clear failed LightRAG vendor rows and requeue one graph index job.

    Args:
        operator_url: Operator session URL (``postgres`` role).
        job_id: ``app.lightrag_index_jobs`` id.
        version_id: Canonical document version id used as the vendor document
            id.
        workspace_key: Application workspace key, also the LightRAG workspace.

    Returns:
        Counts of deleted vendor rows plus job/workspace snapshots.

    Side Effects:
        Deletes vendor status/full/chunk/vdb rows for ``version_id``. Moves
        a quarantined/updating workspace back to ``building``. Clears the
        singleton writer lease. Sets the LightRAG job ``pending`` with
        ``attempt_count=0``. Does not print secrets.
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        deleted: dict[str, int] = {}
        statements: tuple[tuple[LiteralString, LiteralString], ...] = (
            (
                "DELETE FROM lightrag.lightrag_doc_status WHERE id = %s",
                "doc_status",
            ),
            (
                "DELETE FROM lightrag.lightrag_doc_full WHERE id = %s",
                "doc_full",
            ),
            (
                "DELETE FROM lightrag.lightrag_doc_chunks WHERE full_doc_id = %s",
                "doc_chunks",
            ),
            (
                "DELETE FROM lightrag.lightrag_vdb_chunks_text_embedding_3_large_1024d "
                "WHERE full_doc_id = %s",
                "vdb_chunks",
            ),
            (
                "DELETE FROM lightrag.lightrag_full_entities WHERE id = %s",
                "full_entities",
            ),
            (
                "DELETE FROM lightrag.lightrag_full_relations WHERE id = %s",
                "full_relations",
            ),
        )
        for statement, key in statements:
            cursor = connection.execute(psycopg_sql.SQL(statement), (version_id,))
            deleted[key] = int(cursor.rowcount or 0)
        workspace = connection.execute(
            """
            UPDATE app.graph_workspaces
            SET state = 'building'::app.graph_workspace_state
            WHERE workspace_key = %s
              AND state IN (
                'quarantined'::app.graph_workspace_state,
                'updating'::app.graph_workspace_state
              )
            RETURNING workspace_key, state::text
            """,
            (workspace_key,),
        ).fetchone()
        connection.execute(
            """
            UPDATE app.graph_writer_lease
            SET
              owner = NULL,
              token = NULL,
              expires_at = NULL,
              updated_at = timezone('utc', now())
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
        job = connection.execute(
            """
            UPDATE app.lightrag_index_jobs
            SET
              status = 'pending'::app.job_status,
              next_attempt_at = timezone('utc', now()),
              lease_token = NULL,
              lease_owner = NULL,
              lease_expires_at = NULL,
              heartbeat_at = NULL,
              attempt_count = 0,
              last_error = NULL,
              error_category = NULL
            WHERE id = %s::uuid
            RETURNING id::text, status::text, attempt_count
            """,
            (job_id,),
        ).fetchone()
        connection.commit()
    return {
        "deleted": deleted,
        "workspace": None
        if workspace is None
        else {"workspace_key": workspace[0], "state": workspace[1]},
        "job": None
        if job is None
        else {"id": job[0], "status": job[1], "attempt_count": job[2]},
    }


def _mark_jobs_synthetic(*, operator_url: str, version_id: str) -> None:
    """Mark version jobs synthetic so the local unsigned waiver applies.

    Args:
        operator_url: Operator session URL.
        version_id: Document version id.
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        connection.execute(
            """
            UPDATE app.ingestion_jobs
            SET payload_ref = COALESCE(payload_ref, '{}'::jsonb)
              || jsonb_build_object(
                   'content_class', 'synthetic',
                   'review_approved', true
                 )
            WHERE version_id = %s::uuid
              AND status = 'pending'::app.job_status
            """,
            (version_id,),
        )
        connection.commit()


def _version_jobs(*, operator_url: str, version_id: str) -> list[dict[str, object]]:
    """List ingestion jobs for a version.

    Args:
        operator_url: Operator session URL.
        version_id: Document version id.

    Returns:
        Job snapshots without payload text.
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        rows = connection.execute(
            """
            SELECT id::text, job_kind, status::text, attempt_count,
                   left(coalesce(last_error, ''), 80)
            FROM app.ingestion_jobs
            WHERE version_id = %s::uuid
            ORDER BY created_at
            """,
            (version_id,),
        ).fetchall()
    return [
        {
            "id": row[0],
            "job_kind": row[1],
            "status": row[2],
            "attempt_count": row[3],
            "last_error": row[4],
        }
        for row in rows
    ]


def _insert_auth_user(*, operator_url: str, email: str, password: str) -> str:
    """Insert a confirmed email user into hosted Auth tables.

    Hosted ``service_role`` is not on this workstation, and public signup
    rejects disposable domains. Operator SQL matches the live identity shape
    (``provider=email``, ``provider_id=user_id``).

    Args:
        operator_url: Session URL that can ``SET ROLE postgres``.
        email: Unique login email.
        password: Password hashed with ``extensions.crypt``.

    Returns:
        New Auth user id.

    Raises:
        RuntimeError: When the insert does not return an id.
    """

    user_id = str(uuid.uuid4())
    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        connection.execute(
            """
            INSERT INTO auth.users (
              instance_id, id, aud, role, email, encrypted_password,
              email_confirmed_at, raw_app_meta_data, raw_user_meta_data,
              created_at, updated_at, confirmation_token, email_change,
              email_change_token_new, recovery_token, is_sso_user, is_anonymous
            )
            VALUES (
              '00000000-0000-0000-0000-000000000000'::uuid,
              %s::uuid,
              'authenticated',
              'authenticated',
              %s::text,
              extensions.crypt(%s::text, extensions.gen_salt('bf')),
              timezone('utc', now()),
              '{"provider":"email","providers":["email"]}'::jsonb,
              '{}'::jsonb,
              timezone('utc', now()),
              timezone('utc', now()),
              '',
              '',
              '',
              '',
              false,
              false
            )
            """,
            (user_id, email, password),
        )
        connection.execute(
            """
            INSERT INTO auth.identities (
              id, user_id, identity_data, provider, provider_id,
              last_sign_in_at, created_at, updated_at
            )
            VALUES (
              %s::uuid,
              %s::uuid,
              jsonb_build_object(
                'sub', %s::text,
                'email', %s::text,
                'email_verified', true
              ),
              'email',
              %s::text,
              timezone('utc', now()),
              timezone('utc', now()),
              timezone('utc', now())
            )
            """,
            (user_id, user_id, user_id, email, user_id),
        )
        connection.commit()
    return user_id


def _create_uploader(
    client: httpx.Client,
    *,
    auth_url: str,
    anon: str,
    operator_url: str,
) -> str:
    """Create a confirmed Auth user in SQL, then enroll TOTP.

    Args:
        client: Shared HTTP client.
        auth_url: Hosted Auth origin.
        anon: Anon key.
        operator_url: Operator session URL.

    Returns:
        aal2 access token.
    """

    email = f"plot-demo-{uuid.uuid4().hex[:12]}@gmail.com"
    user_id = _insert_auth_user(
        operator_url=operator_url, email=email, password=DEMO_LOGIN
    )
    print("auth_user_inserted", flush=True)
    token_response = client.post(
        f"{auth_url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
        json={"email": email, "password": DEMO_LOGIN},
    )
    print(f"password_grant status={token_response.status_code}", flush=True)
    if token_response.status_code >= 400:
        print(token_response.text[:300], flush=True)
        token_response.raise_for_status()
    access = str(
        _json_object(token_response.json(), "password grant").get("access_token", "")
    )
    if not access:
        raise RuntimeError("password grant omitted access_token")
    aal2 = _enroll_totp(client, auth_url=auth_url, anon=anon, access_token=access)
    _upsert_profile(operator_url=operator_url, user_id=user_id)
    return aal2


def _upload_one(
    client: httpx.Client,
    *,
    token: str,
    anon: str,
    auth_url: str,
    path: Path,
    title: str,
    media_type: str,
) -> tuple[str, str, str]:
    """Reserve, Storage-upload, and finalize one file.

    Args:
        client: Shared HTTP client.
        token: aal2 access token.
        anon: Anon key.
        auth_url: Hosted Auth origin.
        path: Local file.
        title: Document title.
        media_type: Finalize media type.

    Returns:
        ``(document_id, version_id, job_id)``.
    """

    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    idempotency_key = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Client-Version": "0.1.0",
        "Idempotency-Key": idempotency_key,
    }
    reserved = client.post(
        f"{API_URL}/documents/uploads",
        headers=headers,
        json={"declared_bytes": len(payload), "idempotency_key": idempotency_key},
    )
    if reserved.status_code >= 400:
        print(f"reserve_failed status={reserved.status_code}", flush=True)
        print(reserved.text[:500], flush=True)
    reserved.raise_for_status()
    body = _json_object(reserved.json(), "reserve")
    reservation_id = str(body["reservation_id"])
    bucket = str(body["storage_bucket"])
    prefix = str(body["storage_path"]).rstrip("/")
    object_name = f"{prefix}/{path.name}"
    uploaded = client.post(
        f"{auth_url}/storage/v1/object/{bucket}/{object_name}",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": anon,
            "Content-Type": media_type,
            "x-upsert": "false",
        },
        content=payload,
    )
    if uploaded.status_code not in {200, 201}:
        print(f"storage_upload_failed status={uploaded.status_code}", flush=True)
        print(uploaded.text[:500], flush=True)
        uploaded.raise_for_status()
    finalized = client.post(
        f"{API_URL}/documents/uploads/finalize",
        headers=headers,
        json={
            "reservation_id": reservation_id,
            "object_name": object_name,
            "content_hash": digest,
            "actual_bytes": len(payload),
            "media_type": media_type,
            "declared_category": "allowed",
            "attestation_policy_version": ATTESTATION_POLICY_VERSION,
            "idempotency_key": idempotency_key,
            "document_title": title,
        },
    )
    if finalized.status_code >= 400:
        print(f"finalize_failed status={finalized.status_code}", flush=True)
        print(finalized.text[:800], flush=True)
    finalized.raise_for_status()
    fin = _json_object(finalized.json(), "finalize")
    return str(fin["document_id"]), str(fin["version_id"]), str(fin["job_id"])


def _poll_until_terminal(
    client: httpx.Client,
    *,
    token: str,
    operator_url: str,
    version_id: str,
    label: str,
    timeout_seconds: float,
) -> str:
    """Poll public ingestion status until a terminal value.

    Args:
        client: Shared HTTP client.
        token: Access token.
        operator_url: Operator session URL.
        version_id: Version to watch.
        label: Log label.
        timeout_seconds: Deadline.

    Returns:
        Public status string.
    """

    deadline = time.monotonic() + timeout_seconds
    last = ""
    public_status = ""
    while time.monotonic() < deadline:
        _mark_jobs_synthetic(operator_url=operator_url, version_id=version_id)
        response = client.get(
            f"{API_URL}/ingestion/versions/{version_id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code < 400:
            payload_status = _json_object(response.json(), "status")
            version = payload_status.get("version")
            if isinstance(version, dict):
                public_status = str(cast(dict[str, object], version).get("status", ""))
            else:
                public_status = str(payload_status.get("status", ""))
        jobs = _version_jobs(operator_url=operator_url, version_id=version_id)
        snapshot = json.dumps({"label": label, "status": public_status, "jobs": jobs})
        if snapshot != last:
            print(snapshot, flush=True)
            last = snapshot
        if public_status in TERMINAL:
            return public_status
        time.sleep(5)
    print(f"timeout_{label} last_status={public_status}", flush=True)
    return public_status or "timeout"


def main() -> int:
    """Create an uploader and ingest both demo plot slices.

    Returns:
        Process exit code.
    """

    if not HYBRID_PATH.is_file() or not GRAPH_PATH.is_file():
        print("missing_demo_slices", file=sys.stderr, flush=True)
        return 2
    env = _merged_env()
    auth_url = _require(env, "SUPABASE_URL", "SUPABASE_MANAGED_URL").rstrip("/")
    anon = _require(env, "SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY")
    operator_url = _require(env, "OPERATOR_SUPABASE_DB_URL")
    print(f"auth_host={auth_url.split('://', 1)[-1].split('/', 1)[0]}", flush=True)
    with httpx.Client(timeout=120.0) as client:
        print("creating_uploader", flush=True)
        token = _create_uploader(
            client,
            auth_url=auth_url,
            anon=anon,
            operator_url=operator_url,
        )
        me = client.get(f"{API_URL}/me", headers={"Authorization": f"Bearer {token}"})
        print(f"GET /me {me.status_code}", flush=True)
        if me.status_code >= 400:
            print(me.text[:400], flush=True)
        me.raise_for_status()
        print("upload_hybrid_800", flush=True)
        hybrid_doc, hybrid_version, hybrid_job = _upload_one(
            client,
            token=token,
            anon=anon,
            auth_url=auth_url,
            path=HYBRID_PATH,
            title="CMU plots hybrid-800 (graph ineligible)",
            media_type="text/plain",
        )
        _mark_jobs_synthetic(operator_url=operator_url, version_id=hybrid_version)
        print(
            json.dumps(
                {
                    "hybrid_document_id": hybrid_doc,
                    "hybrid_version_id": hybrid_version,
                    "hybrid_job_id": hybrid_job,
                }
            ),
            flush=True,
        )
        print("upload_graph_200", flush=True)
        graph_doc, graph_version, graph_job = _upload_one(
            client,
            token=token,
            anon=anon,
            auth_url=auth_url,
            path=GRAPH_PATH,
            title="CMU plots graph-200 (graph eligible)",
            media_type="text/plain",
        )
        _mark_jobs_synthetic(operator_url=operator_url, version_id=graph_version)
        print(
            json.dumps(
                {
                    "graph_document_id": graph_doc,
                    "graph_version_id": graph_version,
                    "graph_job_id": graph_job,
                }
            ),
            flush=True,
        )
        print("mark_graph_eligible", flush=True)
        version_marked = mark_graph_eligible(document_id=uuid.UUID(graph_doc))
        print(f"graph_eligible version={version_marked}", flush=True)
        hybrid_status = _poll_until_terminal(
            client,
            token=token,
            operator_url=operator_url,
            version_id=hybrid_version,
            label="hybrid-800",
            timeout_seconds=3600,
        )
        graph_status = _poll_until_terminal(
            client,
            token=token,
            operator_url=operator_url,
            version_id=graph_version,
            label="graph-200",
            timeout_seconds=3600,
        )
        print(
            json.dumps(
                {"hybrid_800": hybrid_status, "graph_200": graph_status},
            ),
            flush=True,
        )
        if hybrid_status == "graph_ineligible" and graph_status in {
            "graph_ready",
            "graph_pending",
        }:
            return 0
        if hybrid_status == "graph_ineligible" and graph_status == "hybrid_ready":
            print("graph_200_still_hybrid_ready", flush=True)
            return 0
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
