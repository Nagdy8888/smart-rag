"""Latency report for company-ask timing runs.

Reads run IDs from a private runner answers JSON, loads ``app.runs``,
``app.run_events``, and ``app.llm_usage`` rows for them, and writes one
JSON report. Event payloads are reduced in SQL to the keys ``stage``,
``phase``, ``reason``, and ``code``, so no answer, query, or passage text
leaves the database. Output and stdout hold ids, stage names, event types,
usage kinds, fallback codes, timings, and counts only.

Usage::

    uv run python scripts/eval_latency_report.py subset --gold G --ids a,b --out O
    uv run python scripts/eval_latency_report.py report --answers A --stages S --label L --out O
    uv run python scripts/eval_latency_report.py compare BEFORE AFTER
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import LiteralString, TypeGuard, cast
from uuid import UUID

import psycopg
from psycopg.rows import TupleRow

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.sse.catalog import TERMINAL_SSE_EVENT_TYPES  # noqa: E402

from scripts.eval_ask_stage_export import operator_url  # noqa: E402

SUMMARY_METRICS: tuple[str, ...] = (
    "wall_seconds",
    "post_seconds",
    "first_frame_seconds",
    "sse_seconds",
    "server_total_s",
    "admission_to_first_event_s",
    "pre_first_stage_s",
    "node_gap_total_s",
    "tail_s",
    "event_spacing_median_s",
    "event_count",
)
CLIENT_TIMING_KEYS: tuple[str, ...] = (
    "post_seconds",
    "first_frame_seconds",
    "sse_seconds",
    "wall_seconds",
)
COMPARE_SUFFIXES: tuple[str, ...] = (".mean", ".median", ".p90")

_RUN_SQL: LiteralString = """
SELECT created_at, started_at, deadline_at
FROM app.runs
WHERE id = %s::uuid
"""
_EVENTS_SQL: LiteralString = """
SELECT event_type,
       created_at,
       jsonb_build_object(
         'stage', payload->>'stage',
         'phase', payload->>'phase',
         'reason', payload->>'reason',
         'code', payload->>'code'
       )
FROM app.run_events
WHERE run_id = %s::uuid
ORDER BY sequence
"""
_USAGE_SQL: LiteralString = """
SELECT usage_kind, prompt_tokens, completion_tokens, timeout_after_send
FROM app.llm_usage
WHERE run_id = %s::uuid
"""

CompareRow = tuple[str, float | None, float | None, float | None]


def _is_number(value: object) -> TypeGuard[int | float]:
    """Return whether ``value`` is an int or float but not a bool.

    Args:
        value: Any JSON or database value.

    Returns:
        True for real numbers.
    """

    return isinstance(value, int | float) and not isinstance(value, bool)


def _number(value: object) -> float | None:
    """Return ``value`` as a float rounded to 3 decimals, else None.

    Args:
        value: Any JSON or database value.

    Returns:
        Rounded float, or None when ``value`` is not a real number.
    """

    if not _is_number(value):
        return None
    return round(float(value), 3)


def _mapping(value: object) -> dict[str, object]:
    """Return ``value`` as a string-keyed dict, else an empty dict.

    Args:
        value: Any JSON value.

    Returns:
        String-keyed shallow copy.
    """

    if not isinstance(value, Mapping):
        return {}
    typed = cast(Mapping[object, object], value)
    return {str(key): item for key, item in typed.items()}


def _numbers(values: Iterable[object]) -> list[float]:
    """Keep only real numbers, as floats, in input order.

    Args:
        values: Any values.

    Returns:
        Floats.
    """

    return [float(item) for item in values if _is_number(item)]


def _seconds(later: object, earlier: object) -> float | None:
    """Return ``later - earlier`` in seconds, rounded to 3 decimals.

    Args:
        later: A ``datetime`` or anything else.
        earlier: A ``datetime`` or anything else.

    Returns:
        Seconds, or None when either side is not a ``datetime``.
    """

    if not isinstance(later, datetime) or not isinstance(earlier, datetime):
        return None
    return round((later - earlier).total_seconds(), 3)


def _is_uuid(value: str) -> bool:
    """Return whether ``value`` parses as a UUID.

    Args:
        value: Candidate run id.

    Returns:
        True for a UUID string.
    """

    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _private_out(path: Path) -> bool:
    """Return whether ``path`` is inside a ``.private-eval`` directory.

    Args:
        path: Output path.

    Returns:
        True when one path part is ``.private-eval`` (case-insensitive).
    """

    return ".private-eval" in {part.casefold() for part in path.resolve().parts}


def _read_json(path: Path) -> object:
    """Read one UTF-8 JSON file.

    Args:
        path: JSON file.

    Returns:
        Parsed value.
    """

    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _write_json(path: Path, payload: object) -> None:
    """Write ``payload`` as indented UTF-8 JSON without a BOM.

    Args:
        path: Output file. Parent directories are created.
        payload: JSON-ready value. Datetimes are written with ``str``.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def percentile(values: Sequence[float], fraction: float) -> float:
    """Return the nearest-rank percentile.

    Args:
        values: Numbers in any order.
        fraction: Percentile as a fraction, for example 0.9.

    Returns:
        ``sorted(values)[ceil(fraction * n) - 1]``; 0.0 for empty input.
    """

    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return float(ordered[min(rank, len(ordered)) - 1])


