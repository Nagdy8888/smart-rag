"""Generate foundation OpenAPI and fail on unexpected route drift.

Phase 1 only exposes liveness/readiness health routes. This check regenerates
the committed snapshot and compares; it does not invent later-phase APIs.
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
    allowed = {"/health/live", "/health/ready"}
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
