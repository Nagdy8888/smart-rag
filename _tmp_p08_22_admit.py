"""Reproduce P08-22 admit against local GoTrue and FastAPI. No secret prints."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg

ROOT = Path(__file__).resolve().parent
ADMIN_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
API = "http://127.0.0.1:8000"
PASSWORD = "Phase8Live9x"
ANON = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
)


def _status() -> dict[str, str]:
    """Read local Supabase CLI status JSON without printing keys."""

    bin_name = "supabase.cmd" if sys.platform == "win32" else "supabase"
    binary = ROOT / "node_modules" / ".bin" / bin_name
    result = subprocess.run(
        [str(binary), "status", "-o", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise SystemExit(f"supabase_status_exit={result.returncode}")
    start = result.stdout.find("{")
    end = result.stdout.rfind("}")
    parsed = json.loads(result.stdout[start : end + 1])
    out = {k: v for k, v in parsed.items() if isinstance(v, str)}
    if not out.get("API_URL") or not out.get("SERVICE_ROLE_KEY"):
        raise SystemExit("supabase_status_incomplete")
    return out


def main() -> int:
    """Create a member, admit one message, count local durable rows."""

    status = _status()
    auth = status["API_URL"].rstrip("/")
    service = status["SERVICE_ROLE_KEY"]
    email = f"p08-22-retry-{uuid4().hex[:12]}@example.com"
    with httpx.Client(timeout=20.0) as client:
        created = client.post(
            f"{auth}/auth/v1/admin/users",
            headers={
                "Authorization": f"Bearer {service}",
                "apikey": service,
            },
            json={"email": email, "password": PASSWORD, "email_confirm": True},
        )
        print(f"admin_create={created.status_code}")
        if created.status_code >= 400:
            return 1
        user_id = str(created.json().get("id", ""))
        print(f"user_id={user_id}")
        token = client.post(
            f"{auth}/auth/v1/token?grant_type=password",
            headers={"apikey": ANON, "Authorization": f"Bearer {ANON}"},
            json={"email": email, "password": PASSWORD},
        )
        print(f"password_grant={token.status_code}")
        if token.status_code >= 400:
            return 1
        access = str(token.json().get("access_token", ""))
        if not access:
            print("password_grant_missing_token")
            return 1
        with psycopg.connect(ADMIN_DSN) as connection:
            connection.execute(
                """
                INSERT INTO app.profiles (
                  user_id, role, upload_enabled, monthly_llm_budget_usd
                )
                VALUES (%s, 'member'::app.user_role, true, 200)
                ON CONFLICT (user_id) DO UPDATE
                  SET monthly_llm_budget_usd = 200
                """,
                (user_id,),
            )
            connection.commit()
        print("profile_budget=200")
        headers = {
            "Authorization": f"Bearer {access}",
            "X-Client-Version": "0.1.0",
            "Content-Type": "application/json",
        }
        conv = client.post(
            f"{API}/conversations",
            headers=headers,
            json={"title": "p08-22-admit"},
        )
        print(f"conversations={conv.status_code}")
        if conv.status_code >= 400:
            print(f"conversations_detail={conv.text[:200]}")
            return 1
        conversation_id = str(conv.json().get("conversation_id", ""))
        print(f"conversation_id={conversation_id}")
        idem = str(uuid4())
        submitted = client.post(
            f"{API}/conversations/{conversation_id}/messages",
            headers={**headers, "Idempotency-Key": idem},
            json={"message": "What documents are in the corpus?"},
        )
        print(f"messages={submitted.status_code}")
        body = submitted.json() if submitted.headers.get("content-type", "").startswith("application/json") else {}
        run_id = str(body.get("run_id", ""))
        print(f"run_id={run_id}")
        print(f"admit_status={body.get('status')}")
        print(f"route_family={body.get('route_family')}")
        print(f"reconnect={body.get('reconnect')}")
        if submitted.status_code >= 400:
            print(f"messages_detail={submitted.text[:300]}")
        with psycopg.connect(ADMIN_DSN) as connection:
            counts = connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM app.conversations WHERE id = %s) AS conversations,
                  (SELECT count(*) FROM app.messages WHERE conversation_id = %s) AS messages,
                  (SELECT count(*) FROM app.runs WHERE conversation_id = %s) AS runs,
                  (SELECT count(*) FROM app.runs WHERE id = %s) AS run_by_id,
                  (SELECT count(*) FROM app.run_events WHERE run_id = %s) AS run_events,
                  (SELECT count(*) FROM app.llm_usage WHERE run_id = %s) AS usage_rows
                """,
                (
                    conversation_id,
                    conversation_id,
                    conversation_id,
                    run_id or None,
                    run_id or None,
                    run_id or None,
                ),
            ).fetchone()
        print(
            "local_counts "
            f"conversations={counts[0]} messages={counts[1]} runs={counts[2]} "
            f"run_by_id={counts[3]} run_events={counts[4]} usage_rows={counts[5]}"
        )
    return 0 if submitted.status_code == 202 and counts[2] >= 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
