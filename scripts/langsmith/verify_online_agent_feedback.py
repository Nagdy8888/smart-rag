#!/usr/bin/env python3
"""Poll dedicated online-evaluation roots until hosted feedback lands.

Reads only the bounded evaluator/run endpoints. Does not emit new traces
to hide failures. Prints a secret-free JSON summary.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, TextIO, cast

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from smart_rag_core.evaluation.online import (  # noqa: E402
    ONLINE_EVAL_PROJECT,
    QUERY_AGENT_ONLINE_EVAL_RUN,
)
from smart_rag_core.evaluation.online_provision import (  # noqa: E402
    parse_cli_json,
)
from smart_rag_core.settings import setdefault_process_environ  # noqa: E402

DETERMINISTIC_KEYS = (
    "route_correct",
    "refusal_correct",
    "citation_precision",
    "citation_recall",
    "acl_leak_free",
    "profile_fields_correct",
    "bounds_respected",
    "answer_reference_overlap",
    "target_completed",
)
JUDGE_KEYS = ("correctness", "groundedness", "refusal_quality")


class VerifyCliError(RuntimeError):
    """Feedback verification failed closed. Message is a stable token."""


def load_repo_env() -> None:
    """Fill missing process env from repo ``.env`` without overriding exports.

    Side Effects:
        Reads ``.env`` with ``setdefault``. Values are not logged.
    """

    path = _ROOT / ".env"
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
    """Parse verification flags.

    Args:
        argv: Argument vector excluding the program name.

    Returns:
        Parsed namespace.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Poll smart-rag-agent-eval-online roots for hosted feedback. "
            "Does not emit traces."
        )
    )
    parser.add_argument("--profile", default=None, help="LangSmith CLI profile.")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="Documented poll timeout. Default 600.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=15,
        help="Poll interval. Default 15.",
    )
    parser.add_argument(
        "--expected-roots",
        type=int,
        default=20,
        help="Expected dedicated root count. Default 20.",
    )
    return parser.parse_args(argv)


def print_json(payload: dict[str, object], *, stream: TextIO = sys.stdout) -> None:
    """Write a secret-free JSON object.

    Args:
        payload: JSON-compatible mapping.
        stream: Output stream.
    """

    stream.write(json.dumps(payload, indent=2, sort_keys=True))
    stream.write("\n")


def _cli(args: list[str]) -> Any:
    """Run one authenticated CLI command.

    Args:
        args: Argument vector including ``langsmith``.

    Returns:
        Parsed JSON payload.

    Raises:
        VerifyCliError: Non-zero exit.
    """

    import subprocess

    completed = subprocess.run(  # noqa: S603
        args,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise VerifyCliError("langsmith_feedback_query_failed")
    return parse_cli_json(completed.stdout)


def _run_feedback_keys(run: dict[str, Any]) -> set[str]:
    """Collect feedback keys on one run.

    Args:
        run: LangSmith run JSON.

    Returns:
        Feedback key names.
    """

    keys: set[str] = set()
    feedback: object = run.get("feedback_stats")
    if feedback is None:
        feedback = run.get("feedback")
    if feedback is None:
        feedback = []
    if isinstance(feedback, dict):
        typed = cast(dict[object, object], feedback)
        keys.update(str(key) for key in typed)
        return keys
    if isinstance(feedback, list):
        for item in cast(list[object], feedback):
            if isinstance(item, dict):
                record = {
                    str(key): value
                    for key, value in cast(dict[object, object], item).items()
                }
                key = record.get("key") or record.get("feedback_key")
                if key:
                    keys.add(str(key))
    return keys


def main(argv: list[str] | None = None) -> int:
    """Poll until every dedicated root has deterministic and judge keys.

    Args:
        argv: Optional CLI arguments excluding the program name.

    Returns:
        ``0`` when every expected root has complete feedback. ``2`` on
        timeout or CLI failure.
    """

    args = parse_args(argv)
    load_repo_env()
    prefix = ["langsmith"]
    if args.profile:
        prefix.extend(["--profile", args.profile])
    deadline = time.monotonic() + max(1, args.timeout_seconds)
    last_complete = 0
    last_count = 0
    try:
        while time.monotonic() < deadline:
            payload = _cli(
                [
                    *prefix,
                    "run",
                    "list",
                    "--project",
                    ONLINE_EVAL_PROJECT,
                    "--name",
                    QUERY_AGENT_ONLINE_EVAL_RUN,
                    "--include-feedback",
                    "--format",
                    "json",
                    "--limit",
                    str(max(args.expected_roots, 1)),
                ]
            )
            runs: list[object] = []
            if isinstance(payload, list):
                runs = list(cast(list[object], payload))
            elif isinstance(payload, dict):
                typed = cast(dict[str, Any], payload)
                items = typed.get("runs")
                if items is None:
                    items = typed.get("items")
                if isinstance(items, list):
                    runs = list(cast(list[object], items))
            roots: list[dict[str, Any]] = []
            for item in runs:
                if not isinstance(item, dict):
                    continue
                record = {
                    str(key): value
                    for key, value in cast(dict[object, object], item).items()
                }
                if str(record.get("name")) == QUERY_AGENT_ONLINE_EVAL_RUN:
                    roots.append(record)
            complete = 0
            for run in roots:
                keys = _run_feedback_keys(run)
                if all(key in keys for key in DETERMINISTIC_KEYS) and any(
                    key in keys for key in JUDGE_KEYS
                ):
                    complete += 1
            last_complete = complete
            last_count = len(roots)
            if complete >= args.expected_roots and last_count >= args.expected_roots:
                print_json(
                    {
                        "project": ONLINE_EVAL_PROJECT,
                        "root_run_name": QUERY_AGENT_ONLINE_EVAL_RUN,
                        "root_count": last_count,
                        "complete_feedback_count": complete,
                        "deterministic_keys": list(DETERMINISTIC_KEYS),
                        "judge_keys": list(JUDGE_KEYS),
                        "timed_out": False,
                    }
                )
                return 0
            time.sleep(max(1, args.interval_seconds))
        print_json(
            {
                "error": "online_feedback_timeout",
                "project": ONLINE_EVAL_PROJECT,
                "root_count": last_count,
                "complete_feedback_count": last_complete,
                "expected_roots": args.expected_roots,
                "timed_out": True,
            },
            stream=sys.stderr,
        )
        return 2
    except VerifyCliError as exc:
        print_json({"error": str(exc)}, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
