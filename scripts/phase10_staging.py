#!/usr/bin/env python3
"""Thin Phase 10 Packet 1 CLI for inventory and IaC policy. Does not apply cloud."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from smart_rag_core.release.io import load_json_object
from smart_rag_core.release.phase10_constants import INTENDED_TOPOLOGY_FILE
from smart_rag_core.release.phase10_packet1 import (
    Phase10Packet1GateError,
    evaluate_packet1,
    probe_live_providers,
)
from smart_rag_core.release.phase10_topology import (
    Phase10TopologyError,
    assert_committed_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _cmd_inventory() -> int:
    """Print the committed intended topology without secrets.

    Returns:
        ``0`` when the inventory file exists.
    """

    payload = load_json_object(REPO_ROOT / INTENDED_TOPOLOGY_FILE)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_assert_iac() -> int:
    """Assert committed IaC/Compose/Caddy/inventory policy.

    Returns:
        ``0`` when policy Passed.

    Raises:
        Phase10TopologyError: When policy fails.
    """

    report = assert_committed_policy(REPO_ROOT)
    print(f"iac_policy passed={report.passed} sha256={report.iac_sha256}")
    for finding in report.findings:
        print(f"{finding.check} {'Passed' if finding.passed else 'Failed'}")
    return 0


def _cmd_classify() -> int:
    """Classify P10-01 without applying cloud resources.

    Returns:
        ``0`` when IaC policy Passed. Live Blocked is printed, not greened.
    """

    policy, live, rows = evaluate_packet1(REPO_ROOT)
    print(f"iac_policy passed={policy.passed}")
    print(f"live_apply {live.apply_state}: {live.apply_reason}")
    for row in rows:
        print(f"{row.check} {row.classification}")
    return 0


def _cmd_probe() -> int:
    """Print the live provider probe without logging in or applying.

    Returns:
        ``0`` after printing the probe.
    """

    live = probe_live_providers()
    print(
        json.dumps(
            {
                "terraform_installed": live.terraform_installed,
                "tofu_installed": live.tofu_installed,
                "aws_cli_installed": live.aws_cli_installed,
                "sts_ok": live.sts_ok,
                "sts_detail": live.sts_detail,
                "apply_state": live.apply_state,
                "apply_reason": live.apply_reason,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch inventory / assert-iac / classify / probe.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        Process exit code.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("inventory", "assert-iac", "classify", "probe"),
        help="Read-only Packet 1 command. Never applies Terraform.",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "inventory":
            return _cmd_inventory()
        if args.command == "assert-iac":
            return _cmd_assert_iac()
        if args.command == "classify":
            return _cmd_classify()
        return _cmd_probe()
    except (Phase10TopologyError, Phase10Packet1GateError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
