"""Create one local member for the P08-22 browser query. Prints email only."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg

ROOT = Path(__file__).resolve().parent
ANON = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
)
PASSWORD = "Phase8Live9x"


def main() -> int:
    """Create a confirmed member with a 200 USD monthly budget."""

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
        print(f"supabase_status_exit={result.returncode}")
        return 1
    status = json.loads(result.stdout[result.stdout.find("{") : result.stdout.rfind("}") + 1])
    auth = str(status["API_URL"]).rstrip("/")
    service = str(status["SERVICE_ROLE_KEY"])
    email = f"p08-22-browser-{uuid4().hex[:10]}@example.com"
    with httpx.Client(timeout=20.0) as client:
        created = client.post(
            f"{auth}/auth/v1/admin/users",
            headers={"Authorization": f"Bearer {service}", "apikey": service},
            json={"email": email, "password": PASSWORD, "email_confirm": True},
        )
        print(f"admin_create={created.status_code}")
        if created.status_code >= 400:
            return 1
        user_id = str(created.json().get("id", ""))
    with psycopg.connect("postgresql://postgres:postgres@127.0.0.1:54322/postgres") as connection:
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
    print(f"email={email}")
    print(f"user_id={user_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
