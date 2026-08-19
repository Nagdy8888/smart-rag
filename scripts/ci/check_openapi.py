"""Generate the public OpenAPI snapshot and fail on unexpected route drift.

Additive later-phase routes must be listed explicitly. This check regenerates
the committed snapshot and compares; it does not invent undeclared APIs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "docs" / "api" / "openapi.foundation.json"


def main() -> int:
    """Regenerate and compare the foundation OpenAPI snapshot.

    Returns:
        ``0`` when the snapshot matches the running app schema, else ``1``.
    """

    sys.path.insert(0, str(ROOT / "apps" / "backend" / "src"))
    from smart_rag_api.main import app

    schema = app.openapi()
    paths = sorted(schema.get("paths", {}))
    allowed = {
        "/health/live",
        "/health/ready",
        "/api/meta",
        "/me",
        "/admin/invitations",
        "/invitations/accept",
        "/admin/users/{user_id}/offboard",
        "/documents",
        "/documents/{document_id}",
        "/documents/uploads",
        "/documents/uploads/finalize",
        "/conversations",
        "/conversations/{conversation_id}",
        "/conversations/{conversation_id}/messages",
        "/runs/{run_id}",
        "/runs/{run_id}/cancel",
        "/runs/{run_id}/citations",
        "/runs/{run_id}/events",
        "/runs/{run_id}/feedback",
        "/ingestion/crawls",
        "/ingestion/jobs/{job_id}/retry",
        "/ingestion/versions/{version_id}/status",
        "/admin/glossary/imports",
        "/admin/glossary/imports/{import_id}/approve",
        "/admin/glossary/imports/{import_id}/rollback",
        "/admin/graph/entity-rules",
        "/admin/graph/entity-rules/suggestions",
        "/admin/graph/entity-rules/{rule_id}",
        "/admin/graph/entity-rules/{rule_id}/approve",
        "/admin/graph/entity-rules/{rule_id}/revoke",
        "/graph/inspect",
        "/graph/entities/search",
        "/tables",
        "/tables/analyze",
        "/tools",
        "/admin/tools",
        "/admin/tools/{tool_key}/enable",
        "/admin/tools/{tool_key}/permissions",
        "/usage/me",
        "/usage/company",
        "/ops/ready",
    }
    unexpected = [path for path in paths if path not in allowed]
    if unexpected:
        print(f"unexpected foundation paths: {unexpected}", file=sys.stderr)
        return 1
    missing = sorted(allowed - set(paths))
    if missing:
        print(f"missing foundation paths: {missing}", file=sys.stderr)
        return 1

    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    if not SNAPSHOT.exists():
        SNAPSHOT.write_text(rendered, encoding="utf-8")
        print(f"wrote new snapshot {SNAPSHOT}")
        return 0
    current = SNAPSHOT.read_text(encoding="utf-8")
    if current != rendered:
        SNAPSHOT.write_text(rendered, encoding="utf-8")
        print(
            "openapi.foundation.json drifted; snapshot updated — re-run and commit",
            file=sys.stderr,
        )
        return 1
    print("openapi foundation snapshot matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
