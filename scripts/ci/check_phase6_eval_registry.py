"""Fail CI when a Phase 6 packet-7 eval category has no mapped command."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "core" / "src"))

from smart_rag_core.evaluation.holdout import HoldoutAccess  # noqa: E402
from smart_rag_core.evaluation.online import (  # noqa: E402
    ONLINE_EVAL_MOCK_DEFAULT,
    assert_online_eval_permitted,
)
from smart_rag_core.evaluation.phase6_registry import (  # noqa: E402
    missing_registry_categories,
    qt_eval_009_status,
)


def main() -> int:
    """Return 0 when the registry is complete and holdout stays sealed.

    Returns:
        ``0`` on success; ``1`` when a required category is unmapped, the
        holdout is open, or QT-EVAL-009 is incorrectly claimed proven.
    """

    missing = missing_registry_categories()
    if missing:
        print(f"unmapped Phase 6 eval categories: {list(missing)}", file=sys.stderr)
        return 1
    if HoldoutAccess.denied().allowed:
        print("holdout must remain HoldoutAccess.denied()", file=sys.stderr)
        return 1
    if qt_eval_009_status() != "unverified":
        print("QT-EVAL-009 must remain unverified", file=sys.stderr)
        return 1
    if ONLINE_EVAL_MOCK_DEFAULT is not True:
        print("online eval mock-mode default must be true", file=sys.stderr)
        return 1
    assert_online_eval_permitted(
        mock_mode=True,
        case_count=1,
        max_usd=__import__("decimal").Decimal("2.00"),
        holdout_access=HoldoutAccess.denied(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
