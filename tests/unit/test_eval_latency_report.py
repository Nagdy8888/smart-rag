"""Latency report math uses ids, timestamps, and counts only."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from scripts.eval_latency_report import (
    aggregate,
    compare_reports,
    main,
    percentile,
    run_metrics,
    summarize,
)

_T0 = datetime(2026, 9, 24, 12, 0, 0, tzinfo=UTC)


def _at(seconds: float) -> datetime:
    """Return a timestamp ``seconds`` after the fixed test origin.

    Args:
        seconds: Offset from ``_T0``.

    Returns:
        Timezone-aware timestamp.
    """

    return _T0 + timedelta(seconds=seconds)


def _event(event_type: str, seconds: float, **payload: str) -> dict[str, object]:
    """Build one run-event row as the report reads it.

    Args:
        event_type: SSE event type.
        seconds: ``created_at`` offset from ``_T0``.
        **payload: Payload keys.

    Returns:
        Event mapping.
    """

    return {
        "event_type": event_type,
        "created_at": _at(seconds),
        "payload": dict(payload),
    }


def test_percentile_uses_nearest_rank() -> None:
    """p90 of 1..10 is 9; empty input is 0.0; summaries round to 3 places."""

    values = [float(item) for item in range(1, 11)]
    assert percentile(values, 0.9) == 9.0
    assert percentile([], 0.9) == 0.0
    assert percentile([5.0], 0.9) == 5.0
    assert summarize([1.0, 2.0, 4.0]) == {
        "n": 3,
        "mean": 2.333,
        "median": 2.0,
        "p90": 4.0,
        "max": 4.0,
    }
    assert summarize([]) == {"n": 0}


def test_run_metrics_from_synthetic_events() -> None:
    """Stage, gap, tail, spacing, deadline, and usage numbers follow the doc."""

    events = [
        _event("schema", 0.0),
        _event("status", 1.0, stage="a", phase="started"),
        _event("status", 3.0, stage="a", phase="completed"),
        _event("status", 3.5, stage="b", phase="started"),
        _event("status", 7.5, stage="b", phase="completed"),
        _event("deadline", 8.0),
        _event("completed", 9.0),
    ]
    usage_rows: list[dict[str, object]] = [
        {
            "usage_kind": "rerank",
            "prompt_tokens": 12000,
            "completion_tokens": 700,
            "timeout_after_send": True,
        },
        {
            "usage_kind": "answer",
            "prompt_tokens": 3000,
            "completion_tokens": 400,
            "timeout_after_send": False,
        },
    ]
    metrics = run_metrics(
        run_row={
            "created_at": _at(-2.0),
            "started_at": _at(-1.0),
            "deadline_at": _at(49.0),
        },
        events=events,
        usage_rows=usage_rows,
        client_timing={"wall_seconds": 12.5, "post_seconds": 0.4},
        stage_row={
            "rerank_fallback": "timeout",
            "stage_timings_ms": {"rerank_ms": 8000.0, "bad": "x"},
        },
    )
    assert metrics["server_total_s"] == 9.0
    assert metrics["admission_to_first_event_s"] == 2.0
    assert metrics["deadline_budget_s"] == 50.0
    assert metrics["pre_first_stage_s"] == 1.0
    assert metrics["stage_seconds"] == {"a": 2.0, "b": 4.0}
    assert metrics["open_stage_seconds"] == {}
    assert metrics["node_gap_total_s"] == 0.5
    assert metrics["tail_s"] == 1.5
    assert metrics["event_count"] == 7
    assert metrics["event_spacing_median_s"] == 1.0
    assert metrics["terminal"] == "completed"
    assert metrics["deadline_exhausted"] is True
    assert metrics["rerank_timeout_after_send"] == 1
    assert metrics["usage"] == {
        "rerank": {"calls": 1, "prompt_tokens": 12000, "completion_tokens": 700},
        "answer": {"calls": 1, "prompt_tokens": 3000, "completion_tokens": 400},
    }
    assert metrics["rerank_fallback"] == "timeout"
    assert metrics["stage_timings_ms"] == {"rerank_ms": 8000.0}
    assert metrics["wall_seconds"] == 12.5
    assert metrics["post_seconds"] == 0.4
    assert metrics["first_frame_seconds"] is None


def test_run_metrics_reports_open_stage_until_terminal() -> None:
    """A stage without ``completed`` is open until the terminal event."""

    metrics = run_metrics(
        run_row={},
        events=[
            _event("schema", 0.0),
            _event("status", 1.0, stage="company_scope", phase="started"),
            _event("partial", 5.0, reason="deadline_exhausted"),
        ],
        usage_rows=[],
        client_timing={},
        stage_row={},
    )
    assert metrics["stage_seconds"] == {}
    assert metrics["open_stage_seconds"] == {"company_scope": 4.0}
    assert metrics["terminal"] == "partial"
    assert metrics["deadline_exhausted"] is True
    assert metrics["tail_s"] is None
    assert metrics["admission_to_first_event_s"] is None
    assert metrics["rerank_fallback"] == "unknown"


def test_run_metrics_ignores_payload_text() -> None:
    """Only stage, phase, reason, and code are read from payloads."""

    private_text = "PRIVATE-ANSWER-TEXT"
    metrics = run_metrics(
        run_row={},
        events=[
            {
                "event_type": "token_delta",
                "created_at": _at(0.0),
                "payload": {"delta": private_text, "text": private_text},
            },
            {
                "event_type": "completed",
                "created_at": _at(1.0),
                "payload": {"answer": private_text},
            },
        ],
        usage_rows=[],
        client_timing={},
        stage_row={},
    )
    assert private_text not in json.dumps(metrics, default=str)
    assert metrics["server_total_s"] == 1.0


def test_aggregate_counts_terminals_and_fallbacks() -> None:
    """Counts group terminals, fallbacks, deadlines, and 25/30 s runs."""

    runs: list[dict[str, object]] = [
        {
            "server_total_s": 20.0,
            "terminal": "completed",
            "rerank_fallback": "none",
            "deadline_exhausted": False,
            "rerank_timeout_after_send": 0,
            "stage_seconds": {"company_scope": 10.0},
            "usage": {
                "rerank": {"calls": 1, "prompt_tokens": 1, "completion_tokens": 300}
            },
        },
        {
            "server_total_s": 28.0,
            "terminal": "completed",
            "rerank_fallback": "timeout",
            "deadline_exhausted": False,
            "rerank_timeout_after_send": 1,
            "stage_seconds": {"company_scope": 20.0},
        },
        {
            "server_total_s": 52.0,
            "terminal": "partial",
            "rerank_fallback": "timeout",
            "deadline_exhausted": True,
            "rerank_timeout_after_send": 1,
        },
    ]
    report = aggregate("unit", runs)
    assert report["counts"] == {
        "runs": 3,
        "terminal": {"completed": 2, "partial": 1},
        "rerank_fallback": {"none": 1, "timeout": 2},
        "deadline_exhausted": 1,
        "rerank_timeout_after_send": 2,
        "runs_le_25s": 1,
        "runs_le_30s": 2,
    }
    metrics = cast(dict[str, dict[str, float]], report["metrics"])
    assert metrics["server_total_s"]["median"] == 28.0
    assert metrics["server_total_s"]["n"] == 3
    assert metrics["wall_seconds"] == {"n": 0}
    stages = cast(dict[str, dict[str, float]], report["stages"])
    assert stages["company_scope"]["median"] == 15.0
    assert report["usage_completion_tokens"] == {
        "rerank": {"n": 1, "mean": 300.0, "median": 300.0, "p90": 300.0, "max": 300.0}
    }


def test_compare_reports_deltas_and_missing_metrics() -> None:
    """Delta is after minus before; a one-sided metric has None."""

    before: dict[str, object] = {
        "aggregate": {
            "metrics": {
                "wall_seconds": {
                    "n": 2,
                    "mean": 40.0,
                    "median": 41.0,
                    "p90": 50.0,
                    "max": 50.0,
                }
            },
            "counts": {"runs": 2},
        }
    }
    after: dict[str, object] = {
        "aggregate": {
            "metrics": {
                "wall_seconds": {
                    "n": 2,
                    "mean": 30.0,
                    "median": 29.5,
                    "p90": 35.0,
                    "max": 35.0,
                },
                "tail_s": {"n": 2, "median": 1.0},
            },
            "counts": {"runs": 2},
        }
    }
    rows = {
        metric: (old, new, delta)
        for metric, old, new, delta in compare_reports(before, after)
    }
    assert rows["metrics.wall_seconds.median"] == (41.0, 29.5, -11.5)
    assert rows["metrics.wall_seconds.p90"] == (50.0, 35.0, -15.0)
    assert rows["metrics.tail_s.median"] == (None, 1.0, None)
    assert rows["counts.runs"] == (2.0, 2.0, 0.0)
    assert "metrics.wall_seconds.n" not in rows
    assert "metrics.wall_seconds.max" not in rows


def test_subset_keeps_gold_order_and_rejects_unknown_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``subset`` writes gold-order items and exits 2 on an unknown id."""

    private = tmp_path / ".private-eval"
    private.mkdir()
    gold = private / "gold.json"
    gold.write_text(
        json.dumps(
            [{"id": "a", "page": 1}, {"id": "b", "page": 2}, {"id": "c", "page": 3}]
        ),
        encoding="utf-8",
    )
    out = private / "subset.json"
    assert main(["subset", "--gold", str(gold), "--ids", "c,a", "--out", str(out)]) == 0
    written = cast(list[dict[str, object]], json.loads(out.read_text(encoding="utf-8")))
    assert [item["id"] for item in written] == ["a", "c"]
    assert main(["subset", "--gold", str(gold), "--ids", "a,z", "--out", str(out)]) == 2
    assert "unknown_ids=z" in capsys.readouterr().out
    outside = tmp_path / "subset.json"
    assert (
        main(["subset", "--gold", str(gold), "--ids", "a", "--out", str(outside)]) == 2
    )
