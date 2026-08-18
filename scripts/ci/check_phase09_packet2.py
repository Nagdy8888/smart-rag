"""Fail when Phase 9 Packet 2 mandatory local tests collect zero cases or skip."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

from smart_rag_core.release.constants import ARTIFACT_DIR
from smart_rag_core.release.io import (
    as_json_list,
    as_json_object,
    dump_canonical_json,
    load_json_object,
)
from smart_rag_core.release.old_api_smoke import (
    apply_outcome_to_handoff_row,
    evaluate_old_api_new_schema_smoke,
)
from smart_rag_core.release.packet2 import (
    PACKET2_ARTIFACT_NAME,
    PYTEST_SUITES,
    Packet2Mode,
    Packet2Suite,
    Phase09Packet2GateError,
    assert_holdout_sealed,
    classify_suite_counts,
    executed_suite_payload,
    handoff_payloads,
    junit_counts,
    load_packet1_image_ids,
    merge_suite_rows,
    missing_pytest_files,
    not_run_suite_payload,
    pytest_command,
    schema_version,
    suite_failure_detail,
    suites_for_mode,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / ARTIFACT_DIR / PACKET2_ARTIFACT_NAME


def _run_suite(suite: Packet2Suite) -> dict[str, object]:
    """Execute one fail-closed pytest suite and return its matrix row.

    Args:
        suite: Suite to run.

    Returns:
        JSON-object suite row.

    Raises:
        Phase09Packet2GateError: If JUnit output is missing.

    Side Effects:
        Runs pytest from the repository root.
    """

    with tempfile.TemporaryDirectory(prefix="smart-rag-phase09-p2-") as directory:
        report = Path(directory) / "junit.xml"
        completed = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "pytest", *pytest_command(suite, report)],
            cwd=REPO_ROOT,
            check=False,
        )
        counts = junit_counts(report)
    classification = classify_suite_counts(
        counts,
        returncode=completed.returncode,
        fail_on_skip=suite.fail_on_skip,
    )
    detail = suite_failure_detail(
        counts,
        returncode=completed.returncode,
        fail_on_skip=suite.fail_on_skip,
    )
    print(
        f"phase09_packet2_{suite.suite_id} "
        f"tests={counts.tests} failures={counts.failures} "
        f"errors={counts.errors} skipped={counts.skipped} "
        f"classification={classification}"
    )
    return executed_suite_payload(
        suite,
        counts,
        returncode=completed.returncode,
        classification=classification,
        detail=detail,
    )


def _mode_rows(
    mode: Packet2Mode,
    *,
    emit_unselected: bool,
) -> tuple[list[dict[str, object]], list[str]]:
    """Run selected suites and optionally emit Not Run rows for the others.

    Args:
        mode: Execution mode.
        emit_unselected: When true, unselected suites are recorded as Not Run.
            Merge runs omit those rows so a later overlay pass cannot clobber
            candidate results.

    Returns:
        Suite rows and fail-closed reasons for executed suites that did not pass.
    """

    selected = {suite.suite_id for suite in suites_for_mode(mode)}
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    for suite in PYTEST_SUITES:
        if suite.suite_id not in selected:
            if emit_unselected:
                detail = (
                    "overlay host ports required; run after attaching "
                    "docker-compose.packet8.yml, then detach candidate compose"
                    if suite.overlay_required
                    else f"not selected in mode={mode}"
                )
                rows.append(not_run_suite_payload(suite, detail=detail))
            continue
        row = _run_suite(suite)
        rows.append(row)
        if row["classification"] != "Passed":
            failures.append(f"{suite.suite_id}: {row['detail']}")
    return rows, failures


def _write_artifact(
    *,
    mode: Packet2Mode,
    image_ids: dict[str, str],
    suite_rows: list[dict[str, object]],
    merge: bool,
    handoffs: list[dict[str, object]] | None = None,
) -> None:
    """Write or merge the Packet 2 gate matrix artifact.

    Args:
        mode: Execution mode recorded on this write.
        image_ids: Packet 1 service image Ids.
        suite_rows: Suite rows from this run.
        merge: When true, replace matching ``suite_id`` rows in an existing file.
        handoffs: Optional overlaid handoff rows. Default static Packet 2
            handoffs.

    Side Effects:
        Overwrites ``docs/deployment/phase-09/candidate-packet2-gate-matrix.json``.
    """

    existing_suites: list[dict[str, object]] = []
    existing_commands: list[object] = []
    if merge and ARTIFACT_PATH.is_file():
        previous = load_json_object(ARTIFACT_PATH)
        existing_suites = [
            as_json_object(item, source="packet2.suites[]")
            for item in as_json_list(previous.get("suites"), source="packet2.suites")
        ]
        raw_commands = previous.get("commands")
        if raw_commands is not None:
            existing_commands = as_json_list(raw_commands, source="packet2.commands")
    suites = merge_suite_rows(existing_suites, suite_rows)
    payload: dict[str, object] = {
        "schema_version": schema_version(),
        "requirement_id": "P09-02",
        "mode": mode,
        "holdout_opened": False,
        "compose_file": "docker-compose.yml",
        "overlay_file_is_candidate": False,
        "candidate_image_ids": image_ids,
        "suites": suites,
        "handoffs": handoffs if handoffs is not None else handoff_payloads(),
        "commands": existing_commands,
    }
    dump_canonical_json(payload, ARTIFACT_PATH)


def parse_mode(value: str) -> Packet2Mode:
    """Validate the Packet 2 execution mode.

    Args:
        value: CLI mode string.

    Returns:
        Typed mode.

    Raises:
        ValueError: If the mode is unknown.
    """

    if value == "candidate":
        return "candidate"
    if value == "overlay":
        return "overlay"
    if value == "all":
        return "all"
    raise ValueError(f"unknown Packet 2 mode: {value}")


def main(argv: list[str] | None = None) -> int:
    """Run Packet 2 pytest suites and reject zero collection or required skips.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        ``0`` when selected suites collected tests and none failed.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        default="candidate",
        choices=("candidate", "overlay", "all"),
        help=(
            "candidate uses unpublished ParadeDB via compose exec; overlay "
            "requires docker-compose.packet8.yml already attached."
        ),
    )
    parser.add_argument(
        "--merge-artifact",
        action="store_true",
        help="Merge suite rows into the existing Packet 2 matrix artifact.",
    )
    parsed = parser.parse_args(argv)
    mode = parse_mode(cast(str, parsed.mode))
    try:
        missing = missing_pytest_files(REPO_ROOT)
        if missing:
            raise Phase09Packet2GateError(
                "Packet 2 mapped tests are missing: " + ", ".join(missing)
            )
        image_ids = load_packet1_image_ids(REPO_ROOT)
        assert_holdout_sealed(REPO_ROOT)
        merge = bool(parsed.merge_artifact)
        rows, failures = _mode_rows(mode, emit_unselected=not merge)
        smoke = evaluate_old_api_new_schema_smoke(
            REPO_ROOT,
            freeze_api_id=image_ids["api"],
            run_live=not failures,
        )
        handoffs = [
            apply_outcome_to_handoff_row(row, smoke)
            if row.get("item_id") == "old_api_new_schema_smoke"
            else row
            for row in handoff_payloads()
        ]
        _write_artifact(
            mode=mode,
            image_ids=image_ids,
            suite_rows=rows,
            merge=merge,
            handoffs=handoffs,
        )
        print(f"wrote {ARTIFACT_PATH.relative_to(REPO_ROOT)}")
        print(
            "old_api_new_schema_smoke "
            f"classification={smoke.classification} "
            f"smoke_ran={smoke.smoke_ran}"
        )
        if failures:
            raise Phase09Packet2GateError("; ".join(failures))
        if smoke.classification == "Failed":
            raise Phase09Packet2GateError(smoke.reason)
    except Phase09Packet2GateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
