"""Unit tests for the Pyright error-count ratchet."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check import FAST_TIERS, CheckRunner
from scripts.ci.check_pyright_baseline import (
    error_count_from_report,
    format_ratchet_message,
    load_baseline_error_count,
    main,
    ratchet_exit_code,
    require_non_negative_int,
)


def _write_baseline(path: Path, error_count: int) -> None:
    """Write a schema-v1 baseline file for ratchet tests.

    Args:
        path: Destination JSON path.
        error_count: Recorded error count.
    """

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "measured_at": "2026-08-16",
                "error_count": error_count,
            }
        ),
        encoding="utf-8",
    )


def _write_report(path: Path, error_count: int) -> None:
    """Write a minimal ``pyright --outputjson`` summary for ratchet tests.

    Args:
        path: Destination JSON path.
        error_count: Reported ``summary.errorCount``.
    """

    path.write_text(
        json.dumps(
            {
                "summary": {
                    "filesAnalyzed": 1,
                    "errorCount": error_count,
                    "warningCount": 0,
                    "informationCount": 0,
                },
                "generalDiagnostics": [],
            }
        ),
        encoding="utf-8",
    )


def test_ratchet_fails_when_error_count_exceeds_baseline() -> None:
    """An increase above the recorded baseline must fail the ratchet."""

    assert ratchet_exit_code(current_errors=883, baseline_errors=882) == 1


def test_ratchet_passes_at_baseline_without_waiving_types_debt() -> None:
    """Matching the baseline is not a types-tier pass while errors remain."""

    assert ratchet_exit_code(current_errors=882, baseline_errors=882) == 0
    message = format_ratchet_message(
        current_errors=882,
        baseline_errors=882,
        exit_code=0,
    )
    assert "Types stay red until the count is 0" in message


def test_ratchet_allows_a_lower_count_and_asks_to_update_baseline() -> None:
    """A decrease must not fail, and must tell the caller to lower the JSON."""

    assert ratchet_exit_code(current_errors=800, baseline_errors=882) == 0
    message = format_ratchet_message(
        current_errors=800,
        baseline_errors=882,
        exit_code=0,
    )
    assert "Count decreased" in message


def test_main_fails_on_regression(tmp_path: Path) -> None:
    """``main`` must return 1 when the report exceeds the baseline file."""

    baseline = tmp_path / "baseline.json"
    report = tmp_path / "report.json"
    _write_baseline(baseline, 882)
    _write_report(report, 900)

    result = main(
        [
            "--baseline-path",
            str(baseline),
            "--report-path",
            str(report),
        ]
    )

    assert result == 1


def test_main_succeeds_at_baseline(tmp_path: Path) -> None:
    """``main`` returns 0 at the recorded count so Pyright can still fail."""

    baseline = tmp_path / "baseline.json"
    report = tmp_path / "report.json"
    _write_baseline(baseline, 882)
    _write_report(report, 882)

    result = main(
        [
            "--baseline-path",
            str(baseline),
            "--report-path",
            str(report),
        ]
    )

    assert result == 0


def test_load_baseline_rejects_bool_error_count(tmp_path: Path) -> None:
    """JSON ``true`` must not count as an integer error budget."""

    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps({"schema_version": 1, "error_count": True}),
        encoding="utf-8",
    )

    try:
        load_baseline_error_count(path)
    except ValueError as error:
        assert "error_count" in str(error)
    else:
        raise AssertionError("bool error_count must be rejected")


def test_error_count_from_report_reads_summary() -> None:
    """The ratchet must trust Pyright's summary.errorCount field."""

    count = error_count_from_report({"summary": {"errorCount": 12}})

    assert count == 12


def test_require_non_negative_int_rejects_bool() -> None:
    """``bool`` is a subclass of ``int`` and must not pass the ratchet."""

    try:
        require_non_negative_int(True, "error_count")
    except ValueError:
        return
    raise AssertionError("bool values must be rejected")


def test_types_tier_keeps_direct_pyright_and_stays_in_fast() -> None:
    """Types must remain a real Pyright invocation inside FAST_TIERS."""

    commands = CheckRunner(Path(".")).commands_for_tier("types")
    argument_lists = [command.arguments for command in commands]

    assert "types" in FAST_TIERS
    assert any(args[-2:] == ("-m", "pyright") for args in argument_lists)
    assert any(
        args[-1].replace("\\", "/").endswith("scripts/ci/check_pyright_baseline.py")
        for args in argument_lists
    )
