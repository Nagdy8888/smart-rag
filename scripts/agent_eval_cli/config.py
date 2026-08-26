"""Argument parsing and static configuration for the agent-eval CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from smart_rag_core.settings import setdefault_process_environ

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SIDECAR = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "evaluation"
    / "phase4"
    / "runtime"
    / "gold_id_map.json"
)
DEFAULT_PARADE_PORT = "54329"
EXPERIMENT_NAMESPACE = uuid5(NAMESPACE_URL, "smart-rag-agent-eval")


class AgentEvalCliError(RuntimeError):
    """CLI preflight failure. The message is a stable token without secrets."""


def load_repo_env() -> None:
    """Fill missing process env from repo ``.env`` without overriding exports.

    Side Effects:
        Reads ``.env`` with ``setdefault``. Values are not logged.
    """

    path = REPO_ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        name = key.strip()
        if not name:
            continue
        setdefault_process_environ(name, value.strip().strip('"').strip("'"))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse bounded agent-eval CLI flags.

    Args:
        argv: Argument vector excluding the program name.

    Returns:
        Parsed namespace.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Bounded LangSmith agent evaluation on synthetic development cases. "
            "Holdout stays sealed. Not a quality claim."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate selection and print the plan. No writes or provider calls.",
    )
    parser.add_argument(
        "--online-only",
        action="store_true",
        help=(
            "Emit dedicated online-evaluation traces. Does not create a "
            "dataset or experiment. Uses the frozen representative suite."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum development cases (1..20). Default 3 for the offline "
            "path and the full frozen suite for --online-only."
        ),
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        dest="case_ids",
        help="Repeatable development case id. Qualification/holdout ids fail closed.",
    )
    parser.add_argument(
        "--class",
        action="append",
        default=[],
        dest="query_classes",
        help="Repeatable query-class filter. Unsupported classes fail closed.",
    )
    parser.add_argument(
        "--live-agent",
        action="store_true",
        help="Allow MOCK_MODEL_MODE=false. Required for --llm-judge.",
    )
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="One bounded judge call per case. Requires --live-agent.",
    )
    parser.add_argument(
        "--max-usd",
        default="2.00",
        help="Job USD ceiling. Default 2.00. Values below 0 or above 2.00 fail.",
    )
    parser.add_argument(
        "--allow-bm25-degraded",
        action="store_true",
        help="Permit dense+term fallback when ParadeDB is unavailable.",
    )
    parser.add_argument(
        "--experiment-prefix",
        default=None,
        help="Optional sanitized experiment suffix (alnum, hyphen, underscore).",
    )
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=DEFAULT_SIDECAR,
        help="Phase 4 gold-id sidecar path. Live runs fail if unmapped.",
    )
    return parser.parse_args(argv)