def summarize(values: Sequence[float]) -> dict[str, float | int]:
    """Summarize numbers as n, mean, median, nearest-rank p90, and max.

    Args:
        values: Numbers in any order.

    Returns:
        ``{"n": 0}`` for empty input; otherwise ``n``, ``mean``, ``median``,
        ``p90``, and ``max`` rounded to 3 decimals.
    """

    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 3),
        "median": round(float(statistics.median(values)), 3),
        "p90": round(percentile(values, 0.9), 3),
        "max": round(max(values), 3),
    }


def run_metrics(
    *,
    run_row: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
    usage_rows: Sequence[Mapping[str, object]],
    client_timing: Mapping[str, object],
    stage_row: Mapping[str, object],
) -> dict[str, object]:
    """Compute one run's latency numbers.

    Definitions (seconds unless named ``_ms``):

    - ``server_total_s``: last event minus first event.
    - ``admission_to_first_event_s``: first event minus ``runs.created_at``.
    - ``deadline_budget_s``: ``runs.deadline_at`` minus ``runs.started_at``.
    - ``stage_seconds[stage]``: ``status`` ``completed`` minus the matching
      ``started``, summed when a stage runs twice.
    - ``open_stage_seconds[stage]``: a stage with no ``completed`` (still
      running or failed), measured up to the terminal event.
    - ``pre_first_stage_s``: first ``started`` minus first event.
    - ``node_gap_total_s``: sum of every ``started`` minus the latest
      earlier ``completed``.
    - ``tail_s``: terminal event minus the last ``completed``.
    - ``event_spacing_median_s``: median gap between consecutive events.
    - ``deadline_exhausted``: a ``deadline`` event, or a ``partial`` event
      whose ``reason`` is ``deadline_exhausted``.

    Args:
        run_row: ``created_at``, ``started_at``, ``deadline_at`` of the run.
            May be empty.
        events: Events in ``sequence`` order with ``event_type``,
            ``created_at``, and ``payload`` (only ``stage``, ``phase``,
            ``reason``, ``code`` are read).
        usage_rows: ``usage_kind``, ``prompt_tokens``,
            ``completion_tokens``, ``timeout_after_send`` rows.
        client_timing: Runner ``timing`` mapping. May be empty.
        stage_row: Stage-export row. Only ``stage_timings_ms`` and
            ``rerank_fallback`` are read. May be empty.

    Returns:
        Numbers, stage names, event types, usage kinds, and fallback codes
        only. Values that cannot be measured are None.
    """

    times = [event.get("created_at") for event in events]
    first_at = times[0] if times else None
    last_at = times[-1] if times else None
    terminal_at: object = None
    terminal_type = "none"
    stage_seconds: dict[str, float] = {}
    open_started: dict[str, object] = {}
    first_started: object = None
    last_completed: object = None
    gap_total = 0.0
    deadline_exhausted = False
    for event in events:
        event_type = str(event.get("event_type") or "")
        payload = _mapping(event.get("payload"))
        at = event.get("created_at")
        if event_type == "deadline" or (
            event_type == "partial" and payload.get("reason") == "deadline_exhausted"
        ):
            deadline_exhausted = True
        if event_type in TERMINAL_SSE_EVENT_TYPES and terminal_at is None:
            terminal_at = at
            terminal_type = event_type
        if event_type != "status":
            continue
        stage = str(payload.get("stage") or "unknown")
        phase = payload.get("phase")
        if phase == "started":
            if first_started is None:
                first_started = at
            gap = _seconds(at, last_completed)
            if gap is not None:
                gap_total += gap
            open_started[stage] = at
        elif phase == "completed":
            last_completed = at
            seconds = _seconds(at, open_started.pop(stage, None))
            if seconds is not None:
                stage_seconds[stage] = round(stage_seconds.get(stage, 0.0) + seconds, 3)
    end_at = terminal_at if terminal_at is not None else last_at
    open_stage_seconds: dict[str, float] = {}
    for stage, began in open_started.items():
        seconds = _seconds(end_at, began)
        if seconds is not None:
            open_stage_seconds[stage] = seconds
    spacings: list[float] = []
    for earlier, later in itertools.pairwise(times):
        spacing = _seconds(later, earlier)
        if spacing is not None:
            spacings.append(spacing)
    usage: dict[str, dict[str, int]] = {}
    rerank_timeouts = 0
    for row in usage_rows:
        kind = str(row.get("usage_kind") or "unknown")
        bucket = usage.setdefault(
            kind, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        )
        bucket["calls"] += 1
        bucket["prompt_tokens"] += int(_number(row.get("prompt_tokens")) or 0)
        bucket["completion_tokens"] += int(_number(row.get("completion_tokens")) or 0)
        if kind == "rerank" and row.get("timeout_after_send") is True:
            rerank_timeouts += 1
    hybrid: dict[str, float] = {}
    for key, item in _mapping(stage_row.get("stage_timings_ms")).items():
        value = _number(item)
        if value is not None:
            hybrid[key] = value
    metrics: dict[str, object] = {
        "server_total_s": _seconds(last_at, first_at),
        "admission_to_first_event_s": _seconds(first_at, run_row.get("created_at")),
        "deadline_budget_s": _seconds(
            run_row.get("deadline_at"), run_row.get("started_at")
        ),
        "pre_first_stage_s": _seconds(first_started, first_at),
        "node_gap_total_s": round(gap_total, 3),
        "tail_s": _seconds(terminal_at, last_completed),
        "event_count": len(events),
        "event_spacing_median_s": (
            round(float(statistics.median(spacings)), 3) if spacings else None
        ),
        "terminal": terminal_type,
        "deadline_exhausted": deadline_exhausted,
        "stage_seconds": stage_seconds,
        "open_stage_seconds": open_stage_seconds,
        "usage": usage,
        "rerank_timeout_after_send": rerank_timeouts,
        "rerank_fallback": str(stage_row.get("rerank_fallback") or "unknown"),
        "stage_timings_ms": hybrid,
    }
    for key in CLIENT_TIMING_KEYS:
        metrics[key] = _number(client_timing.get(key))
    return metrics


