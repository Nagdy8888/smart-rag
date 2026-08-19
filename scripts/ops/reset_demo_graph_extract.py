"""Reset the failed demo graph extract and requeue the LightRAG job.

Does not upload files and does not print secrets. Stop the laptop worker
before running so it cannot race the vendor-row delete.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ops.ingest_demo_plot_slices import (  # noqa: E402
    merged_env,
    require_env,
    reset_failed_graph_extract,
)

GRAPH_LIGHTRAG_JOB_ID = "542628df-2c38-4b15-a180-893d7fd74998"
GRAPH_VERSION_ID = "c9b7a989-d575-4346-be92-2537f01fa7c8"


def main() -> int:
    """Clear failed vendor rows and requeue the graph-200 LightRAG job.

    Returns:
        Process exit code.
    """

    env = merged_env()
    operator_url = require_env(env, "OPERATOR_SUPABASE_DB_URL")
    snapshot = reset_failed_graph_extract(
        operator_url=operator_url,
        job_id=GRAPH_LIGHTRAG_JOB_ID,
        version_id=GRAPH_VERSION_ID,
    )
    print(json.dumps(snapshot, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
