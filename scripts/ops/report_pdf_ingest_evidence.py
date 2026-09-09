"""Print count-only Packet 14 ingest evidence. Never prints source text."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ops.ingest_demo_plot_slices import (  # noqa: E402
    _merged_env,
    _require,
)

VERSION_ID = "4324c385-80fd-4464-9c97-a7568bf364db"
DOCUMENT_ID = "9c9fcbfe-d86b-4850-bc7f-94f0fcd8ccb2"
HYBRID_JOB_ID = "0998baed-df79-4538-8467-d55c60527b3e"
SCAN_JOB_ID = "029848c0-bc3b-4dbe-b7a8-195b97c699ec"


def _band(token_count: int) -> str:
    """Map a stored token count onto a reporting band.

    Args:
        token_count: Stored ``document_chunks.token_count``.

    Returns:
        Band label.
    """

    if token_count < 200:
        return "under_200"
    if token_count <= 400:
        return "200_400"
    if token_count <= 600:
        return "401_600"
    return "over_600"


def main() -> int:
    """Query hosted counts and print JSON without text fields.

    Returns:
        Process exit code.
    """

    env = _merged_env()
    url = _require(env, "OPERATOR_SUPABASE_DB_URL")
    with psycopg.connect(url, connect_timeout=20) as connection:
        connection.execute("SET ROLE postgres")
        version = connection.execute(
            """
            SELECT status::text, graph_eligible, is_current,
                   embedding_model, chunk_set_hash IS NOT NULL
            FROM app.document_versions
            WHERE id = %s::uuid
            """,
            (VERSION_ID,),
        ).fetchone()
        document = connection.execute(
            "SELECT graph_eligible FROM app.documents WHERE id = %s::uuid",
            (DOCUMENT_ID,),
        ).fetchone()
        jobs = connection.execute(
            """
            SELECT id::text, job_kind::text, status::text, attempt_count,
                   coalesce(payload_ref ->> 'content_class', 'real_company')
            FROM app.ingestion_jobs
            WHERE version_id = %s::uuid
            ORDER BY created_at
            """,
            (VERSION_ID,),
        ).fetchall()
        chunk_rows = connection.execute(
            """
            SELECT token_count, is_search_representative, embedding IS NOT NULL
            FROM app.document_chunks
            WHERE version_id = %s::uuid
            """,
            (VERSION_ID,),
        ).fetchall()
        bm25 = connection.execute(
            """
            SELECT id::text, status::text, operation::text
            FROM app.bm25_index_jobs
            WHERE version_id = %s::uuid
            ORDER BY created_at
            """,
            (VERSION_ID,),
        ).fetchall()
        ledger = connection.execute(
            """
            SELECT status, input_count, actual_usd, result_ref
            FROM app.embedding_operation_ledger
            WHERE version_id = %s::uuid
            ORDER BY created_at
            """,
            (VERSION_ID,),
        ).fetchall()
        try:
            lightrag = connection.execute(
                """
                SELECT count(*)
                FROM app.lightrag_index_jobs
                WHERE version_id = %s::uuid
                """,
                (VERSION_ID,),
            ).fetchone()
            lightrag_count = int(lightrag[0]) if lightrag else 0
        except psycopg.Error:
            connection.rollback()
            connection.execute("SET ROLE postgres")
            lightrag_count = -1
    bands = Counter(_band(int(row[0])) for row in chunk_rows)
    embedded = sum(1 for row in chunk_rows if row[2] is True)
    representatives = sum(1 for row in chunk_rows if row[1] is True)
    ledger_payload: list[dict[str, object]] = []
    for row in ledger:
        result_ref = row[3] if isinstance(row[3], dict) else {}
        ledger_payload.append(
            {
                "status": row[0],
                "input_count": row[1],
                "actual_usd": str(row[2]) if row[2] is not None else None,
                "vectors_inline": result_ref.get("vectors_inline")
                if isinstance(result_ref, dict)
                else None,
                "vector_count": result_ref.get("vector_count")
                if isinstance(result_ref, dict)
                else None,
            }
        )
    print(
        json.dumps(
            {
                "document_id": DOCUMENT_ID,
                "version_id": VERSION_ID,
                "scan_job_id": SCAN_JOB_ID,
                "hybrid_job_id": HYBRID_JOB_ID,
                "version_status": version[0] if version else None,
                "version_graph_eligible": bool(version[1]) if version else None,
                "is_current": bool(version[2]) if version else None,
                "embedding_model": version[3] if version else None,
                "chunk_set_hash_set": bool(version[4]) if version else None,
                "document_graph_eligible": bool(document[0]) if document else None,
                "jobs": [
                    {
                        "id": row[0],
                        "kind": row[1],
                        "status": row[2],
                        "attempts": row[3],
                        "content_class": row[4],
                    }
                    for row in jobs
                ],
                "chunk_count": len(chunk_rows),
                "embedded_chunks": embedded,
                "search_representatives": representatives,
                "token_bands": dict(bands),
                "bm25_jobs": [
                    {"id": row[0], "status": row[1], "operation": row[2]}
                    for row in bm25
                ],
                "embedding_ledger": ledger_payload,
                "lightrag_index_jobs": lightrag_count,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
