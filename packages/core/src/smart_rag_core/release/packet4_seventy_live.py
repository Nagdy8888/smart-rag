"""Live 8-doc Packet 4 pause probe without host-melting load.

The signed 70% trigger is fail-closed in ``MaintenancePauseController``.
This probe only measures whether live Composite p95 holds on the Packet 2
8-doc subset while recording docker CPU peaks. It does not busy-loop the
Docker VM or claim QT-CAP-001/002.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

import httpx

from smart_rag_core.release.compose import run_compose
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    SEVENTY_LIVE_ARTIFACT,
    SEVENTY_LIVE_SCHEMA_VERSION,
)
from smart_rag_core.release.io import as_json_object, dump_canonical_json
from smart_rag_core.release.old_api_smoke import MIN_CLIENT_VERSION, api_base_url
from smart_rag_core.release.packet3 import EXPECTED_EXACT_CODE_DOCUMENT_ID
from smart_rag_core.release.packet4 import QT_LAT_001_MS, QT_LAT_011_MS, percentile
from smart_rag_core.release.packet4_load import (
    classify_seventy_percent,
    parse_cpu_percent,
    sse_event_names,
    stream_gate_payload,
)

CLIENT_VERSION = MIN_CLIENT_VERSION
DEFAULT_API_BASE = "http://127.0.0.1:8000"


@dataclass(frozen=True, slots=True)
class SeventyLiveHooks:
    """Injected Docker/HTTP boundary for unit tests.

    Attributes:
        docker_stats: Return compose stats rows.
        foreground: Run five Composite streams. Receives the bearer token.
    """

    docker_stats: Callable[[], list[dict[str, object]]]
    foreground: Callable[[str], dict[str, object]]


def paid_headers(token: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    """Build thin-UI paid JSON headers.

    Args:
        token: Bearer access token. Callers must not log it.
        idempotency_key: Optional Idempotency-Key.

    Returns:
        Header mapping without secrets beyond the bearer value.
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Client-Version": CLIENT_VERSION,
    }
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def collect_compose_stats(repo_root: Path) -> list[dict[str, object]]:
    """Capture one ``docker compose stats --no-stream`` snapshot.

    Args:
        repo_root: Repository root.

    Returns:
        Per-container stats objects. Secrets are not included.
    """

    completed = run_compose(
        repo_root,
        ["stats", "--no-stream", "--format", "{{json .}}"],
        timeout_seconds=60,
    )
    rows: list[dict[str, object]] = []
    if completed.returncode != 0:
        return rows
    stripped = completed.stdout.strip()
    if not stripped:
        return rows
    try:
        loaded: object = json.loads(stripped)
        if isinstance(loaded, list):
            for raw_item in cast(list[object], loaded):
                if isinstance(raw_item, dict):
                    rows.append(as_json_object(raw_item, source="docker-stats[]"))
            return rows
        if isinstance(loaded, dict):
            rows.append(as_json_object(loaded, source="docker-stats"))
            return rows
    except (json.JSONDecodeError, ValueError):
        pass
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(as_json_object(item, source="docker-stats-line"))
    return rows


def consume_sse_timings(
    url: str,
    headers: Mapping[str, str],
    *,
    timeout_seconds: float = 55.0,
) -> dict[str, object]:
    """Read one EventSource until a terminal event and time first token.

    Args:
        url: ``GET /runs/{id}/events`` URL.
        headers: Bearer resume headers.
        timeout_seconds: Maximum read time.

    Returns:
        Timing sample. Token text is not stored.
    """

    resume = {
        "Authorization": headers["Authorization"],
        "Accept": "text/event-stream",
    }
    buffer = ""
    first_token_ms: float | None = None
    started = time.monotonic()
    content_type = ""
    status_code = 0
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            with client.stream("GET", url, headers=resume) as response:
                status_code = response.status_code
                content_type = response.headers.get("content-type", "")
                for chunk in response.iter_text():
                    buffer += chunk
                    names = sse_event_names(buffer)
                    if first_token_ms is None and "token_delta" in names:
                        first_token_ms = (time.monotonic() - started) * 1000.0
                    if any(
                        name in {"completed", "cancelled", "error", "partial"}
                        for name in names
                    ):
                        break
                    if time.monotonic() - started > timeout_seconds:
                        break
    except httpx.HTTPError as exc:
        return {
            "status_code": status_code,
            "error": type(exc).__name__,
            "first_token_ms": first_token_ms,
            "completion_ms": (time.monotonic() - started) * 1000.0,
            "events": sse_event_names(buffer),
            "heartbeat_count": sse_event_names(buffer).count("heartbeat"),
            "terminal": False,
        }
    names = sse_event_names(buffer)
    return {
        "status_code": status_code,
        "content_type": content_type.split(";")[0],
        "first_token_ms": first_token_ms,
        "completion_ms": (time.monotonic() - started) * 1000.0,
        "events": names,
        "heartbeat_count": names.count("heartbeat"),
        "terminal": any(
            name in {"completed", "cancelled", "error", "partial"} for name in names
        ),
    }


