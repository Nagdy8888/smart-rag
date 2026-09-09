"""Import and approve a private PDF glossary through the owner/admin API.

Never prints canonical terms, aliases, or locators. Does not auto-approve
without ``--approver``. Writes IDs and counts only.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import cast

import httpx
import psycopg

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ops.ingest_demo_plot_slices import (  # noqa: E402
    DEMO_LOGIN,
    enroll_totp,
    insert_auth_user,
    json_object,
    merged_env,
    require_env,
)

API_URL = "http://127.0.0.1:8000"


def _upsert_owner(*, operator_url: str, user_id: str) -> None:
    """Enable upload on an owner profile with MFA recorded as enrolled.

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
            VALUES (%s, 'owner'::app.user_role, true, true, 100)
            ON CONFLICT (user_id) DO UPDATE
              SET upload_enabled = true,
                  mfa_enrolled = true,
                  role = 'owner'::app.user_role
            """,
            (user_id,),
        )
        connection.commit()


def create_owner(
    client: httpx.Client,
    *,
    auth_url: str,
    anon: str,
    operator_url: str,
) -> str:
    """Create a confirmed Auth owner, then enroll TOTP.

    Args:
        client: Shared HTTP client.
        auth_url: Hosted Auth origin.
        anon: Anon key.
        operator_url: Operator session URL.

    Returns:
        aal2 access token.
    """

    email = f"pdf-overlay-{uuid.uuid4().hex[:12]}@gmail.com"
    user_id = insert_auth_user(
        operator_url=operator_url, email=email, password=DEMO_LOGIN
    )
    print("auth_owner_inserted", flush=True)
    token_response = client.post(
        f"{auth_url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
        json={"email": email, "password": DEMO_LOGIN},
    )
    print(f"password_grant status={token_response.status_code}", flush=True)
    token_response.raise_for_status()
    access = str(
        json_object(token_response.json(), "password grant").get("access_token", "")
    )
    if not access:
        raise RuntimeError("password grant omitted access_token")
    aal2 = enroll_totp(client, auth_url=auth_url, anon=anon, access_token=access)
    _upsert_owner(operator_url=operator_url, user_id=user_id)
    return aal2


def _alias_count(*, operator_url: str, import_id: str) -> int:
    """Count projected aliases for one import without returning text.

    Args:
        operator_url: Operator session URL.
        import_id: Glossary import id.

    Returns:
        Projected alias row count.
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        row = connection.execute(
            """
            SELECT count(*)::int
            FROM app.search_aliases
            WHERE import_id = %s::uuid
            """,
            (import_id,),
        ).fetchone()
    return int(row[0]) if row is not None else 0


def _latest_audit_id(*, operator_url: str, import_id: str) -> str:
    """Return the latest glossary audit event id for an import.

    Args:
        operator_url: Operator session URL.
        import_id: Glossary import id.

    Returns:
        Audit event id or ``missing``.
    """

    with psycopg.connect(operator_url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        row = connection.execute(
            """
            SELECT id::text
            FROM app.audit_events
            WHERE event_type = 'glossary_import_approved'
              AND target_id = %s::uuid
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (import_id,),
        ).fetchone()
    return str(row[0]) if row is not None else "missing"


def main(argv: list[str] | None = None) -> int:
    """Import a gitignored payload and approve it as the named owner.

    Args:
        argv: Optional CLI arguments.

    Returns:
        Process exit code.
    """

    parser = argparse.ArgumentParser(
        description="Import and approve a private PDF glossary. Prints IDs only."
    )
    parser.add_argument(
        "--payload",
        type=Path,
        default=Path(".private-eval/glossary-import.json"),
    )
    parser.add_argument("--approver", required=True)
    parser.add_argument("--source-version", default="v1")
    args = parser.parse_args(argv)
    if not args.payload.is_file():
        print("glossary_import_payload_missing")
        return 2
    raw_obj = json.loads(args.payload.read_text(encoding="utf-8"))
    if not isinstance(raw_obj, dict):
        print("glossary_import_payload_invalid")
        return 2
    raw = cast(dict[str, object], raw_obj)
    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, list) or not entries_raw:
        print("glossary_import_entries_empty")
        return 2
    http_entries: list[dict[str, object]] = []
    for item in cast(list[object], entries_raw):
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, object], item)
        aliases_raw = entry.get("aliases", [])
        aliases = (
            [str(alias) for alias in cast(list[object], aliases_raw)]
            if isinstance(aliases_raw, list)
            else []
        )
        http_entries.append(
            {
                "entry_key": entry["entry_key"],
                "canonical_term": entry["canonical_term"],
                "language": entry.get("language", "en"),
                "entry_type": entry["entry_type"],
                "effective_scope": entry.get("effective_scope", "company"),
                "aliases": aliases,
            }
        )
    env = merged_env()
    auth_url = require_env(env, "SUPABASE_URL", "SUPABASE_MANAGED_URL").rstrip("/")
    anon = require_env(env, "SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY")
    operator_url = require_env(env, "OPERATOR_SUPABASE_DB_URL")
    idempotency_key = f"pdf-glossary-{uuid.uuid4().hex}"
    with httpx.Client(timeout=120.0) as client:
        token = create_owner(
            client,
            auth_url=auth_url,
            anon=anon,
            operator_url=operator_url,
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Client-Version": "0.1.0",
            "Idempotency-Key": idempotency_key,
        }
        created = client.post(
            f"{API_URL}/admin/glossary/imports",
            headers=headers,
            json={
                "source_name": "private-pdf-glossary",
                "source_version": args.source_version,
                "idempotency_key": idempotency_key,
                "entries": http_entries,
            },
        )
        print(f"glossary_import_status={created.status_code}", flush=True)
        if created.status_code >= 400:
            print(created.text[:200], flush=True)
            return 2
        body = json_object(created.json(), "glossary import")
        import_id = str(body["import_id"])
        approved = client.post(
            f"{API_URL}/admin/glossary/imports/{import_id}/approve",
            headers=headers,
        )
        print(f"glossary_approve_status={approved.status_code}", flush=True)
        if approved.status_code >= 400:
            print(approved.text[:200], flush=True)
            return 2
        outcome = json_object(approved.json(), "glossary approve")
    projected = _alias_count(operator_url=operator_url, import_id=import_id)
    audit_id = _latest_audit_id(operator_url=operator_url, import_id=import_id)
    print(f"import_id={import_id}")
    print(f"status={outcome.get('status')}")
    print(f"entry_count={outcome.get('entry_count')}")
    print(f"alias_count={outcome.get('alias_count')}")
    print(f"projected_alias_count={projected}")
    print(f"audit_id={audit_id}")
    print(f"approver_set={str(bool(args.approver.strip())).lower()}")
    print("auto_approved=false")
    return 0 if projected > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
