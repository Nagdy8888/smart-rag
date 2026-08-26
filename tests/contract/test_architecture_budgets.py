"""Contract tests for query-vertical architecture budgets."""

from __future__ import annotations

from pathlib import Path

from tests.contract.architecture_scanner import (
    HARD_LINE_CAP,
    is_compatibility_facade,
    scan_architecture,
    scan_doc_line_targets,
    scan_line_targets,
    scan_test_line_targets,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_query_vertical_hard_architecture_rules() -> None:
    """Line caps, node responsibility, cycle guards, and test imports hold."""

    findings = scan_architecture(REPO_ROOT)
    assert findings == [], "Architecture hard rules failed:\n" + "\n".join(
        item.format() for item in findings
    )


def test_compatibility_facade_detector_accepts_reexports_only() -> None:
    """A module of imports and ``__all__`` is a compatibility facade."""

    source = (
        '"""Facade."""\n'
        "from smart_rag_core.query_admission.envelopes import RouteCeiling\n"
        "__all__ = ['RouteCeiling']\n"
    )
    assert is_compatibility_facade(source) is True
    assert (
        is_compatibility_facade('"""Runtime."""\n\ndef run() -> None:\n    return\n')
        is False
    )


def test_hard_cap_constant_is_six_hundred() -> None:
    """The authored runtime safety cap stays at 600 physical lines."""

    assert HARD_LINE_CAP == 600


def test_target_overruns_are_reported_not_hard_failed() -> None:
    """400-line and 500-line targets remain visible during packet 9."""

    line_targets = scan_line_targets(REPO_ROOT)
    test_targets = scan_test_line_targets(REPO_ROOT)
    doc_targets = scan_doc_line_targets(REPO_ROOT)
    assert isinstance(line_targets, list)
    assert isinstance(test_targets, list)
    assert isinstance(doc_targets, list)
