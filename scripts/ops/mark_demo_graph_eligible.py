"""Mark one demo plot version graph-eligible after promote.

Must run after ``current_version_id`` exists and before BM25
``finalize_hybrid_ready``. Restricted documents cannot be graph-eligible.
Uses the operator session DSN, not the API runtime DSN.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from uuid import UUID

import psycopg


def _require_operator_url() -> str:
    """Return the operator session URL from the environment.

    Returns:
        Postgres URL that can ``SET ROLE postgres`` for this one-shot.

    Raises:
        RuntimeError: When the variable is missing.
    """

    url = os.environ.get("OPERATOR_SUPABASE_DB_URL", "").strip()
    if not url:
        env_path = Path(__file__).resolve().parents[2] / ".env.compose"
        if env_path.is_file():
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line.startswith("OPERATOR_SUPABASE_DB_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not url:
        raise RuntimeError("OPERATOR_SUPABASE_DB_URL is required")
    return url


def mark_graph_eligible(*, document_id: UUID, timeout_seconds: float = 180.0) -> UUID:
    """Wait for a current version, then set document and version eligibility.

    Args:
        document_id: Uploaded graph-200 document.
        timeout_seconds: How long to wait for ``current_version_id``.

    Returns:
        The current version id that was marked eligible.

    Raises:
        RuntimeError: If the document is restricted, missing, or never
            promoted within the timeout.

    Side Effects:
        Updates ``app.documents.graph_eligible`` and
        ``app.document_versions.graph_eligible``. Does not enqueue LightRAG
        itself; Hybrid Ready finalize does that.
    """

    deadline = time.monotonic() + timeout_seconds
    url = _require_operator_url()
    version_id: UUID | None = None
    while time.monotonic() < deadline:
        with psycopg.connect(url) as connection:
            connection.execute("SET ROLE postgres")
            row = connection.execute(
                """
                SELECT visibility::text, current_version_id, deleted_at
                FROM app.documents
                WHERE id = %s
                """,
                (document_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("document_not_found")
            visibility, current_version_id, deleted_at = row
            if deleted_at is not None:
                raise RuntimeError("document_deleted")
            if visibility != "company_visible":
                raise RuntimeError("document_not_company_visible")
            if current_version_id is not None:
                version_id = UUID(str(current_version_id))
                connection.execute(
                    """
                    UPDATE app.documents
                    SET graph_eligible = true, updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (document_id,),
                )
                connection.execute(
                    """
                    UPDATE app.document_versions
                    SET graph_eligible = true, updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (version_id,),
                )
                connection.commit()
                return version_id
        time.sleep(2)
    raise RuntimeError("current_version_timeout")


def main(argv: list[str]) -> int:
    """CLI: ``mark_demo_graph_eligible.py <document_uuid>``.

    Args:
        argv: Command-line arguments after the script name.

    Returns:
        Process exit code.
    """

    if len(argv) != 1:
        print("usage: mark_demo_graph_eligible.py <document_uuid>", file=sys.stderr)
        return 2
    version_id = mark_graph_eligible(document_id=UUID(argv[0]))
    print(f"graph_eligible version={version_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