def _summaries(
    runs: Sequence[Mapping[str, object]], field_name: str
) -> dict[str, dict[str, float | int]]:
    """Summarize one nested per-run mapping key by key.

    Args:
        runs: Per-run metrics.
        field_name: Nested mapping name, for example ``stage_seconds``.

    Returns:
        ``summarize`` result per key, keys sorted.
    """

    values: dict[str, list[float]] = {}
    for run in runs:
        for key, item in _mapping(run.get(field_name)).items():
            if _is_number(item):
                values.setdefault(key, []).append(float(item))
    return {key: summarize(items) for key, items in sorted(values.items())}


def aggregate(label: str, runs: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Summarize many ``run_metrics`` results.

    Args:
        label: Report label, for example ``L0-a``.
        runs: Per-run metrics.

    Returns:
        ``label``; ``metrics`` (``summarize`` per ``SUMMARY_METRICS``
        name); ``stages``, ``open_stages``, and ``stage_timings_ms``
        (``summarize`` per key); ``usage_completion_tokens`` (``summarize``
        per usage kind); and ``counts`` (runs, terminal types, rerank
        fallbacks, deadline runs, rerank timeouts after send, and runs whose
        ``server_total_s`` is at most 25 s and 30 s).
    """

    metrics = {
        name: summarize(_numbers(run.get(name) for run in runs))
        for name in SUMMARY_METRICS
    }
    completion: dict[str, list[float]] = {}
    terminals: dict[str, int] = {}
    fallbacks: dict[str, int] = {}
    for run in runs:
        for kind, bucket in _mapping(run.get("usage")).items():
            tokens = _mapping(bucket).get("completion_tokens")
            if _is_number(tokens):
                completion.setdefault(kind, []).append(float(tokens))
        terminal = str(run.get("terminal") or "none")
        terminals[terminal] = terminals.get(terminal, 0) + 1
        fallback = str(run.get("rerank_fallback") or "unknown")
        fallbacks[fallback] = fallbacks.get(fallback, 0) + 1
    totals = _numbers(run.get("server_total_s") for run in runs)
    counts: dict[str, object] = {
        "runs": len(runs),
        "terminal": dict(sorted(terminals.items())),
        "rerank_fallback": dict(sorted(fallbacks.items())),
        "deadline_exhausted": sum(
            1 for run in runs if run.get("deadline_exhausted") is True
        ),
        "rerank_timeout_after_send": int(
            sum(_numbers(run.get("rerank_timeout_after_send") for run in runs))
        ),
        "runs_le_25s": sum(1 for value in totals if value <= 25.0),
        "runs_le_30s": sum(1 for value in totals if value <= 30.0),
    }
    return {
        "label": label,
        "metrics": metrics,
        "stages": _summaries(runs, "stage_seconds"),
        "open_stages": _summaries(runs, "open_stage_seconds"),
        "stage_timings_ms": _summaries(runs, "stage_timings_ms"),
        "usage_completion_tokens": {
            kind: summarize(values) for kind, values in sorted(completion.items())
        },
        "counts": counts,
    }


def _flatten(prefix: str, value: object, out: dict[str, float]) -> None:
    """Flatten nested numbers into ``out`` with dotted keys.

    Args:
        prefix: Dotted key so far; empty at the top.
        value: Nested mapping or number. Other values are ignored.
        out: Destination, updated in place.
    """

    if _is_number(value):
        out[prefix] = round(float(value), 3)
        return
    for key, item in _mapping(value).items():
        _flatten(f"{prefix}.{key}" if prefix else key, item, out)


def _comparable(report: Mapping[str, object]) -> dict[str, float]:
    """Return the report numbers that ``compare`` shows.

    Args:
        report: A report written by ``report``.

    Returns:
        Every mean, median, and p90 in ``aggregate`` plus every count,
        keyed like ``metrics.wall_seconds.median`` or ``counts.runs``.
    """

    flat: dict[str, float] = {}
    _flatten("", report.get("aggregate"), flat)
    return {
        key: value
        for key, value in flat.items()
        if key.startswith("counts.") or key.endswith(COMPARE_SUFFIXES)
    }


def compare_reports(
    before: Mapping[str, object], after: Mapping[str, object]
) -> list[CompareRow]:
    """Compare two reports metric by metric.

    Args:
        before: Earlier report.
        after: Later report.

    Returns:
        ``(metric, before, after, after - before)`` rows sorted by metric.
        A side that lacks the metric is None, and so is its delta.
    """

    left = _comparable(before)
    right = _comparable(after)
    rows: list[CompareRow] = []
    for key in sorted(set(left) | set(right)):
        old = left.get(key)
        new = right.get(key)
        delta = round(new - old, 3) if old is not None and new is not None else None
        rows.append((key, old, new, delta))
    return rows


def _fmt(value: float | None) -> str:
    """Format one compare cell.

    Args:
        value: Number or None.

    Returns:
        ``-`` for None, else 3 decimals.
    """

    return "-" if value is None else f"{value:.3f}"


def format_compare(rows: Sequence[CompareRow]) -> list[str]:
    """Render compare rows as a fixed-width table.

    Args:
        rows: Output of ``compare_reports``.

    Returns:
        Header line plus one line per row.
    """

    lines = [f"{'metric':<60} {'before':>10} {'after':>10} {'delta':>10}"]
    for metric, old, new, delta in rows:
        lines.append(f"{metric:<60} {_fmt(old):>10} {_fmt(new):>10} {_fmt(delta):>10}")
    return lines


def subset_items(
    items: Sequence[Mapping[str, object]], ids: Sequence[str]
) -> tuple[list[dict[str, object]], list[str]]:
    """Pick gold items by ``id``, keeping the gold file's order.

    Args:
        items: Gold items, each with an ``id`` key.
        ids: Wanted ids.

    Returns:
        ``(chosen, unknown_ids)``. ``unknown_ids`` keeps the order given.
    """

    wanted = set(ids)
    chosen = [dict(item) for item in items if str(item.get("id")) in wanted]
    found = {str(item.get("id")) for item in chosen}
    unknown = [item for item in ids if item not in found]
    return chosen, unknown


def load_run(
    connection: psycopg.Connection[TupleRow], run_id: str
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    """Read one run's row, reduced events, and usage rows.

    Args:
        connection: Operator session with ``SET ROLE postgres`` applied.
        run_id: Run UUID string.

    Returns:
        ``(run_row, events, usage_rows)`` shaped for ``run_metrics``.
        ``run_row`` is empty when the run is missing.

    Side Effects:
        Three read-only SELECTs.
    """

    found = connection.execute(_RUN_SQL, (run_id,)).fetchone()
    run_row: dict[str, object] = {}
    if found is not None:
        run_row = {
            "created_at": found[0],
            "started_at": found[1],
            "deadline_at": found[2],
        }
    events: list[dict[str, object]] = [
        {"event_type": row[0], "created_at": row[1], "payload": row[2]}
        for row in connection.execute(_EVENTS_SQL, (run_id,)).fetchall()
    ]
    usage_rows: list[dict[str, object]] = [
        {
            "usage_kind": row[0],
            "prompt_tokens": row[1],
            "completion_tokens": row[2],
            "timeout_after_send": row[3],
        }
        for row in connection.execute(_USAGE_SQL, (run_id,)).fetchall()
    ]
    return run_row, events, usage_rows


def _cmd_subset(gold_path: Path, ids_text: str, out: Path) -> int:
    """Write a gold subset file.

    Args:
        gold_path: Gold JSON array.
        ids_text: Comma-separated ids.
        out: Output path under ``.private-eval``.

    Returns:
        0 on success; 2 for a non-private output, a non-list gold file, or
        unknown ids.

    Side Effects:
        Writes ``out``. Prints ``subset=<n>`` or a ``blocked=`` /
        ``unknown_ids=`` line.
    """

    if not _private_out(out):
        print("blocked=out_not_private")
        return 2
    raw = _read_json(gold_path)
    if not isinstance(raw, list):
        print("blocked=gold_not_list")
        return 2
    items = [_mapping(item) for item in cast(list[object], raw)]
    ids = [part.strip() for part in ids_text.split(",") if part.strip()]
    chosen, unknown = subset_items(items, ids)
    if unknown:
        print(f"unknown_ids={','.join(unknown)}")
        return 2
    _write_json(out, chosen)
    print(f"subset={len(chosen)}")
    return 0


def _cmd_report(
    answers_path: Path, stages_path: Path | None, label: str, out: Path
) -> int:
    """Build and write a latency report for one runner answers file.

    Args:
        answers_path: Runner ``--answers-out`` JSON (question id to row).
        stages_path: Optional runner ``--stage-export`` JSON.
        label: Report label, for example ``L1-after``.
        out: Report path under ``.private-eval``.

    Returns:
        0 on success; 2 for a non-private output or a missing operator URL.

    Side Effects:
        Read-only SELECTs as the operator role. Writes ``out``. Prints run
        count, three metric summaries, and the deadline count.
    """

    if not _private_out(out):
        print("blocked=out_not_private")
        return 2
    try:
        url = operator_url()
    except RuntimeError as error:
        print(f"blocked={error}")
        return 2
    answers = _mapping(_read_json(answers_path))
    stage_runs: dict[str, object] = {}
    if stages_path is not None:
        stage_runs = _mapping(_mapping(_read_json(stages_path)).get("runs"))
    runs: list[dict[str, object]] = []
    with psycopg.connect(url, connect_timeout=20) as connection:
        connection.execute("SET ROLE postgres")
        for question_id, row_value in sorted(answers.items()):
            row = _mapping(row_value)
            run_id = str(row.get("run_id") or "").strip()
            if not _is_uuid(run_id):
                continue
            run_row, events, usage_rows = load_run(connection, run_id)
            metrics = run_metrics(
                run_row=run_row,
                events=events,
                usage_rows=usage_rows,
                client_timing=_mapping(row.get("timing")),
                stage_row=_mapping(stage_runs.get(question_id)),
            )
            runs.append({"question_id": question_id, "run_id": run_id, **metrics})
    summary = aggregate(label, runs)
    _write_json(
        out,
        {
            "label": label,
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "run_count": len(runs),
            "aggregate": summary,
            "runs": runs,
        },
    )
    metric_block = _mapping(summary.get("metrics"))
    print(f"runs={len(runs)}")
    for name in ("server_total_s", "wall_seconds", "event_spacing_median_s"):
        values = _mapping(metric_block.get(name))
        print(
            f"{name} n={values.get('n')} mean={values.get('mean')} "
            f"median={values.get('median')} p90={values.get('p90')}"
        )
    counts = _mapping(summary.get("counts"))
    print(f"deadline_exhausted={counts.get('deadline_exhausted')}")
    return 0


def _cmd_compare(before_path: Path, after_path: Path) -> int:
    """Print the compare table for two reports.

    Args:
        before_path: Earlier report.
        after_path: Later report.

    Returns:
        Always 0.
    """

    rows = compare_reports(
        _mapping(_read_json(before_path)), _mapping(_read_json(after_path))
    )
    for line in format_compare(rows):
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the ``subset``, ``report``, or ``compare`` command.

    Args:
        argv: Optional CLI arguments without the program name.

    Returns:
        Process exit code.
    """

    parser = argparse.ArgumentParser(description="Company-ask latency report.")
    commands = parser.add_subparsers(dest="command", required=True)
    subset = commands.add_parser("subset", help="Write a gold subset file.")
    subset.add_argument("--gold", type=Path, required=True)
    subset.add_argument("--ids", required=True)
    subset.add_argument("--out", type=Path, required=True)
    report = commands.add_parser("report", help="Build a latency report.")
    report.add_argument("--answers", type=Path, required=True)
    report.add_argument("--stages", type=Path, default=None)
    report.add_argument("--label", required=True)
    report.add_argument("--out", type=Path, required=True)
    compare = commands.add_parser("compare", help="Compare two reports.")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    args = parser.parse_args(argv)
    command = cast(str, args.command)
    if command == "subset":
        return _cmd_subset(
            cast(Path, args.gold), cast(str, args.ids), cast(Path, args.out)
        )
    if command == "report":
        return _cmd_report(
            cast(Path, args.answers),
            cast(Path | None, args.stages),
            cast(str, args.label),
            cast(Path, args.out),
        )
    return _cmd_compare(cast(Path, args.before), cast(Path, args.after))


if __name__ == "__main__":
    raise SystemExit(main())
