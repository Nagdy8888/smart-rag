"""Worker-side Hybrid retrieve timings for Packet 4 foreground load.

Frozen Packet 1 images do not include Packet 4 modules. This file is injected
onto worker ``/tmp`` and uses existing ``HybridRetriever.retrieve``. It does
not attach the Packet 8 overlay, SQL-stamp ready states, or change document
ids. Query text is accepted on stdin and is not written to the result JSON.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence

import psycopg

from smart_rag_core.gateways.embedding import create_embedding_gateway
from smart_rag_core.release.io import as_json_list, as_json_object
from smart_rag_core.retrieval.bm25 import Bm25Retriever
from smart_rag_core.retrieval.dense import DenseRetriever
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.retrieval.terms import TermRetriever
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.settings import SharedSettings

FOREGROUND_SCHEMA_VERSION = "phase09-candidate-packet4-hybrid-foreground-v1"


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
        raise ValueError("hybrid foreground profile missing")
    return CallerContext.from_profile_row(
        user_id=str(row[0]),
        role=str(row[1]),
        authorization_version=int(str(version_row[0])),
        disabled_at=row[2],
    )


def run_hybrid_foreground(
    *,
    supabase_url: str,
    parade_url: str,
    user_id: str,
    queries: Sequence[tuple[str, str]],
) -> dict[str, object]:
    """Time ``HybridRetriever.retrieve`` for each case id.

    Args:
        supabase_url: Canonical Postgres URL.
        parade_url: Unpublished worker ParadeDB URL.
        user_id: Profile used as the retrieve caller.
        queries: ``(case_id, query)`` pairs. Query text is not stored.

    Returns:
        Timing payload with ``first_evidence_ms`` samples.

    Side Effects:
        Opens two autocommit database connections and runs retrieve. Mock
        embeddings follow worker ``MOCK_MODEL_MODE``. Autocommit keeps the
        connection idle so ``retrieval_transaction`` can begin.
    """

    settings = SharedSettings()
    gateway = create_embedding_gateway(settings)
    samples: list[dict[str, object]] = []
    with (
        psycopg.connect(supabase_url, autocommit=True) as supabase,
        psycopg.connect(parade_url, connect_timeout=8, autocommit=True) as parade,
    ):
        caller = _load_caller(supabase, user_id)
        retriever = HybridRetriever(
            embedding_gateway=gateway,
            supabase=supabase,
            paradedb=parade,
            supabase_dsn=supabase_url,
            dense=DenseRetriever(supabase),
            bm25=Bm25Retriever(parade),
            term=TermRetriever(supabase),
        )
        for case_id, query in queries:
            result = retriever.retrieve(query=query, caller=caller)
            samples.append(
                {
                    "case_id": case_id,
                    "first_evidence_ms": result.first_evidence_ms,
                    "ranked_count": len(result.ranked_ids),
                }
            )
    values = [
        float(item["first_evidence_ms"])
        for item in samples
        if isinstance(item["first_evidence_ms"], (int, float))
        and not isinstance(item["first_evidence_ms"], bool)
    ]
    p95 = _percentile(values, 0.95)
    return {
        "schema_version": FOREGROUND_SCHEMA_VERSION,
        "driver": "HybridRetriever.retrieve",
        "sample_is_eight_doc_subset": True,
        "unpublished_paradedb": True,
        "overlay_required": False,
        "sample_size": len(values),
        "first_evidence_ms": values,
        "first_evidence_p95_ms": p95,
        "cases": [{"case_id": item["case_id"]} for item in samples],
        "passed": p95 is not None,
        "mock_model_mode": settings.mock_model_mode,
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    """Return a linear-interpolation percentile.

    Args:
        values: Sample.
        fraction: 0.95 for p95.

    Returns:
        Percentile, or ``None`` when empty.
    """

    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def parse_foreground_stdin(raw: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Parse worker stdin JSON into caller id and queries.

    Args:
        raw: JSON object with ``user_id`` and ``queries``.

    Returns:
        ``(user_id, ((case_id, query), ...))``.

    Raises:
        ValueError: If the payload is malformed.
    """

    loaded: object = json.loads(raw)
    payload = as_json_object(loaded, source="hybrid-foreground-stdin")
    user_id = payload.get("user_id")
    if not isinstance(user_id, str) or user_id == "":
        raise ValueError("hybrid foreground requires user_id")
    rows = as_json_list(payload.get("queries"), source="hybrid-foreground-stdin.queries")
    queries: list[tuple[str, str]] = []
    for item in rows:
        row = as_json_object(item, source="hybrid-foreground-stdin.queries[]")
        case_id = row.get("case_id")
        query = row.get("query")
        if not isinstance(case_id, str) or not isinstance(query, str):
            raise ValueError("hybrid foreground query row is invalid")
        queries.append((case_id, query))
    if not queries:
        raise ValueError("hybrid foreground queries are empty")
    return user_id, tuple(queries)


def main() -> int:
    """CLI entry used inside the frozen worker via ``/tmp`` injection.

    Returns:
        Process exit code.
    """

    supabase_url = os.environ.get("SUPABASE_DB_URL")
    parade_url = os.environ.get("PARADEDB_URL")
    if not supabase_url or not parade_url:
        sys.stderr.write("SUPABASE_DB_URL and PARADEDB_URL are required\n")
        return 2
    try:
        user_id, queries = parse_foreground_stdin(sys.stdin.read())
        payload = run_hybrid_foreground(
            supabase_url=supabase_url,
            parade_url=parade_url,
            user_id=user_id,
            queries=queries,
        )
    except (ValueError, json.JSONDecodeError, OSError, psycopg.Error) as exc:
        sys.stderr.write(f"hybrid foreground failed: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    return 0 if payload.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
