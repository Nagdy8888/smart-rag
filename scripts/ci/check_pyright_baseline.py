#!/usr/bin/env python3
"""Fail when full-repo Pyright errors exceed the recorded baseline.

This ratchet is not a types-tier waiver. A count at or below the baseline
still leaves ``python -m pyright`` red until the error count is zero. Do
not raise the baseline to hide new errors. Do not use ``|| true``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = REPO_ROOT / "scripts" / "ci" / "pyright_baseline.json"


@dataclass(frozen=True)
class RatchetOptions:
    """Command-line options for the Pyright error-count ratchet.

    Attributes:
        baseline_path: JSON file that stores the recorded error count.
        report_path: Optional precomputed ``pyright --outputjson`` payload.
            When omitted, this script invokes ``python -m pyright``.
    """

    baseline_path: Path
    report_path: Path | None


def parse_options(argv: Sequence[str] | None = None) -> RatchetOptions:
    """Parse baseline and optional report paths.

    Args:
        argv: Argument sequence excluding the program name.

    Returns:
        Validated ratchet options rooted at this repository.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-path",
        default=str(DEFAULT_BASELINE),
        help="Machine-readable baseline JSON with error_count.",
    )
    parser.add_argument(
        "--report-path",
        help="Existing pyright --outputjson file. Omit to invoke pyright.",
    )
    parsed = parser.parse_args(argv)
    report_raw = cast(str | None, parsed.report_path)
    return RatchetOptions(
        baseline_path=Path(cast(str, parsed.baseline_path)).resolve(),
        report_path=Path(report_raw).resolve() if report_raw else None,
    )


def read_json_object(path: Path) -> dict[str, object]:
    """Load one JSON object from UTF-8 or UTF-16 text.

    Args:
        path: File containing a JSON object, optionally with a leading BOM
            or Windows UTF-16 encoding from PowerShell redirection.

    Returns:
        Parsed JSON object.

    Raises:
        ValueError: If the file is missing, not an object, or not JSON.
        OSError: If the file cannot be read.
    """

    if not path.is_file():
        raise ValueError(f"JSON file is missing: {path}")
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    return parse_json_object(text)


def parse_json_object(payload: str) -> dict[str, object]:
    """Parse a JSON object, skipping any leading non-JSON stdout.

    Args:
        payload: File or process stdout that contains a JSON object.

    Returns:
        Parsed JSON object.

    Raises:
        ValueError: If no JSON object is present or the root is not an object.
    """

    start = payload.find("{")
    if start < 0:
        raise ValueError("payload does not contain a JSON object")
    loaded = json.loads(payload[start:])
    if not isinstance(loaded, dict):
        raise ValueError("JSON root must be an object")
    return cast(dict[str, object], loaded)


def as_object_map(value: object, field: str) -> dict[str, object]:
    """Return ``value`` as a string-keyed JSON object.

    Args:
        value: Parsed JSON value.
        field: Field name used in error messages.

    Returns:
        A ``dict`` with string keys.

    Raises:
        ValueError: If ``value`` is not an object.
    """

    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return cast(dict[str, object], value)


