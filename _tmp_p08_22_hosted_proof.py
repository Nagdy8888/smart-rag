"""Bounded hosted P08-22 API proof. Never prints secrets or DSNs."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts" / "ops"))
from ensure_app_runtime_role import _parse_env
from ingest_demo_plot_slices import DEMO_LOGIN, _insert_auth_user, _upsert_profile

REPO = Path(__file__).resolve().parent
API = "http://127.0.0.1:8000"
LOCAL_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def _classify_url(name: str, value: str) -> str:
    """Return host/port labels without secrets.

    Args:
        name: Variable name.
        value: URL. Never printed.

    Returns:
        Classification string.
    """

    parsed = urlparse(value)
    host = parsed.hostname or ""
    user = (parsed.username or "").split(".")[0]
    hosted = host.endswith(".supabase.co") or host.endswith("pooler.supabase.com")
    return (
        f"{name} user={user or '-'} host_suffix={host[-24:]} "
        f"port={parsed.port or 'default'} hosted={hosted}"
    )


def _counts(dsn: str, conversation_id: str, run_id: str) -> dict[str, object]:
    """Read durable chat counts for one conversation/run.

    Args:
        dsn: Postgres URL. Never logged.
        conversation_id: Conversation UUID.
        run_id: Run UUID.

    Returns:
        Count mapping. Empty mapping when the database is unreachable.
    """

    try:
        connection = psycopg.connect(dsn, connect_timeout=8)
    except psycopg.Error:
        return {"reachable": False}
    with connection:
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM app.conversations WHERE id = %s),
              (SELECT count(*) FROM app.messages WHERE conversation_id = %s),
              (SELECT count(*) FROM app.runs WHERE id = %s),
              (SELECT status::text FROM app.runs WHERE id = %s),
              (SELECT count(*) FROM app.run_events WHERE run_id = %s),
              (SELECT count(*) FROM app.run_events
                 WHERE run_id = %s AND event_type = 'token_delta'),
              (SELECT count(*) FROM app.run_events
                 WHERE run_id = %s AND event_type IN (
                   'completed', 'cancelled', 'error', 'deadline', 'partial'
                 )),
              (SELECT string_agg(event_type, ',' ORDER BY sequence)
                 FROM app.run_events WHERE run_id = %s),
              (SELECT count(*) FROM langgraph.checkpoints
                 WHERE thread_id = %s),
              (SELECT count(*) FROM app.llm_usage WHERE run_id = %s)
            """,
            (
                conversation_id,
                conversation_id,
                run_id,
                run_id,
                run_id,
                run_id,
                run_id,
                run_id,
                conversation_id,
                run_id,
            ),
        ).fetchone()
    if row is None:
        return {"reachable": True}
    return {
        "reachable": True,
        "conversations": row[0],
        "messages": row[1],
        "runs": row[2],
        "run_status": row[3],
        "events": row[4],
        "token_delta": row[5],
        "terminals": row[6],
        "event_types": row[7],
        "checkpoints": row[8],
        "usage_rows": row[9],
    }


def main() -> int:
    """Create one hosted member, admit one query, and compare stores.

    Returns:
        Process exit code.

    Side Effects:
        Inserts one hosted Auth user/profile and one conversation/run.
        Never prints passwords, tokens, or DSNs.
    """

    root = _parse_env(REPO / ".env")
    compose = _parse_env(REPO / ".env.compose")
    auth_url = (compose.get("SUPABASE_URL") or root.get("SUPABASE_MANAGED_URL") or "").rstrip(
        "/"
    )
    anon = (
        compose.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or root.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or root.get("SUPABASE_ANON_KEY")
        or ""
    )
    operator = (
        compose.get("OPERATOR_SUPABASE_DB_URL")
        or root.get("STAGING_SUPABASE_SESSION_URL")
        or ""
    )
    if "supabase.co" not in auth_url or not anon or not operator:
        print("blocked_missing_hosted_auth")
        return 1
    print(_classify_url("hosted_auth", auth_url))
    print(_classify_url("operator_session", operator))

    email = f"p08-22-hosted-{uuid4().hex[:10]}@gmail.com"
    user_id = _insert_auth_user(operator_url=operator, email=email, password=DEMO_LOGIN)
    _upsert_profile(operator_url=operator, user_id=user_id)
    with psycopg.connect(operator, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        connection.execute(
            """
            UPDATE app.profiles
            SET monthly_llm_budget_usd = 200
            WHERE user_id = %s
            """,
            (user_id,),
        )
        connection.commit()
    print(f"hosted_user_inserted email_domain={email.split('@', 1)[1]}")

    with httpx.Client(timeout=30.0) as client:
        ready = client.get(f"{API}/health/ready")
        print(f"ready status={ready.status_code} query_ready={ready.json().get('query_ready')}")
        grant = client.post(
            f"{auth_url}/auth/v1/token?grant_type=password",
            headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            json={"email": email, "password": DEMO_LOGIN},
        )
        print(f"password_grant status={grant.status_code}")
        if grant.status_code >= 400:
            return 1
        token = str(grant.json().get("access_token") or "")
        if not token:
            print("blocked_missing_access_token")
            return 1
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Client-Version": "0.1.0",
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid4()),
        }
        created = client.post(f"{API}/conversations", headers=headers, json={})
        print(f"conversations status={created.status_code}")
        if created.status_code != 201:
            return 1
        conversation_id = str(created.json()["conversation_id"])
        submitted = client.post(
            f"{API}/conversations/{conversation_id}/messages",
            headers=headers,
            json={"message": "What documents are in the corpus?"},
        )
        print(f"messages status={submitted.status_code}")
        if submitted.status_code != 202:
            detail = submitted.json() if submitted.headers.get("content-type", "").startswith("application/json") else {}
            code = detail.get("detail") if isinstance(detail, dict) else None
            print(f"messages_detail={code}")
            return 1
        run_id = str(submitted.json()["run_id"])
        print(f"run_id={run_id}")
        events = client.get(
            f"{API}/runs/{run_id}/events?after=0",
            headers=headers,
            timeout=90.0,
        )
        print(f"sse status={events.status_code}")
        for _ in range(30):
            hosted = _counts(operator, conversation_id, run_id)
            if hosted.get("terminals"):
                break
            time.sleep(2)
        hosted = _counts(operator, conversation_id, run_id)
        local = _counts(LOCAL_DSN, conversation_id, run_id)
        print("hosted " + " ".join(f"{key}={value}" for key, value in hosted.items()))
        print("local " + " ".join(f"{key}={value}" for key, value in local.items()))
        print(f"email={email}")
        print(f"conversation_id={conversation_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
