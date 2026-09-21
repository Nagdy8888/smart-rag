"""Apply the reviewed extra-terms term RPC on hosted smart-rag.

Uses the same operator-DSN path as ``apply_pdf_overlay_migrations.py``:
``OPERATOR_SUPABASE_DB_URL``, ``SET ROLE postgres``, execute the reviewed
SQL file, then register ``supabase_migrations.schema_migrations``. Credentials
are never printed. Checkpoint counts are reason totals only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID

import psycopg
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

REPO = Path(__file__).resolve().parents[2]
MIGRATION = (
    REPO
    / "supabase"
    / "migrations"
    / "20260917120000_retrieve_term_candidates_extra_terms_v1.sql"
)
HYBRID_FAMILIES = frozenset({"hybrid", "Hybrid"})
REASON_KEYS = (
    "term_unavailable",
    "bm25_unavailable",
    "dense_unavailable",
    "retrieval_timeout",
    "timeout",
    "none",
    "null",
    "other",
)


def _parse_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from one gitignored env file.

    Args:
        path: Env file path.

    Returns:
        Mapping of keys to values. Values are never logged.
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


def operator_url() -> str:
    """Return the operator DSN from gitignored env files.

    Returns:
        Non-empty DSN. Never logged.

    Raises:
        RuntimeError: When ``OPERATOR_SUPABASE_DB_URL`` is missing.
    """

    env = _parse_env(REPO / ".env")
    env.update(_parse_env(REPO / ".env.compose"))
    url = env.get("OPERATOR_SUPABASE_DB_URL", "").strip()
    if not url:
        raise RuntimeError("missing_operator_url")
    return url


def migration_sha256() -> str:
    """Return the SHA-256 digest of the reviewed extra-terms SQL file.

    Returns:
        Lowercase hex digest of the file bytes.
    """

    return hashlib.sha256(MIGRATION.read_bytes()).hexdigest()


def _connect() -> psycopg.Connection:
    """Open an autocommit operator session as ``postgres``.

    Returns:
        Live connection. Caller closes it.

    Side Effects:
        Sets ``ROLE postgres`` for the session.
    """

    connection = psycopg.connect(operator_url(), autocommit=True)
    connection.execute("SET ROLE postgres")
    return connection


def _reason_label(raw: object) -> str:
    """Normalize one Hybrid ``fallback_reason`` to a count bucket.

    Args:
        raw: Persisted BranchResult reason, or None.

    Returns:
        One of the allow-listed reason keys, or ``other``.
    """

    if raw is None:
        return "null"
    text = str(getattr(raw, "value", raw) or "").strip()
    if text == "":
        return "null"
    if text in REASON_KEYS:
        return text
    return "other"


def count_hybrid_fallback_reasons(
    connection: psycopg.Connection,
    *,
    days: int = 7,
) -> dict[str, int]:
    """Count Hybrid ``BranchResult.fallback_reason`` values from checkpoints.

    Args:
        connection: Operator session already running as ``postgres``.
        days: Inclusive lookback for ``app.runs.started_at``.

    Returns:
        Count-only mapping. Query text and blob bytes are discarded.

    Side Effects:
        Read-only SQL over ``app.runs`` and ``langgraph.checkpoint_blobs``.
    """

    serde = JsonPlusSerializer()
    rows = connection.execute(
        """
        WITH recent_company AS (
          SELECT conversation_id::text AS thread_id
          FROM app.runs
          WHERE requested_search_scope = 'company_documents'
            AND started_at >= now() - (%s * interval '1 day')
        ),
        latest_blob AS (
          SELECT DISTINCT ON (b.thread_id)
            b.type,
            b.blob
          FROM langgraph.checkpoint_blobs AS b
          INNER JOIN recent_company AS r ON r.thread_id = b.thread_id
          WHERE b.channel = 'branch_results'
          ORDER BY b.thread_id, b.version DESC
        )
        SELECT type, blob
        FROM latest_blob
        """,
        (days,),
    ).fetchall()
    counts: Counter[str] = Counter({key: 0 for key in REASON_KEYS})
    hybrid_branches = 0
    decode_errors = 0
    for type_name, blob in rows:
        if blob is None:
            decode_errors += 1
            continue
        try:
            payload = serde.loads_typed((str(type_name), bytes(blob)))
        except Exception:
            decode_errors += 1
            continue
        branches = payload if isinstance(payload, list) else []
        for item in branches:
            if not isinstance(item, Mapping):
                continue
            family = str(item.get("family") or "")
            kind = str(item.get("kind") or "")
            if family not in HYBRID_FAMILIES and kind != "hybrid":
                continue
            hybrid_branches += 1
            counts[_reason_label(item.get("fallback_reason"))] += 1
    return {
        "company_threads_with_blobs": len(rows),
        "hybrid_branches": hybrid_branches,
        "decode_errors": decode_errors,
        **{key: int(counts[key]) for key in REASON_KEYS},
    }


def function_inventory(connection: psycopg.Connection) -> dict[str, object]:
    """Return hosted ``retrieve_term_candidates`` signature proof.

    Args:
        connection: Operator session.

    Returns:
        Signature, ``prosecdef``, argument count, functiondef digest, and
        grants. Function source is digested, never printed.
    """

    row = connection.execute(
        """
        SELECT
          p.oid::regprocedure::text AS signature,
          p.pronargs,
          p.prosecdef,
          pg_catalog.pg_get_function_identity_arguments(p.oid) AS args,
          md5(pg_catalog.pg_get_functiondef(p.oid)) AS functiondef_md5,
          COALESCE(
            (
              SELECT array_agg(privilege_type || ':' || grantee ORDER BY grantee)
              FROM information_schema.routine_privileges
              WHERE routine_schema = 'app'
                AND routine_name = 'retrieve_term_candidates'
                AND grantee <> current_user
            ),
            ARRAY[]::text[]
          ) AS grants
        FROM pg_proc AS p
        INNER JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = 'app'
          AND p.proname = 'retrieve_term_candidates'
        ORDER BY p.pronargs DESC
        LIMIT 1
        """
    ).fetchone()
    seven_present = connection.execute(
        """
        SELECT to_regprocedure(
          'app.retrieve_term_candidates(uuid,text,bigint,text,integer,text,text[])'
        ) IS NOT NULL
        """
    ).fetchone()
    six_present = connection.execute(
        """
        SELECT to_regprocedure(
          'app.retrieve_term_candidates(uuid,text,bigint,text,integer,text)'
        ) IS NOT NULL
        """
    ).fetchone()
    search_path = None
    if row is not None:
        path_row = connection.execute(
            """
            SELECT pg_catalog.pg_get_functiondef(p.oid)
            FROM pg_proc AS p
            INNER JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'app'
              AND p.proname = 'retrieve_term_candidates'
            ORDER BY p.pronargs DESC
            LIMIT 1
            """
        ).fetchone()
        definition = str(path_row[0]) if path_row is not None else ""
        marker = "SET search_path TO "
        if marker in definition:
            search_path = definition.split(marker, 1)[1].split("\n", 1)[0].strip()
        elif "SET search_path =" in definition:
            search_path = (
                definition.split("SET search_path =", 1)[1].split("\n", 1)[0].strip()
            )
    return {
        "signature": None if row is None else row[0],
        "pronargs": None if row is None else int(row[1]),
        "prosecdef": None if row is None else bool(row[2]),
        "args": None if row is None else row[3],
        "functiondef_md5": None if row is None else row[4],
        "grants": [] if row is None else list(row[5] or ()),
        "seven_arg_present": bool(seven_present[0]) if seven_present else False,
        "six_arg_present": bool(six_present[0]) if six_present else False,
        "search_path": search_path,
    }


def apply_reviewed_sql(connection: psycopg.Connection) -> None:
    """Execute the reviewed extra-terms SQL and register the version.

    Args:
        connection: Autocommit operator session as ``postgres``.

    Side Effects:
        Replaces the six-argument overload with the seven-argument
        SECURITY INVOKER function. Inserts
        ``20260917120000`` into ``supabase_migrations.schema_migrations``.
    """

    connection.execute(cast(LiteralString, MIGRATION.read_text(encoding="utf-8")))
    connection.execute(
        """
        INSERT INTO supabase_migrations.schema_migrations (version, name)
        VALUES (%s, %s)
        ON CONFLICT (version) DO NOTHING
        """,
        (MIGRATION.name.split("_", 1)[0], MIGRATION.stem),
    )


def count_smoke_reasons(
    connection: psycopg.Connection,
    conversation_ids: tuple[UUID, ...],
) -> dict[str, object]:
    """Count Hybrid fallback reasons for specific smoke conversations.

    Args:
        connection: Operator session.
        conversation_ids: Fresh Ask conversation UUIDs.

    Returns:
        Count-only mapping plus the conversation count. No query text.
    """

    if not conversation_ids:
        return {"conversations": 0, "hybrid_branches": 0, "term_unavailable": 0}
    serde = JsonPlusSerializer()
    rows = connection.execute(
        """
        SELECT DISTINCT ON (b.thread_id)
          b.thread_id,
          b.type,
          b.blob
        FROM langgraph.checkpoint_blobs AS b
        WHERE b.channel = 'branch_results'
          AND b.thread_id = ANY(%s)
        ORDER BY b.thread_id, b.version DESC
        """,
        ([str(item) for item in conversation_ids],),
    ).fetchall()
    counts: Counter[str] = Counter({key: 0 for key in REASON_KEYS})
    hybrid_branches = 0
    for _thread_id, type_name, blob in rows:
        if blob is None:
            continue
        payload = serde.loads_typed((str(type_name), bytes(blob)))
        branches = payload if isinstance(payload, list) else []
        for item in branches:
            if not isinstance(item, Mapping):
                continue
            family = str(item.get("family") or "")
            kind = str(item.get("kind") or "")
            if family not in HYBRID_FAMILIES and kind != "hybrid":
                continue
            hybrid_branches += 1
            counts[_reason_label(item.get("fallback_reason"))] += 1
    return {
        "conversations": len(conversation_ids),
        "blobs": len(rows),
        "hybrid_branches": hybrid_branches,
        **{key: int(counts[key]) for key in REASON_KEYS},
    }


def main(argv: list[str] | None = None) -> int:
    """Prove the hosted signature, optionally apply, then re-verify.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` on success. ``2`` when the operator DSN is missing.
        ``3`` when post-apply grants or signature fail.
    """

    parser = argparse.ArgumentParser(
        description="Apply reviewed extra-terms retrieve_term_candidates SQL."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the reviewed SQL after printing pre-deploy proof.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Checkpoint lookback in days for company Hybrid branches.",
    )
    parser.add_argument(
        "--smoke-answers",
        type=Path,
        default=None,
        help="Gitignored Ask answers JSON whose conversation ids are counted.",
    )
    args = parser.parse_args(argv)
    print(f"project_ref=qsjivtwtmlmtksufqjik")
    print(f"migration={MIGRATION.name}")
    print(f"migration_sha256={migration_sha256()}")
    try:
        connection = _connect()
    except RuntimeError as exc:
        print(f"blocked={exc}")
        return 2
    with connection:
        pre_sig = function_inventory(connection)
        print(f"pre_seven_arg_present={pre_sig['seven_arg_present']}")
        print(f"pre_six_arg_present={pre_sig['six_arg_present']}")
        print(f"pre_pronargs={pre_sig['pronargs']}")
        print(f"pre_prosecdef={pre_sig['prosecdef']}")
        print(f"pre_signature={pre_sig['signature']}")
        print(f"pre_functiondef_md5={pre_sig['functiondef_md5']}")
        print(f"pre_grants={pre_sig['grants']}")
        pre_counts = count_hybrid_fallback_reasons(connection, days=args.days)
        print(f"pre_checkpoint_counts={pre_counts}")
        hybrid = max(int(pre_counts["hybrid_branches"]), 0)
        term = int(pre_counts["term_unavailable"])
        share = (term / hybrid) if hybrid else None
        print(f"pre_term_unavailable_share={share}")
        if args.apply:
            print(f"applying={MIGRATION.name}")
            apply_reviewed_sql(connection)
            print(f"applied={MIGRATION.name}")
        post_sig = function_inventory(connection)
        print(f"post_seven_arg_present={post_sig['seven_arg_present']}")
        print(f"post_six_arg_present={post_sig['six_arg_present']}")
        print(f"post_pronargs={post_sig['pronargs']}")
        print(f"post_prosecdef={post_sig['prosecdef']}")
        print(f"post_signature={post_sig['signature']}")
        print(f"post_functiondef_md5={post_sig['functiondef_md5']}")
        print(f"post_search_path={post_sig['search_path']}")
        print(f"post_grants={post_sig['grants']}")
        if args.apply:
            grants = {str(item) for item in cast(list[object], post_sig["grants"])}
            if (
                post_sig["seven_arg_present"] is not True
                or post_sig["pronargs"] != 7
                or post_sig["prosecdef"] is not False
                or "EXECUTE:PUBLIC" in grants
                or "EXECUTE:app_api" not in {item for item in grants}
            ):
                print("blocked=post_apply_signature_or_grants")
                return 3
        if args.smoke_answers is not None:
            payload_obj: object = json.loads(
                args.smoke_answers.read_text(encoding="utf-8")
            )
            if not isinstance(payload_obj, dict):
                print("blocked=smoke_answers_not_object")
                return 2
            conversation_ids: list[UUID] = []
            for question_id, row in cast(dict[object, object], payload_obj).items():
                if not isinstance(row, dict):
                    continue
                raw_id = str(row.get("conversation_id") or "").strip()
                if raw_id:
                    conversation_ids.append(UUID(raw_id))
                    print(f"smoke_question={question_id} conversation_present=true")
            smoke = count_smoke_reasons(connection, tuple(conversation_ids))
            print(f"smoke_checkpoint_counts={smoke}")
            print(f"smoke_term_unavailable={smoke.get('term_unavailable', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