def require_non_negative_int(value: object, field: str) -> int:
    """Return ``value`` when it is a non-negative int, not a bool.

    Args:
        value: JSON value to validate.
        field: Field name used in error messages.

    Returns:
        The non-negative integer.

    Raises:
        ValueError: If ``value`` is a bool, not an int, or negative.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an int")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def load_baseline_error_count(path: Path) -> int:
    """Read the recorded Pyright error count.

    Args:
        path: Baseline JSON created with this repository's schema.

    Returns:
        Recorded ``error_count``.

    Raises:
        ValueError: If the baseline is missing required fields.
        OSError: If the file cannot be read.
    """

    baseline = read_json_object(path)
    version = baseline.get("schema_version")
    if version != 1:
        raise ValueError(f"{path} schema_version must be 1, got {version!r}")
    return require_non_negative_int(baseline.get("error_count"), "error_count")


def error_count_from_report(report: Mapping[str, object]) -> int:
    """Return Pyright's summary error count.

    Args:
        report: Parsed ``pyright --outputjson`` object.

    Returns:
        ``summary.errorCount``.

    Raises:
        ValueError: If the summary or error count is missing or invalid.
    """

    summary = as_object_map(report.get("summary"), "summary")
    return require_non_negative_int(summary.get("errorCount"), "summary.errorCount")


def ratchet_exit_code(*, current_errors: int, baseline_errors: int) -> int:
    """Return ``1`` when the current error count exceeds the baseline.

    A current count at or below the baseline is not a pass of the types
    tier. It only means the recorded debt did not grow.

    Args:
        current_errors: Error count from the current Pyright report.
        baseline_errors: Recorded baseline error count.

    Returns:
        ``1`` on regression, otherwise ``0``.

    Raises:
        ValueError: If either count is negative.
    """

    if current_errors < 0 or baseline_errors < 0:
        raise ValueError("error counts must be non-negative")
    if current_errors > baseline_errors:
        return 1
    return 0


def run_pyright_report(repo_root: Path) -> dict[str, object]:
    """Invoke ``python -m pyright --outputjson`` from the repository root.

    Args:
        repo_root: Workspace root that contains ``pyproject.toml``.

    Returns:
        Parsed Pyright JSON report.

    Raises:
        ValueError: If Pyright produced no JSON object.
        OSError: If the interpreter cannot launch Pyright.
    """

    completed = subprocess.run(
        (sys.executable, "-m", "pyright", "--outputjson"),
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    payload = completed.stdout.decode("utf-8-sig")
    if "{" not in payload:
        stderr = completed.stderr.decode("utf-8-sig", errors="replace")
        raise ValueError(
            "pyright --outputjson produced no JSON "
            f"(exit {completed.returncode}): {stderr.strip() or payload.strip()}"
        )
    return parse_json_object(payload)


def format_ratchet_message(
    *,
    current_errors: int,
    baseline_errors: int,
    exit_code: int,
) -> str:
    """Build the human-readable ratchet result.

    Args:
        current_errors: Error count from the current report.
        baseline_errors: Recorded baseline error count.
        exit_code: ``1`` on regression, otherwise ``0``.

    Returns:
        Message explaining count delta and that types stay red until zero.
    """

    if exit_code != 0:
        delta = current_errors - baseline_errors
        return (
            f"ERROR: Pyright error count rose from {baseline_errors} to "
            f"{current_errors} (+{delta}). The baseline is not a waiver; "
            "do not raise it to hide new errors. Types stay red until the "
            "count is 0. See docs/development/PYRIGHT_BASELINE.md and run "
            "`uv run pyright` for diagnostics."
        )
    if current_errors == 0:
        return (
            f"Pyright ratchet: 0 errors (baseline {baseline_errors}). "
            "Set scripts/ci/pyright_baseline.json error_count to 0 in the "
            "same change that lands a green types tier."
        )
    if current_errors < baseline_errors:
        return (
            f"Pyright ratchet: {current_errors} errors "
            f"(baseline {baseline_errors}). Count decreased; update "
            "scripts/ci/pyright_baseline.json and "
            "docs/development/PYRIGHT_BASELINE.md in the same change. "
            "Types stay red until the count is 0."
        )
    return (
        f"Pyright ratchet: {current_errors} errors "
        f"(baseline {baseline_errors}). No count regression. "
        "Types stay red until the count is 0. "
        "Next command runs python -m pyright."
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Compare the current Pyright error count to the recorded baseline.

    Args:
        argv: Argument sequence excluding the program name.

    Returns:
        ``0`` when the count did not increase; ``1`` on regression or
        invalid inputs. This is not a types-tier pass.

    Side Effects:
        Invokes Pyright when ``--report-path`` is omitted. Prints the
        comparison to stdout, or to stderr on failure.
    """

    options = parse_options(argv)
    try:
        baseline_errors = load_baseline_error_count(options.baseline_path)
        if options.report_path is None:
            report = run_pyright_report(REPO_ROOT)
        else:
            report = read_json_object(options.report_path)
        current_errors = error_count_from_report(report)
        exit_code = ratchet_exit_code(
            current_errors=current_errors,
            baseline_errors=baseline_errors,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    message = format_ratchet_message(
        current_errors=current_errors,
        baseline_errors=baseline_errors,
        exit_code=exit_code,
    )
    stream = sys.stderr if exit_code else sys.stdout
    print(message, file=stream)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
