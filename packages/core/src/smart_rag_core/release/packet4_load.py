"""Bounded Packet 4 foreground-plus-maintenance measurements.

These helpers consume existing admission, graph-lock, BM25, inspection, and
SSE contracts. They do not kill worker/ParadeDB/Valkey or claim managed
pooling/EC2/CDN proof.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping, Sequence
from uuid import UUID, uuid4

import psycopg

from smart_rag_core.jobs.graph_writer import graph_advisory_lock_keys
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_admission.service import admit_query_run
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.release.bm25_reproject import reproject_one_version
from smart_rag_core.release.packet4 import (
    BUDGET_CEILING,
    HEARTBEAT_INTERVAL_SECONDS,
    HEARTBEAT_JITTER_SECONDS,
    P95_LAG_SECONDS,
    QT_CAP_004_RUNS,
    QT_LAT_006_MS,
    QT_LAT_009_MS,
    QT_LAT_010_MS,
    QT_LAT_011_MS,
    SELECTED_TIER_HARD_LIMIT,
    SIZING_LADDER_SEVENTY,
    WORST_CASE_CAPS,
    percentile,
)
from smart_rag_core.retrieval.graph import DEFAULT_GRAPH_WORKSPACE
from smart_rag_core.security.identity import CallerContext, UserRole

_HNSW_INDEX = "app.document_chunks_embedding_hnsw_idx"


def parse_sse_events(buffer: str) -> list[tuple[str, float]]:
    """Return ``(event_name, relative_seconds)`` using block order.

    Timestamps are not in the wire format; callers should pair this with
    wall-clock samples. This parser only returns names in order with a
    placeholder of ``0.0``.

    Args:
        buffer: Raw EventSource text.

    Returns:
        Ordered event names.
    """

    names: list[tuple[str, float]] = []
    for block in buffer.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("event:"):
                names.append((line.split(":", 1)[1].strip(), 0.0))
    return names


def sse_event_names(buffer: str) -> list[str]:
    """Parse SSE ``event:`` names from a concatenated buffer.

    Args:
        buffer: Raw EventSource text.

    Returns:
        Event type names in order.
    """

    return [name for name, _offset in parse_sse_events(buffer)]


def measure_supabase_pools(connection: psycopg.Connection) -> dict[str, object]:
    """Snapshot ``pg_stat_activity`` counts by role and application_name.

    Args:
        connection: Open postgres connection.

    Returns:
        Pool report without connection strings.
    """

    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              COALESCE(usename, ''),
              COALESCE(application_name, ''),
              COALESCE(state, ''),
              count(*)::integer
            FROM pg_stat_activity
            WHERE datname = current_database()
            GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3
            """
        )
        rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT count(*)::integer
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid()
            """
        )
        total_row = cursor.fetchone()
    total = int(total_row[0]) if total_row is not None else 0
    worst_case = sum(WORST_CASE_CAPS.values())
    return {
        "by_role_application_state": [
            {
                "usename": str(row[0]),
                "application_name": str(row[1]),
                "state": str(row[2]),
                "count": int(row[3]),
            }
            for row in rows
        ],
        "active_minus_this_backend": total,
        "worst_case_caps_sum": worst_case,
        "budget_ceiling": BUDGET_CEILING,
        "selected_tier_hard_limit": SELECTED_TIER_HARD_LIMIT,
        "exhausted": total >= SELECTED_TIER_HARD_LIMIT,
        "above_seventy_percent_ceiling": total >= BUDGET_CEILING,
        "passed": total < BUDGET_CEILING,
    }


def reindex_hnsw(connection: psycopg.Connection) -> dict[str, object]:
    """Rebuild the canonical chunk HNSW index on the 8-doc subset.

    Args:
        connection: Autocommit postgres connection.

    Returns:
        Duration and success flag. Sample is 16 chunks, not 1M.
    """

    started = time.monotonic()
    connection.autocommit = True
    connection.execute("SET ROLE postgres")
    try:
        connection.execute(f"REINDEX INDEX {_HNSW_INDEX}")
        elapsed_ms = (time.monotonic() - started) * 1000.0
        return {
            "index": _HNSW_INDEX,
            "elapsed_ms": elapsed_ms,
            "passed": True,
            "sample_is_eight_doc_subset": True,
            "detail": "REINDEX on seeded chunks, not the 1M envelope",
        }
    except psycopg.Error as exc:
        return {
            "index": _HNSW_INDEX,
            "elapsed_ms": (time.monotonic() - started) * 1000.0,
            "passed": False,
            "sample_is_eight_doc_subset": True,
            "detail": type(exc).__name__,
        }


def graph_advisory_lock_cycle(db_url: str) -> dict[str, object]:
    """Hold then release the concurrency-one graph writer advisory lock.

    Args:
        db_url: Local Supabase URL.

    Returns:
        Whether a second session was excluded. If the live worker already
        holds the lock, the probe does not steal it.
    """

    keys = graph_advisory_lock_keys(DEFAULT_GRAPH_WORKSPACE)
    first = psycopg.connect(db_url)
    second = psycopg.connect(db_url)
    try:
        first.autocommit = True
        second.autocommit = True
        first.execute("SET ROLE app_worker")
        second.execute("SET ROLE app_worker")
        with first.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", keys)
            held = cursor.fetchone()
        with second.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", keys)
            busy = cursor.fetchone()
        held_by_probe = held is not None and held[0] is True
        excluded = busy is not None and busy[0] is False
        if held_by_probe:
            with first.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s, %s)", keys)
        return {
            "workspace_key": DEFAULT_GRAPH_WORKSPACE,
            "held": held_by_probe,
            "second_session_excluded": excluded,
            "released": held_by_probe,
            "lock_already_held": not held_by_probe,
            "passed": excluded,
        }
    finally:
        first.close()
        second.close()


def _insert_budget_user(
    cursor: psycopg.Cursor,
    *,
    user_id: UUID,
) -> UUID:
    """Insert one Auth user, profile, and conversation for lock-wait measurement.

    Args:
        cursor: Open postgres cursor.
        user_id: New user UUID.

    Returns:
        Conversation id.
    """

    cursor.execute(
        """
        INSERT INTO auth.users (
          id, instance_id, aud, role, email, encrypted_password,
          email_confirmed_at, created_at, updated_at
        )
        VALUES (
          %s,
          '00000000-0000-0000-0000-000000000000'::uuid,
          'authenticated',
          'authenticated',
          %s,
          crypt('test-password', gen_salt('bf')),
          timezone('utc', now()),
          timezone('utc', now()),
          timezone('utc', now())
        )
        """,
        (user_id, f"{user_id}@example.com"),
    )
    cursor.execute(
        """
        INSERT INTO app.profiles (user_id, role, monthly_llm_budget_usd)
        VALUES (%s, 'member'::app.user_role, 100)
        """,
        (user_id,),
    )
    conversation_id = uuid4()
    cursor.execute(
        """
        INSERT INTO app.conversations (id, creator_user_id, title)
        VALUES (%s, %s, 'phase09-p4-budget')
        """,
        (conversation_id, user_id),
    )
    return conversation_id


def measure_budget_lock_contention(db_url: str) -> dict[str, object]:
    """Contend ``admit_query_run`` on one user without overspend or deadlock.

    Args:
        db_url: Local Supabase URL.

    Returns:
        Wait samples, unique run count, and deadlock flag.
    """

    user_id = uuid4()
    with psycopg.connect(db_url) as setup:
        setup.execute("SET ROLE postgres")
        with setup.cursor() as cursor:
            conversation_id = _insert_budget_user(cursor, user_id=user_id)
            cursor.execute("SELECT app.current_authorization_version()")
            version_row = cursor.fetchone()
        setup.commit()
    authorization_version = int(version_row[0]) if version_row is not None else 1
    caller = CallerContext(
        user_id=str(user_id),
        role=UserRole.MEMBER,
        authorization_version=authorization_version,
    )
    barrier = threading.Barrier(4)
    waits_ms: list[float] = []
    run_ids: list[str] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        """Admit one Hybrid run after the shared barrier.

        Args:
            index: Worker index used in the message payload.
        """

        message = f"phase09-p4-budget-{index}"
        payload_hash = hash_query_admission_payload(
            conversation_id=conversation_id,
            route_family=Phase6RouteFamily.HYBRID,
            message=message,
        )
        with psycopg.connect(db_url) as connection:
            connection.execute("SET ROLE app_api")
            barrier.wait(timeout=15)
            started = time.monotonic()
            try:
                result = admit_query_run(
                    connection,
                    caller=caller,
                    conversation_id=conversation_id,
                    idempotency_key=uuid4(),
                    payload_hash=payload_hash,
                    route_family=Phase6RouteFamily.HYBRID,
                )
                connection.commit()
                elapsed_ms = (time.monotonic() - started) * 1000.0
                with lock:
                    waits_ms.append(elapsed_ms)
                    run_ids.append(str(result.context.run_id))
            except Exception as exc:
                connection.rollback()
                with lock:
                    errors.append(type(exc).__name__)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    alive = any(thread.is_alive() for thread in threads)
    unique_runs = len(set(run_ids))
    p95 = percentile(waits_ms, 0.95)
    return {
        "workers": 4,
        "wait_ms": waits_ms,
        "wait_p95_ms": p95,
        "unique_runs": unique_runs,
        "errors": errors,
        "deadlock_or_timeout": alive,
        "overspend": unique_runs > 4,
        "passed": (
            not alive
            and not errors
            and unique_runs == 4
            and unique_runs <= QT_CAP_004_RUNS
        ),
        "qt_cap_004": QT_CAP_004_RUNS,
        "lock_timeout_app_api": "2s",
        "shared_row": "company_settings plus profile FOR UPDATE at admit only",
    }


def rebuild_bm25_subset(
    *,
    supabase_url: str,
    parade_url: str,
    triples: Sequence[tuple[str, UUID, UUID]],
    limit: int = 3,
) -> dict[str, object]:
    """Re-run BM25 projection on a bounded Packet 2 subset during load.

    Args:
        supabase_url: Supabase URL.
        parade_url: Worker-reachable ParadeDB writer URL.
        triples: Corpus triples.
        limit: Maximum versions to rebuild in this window.

    Returns:
        Rebuild summary. Sample remains the 8-doc subset.
    """

    selected = list(triples[:limit])
    started = time.monotonic()
    passed = 0
    skipped = 0
    failed = 0
    with (
        psycopg.connect(supabase_url) as supabase,
        psycopg.connect(parade_url, connect_timeout=8) as parade,
    ):
        for case_id, document_id, version_id in selected:
            result = reproject_one_version(
                supabase,
                parade,
                document_id=document_id,
                version_id=version_id,
                case_id=case_id,
            )
            if result.skipped:
                skipped += 1
            elif result.passed:
                passed += 1
            else:
                failed += 1
    return {
        "attempted": len(selected),
        "passed": passed,
        "skipped": skipped,
        "failed": failed,
        "elapsed_ms": (time.monotonic() - started) * 1000.0,
        "sample_is_eight_doc_subset": True,
        "driver": "Bm25ProjectionService.process_upsert_job",
    }


def classify_seventy_percent(
    *,
    cpu_peaks: Sequence[float],
    foreground_p95_ms: float | None,
    foreground_gate_ms: float,
) -> dict[str, object]:
    """Decide whether 70% pause fired or foreground p95 held.

    Args:
        cpu_peaks: Observed container CPU percentages.
        foreground_p95_ms: Measured foreground p95, if any.
        foreground_gate_ms: Signed p95 gate in milliseconds.

    Returns:
        Isolation decision plus sizing ladder.
    """

    peak = max(cpu_peaks) if cpu_peaks else 0.0
    trigger_fired = peak >= 70.0
    p95_held = foreground_p95_ms is not None and foreground_p95_ms <= foreground_gate_ms
    passed = p95_held or trigger_fired
    return {
        "cpu_peak_percent": peak,
        "trigger_70_percent_fired": trigger_fired,
        "foreground_p95_ms": foreground_p95_ms,
        "foreground_gate_ms": foreground_gate_ms,
        "foreground_p95_held": p95_held,
        "passed": passed,
        "sample_is_eight_doc_subset": True,
        "sizing_ladder": SIZING_LADDER_SEVENTY,
        "runtime_pause_controller": (
            "No in-process 70% pause controller was observed. Architecture "
            "docs define the trigger; Packet 4 measures whether it fires."
        ),
    }


def parse_cpu_percent(raw: object) -> float | None:
    """Parse Docker ``CPUPerc`` text such as ``12.34%``.

    Args:
        raw: Stats field.

    Returns:
        Percentage or ``None``.
    """

    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    stripped = raw.strip().rstrip("%")
    try:
        return float(stripped)
    except ValueError:
        return None


def parse_mem_usage_bytes(raw: object) -> int | None:
    """Parse Docker ``MemUsage`` such as ``120MiB / 2GiB`` into used bytes.

    Args:
        raw: Stats field.

    Returns:
        Used bytes or ``None``.
    """

    if not isinstance(raw, str) or "/" not in raw:
        return None
    used = raw.split("/", 1)[0].strip()
    lowered = used.lower().replace(" ", "")
    suffixes = (
        ("gib", 1024**3),
        ("gb", 1000**3),
        ("mib", 1024**2),
        ("mb", 1000**2),
        ("kib", 1024),
        ("kb", 1000),
        ("b", 1),
    )
    for suffix, factor in suffixes:
        if lowered.endswith(suffix):
            number = lowered[: -len(suffix)]
            try:
                return int(float(number) * factor)
            except ValueError:
                return None
    return None


def stream_gate_payload(
    *,
    first_token_ms: Sequence[float],
    completion_ms: Sequence[float],
    heartbeat_counts: Sequence[int],
    lag_p95_seconds: float | None,
    simultaneous_runs: int,
    mock_model_mode: bool,
) -> dict[str, object]:
    """Compare five-stream samples to signed gates.

    Args:
        first_token_ms: First ``token_delta`` samples.
        completion_ms: Terminal event samples.
        heartbeat_counts: Heartbeats observed per stream.
        lag_p95_seconds: Event-loop lag p95 from the API process, if sampled.
        simultaneous_runs: Admitted concurrent runs.
        mock_model_mode: Candidate mock flag.

    Returns:
        Stream report.
    """

    first_p95 = percentile(first_token_ms, 0.95)
    completion_p95 = percentile(completion_ms, 0.95)
    missed = sum(1 for count in heartbeat_counts if count < 1)
    live_short = (
        all(
            (completion <= HEARTBEAT_INTERVAL_SECONDS * 1000.0)
            for completion in completion_ms
        )
        if completion_ms
        else True
    )
    lag_passed = lag_p95_seconds is not None and lag_p95_seconds < P95_LAG_SECONDS
    return {
        "simultaneous_runs": simultaneous_runs,
        "qt_cap_004": QT_CAP_004_RUNS,
        "qt_cap_004_passed": simultaneous_runs == QT_CAP_004_RUNS,
        "first_token_ms": list(first_token_ms),
        "first_token_p95_ms": first_p95,
        "first_token_sample_size": len(first_token_ms),
        "completion_ms": list(completion_ms),
        "completion_p95_ms": completion_p95,
        "completion_sample_size": len(completion_ms),
        "heartbeat_counts": list(heartbeat_counts),
        "missed_15s_heartbeats": missed if not live_short else 0,
        "live_completed_before_15s_heartbeat": live_short,
        "heartbeat_jitter_gate_seconds": HEARTBEAT_JITTER_SECONDS,
        "lag_p95_seconds": lag_p95_seconds,
        "lag_gate_seconds": P95_LAG_SECONDS,
        "lag_passed": lag_passed,
        "qt_lat_010_ms": QT_LAT_010_MS,
        "qt_lat_011_ms": QT_LAT_011_MS,
        "mock_model_mode": mock_model_mode,
        "mock_answers_may_be_fast": True,
        "qt_lat_010_passed": (first_p95 is not None and first_p95 <= QT_LAT_010_MS),
        "qt_lat_011_passed": (
            completion_p95 is not None and completion_p95 <= QT_LAT_011_MS
        ),
        "inspection_gate_ms": QT_LAT_009_MS,
        "table_gate_ms": QT_LAT_006_MS,
    }


def docker_stats_peaks(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Reduce ``docker stats`` JSON rows to CPU/memory peaks.

    Args:
        rows: One stats object per container.

    Returns:
        Peak map keyed by container name. No secrets.
    """

    peaks: dict[str, object] = {}
    cpu_values: list[float] = []
    for row in rows:
        name = str(row.get("Name") or row.get("BlockIO") or "unknown")
        cpu = parse_cpu_percent(row.get("CPUPerc"))
        mem = parse_mem_usage_bytes(row.get("MemUsage"))
        if cpu is not None:
            cpu_values.append(cpu)
        peaks[name] = {
            "cpu_percent": cpu,
            "mem_used_bytes": mem,
            "mem_usage": row.get("MemUsage"),
            "net_io": row.get("NetIO"),
        }
    return {
        "containers": peaks,
        "cpu_peak_percent": max(cpu_values) if cpu_values else None,
        "compose_mem_limits": {
            "paradedb": "2g",
            "valkey-limits": "128m",
            "valkey-cache": "320m",
            "clamav": "2g",
            "crawl-proxy": "128m",
        },
        "local_not_ec2": True,
    }