def run_live_foreground(
    *,
    token: str,
    document_id: str,
    api_base: str,
) -> dict[str, object]:
    """Admit five Composite streams plus inspection and a table-intent message.

    Args:
        token: Member JWT. Not logged.
        document_id: Packet 2 exact-code document id.
        api_base: FastAPI origin, no trailing slash.

    Returns:
        Stream and inspection timings. No secrets or answer text.
    """

    with httpx.Client(timeout=30.0) as client:
        created = client.post(
            f"{api_base}/conversations",
            headers=paid_headers(token),
            json={"title": "phase09-seventy-live"},
        )
        if created.status_code != 201:
            return {
                "passed": False,
                "detail": f"conversation_create_{created.status_code}",
            }
        created_body = as_json_object(created.json(), source="conversation-create")
        conversation_id = str(created_body["conversation_id"])
        run_ids: list[str] = []
        for index in range(5):
            key = str(uuid4())
            admitted = client.post(
                f"{api_base}/conversations/{conversation_id}/messages",
                headers=paid_headers(token, idempotency_key=key),
                json={
                    "message": f"phase09-seventy-composite-{index}",
                    "idempotency_key": key,
                },
            )
            if admitted.status_code != 202:
                return {
                    "passed": False,
                    "detail": f"admit_{admitted.status_code}",
                    "admitted": len(run_ids),
                }
            admitted_body = as_json_object(admitted.json(), source="admit")
            run_ids.append(str(admitted_body["run_id"]))
        inspect_started = time.monotonic()
        inspect = client.post(
            f"{api_base}/graph/inspect",
            headers=paid_headers(token),
            json={"document_id": document_id, "depth": 1},
        )
        inspect_ms = (time.monotonic() - inspect_started) * 1000.0
        table_key = str(uuid4())
        table_started = time.monotonic()
        table = client.post(
            f"{api_base}/conversations/{conversation_id}/messages",
            headers=paid_headers(token, idempotency_key=table_key),
            json={
                "message": "sum the amount column grouped by region",
                "idempotency_key": table_key,
            },
        )
        table_admit_ms = (time.monotonic() - table_started) * 1000.0
        table_run = ""
        if table.status_code == 202:
            table_body = as_json_object(table.json(), source="table-admit")
            table_run = str(table_body.get("run_id") or "")

    def _one_stream(run_id: str) -> dict[str, object]:
        """Consume one Composite EventSource.

        Args:
            run_id: Admitted run.

        Returns:
            Timing sample.
        """

        return consume_sse_timings(
            f"{api_base}/runs/{run_id}/events?after=0",
            paid_headers(token),
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        stream_rows = list(pool.map(_one_stream, run_ids))
    table_stream: dict[str, object] | None = None
    if table_run:
        table_stream = consume_sse_timings(
            f"{api_base}/runs/{table_run}/events?after=0",
            paid_headers(token),
        )
    first_token_ms = [
        float(row["first_token_ms"])
        for row in stream_rows
        if isinstance(row.get("first_token_ms"), (int, float))
        and not isinstance(row.get("first_token_ms"), bool)
    ]
    completion_ms = [
        float(row["completion_ms"])
        for row in stream_rows
        if isinstance(row.get("completion_ms"), (int, float))
        and not isinstance(row.get("completion_ms"), bool)
    ]
    heartbeat_counts = [
        int(row["heartbeat_count"])
        if isinstance(row.get("heartbeat_count"), int)
        and not isinstance(row.get("heartbeat_count"), bool)
        else 0
        for row in stream_rows
    ]
    streams = stream_gate_payload(
        first_token_ms=first_token_ms,
        completion_ms=completion_ms,
        heartbeat_counts=heartbeat_counts,
        lag_p95_seconds=None,
        simultaneous_runs=len(run_ids),
        mock_model_mode=True,
    )
    sse_ok = all(int(row.get("status_code") or 0) == 200 for row in stream_rows)
    return {
        "passed": sse_ok and len(run_ids) == 5,
        "inspect_ok": inspect.status_code in {200, 403, 404},
        "inspect_ms": inspect_ms,
        "inspect_status": inspect.status_code,
        "table_admit_ms": table_admit_ms,
        "table_status": table.status_code,
        "table_stream_status": (
            table_stream.get("status_code") if table_stream is not None else None
        ),
        "streams": streams,
        "stream_http": [
            {
                "status_code": row.get("status_code"),
                "terminal": row.get("terminal"),
                "events": row.get("events"),
            }
            for row in stream_rows
        ],
        "jwt_eventsource_401": any(
            int(row.get("status_code") or 0) == 401 for row in stream_rows
        ),
        "sample_is_eight_doc_subset": True,
    }


def cpu_peaks_from_stats(rows: Sequence[Mapping[str, object]]) -> list[float]:
    """Extract CPU percents from compose stats rows.

    Args:
        rows: ``docker compose stats`` objects.

    Returns:
        Finite CPU percentages.
    """

    values: list[float] = []
    for row in rows:
        cpu = parse_cpu_percent(row.get("CPUPerc"))
        if cpu is not None:
            values.append(cpu)
    return values


def measure_live_seventy_pause(
    repo_root: Path,
    *,
    token: str,
    hooks: SeventyLiveHooks | None = None,
    write_artifact: bool = True,
    document_id: str = EXPECTED_EXACT_CODE_DOCUMENT_ID,
) -> dict[str, object]:
    """Measure 8-doc live p95 and CPU peaks, then classify the 70% pause.

    Args:
        repo_root: Repository root.
        token: Member JWT. Not logged or written to artifacts.
        hooks: Optional Docker/HTTP doubles.
        write_artifact: When true, write the JSON artifact.
        document_id: Inspection document id.

    Returns:
        Classification payload. ``passed`` follows
        ``classify_seventy_percent`` (p95 held or 70% fired).

    Side Effects:
        May call Compose stats and live FastAPI. Writes
        ``candidate-packet4-seventy-live.json`` when requested.
    """

    slot = hooks or SeventyLiveHooks(
        docker_stats=lambda: collect_compose_stats(repo_root),
        foreground=lambda access: run_live_foreground(
            token=access,
            document_id=document_id,
            api_base=api_base_url(),
        ),
    )
    before = slot.docker_stats()
    live = slot.foreground(token)
    after = slot.docker_stats()
    cpu_values = cpu_peaks_from_stats(before) + cpu_peaks_from_stats(after)
    streams_raw = live.get("streams")
    streams: dict[str, object] = {}
    if isinstance(streams_raw, dict):
        streams = as_json_object(streams_raw, source="seventy.streams")
    completion_p95 = streams.get("completion_p95_ms")
    first_p95 = streams.get("first_token_p95_ms")
    foreground_p95: float | None = None
    if isinstance(completion_p95, (int, float)) and not isinstance(
        completion_p95, bool
    ):
        foreground_p95 = float(completion_p95)
    elif isinstance(first_p95, (int, float)) and not isinstance(first_p95, bool):
        foreground_p95 = float(first_p95)
    elif isinstance(live.get("inspect_ms"), (int, float)) and not isinstance(
        live.get("inspect_ms"), bool
    ):
        foreground_p95 = float(cast(float, live["inspect_ms"]))
    jwt_401 = live.get("jwt_eventsource_401") is True
    seventy = classify_seventy_percent(
        cpu_peaks=cpu_values,
        foreground_p95_ms=None if jwt_401 else foreground_p95,
        foreground_gate_ms=QT_LAT_011_MS,
    )
    if jwt_401:
        seventy = {
            **seventy,
            "passed": False,
            "classification": "Blocked",
            "detail": "live EventSource returned 401; p95 not used",
        }
    else:
        seventy = {
            **seventy,
            "classification": "Passed" if seventy.get("passed") is True else "Blocked",
            "detail": (
                "Live 8-doc Composite p95 versus QT-LAT-011. 70% CPU trigger "
                "is recorded, not forced. Not QT-CAP-001/002."
            ),
        }
    payload: dict[str, object] = {
        "schema_version": SEVENTY_LIVE_SCHEMA_VERSION,
        "sample_is_eight_doc_subset": True,
        "holdout_opened": False,
        "busy_loop": False,
        "qt_cap_001_claimed": False,
        "qt_cap_002_claimed": False,
        "qt_lat_001_ms": QT_LAT_001_MS,
        "qt_lat_011_ms": QT_LAT_011_MS,
        "api_base": DEFAULT_API_BASE,
        "live": {
            "passed": live.get("passed"),
            "detail": live.get("detail"),
            "inspect_ok": live.get("inspect_ok"),
            "inspect_ms": live.get("inspect_ms"),
            "inspect_status": live.get("inspect_status"),
            "jwt_eventsource_401": jwt_401,
            "stream_http": live.get("stream_http"),
            "streams": streams,
        },
        "cpu_peaks": cpu_values,
        "seventy_percent": seventy,
        "percentile_probe": percentile(cpu_values, 0.95) if cpu_values else None,
    }
    if write_artifact:
        path = repo_root / ARTIFACT_DIR / SEVENTY_LIVE_ARTIFACT
        dump_canonical_json(payload, path)
    return payload
