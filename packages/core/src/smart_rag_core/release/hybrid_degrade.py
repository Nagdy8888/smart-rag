"""Worker-side Hybrid retrieve under ParadeDB unavailability for Packet 5.

Frozen Packet 1 images do not include Packet 5 modules. This file is injected
onto worker ``/tmp``. When ParadeDB connect fails, ``HybridRetriever`` is
constructed with ``paradedb=None`` / ``bm25=None`` so retrieve degrades to
dense+term with ``bm25_unavailable``. Query text is not written to JSON.
"""

from __future__ import annotations

import json
import sys

import psycopg

from smart_rag_core.gateways.embedding import create_embedding_gateway
from smart_rag_core.release.io import as_json_object
from smart_rag_core.retrieval.dense import DenseRetriever
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.retrieval.terms import TermRetriever
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.settings import SharedSettings
from smart_rag_core.settings.base import get_process_environ

DEGRADE_SCHEMA_VERSION = "phase09-candidate-packet5-hybrid-degrade-v1"


def _load_caller(connection: psycopg.Connection, user_id: str) -> CallerContext:
    """Load one profile row as ``CallerContext``.

    Args:
        connection: Open Postgres connection.
        user_id: Profile primary key.

    Returns:
        Active caller for Hybrid retrieve.

    Raises:
        ValueError: If the profile is missing.
    """

    with connection.cursor() as cursor:
        cursor.execute("SELECT app.current_authorization_version()")
        version_row = cursor.fetchone()
        cursor.execute(
            """
            SELECT user_id::text, role::text, disabled_at
            FROM app.profiles
            WHERE user_id = %s
            """,
            (user_id,),
        )
        row = cursor.fetchone()
    if row is None or version_row is None:
        raise ValueError("hybrid degrade profile missing")
    return CallerContext.from_profile_row(
        user_id=str(row[0]),
        role=str(row[1]),
        authorization_version=int(str(version_row[0])),
        disabled_at=row[2],
    )


def _parade_connects(parade_url: str) -> bool:
    """Return True when unpublished ParadeDB accepts a connection.

    Args:
        parade_url: Worker ``PARADEDB_URL``.

    Returns:
        True on successful ``SELECT 1``.
    """

    try:
        with psycopg.connect(parade_url, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except (psycopg.Error, OSError, TimeoutError):
        return False
    return True


def run_hybrid_degrade(
    *,
    supabase_url: str,
    parade_url: str,
    user_id: str,
    query: str,
) -> dict[str, object]:
    """Retrieve with ParadeDB omitted when the projection is unreachable.

    Args:
        supabase_url: Canonical Postgres URL.
        parade_url: Unpublished worker ParadeDB URL.
        user_id: Profile used as the retrieve caller.
        query: Retrieve text. Not stored in the result.

    Returns:
        Degrade payload with fallback reason and ranked count.

    Side Effects:
        Opens canonical Postgres. Opens ParadeDB only for the reachability
        probe. Mock embeddings follow worker ``MOCK_MODEL_MODE``.
    """

    parade_up = _parade_connects(parade_url)
    settings = SharedSettings()
    gateway = create_embedding_gateway(settings)
    with psycopg.connect(supabase_url) as supabase:
        caller = _load_caller(supabase, user_id)
        supabase.rollback()
        retriever = HybridRetriever(
            embedding_gateway=gateway,
            supabase=supabase,
            paradedb=None,
            bm25=None,
            dense=DenseRetriever(supabase),
            term=TermRetriever(supabase),
            supabase_dsn=supabase_url,
        )
        result = retriever.retrieve(query=query, caller=caller)
    reason_value = result.fallback_reason.value
    expected = RetrievalFallbackReason.BM25_UNAVAILABLE.value
    passed = (not parade_up) and reason_value == expected
    return {
        "schema_version": DEGRADE_SCHEMA_VERSION,
        "driver": "HybridRetriever.retrieve",
        "paradedb_reachable": parade_up,
        "constructor": "paradedb_none_bm25_none",
        "fallback_reason": reason_value,
        "ranked_count": len(result.ranked_ids),
        "sample_is_eight_doc_subset": True,
        "unpublished_paradedb": True,
        "overlay_required": False,
        "passed": passed,
        "mock_model_mode": settings.mock_model_mode,
    }


def parse_degrade_stdin(raw: str) -> tuple[str, str]:
    """Parse worker stdin JSON into caller id and query.

    Args:
        raw: JSON object with ``user_id`` and ``query``.

    Returns:
        ``(user_id, query)``.

    Raises:
        ValueError: If the payload is malformed.
    """

    loaded: object = json.loads(raw)
    payload = as_json_object(loaded, source="hybrid-degrade-stdin")
    user_id = payload.get("user_id")
    query = payload.get("query")
    if not isinstance(user_id, str) or user_id == "":
        raise ValueError("hybrid degrade requires user_id")
    if not isinstance(query, str) or query == "":
        raise ValueError("hybrid degrade requires query")
    return user_id, query


def main() -> int:
    """CLI entry used inside the frozen worker via ``/tmp`` injection.

    Returns:
        Process exit code.
    """

    supabase_url = get_process_environ("SUPABASE_DB_URL")
    parade_url = get_process_environ("PARADEDB_URL")
    if not supabase_url or not parade_url:
        sys.stderr.write("SUPABASE_DB_URL and PARADEDB_URL are required\n")
        return 2
    try:
        user_id, query = parse_degrade_stdin(sys.stdin.read())
        payload = run_hybrid_degrade(
            supabase_url=supabase_url,
            parade_url=parade_url,
            user_id=user_id,
            query=query,
        )
    except (
        ValueError,
        json.JSONDecodeError,
        OSError,
        psycopg.Error,
        RuntimeError,
    ) as exc:
        payload = {
            "schema_version": DEGRADE_SCHEMA_VERSION,
            "passed": False,
            "error_type": type(exc).__name__,
        }
        sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
        sys.stderr.write(f"hybrid degrade failed: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    return 0 if payload.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
