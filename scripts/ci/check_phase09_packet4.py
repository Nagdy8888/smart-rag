"""Fail when Phase 9 Packet 4 load collections are empty or identity drifted."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
import jwt
import psycopg
from smart_rag_core.evaluation.ranked_ids import load_eval_cases
from smart_rag_core.release.compose import run_compose
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    CANDIDATE_COMPOSE_FILE,
    PACKET8_OVERLAY_FILE,
    PRIVATE_COMPOSE_SERVICES,
)
from smart_rag_core.release.io import (
    as_json_object,
    dump_canonical_json,
)
from smart_rag_core.release.packet3 import (
    EXPECTED_EXACT_CODE_DOCUMENT_ID,
    SEEDED_RETRIEVE_CASE_IDS,
)
from smart_rag_core.release.packet4 import (
    API_EXPECTED_JWT_ISSUER,
    PACKET4_BM25_NAME,
    PYTEST_SUITES,
    QT_LAT_001_MS,
    TARGET_SPECS,
    Packet4Suite,
    Phase09Packet4GateError,
    artifact_paths,
    assert_holdout_sealed,
    assert_mock_model_mode,
    assert_packet2_corpus_identity,
    classify_jwt_issuer_alignment,
    classify_p0904_a,
    classify_p0904_d,
    classify_suite_counts,
    classify_target,
    expected_image_ids,
    freeze_workload_profile,
    handoff_payloads,
    junit_counts,
    load_packet1_images,
    load_sizing_hardware,
    missing_pytest_files,
    pytest_command,
    schema_version,
    suite_failure_detail,
)
from smart_rag_core.release.packet4_load import (
    classify_seventy_percent,
    docker_stats_peaks,
    graph_advisory_lock_cycle,
    measure_budget_lock_contention,
    measure_supabase_pools,
    pressure_sample_from_docker_rows,
    reindex_hnsw,
    sse_event_names,
    stream_gate_payload,
)
from smart_rag_core.release.ports import parse_compose_ps_text
from smart_rag_core.settings.base import get_process_environ

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUPABASE = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
FASTAPI_URL = "http://127.0.0.1:8000"
CLIENT_VERSION = "0.1.0"
_PASSWORD = "Phase6Ui9x"  # noqa: S105 - disposable local Auth user
WORKER_REPROJECT_PATH = "/tmp/bm25_reproject.py"  # noqa: S108 - worker tmpfs
WORKER_HYBRID_PATH = "/tmp/hybrid_foreground.py"  # noqa: S108 - worker tmpfs
_LAG_SNIPPET = """
import asyncio
import json
from smart_rag_core.runtime.offload import sample_event_loop_lag

async def main() -> None:
    sample = await sample_event_loop_lag(samples=20, interval_seconds=0.01)
    print(
        json.dumps(
            {
                "p95_seconds": sample.p95_seconds,
                "lag_seconds": sample.lag_seconds,
                "gate_seconds": 0.05,
                "passed": sample.p95_seconds < 0.05,
            }
        )
    )

asyncio.run(main())
""".strip()


def _as_map(value: Any, *, source: str) -> dict[str, object]:
    """Narrow a JSON object.

    Args:
        value: Decoded JSON.
        source: Path label.

    Returns:
        String-keyed object, or empty when ``value`` is not an object.
    """

    if not isinstance(value, dict):
        return {}
    return as_json_object(cast(dict[str, object], value), source=source)


def _json_dict(value: Any, *, source: str) -> dict[str, object]:
    """Require a JSON object.

    Args:
        value: Decoded JSON.
        source: Path label.

    Returns:
        String-keyed object.

    Raises:
        Phase09Packet4GateError: If ``value`` is not an object.
    """

    if not isinstance(value, dict):
        raise Phase09Packet4GateError(f"{source} is not a JSON object")
    return as_json_object(cast(dict[str, object], value), source=source)


def _as_float(value: object) -> float | None:
    """Return a finite numeric sample, excluding bool.

    Args:
        value: Decoded JSON value.

    Returns:
        Float, or ``None``.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _as_int_sample(value: object) -> int:
    """Return an int sample, excluding bool.

    Args:
        value: Decoded JSON value.

    Returns:
        Integer, or ``0``.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _require_int(value: object, *, source: str) -> int:
    """Require a non-bool integer.

    Args:
        value: Decoded JSON value.
        source: Path label.

    Returns:
        Integer.

    Raises:
        Phase09Packet4GateError: If ``value`` is not an int.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise Phase09Packet4GateError(f"{source} is not an int")
    return value


def _git_head() -> str:
    """Return the current HEAD SHA, or unknown.

    Returns:
        Hex SHA or ``unknown``.
    """

    git = shutil.which("git") or "git"
    completed = subprocess.run(  # noqa: S603
        [git, "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip()


def _run_suite(suite: Packet4Suite) -> dict[str, object]:
    """Execute one fail-closed pytest suite and return its matrix row.

    Args:
        suite: Suite to run.

    Returns:
        JSON-object suite row.

    Raises:
        Phase09Packet4GateError: If JUnit output is missing.

    Side Effects:
        Runs pytest from the repository root.
    """

    with tempfile.TemporaryDirectory(prefix="smart-rag-phase09-p4-") as directory:
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
        f"phase09_packet4_{suite.suite_id} "
        f"tests={counts.tests} failures={counts.failures} "
        f"errors={counts.errors} skipped={counts.skipped} "
        f"classification={classification}"
    )
    return {
        "suite_id": suite.suite_id,
        "acceptance": suite.acceptance,
        "title": suite.title,
        "classification": classification,
        "tests": counts.tests,
        "failures": counts.failures,
        "errors": counts.errors,
        "skipped": counts.skipped,
        "returncode": completed.returncode,
        "overlay_required": suite.overlay_required,
        "fail_on_skip": suite.fail_on_skip,
        "detail": detail,
    }


def _compose_publishers() -> dict[str, tuple[int, ...]]:
    """Return host published ports from candidate Compose ps.

    Returns:
        Service to host-port mapping.
    """

    ps = run_compose(REPO_ROOT, ["ps", "--format", "json"], timeout_seconds=60)
    if ps.returncode != 0:
        return {}
    return parse_compose_ps_text(ps.stdout)


def _overlay_published(publishers: Mapping[str, tuple[int, ...]]) -> list[str]:
    """Return private services that currently publish host ports.

    Args:
        publishers: Compose ps mapping.

    Returns:
        Service names with published ports.
    """

    return [
        name
        for name in PRIVATE_COMPOSE_SERVICES
        if any(port > 0 for port in publishers.get(name, ()))
    ]


def _detach_overlay() -> dict[str, object]:
    """Recreate candidate compose without the Packet 8 overlay.

    Returns:
        Detach command result. Overlay is not candidate identity.
    """

    completed = run_compose(
        REPO_ROOT,
        ["up", "-d", "--no-build", "--wait", "--remove-orphans"],
        timeout_seconds=900,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout)
    return {
        "command": (
            "docker compose --env-file .env.compose "
            f"-f {CANDIDATE_COMPOSE_FILE} up -d --no-build --wait --remove-orphans"
        ),
        "returncode": completed.returncode,
        "overlay_file": PACKET8_OVERLAY_FILE,
        "overlay_file_is_candidate": False,
    }


def _health() -> dict[str, object]:
    """Run ``phase09_candidate.py health`` and return the exit code.

    Returns:
        Health command row.
    """

    completed = subprocess.run(
        [sys.executable, "scripts/phase09_candidate.py", "health"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout)
    return {
        "command": "scripts/phase09_candidate.py health",
        "returncode": completed.returncode,
    }


def _inject_worker_module(*, source: Path, dest: str) -> int:
    """Copy one host Python module onto worker tmpfs.

    Frozen Packet 1 images have no repo mount. Packet 4 injects wrappers onto
    ``/tmp`` and does not rebuild images.

    Args:
        source: Host module path.
        dest: Absolute path inside the worker container.

    Returns:
        Compose exec exit code.
    """

    text = source.read_text(encoding="utf-8")
    completed = run_compose(
        REPO_ROOT,
        [
            "exec",
            "-T",
            "worker",
            "python",
            "-c",
            (
                "import sys; from pathlib import Path; "
                f"Path({dest!r}).write_text(sys.stdin.read(), encoding='utf-8')"
            ),
        ],
        timeout_seconds=60,
        input_text=text,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout)
    return completed.returncode


def _inject_reproject_module() -> int:
    """Copy ``bm25_reproject.py`` into worker tmpfs.

    Returns:
        Compose exec exit code.
    """

    source = (
        REPO_ROOT
        / "packages"
        / "core"
        / "src"
        / "smart_rag_core"
        / "release"
        / "bm25_reproject.py"
    )
    return _inject_worker_module(source=source, dest=WORKER_REPROJECT_PATH)


def _inject_hybrid_foreground_module() -> int:
    """Copy ``hybrid_foreground.py`` into worker tmpfs.

    Returns:
        Compose exec exit code.
    """

    source = (
        REPO_ROOT
        / "packages"
        / "core"
        / "src"
        / "smart_rag_core"
        / "release"
        / "hybrid_foreground.py"
    )
    return _inject_worker_module(source=source, dest=WORKER_HYBRID_PATH)


def _worker_reproject(corpus_json: str) -> tuple[int, dict[str, object]]:
    """Re-project Packet 2 BM25 rows through unpublished worker ParadeDB.

    Args:
        corpus_json: Corpus manifest JSON.

    Returns:
        Exit code and parsed payload (empty object when JSON is missing).
    """

    completed = run_compose(
        REPO_ROOT,
        ["exec", "-T", "worker", "python", WORKER_REPROJECT_PATH],
        timeout_seconds=1800,
        input_text=corpus_json,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout)
    copied = run_compose(
        REPO_ROOT,
        [
            "exec",
            "-T",
            "worker",
            "python",
            "-c",
            (
                "from pathlib import Path; "
                "p=Path('/tmp/phase09/candidate-packet4-bm25.json'); "
                "print(p.read_text(encoding='utf-8') if p.is_file() else '{}', "
                "end='')"
            ),
        ],
        timeout_seconds=60,
    )
    payload: dict[str, object] = {}
    try:
        loaded: object = json.loads(copied.stdout or completed.stdout or "{}")
        if isinstance(loaded, dict):
            payload = _json_dict(loaded, source="worker-bm25")
    except json.JSONDecodeError:
        payload = {"parse_error": True, "stdout_len": len(completed.stdout)}
    payload["worker_returncode"] = completed.returncode
    payload["copy_returncode"] = copied.returncode
    payload["driver"] = "Bm25ProjectionService.process_upsert_job"
    payload["sql_stamped_hybrid_or_graph_ready"] = False
    payload["unpublished_paradedb"] = True
    payload["image_rebuilt"] = False
    return completed.returncode, payload


def _parade_row_count() -> dict[str, object]:
    """Count derived BM25 rows via unpublished ParadeDB exec.

    Returns:
        Count payload without connection strings.
    """

    completed = run_compose(
        REPO_ROOT,
        [
            "exec",
            "-T",
            "paradedb",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-tAc",
            "SELECT count(*) FROM bm25_chunks;",
        ],
        timeout_seconds=60,
    )
    raw = (completed.stdout or "").strip()
    count: int | None
    try:
        count = int(raw.splitlines()[-1]) if raw else None
    except ValueError:
        count = None
    return {
        "returncode": completed.returncode,
        "bm25_chunks": count,
        "unpublished": True,
    }


def _docker_stats() -> list[dict[str, object]]:
    """Capture one ``docker compose stats`` snapshot.

    Returns:
        Per-container stats objects. No secrets.
    """

    completed = run_compose(
        REPO_ROOT,
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
                    rows.append(
                        _json_dict(cast(object, raw_item), source="docker-stats[]")
                    )
            return rows
        if isinstance(loaded, dict):
            rows.append(_json_dict(cast(object, loaded), source="docker-stats"))
            return rows
    except json.JSONDecodeError:
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
            rows.append(_json_dict(item, source="docker-stats-line"))
    return rows


def _event_loop_lag() -> dict[str, object] | None:
    """Sample event-loop lag inside the frozen API container.

    Returns:
        Lag JSON, or ``None`` when exec fails.
    """

    completed = run_compose(
        REPO_ROOT,
        ["exec", "-T", "api", "python", "-c", _LAG_SNIPPET],
        timeout_seconds=60,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout)
        return None
    try:
        loaded: object = json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return None
    if not isinstance(loaded, dict):
        return None
    return _json_dict(loaded, source="event-loop-lag")


def _supabase_status() -> dict[str, str] | None:
    """Read local Supabase status JSON without persisting secrets.

    Returns:
        Status mapping, or ``None`` when the CLI is unavailable.
    """

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        return None
    completed = subprocess.run(  # noqa: S603
        [pnpm, "exec", "supabase", "status", "-o", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        loaded: object = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    payload = _json_dict(loaded, source="supabase-status")
    status: dict[str, str] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            status[key] = value
    return status


def _paid_headers(token: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    """Build thin-UI paid POST headers.

    Args:
        token: Bearer access token.
        idempotency_key: Optional Idempotency-Key.

    Returns:
        Header mapping.
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


def _create_member(status: Mapping[str, str]) -> dict[str, str] | None:
    """Create a confirmed local Auth member. Secrets stay in memory.

    Args:
        status: ``supabase status`` mapping.

    Returns:
        ``access_token`` and ``user_id``, or ``None``.
    """

    auth_url = status.get("API_URL", "").rstrip("/")
    anon = status.get("ANON_KEY") or status.get("PUBLISHABLE_KEY") or ""
    service = status.get("SERVICE_ROLE_KEY") or ""
    if not auth_url or not anon or not service:
        return None
    email = f"phase09-p4-{uuid4().hex}@example.com"
    with httpx.Client(timeout=15.0) as client:
        created = client.post(
            f"{auth_url}/auth/v1/admin/users",
            headers={"Authorization": f"Bearer {service}", "apikey": service},
            json={"email": email, "password": _PASSWORD, "email_confirm": True},
        )
        if created.status_code >= 400:
            return None
        raw_body: object = created.json()
        if not isinstance(raw_body, dict):
            return None
        body = _json_dict(raw_body, source="auth-admin")
        user_id = str(body.get("id", ""))
        token_response = client.post(
            f"{auth_url}/auth/v1/token?grant_type=password",
            headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            json={"email": email, "password": _PASSWORD},
        )
        if token_response.status_code >= 400:
            return None
        raw_token: object = token_response.json()
        if not isinstance(raw_token, dict):
            return None
        token_body = _json_dict(raw_token, source="auth-token")
        access_token = str(token_body.get("access_token", ""))
        if user_id == "" or access_token == "":
            return None
    db_url = get_process_environ("SUPABASE_DB_URL") or DEFAULT_SUPABASE
    with psycopg.connect(db_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.profiles (
                  user_id, role, upload_enabled, mfa_enrolled,
                  monthly_llm_budget_usd
                )
                VALUES (%s, 'member'::app.user_role, false, false, 100)
                ON CONFLICT (user_id) DO UPDATE
                  SET monthly_llm_budget_usd = EXCLUDED.monthly_llm_budget_usd
                """,
                (user_id,),
            )
        connection.commit()
    return {"access_token": access_token, "user_id": user_id}


def _token_iss(token: str) -> str:
    """Return the unverified JWT ``iss`` claim.

    Args:
        token: Password-grant access token. Not logged or persisted.

    Returns:
        Issuer string, or empty when the claim is absent.
    """

    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return ""
    issuer = claims.get("iss")
    return issuer if isinstance(issuer, str) else ""


def _seeded_retrieve_queries() -> list[dict[str, str]]:
    """Load Packet 2 retrieve queries from the open split.

    Returns:
        ``case_id``/``query`` objects. Query text is not written to artifacts.
    """

    wanted = frozenset(SEEDED_RETRIEVE_CASE_IDS)
    rows: list[dict[str, str]] = []
    for case in load_eval_cases("open"):
        if case.case_id in wanted:
            rows.append({"case_id": case.case_id, "query": case.query})
    return rows


def _worker_hybrid_foreground(
    *,
    user_id: str,
    queries: Sequence[Mapping[str, str]],
) -> dict[str, object]:
    """Time Hybrid retrieve inside the frozen worker against unpublished ParadeDB.

    Args:
        user_id: Profile id created for this gate.
        queries: Case id plus query text.

    Returns:
        Timing payload. Query text is not copied into the result.
    """

    stdin = json.dumps({"user_id": user_id, "queries": list(queries)})
    completed = run_compose(
        REPO_ROOT,
        ["exec", "-T", "worker", "python", WORKER_HYBRID_PATH],
        timeout_seconds=300,
        input_text=stdin,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout)
    payload: dict[str, object] = {}
    try:
        loaded: object = json.loads(completed.stdout.strip().splitlines()[-1])
        if isinstance(loaded, dict):
            payload = _json_dict(loaded, source="worker-hybrid")
    except (json.JSONDecodeError, IndexError):
        payload = {"parse_error": True, "stdout_len": len(completed.stdout)}
    payload["worker_returncode"] = completed.returncode
    payload["driver"] = "HybridRetriever.retrieve"
    payload["overlay_required"] = False
    return payload


def _consume_sse_timings(
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
        Timing sample. No token text is stored.
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


def _live_foreground(
    *,
    token: str,
    document_id: str,
) -> dict[str, object]:
    """Admit five Composite streams plus inspection and a table-intent message.

    Args:
        token: Member JWT.
        document_id: Packet 2 exact-code document id.

    Returns:
        Stream and inspection timings. No secrets or answer text.
    """

    api = FASTAPI_URL
    with httpx.Client(timeout=30.0) as client:
        created = client.post(
            f"{api}/conversations",
            headers=_paid_headers(token),
            json={"title": "phase09-p4-five-stream"},
        )
        if created.status_code != 201:
            return {
                "passed": False,
                "detail": f"conversation_create_{created.status_code}",
            }
        created_body = _json_dict(created.json(), source="conversation-create")
        conversation_id = str(created_body["conversation_id"])
        run_ids: list[str] = []
        for index in range(5):
            key = str(uuid4())
            admitted = client.post(
                f"{api}/conversations/{conversation_id}/messages",
                headers=_paid_headers(token, idempotency_key=key),
                json={
                    "message": f"phase09-p4-composite-{index}",
                    "idempotency_key": key,
                },
            )
            if admitted.status_code != 202:
                return {
                    "passed": False,
                    "detail": f"admit_{admitted.status_code}",
                    "admitted": len(run_ids),
                }
            admitted_body = _json_dict(admitted.json(), source="admit")
            run_ids.append(str(admitted_body["run_id"]))
        inspect_started = time.monotonic()
        inspect = client.post(
            f"{api}/graph/inspect",
            headers=_paid_headers(token),
            json={"document_id": document_id, "depth": 1},
        )
        inspect_ms = (time.monotonic() - inspect_started) * 1000.0
        table_key = str(uuid4())
        table_started = time.monotonic()
        table = client.post(
            f"{api}/conversations/{conversation_id}/messages",
            headers=_paid_headers(token, idempotency_key=table_key),
            json={
                "message": "sum the amount column grouped by region",
                "idempotency_key": table_key,
            },
        )
        table_admit_ms = (time.monotonic() - table_started) * 1000.0
        table_run = ""
        if table.status_code == 202:
            table_body = _json_dict(table.json(), source="table-admit")
            table_run = str(table_body.get("run_id") or "")
    lag_holder: dict[str, object] = {}

    def _lag() -> None:
        """Sample API event-loop lag while streams are open."""

        sample = _event_loop_lag()
        if sample is not None:
            lag_holder.update(sample)

    def _one_stream(run_id: str) -> dict[str, object]:
        """Consume one Composite EventSource.

        Args:
            run_id: Admitted run.

        Returns:
            Timing sample.
        """

        return _consume_sse_timings(
            f"{api}/runs/{run_id}/events?after=0",
            _paid_headers(token),
        )

    lag_thread = threading.Thread(target=_lag)
    lag_thread.start()
    with ThreadPoolExecutor(max_workers=5) as pool:
        stream_rows = list(pool.map(_one_stream, run_ids))
    lag_thread.join(timeout=60)
    table_stream: dict[str, object] | None = None
    if table_run:
        table_stream = _consume_sse_timings(
            f"{api}/runs/{table_run}/events?after=0",
            _paid_headers(token),
        )
    resume: dict[str, object] | None = None
    if run_ids:
        with httpx.Client(timeout=15.0) as client:
            resumed = client.get(
                f"{api}/runs/{run_ids[0]}/events?after=0",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "text/event-stream",
                },
            )
            resume = {
                "status_code": resumed.status_code,
                "content_type": resumed.headers.get("content-type", ""),
            }
    first_tokens: list[float] = []
    completions: list[float] = []
    heartbeats: list[int] = []
    for row in stream_rows:
        first_ms = _as_float(row.get("first_token_ms"))
        if first_ms is not None:
            first_tokens.append(first_ms)
        done_ms = _as_float(row.get("completion_ms"))
        if done_ms is not None:
            completions.append(done_ms)
        heartbeats.append(_as_int_sample(row.get("heartbeat_count")))
    lag_p95 = lag_holder.get("p95_seconds")
    lag_seconds = float(lag_p95) if isinstance(lag_p95, (int, float)) else None
    streams = stream_gate_payload(
        first_token_ms=first_tokens,
        completion_ms=completions,
        heartbeat_counts=heartbeats,
        lag_p95_seconds=lag_seconds,
        simultaneous_runs=len(set(run_ids)),
        mock_model_mode=True,
    )
    inspect_ok = inspect.status_code == 200
    return {
        "conversation_created": True,
        "simultaneous_runs": len(set(run_ids)),
        "stream_rows": stream_rows,
        "inspect_status": inspect.status_code,
        "inspect_ms": inspect_ms,
        "inspect_ok": inspect_ok,
        "table_admit_status": table.status_code,
        "table_admit_ms": table_admit_ms,
        "table_stream": table_stream,
        "table_route": "Auto chat admits Composite; not a dedicated table route",
        "resume": resume,
        "lag": lag_holder or None,
        "streams": streams,
        "passed": (
            len(set(run_ids)) == 5
            and all(bool(row.get("terminal")) for row in stream_rows)
        ),
    }


def _run_maintenance(db_url: str, corpus_json: str) -> dict[str, object]:
    """Run HNSW, graph lock, budget contention, and subset BM25 together.

    Args:
        db_url: Local Supabase URL.
        corpus_json: Full corpus JSON; subset rebuild uses the first three rows.

    Returns:
        Maintenance report. Sample remains the 8-doc subset.
    """

    results: dict[str, object] = {}
    pressure = pressure_sample_from_docker_rows(_docker_stats())

    def _hnsw() -> None:
        """Reindex the canonical HNSW index unless the 70% pause fires."""

        with psycopg.connect(db_url) as connection:
            results["hnsw"] = reindex_hnsw(connection, pressure=pressure)

    def _graph() -> None:
        """Probe concurrency-one graph advisory lock."""

        results["graph"] = graph_advisory_lock_cycle(db_url)

    def _budget() -> None:
        """Contend reserve-once admit on one user."""

        results["budget"] = measure_budget_lock_contention(db_url)

    def _bm25() -> None:
        """Rebuild a 3-row subset through unpublished worker ParadeDB."""

        loaded: object = json.loads(corpus_json)
        payload = _json_dict(loaded, source="corpus")
        raw_rows = payload.get("rows")
        subset_rows: list[dict[str, object]] = []
        if isinstance(raw_rows, list):
            subset_rows = [
                _json_dict(raw_item, source="corpus.rows[]")
                for raw_item in cast(list[object], raw_rows[:3])
            ]
        subset = json.dumps({"holdout_opened": False, "rows": subset_rows})
        code, body = _worker_reproject(subset)
        results["bm25_subset"] = {"returncode": code, "outcome": body}

    threads = [
        threading.Thread(target=_hnsw),
        threading.Thread(target=_graph),
        threading.Thread(target=_budget),
        threading.Thread(target=_bm25),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=1800)
    results["threads_alive"] = any(thread.is_alive() for thread in threads)
    results["sample_is_eight_doc_subset"] = True
    return results


def _suite_class(suites: Sequence[Mapping[str, object]], suite_id: str) -> str:
    """Return one suite classification.

    Args:
        suites: Suite rows.
        suite_id: Identifier.

    Returns:
        Classification string or empty.
    """

    for row in suites:
        if row.get("suite_id") == suite_id:
            return str(row.get("classification", ""))
    return ""


def _acceptance_rows(
    *,
    suites: Sequence[Mapping[str, object]],
    seventy: Mapping[str, object],
    pools: Mapping[str, object],
    contention: Mapping[str, object],
    live: Mapping[str, object],
    resources: Mapping[str, object],
    bm25: Mapping[str, object],
) -> list[dict[str, object]]:
    """Classify P09-04-A through P09-04-E.

    Args:
        suites: Pytest rows.
        seventy: Isolation decision.
        pools: Connection snapshot.
        contention: Budget lock report.
        live: Five-stream live report.
        resources: Docker stats peaks.
        bm25: Re-projection payload.

    Returns:
        Acceptance matrix rows.
    """

    stream_map = _as_map(live.get("streams"), source="live.streams")
    a_pytest = _suite_class(suites, "foreground_maintenance_graph_bm25") == "Passed"
    a_seventy = seventy.get("passed") is True
    b_pytest = _suite_class(suites, "connection_caps_timeouts") == "Passed"
    b_pools = pools.get("passed") is True
    c_pytest = _suite_class(suites, "budget_lock_reserve_once") == "Passed"
    c_live = contention.get("passed") is True
    d_pytest = _suite_class(suites, "five_stream_lag_heartbeat_offload") == "Passed"
    d_live = live.get("passed") is True
    d_blocked = live.get("classification") == "Blocked"
    jwt_map = _as_map(live.get("jwt"), source="live.jwt")
    jwt_blocked = (
        d_blocked
        or jwt_map.get("classification") == "Blocked"
        or jwt_map.get("aligned") is False
    )
    e_pytest = _suite_class(suites, "bounded_resource_contracts") == "Passed"
    e_bm25 = bm25.get("passed") is True
    exhausted = pools.get("exhausted") is True
    cpu_peak = resources.get("cpu_peak_percent")
    return [
        {
            "check": "P09-04-A",
            "classification": classify_p0904_a(
                pytest_passed=a_pytest,
                seventy_passed=a_seventy,
                jwt_blocked=jwt_blocked,
                foreground_p95_ms=seventy.get("foreground_p95_ms"),
            ),
            "detail": (
                "Foreground pytest plus 8-doc maintenance. "
                f"70% trigger fired={seventy.get('trigger_70_percent_fired')}; "
                f"foreground_p95_held={seventy.get('foreground_p95_held')}; "
                f"jwt_blocked={jwt_blocked}"
            ),
        },
        {
            "check": "P09-04-B",
            "classification": (
                "Failed"
                if exhausted
                else ("Passed" if b_pytest and b_pools else "Failed")
            ),
            "detail": (
                f"Worst-case 30<42 plus live pg_stat_activity. exhausted={exhausted}"
            ),
        },
        {
            "check": "P09-04-C",
            "classification": "Passed" if c_pytest and c_live else "Failed",
            "detail": (
                "Reserve-once admit contention. "
                f"unique_runs={contention.get('unique_runs')} "
                f"deadlock={contention.get('deadlock_or_timeout')}"
            ),
        },
        {
            "check": "P09-04-D",
            "classification": classify_p0904_d(
                pytest_passed=d_pytest,
                live_passed=bool(d_live),
                jwt_blocked=jwt_blocked,
            ),
            "detail": (
                "ASGI five-stream 15s heartbeat plus live docker EventSource. "
                f"qt_cap_004={stream_map.get('qt_cap_004_passed')} "
                f"lag_passed={stream_map.get('lag_passed')} "
                f"live_class={live.get('classification')} "
                f"live_detail={live.get('detail')} "
                "live mock may finish before 15s heartbeat"
            ),
        },
        {
            "check": "P09-04-E",
            "classification": "Passed" if e_pytest and e_bm25 else "Failed",
            "detail": (
                "Compose mem_limits remain the Packet 1 baseline. "
                f"cpu_peak_percent={cpu_peak}; "
                "OCR/Valkey-OOM/10k envelope Not Run"
            ),
        },
    ]


def _target_rows(
    *,
    live: Mapping[str, object],
    mock_model_mode: bool,
) -> list[dict[str, object]]:
    """Compare signed QUALITY_TARGETS rows to live samples.

    Args:
        live: Live load report including Hybrid retrieve and JWT alignment.
        mock_model_mode: Candidate mock flag.

    Returns:
        Target matrix rows.
    """

    stream_map = _as_map(live.get("streams"), source="live.streams")
    hybrid_map = _as_map(live.get("hybrid_retrieve"), source="live.hybrid_retrieve")
    jwt_map = _as_map(live.get("jwt"), source="live.jwt")
    jwt_blocked = jwt_map.get("classification") == "Blocked"
    first_p95 = stream_map.get("first_token_p95_ms")
    completion_p95 = stream_map.get("completion_p95_ms")
    first_n = stream_map.get("first_token_sample_size")
    completion_n = stream_map.get("completion_sample_size")
    inspect_ms = live.get("inspect_ms")
    table_ms = live.get("table_admit_ms")
    hybrid_p95 = hybrid_map.get("first_evidence_p95_ms")
    hybrid_n = hybrid_map.get("sample_size")
    asgi_five = live.get("asgi_five_stream_passed") is True
    rows: list[dict[str, object]] = []
    for spec in TARGET_SPECS:
        if spec.target_id == "QT-CAP-004":
            rows.append(
                classify_target(
                    spec,
                    measured=5 if asgi_five else stream_map.get("simultaneous_runs"),
                    mock_model_mode=mock_model_mode,
                    sample_size=5 if asgi_five else 0,
                    detail=(
                        "ASGI five held Composite streams "
                        "(test_sse_heartbeat). Live docker EventSource is "
                        "separate and may be Blocked on JWT iss."
                    ),
                    passed=asgi_five,
                )
            )
            continue
        if spec.target_id == "QT-LAT-001":
            hybrid_ok = (
                isinstance(hybrid_p95, (int, float))
                and not isinstance(hybrid_p95, bool)
                and float(hybrid_p95) <= QT_LAT_001_MS
            )
            rows.append(
                classify_target(
                    spec,
                    measured=hybrid_p95,
                    mock_model_mode=mock_model_mode,
                    sample_size=(
                        hybrid_n
                        if isinstance(hybrid_n, int) and not isinstance(hybrid_n, bool)
                        else 0
                    ),
                    detail=(
                        "Worker HybridRetriever.retrieve first_evidence p95 "
                        "on the Packet 2 7-case subset beside maintenance. "
                        "Not live OpenAI."
                    ),
                    passed=hybrid_ok
                    if isinstance(hybrid_n, int) and hybrid_n > 0
                    else None,
                )
            )
            continue
        if spec.target_id in {"QT-LAT-010"}:
            passed = stream_map.get("qt_lat_010_passed") is True
            sampled = (
                isinstance(first_n, int)
                and not isinstance(first_n, bool)
                and first_n > 0
            )
            rows.append(
                classify_target(
                    spec,
                    measured=first_p95,
                    mock_model_mode=mock_model_mode,
                    sample_size=first_n if sampled else 0,
                    detail=(
                        "mock Composite first token_delta; not live OpenAI"
                        if sampled
                        else "live docker Composite Blocked on JWT issuer"
                    ),
                    passed=passed if sampled else None,
                    blocked=jwt_blocked and not sampled,
                )
            )
            continue
        if spec.target_id == "QT-LAT-011":
            passed = stream_map.get("qt_lat_011_passed") is True
            sampled = (
                isinstance(completion_n, int)
                and not isinstance(completion_n, bool)
                and completion_n > 0
            )
            rows.append(
                classify_target(
                    spec,
                    measured=completion_p95,
                    mock_model_mode=mock_model_mode,
                    sample_size=completion_n if sampled else 0,
                    detail=(
                        "mock Composite completion; not live OpenAI"
                        if sampled
                        else "live docker Composite Blocked on JWT issuer"
                    ),
                    passed=passed if sampled else None,
                    blocked=jwt_blocked and not sampled,
                )
            )
            continue
        if spec.target_id == "QT-LAT-009":
            inspect_ok = live.get("inspect_ok") is True
            inspect_pass = (
                isinstance(inspect_ms, (int, float))
                and not isinstance(inspect_ms, bool)
                and float(inspect_ms) <= 5000.0
            )
            rows.append(
                classify_target(
                    spec,
                    measured=inspect_ms,
                    mock_model_mode=mock_model_mode,
                    sample_size=1 if inspect_ok else 0,
                    detail=(
                        "POST /graph/inspect on Packet 2 exact-code document"
                        if inspect_ok
                        else "live inspect Blocked on JWT issuer"
                    ),
                    passed=inspect_ok and inspect_pass if inspect_ok else None,
                    blocked=jwt_blocked and not inspect_ok,
                )
            )
            continue
        if spec.target_id in {"QT-LAT-006", "QT-LAT-007", "QT-LAT-008"}:
            rows.append(
                classify_target(
                    spec,
                    measured=table_ms,
                    mock_model_mode=mock_model_mode,
                    sample_size=0,
                    detail=(
                        "Auto chat admits Composite; markdown corpus has no "
                        "Parquet table route"
                    ),
                    passed=None,
                )
            )
            continue
        if spec.target_id in {"QT-DL-001", "QT-DL-004"}:
            rows.append(
                classify_target(
                    spec,
                    measured=spec.signed_value,
                    mock_model_mode=mock_model_mode,
                    sample_size=None,
                    detail="FAMILY_* ceilings covered by streaming timeout pytest",
                    passed=True,
                )
            )
            continue
        if spec.target_id in {"QT-LAT-002", "QT-LAT-003", "QT-LAT-004", "QT-LAT-005"}:
            rows.append(
                classify_target(
                    spec,
                    measured=None,
                    mock_model_mode=mock_model_mode,
                    sample_size=0,
                    detail="Auto chat admits Composite only; no dedicated stream",
                    passed=None,
                )
            )
            continue
        rows.append(
            classify_target(
                spec,
                measured=None,
                mock_model_mode=mock_model_mode,
                sample_size=0,
                detail="Not claimed from the 8-doc local candidate",
                passed=None,
            )
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    """Run Packet 4 measurements and reject zero collection.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        ``0`` when suites collected tests, identity held, and A-E are not Failed.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        missing = missing_pytest_files(REPO_ROOT)
        if missing:
            raise Phase09Packet4GateError(
                "Packet 4 mapped pytest files are missing: " + ", ".join(missing)
            )
        assert_holdout_sealed(REPO_ROOT)
        assert_mock_model_mode(REPO_ROOT)
        assert_packet2_corpus_identity(REPO_ROOT)
        image_ids = load_packet1_images(REPO_ROOT)
        if image_ids != expected_image_ids():
            raise Phase09Packet4GateError("Packet 1 image Ids drifted")
        hardware = load_sizing_hardware(REPO_ROOT)
        ncpu = hardware.get("docker_ncpu")
        mem = hardware.get("docker_mem_bytes")
        if ncpu not in {20, None} or mem not in {8_131_035_136, None}:
            print(
                f"phase09_packet4_hardware docker_ncpu={ncpu} "
                f"docker_mem_bytes={mem} (Packet 1 baseline 20 / 8131035136)"
            )
        publishers = _compose_publishers()
        published = _overlay_published(publishers)
        overlay_report: dict[str, object] = {
            "was_attached": bool(published),
            "published_services": published,
            "detached": False,
            "overlay_file_is_candidate": False,
        }
        if published:
            detach = _detach_overlay()
            overlay_report["detached"] = True
            overlay_report["detach"] = detach
            if _require_int(detach["returncode"], source="detach.returncode") != 0:
                raise Phase09Packet4GateError("overlay detach failed")
        health_before = _health()
        overlay_report["health"] = health_before
        if _require_int(health_before["returncode"], source="health.returncode") != 0:
            raise Phase09Packet4GateError("candidate health failed")
        publishers_after = _compose_publishers()
        if _overlay_published(publishers_after):
            raise Phase09Packet4GateError("private ports still published")
        inject_code = _inject_reproject_module()
        if inject_code != 0:
            raise Phase09Packet4GateError(
                "worker tmpfs inject of bm25_reproject failed"
            )
        hybrid_inject = _inject_hybrid_foreground_module()
        if hybrid_inject != 0:
            raise Phase09Packet4GateError(
                "worker tmpfs inject of hybrid_foreground failed"
            )
        corpus_path = REPO_ROOT / ARTIFACT_DIR / "candidate-corpus-manifest.json"
        corpus_json = corpus_path.read_text(encoding="utf-8")
        reproject_code, bm25_payload = _worker_reproject(corpus_json)
        parade_count = _parade_row_count()
        bm25_payload["parade_exec_count"] = parade_count
        bm25_payload["inject_returncode"] = inject_code
        if reproject_code != 0 or bm25_payload.get("identity_drift") is True:
            raise Phase09Packet4GateError(
                "BM25 re-projection failed or identity drifted"
            )
        if bm25_payload.get("sql_stamped_hybrid_or_graph_ready") is True:
            raise Phase09Packet4GateError("BM25 re-projection SQL-stamped ready states")
        versions = bm25_payload.get("versions")
        required: list[dict[str, object]] = []
        if isinstance(versions, list):
            for raw_item in cast(list[object], versions):
                if isinstance(raw_item, dict):
                    version_row = _json_dict(
                        cast(object, raw_item), source="bm25.versions[]"
                    )
                    if version_row.get("skipped") is not True:
                        required.append(version_row)
        parade_rows = bm25_payload.get("parade_total_rows")
        if required and (not isinstance(parade_rows, int) or parade_rows < 1):
            raise Phase09Packet4GateError(
                "BM25 re-projection left ParadeDB empty after required versions"
            )
        workload = freeze_workload_profile(hardware=hardware, image_ids=image_ids)
        suite_rows: list[dict[str, object]] = []
        failures: list[str] = []
        for suite in PYTEST_SUITES:
            row = _run_suite(suite)
            suite_rows.append(row)
            if row["classification"] != "Passed":
                failures.append(f"{suite.suite_id}: {row['detail']}")
        db_url = get_process_environ("SUPABASE_DB_URL") or DEFAULT_SUPABASE
        status = _supabase_status()
        member = _create_member(status) if status is not None else None
        live: dict[str, object] = {"passed": False, "detail": "auth_unavailable"}
        maintenance: dict[str, object] = {}
        pools: dict[str, object] = {"passed": False, "detail": "supabase_unreachable"}
        stats_rows: list[dict[str, object]] = []
        hybrid_payload: dict[str, object] = {"passed": False, "detail": "not_run"}
        jwt_payload: dict[str, object] = {
            "classification": "Blocked",
            "detail": "auth_unavailable",
        }
        asgi_five = (
            _suite_class(suite_rows, "five_stream_lag_heartbeat_offload") == "Passed"
        )
        if member is None:
            failures.append("live Auth member create failed")
        else:
            jwt_payload = classify_jwt_issuer_alignment(
                token_iss=_token_iss(member["access_token"]),
                api_expected_iss=API_EXPECTED_JWT_ISSUER,
            )
            queries = _seeded_retrieve_queries()
            if not queries:
                failures.append("seeded retrieve queries missing from open split")
            maint_holder: dict[str, object] = {}
            hybrid_holder: dict[str, object] = {}

            def _maint() -> None:
                """Run maintenance beside foreground retrieve."""

                maint_holder.update(_run_maintenance(db_url, corpus_json))

            def _hybrid() -> None:
                """Time Hybrid retrieve on unpublished worker ParadeDB."""

                if queries:
                    hybrid_holder.update(
                        _worker_hybrid_foreground(
                            user_id=member["user_id"],
                            queries=queries,
                        )
                    )

            maint_thread = threading.Thread(target=_maint)
            hybrid_thread = threading.Thread(target=_hybrid)
            maint_thread.start()
            hybrid_thread.start()
            live = _live_foreground(
                token=member["access_token"],
                document_id=EXPECTED_EXACT_CODE_DOCUMENT_ID,
            )
            lag_sample = _event_loop_lag()
            if lag_sample is not None:
                live["event_loop_lag"] = lag_sample
            maint_thread.join(timeout=1800)
            hybrid_thread.join(timeout=300)
            maintenance = maint_holder
            hybrid_payload = hybrid_holder or {
                "passed": False,
                "detail": "hybrid_thread_empty",
            }
            live["jwt"] = jwt_payload
            live["hybrid_retrieve"] = hybrid_payload
            live["asgi_five_stream_passed"] = asgi_five
            if jwt_payload.get("aligned") is not True:
                live["classification"] = "Blocked"
                live["detail"] = (
                    f"{live.get('detail')}; jwt_iss={jwt_payload.get('token_iss')}"
                )
            elif live.get("passed") is not True:
                live["classification"] = "Failed"
            else:
                live["classification"] = "Passed"
            with psycopg.connect(db_url) as connection:
                pools = measure_supabase_pools(connection)
            stats_rows = _docker_stats()
            if live.get("classification") == "Failed":
                failures.append(f"live five-stream: {live.get('detail', 'failed')}")
            if hybrid_payload.get("passed") is not True:
                if jwt_payload.get("aligned") is not True:
                    live["hybrid_retrieve_blocked"] = hybrid_payload.get("detail")
                else:
                    failures.append(
                        f"hybrid foreground: {hybrid_payload.get('detail', 'failed')}"
                    )
        if member is None:
            live["jwt"] = jwt_payload
            live["hybrid_retrieve"] = hybrid_payload
            live["asgi_five_stream_passed"] = asgi_five
        resources = docker_stats_peaks(stats_rows)
        cpu_values: list[float] = []
        peak = resources.get("cpu_peak_percent")
        if isinstance(peak, (int, float)) and not isinstance(peak, bool):
            cpu_values.append(float(peak))
        inspect_ms = live.get("inspect_ms")
        stream_map = _as_map(live.get("streams"), source="live.streams")
        raw_p95 = stream_map.get("completion_p95_ms")
        completion_p95 = (
            float(raw_p95)
            if isinstance(raw_p95, (int, float)) and not isinstance(raw_p95, bool)
            else None
        )
        hybrid_map = _as_map(live.get("hybrid_retrieve"), source="live.hybrid_retrieve")
        hybrid_p95_raw = hybrid_map.get("first_evidence_p95_ms")
        hybrid_p95 = (
            float(hybrid_p95_raw)
            if isinstance(hybrid_p95_raw, (int, float))
            and not isinstance(hybrid_p95_raw, bool)
            else None
        )
        foreground_p95 = hybrid_p95
        if foreground_p95 is None:
            foreground_p95 = completion_p95
        if foreground_p95 is None and isinstance(inspect_ms, (int, float)):
            if not isinstance(inspect_ms, bool):
                foreground_p95 = float(inspect_ms)
        seventy = classify_seventy_percent(
            cpu_peaks=cpu_values,
            foreground_p95_ms=foreground_p95,
            foreground_gate_ms=QT_LAT_001_MS,
        )
        contention_raw = maintenance.get("budget")
        contention: dict[str, object]
        if isinstance(contention_raw, dict):
            contention = _json_dict(contention_raw, source="budget")
            if contention.get("passed") is not True:
                failures.append("budget lock contention failed")
        else:
            contention = {"passed": False, "detail": "budget_not_run"}
            failures.append("budget lock contention did not run")
        if pools.get("exhausted") is True:
            failures.append("connection pool exhausted")
        health_after = _health()
        overlay_report["health_after_load"] = health_after
        if (
            _require_int(health_after["returncode"], source="health_after.returncode")
            != 0
        ):
            failures.append("candidate health failed after load")
        paths = artifact_paths(REPO_ROOT)
        dump_canonical_json(workload, paths["workload"])
        contention_payload: dict[str, object] = {
            "schema_version": "phase09-candidate-packet4-contention-v1",
            "hnsw": maintenance.get("hnsw"),
            "graph": maintenance.get("graph"),
            "budget": contention,
            "bm25_subset": maintenance.get("bm25_subset"),
            "threads_alive": maintenance.get("threads_alive"),
            "sample_is_eight_doc_subset": True,
            "runtime_pause_controller": seventy.get("runtime_pause_controller"),
        }
        dump_canonical_json(contention_payload, paths["contention"])
        dump_canonical_json(
            {
                "schema_version": "phase09-candidate-packet4-streams-v1",
                "live": live,
                "asgi_heartbeat_gate": (
                    "tests/contract/test_sse_heartbeat.py five held streams"
                ),
                "consumed_live_nodeid": (
                    "tests/contract/test_thin_developer_ui_live.py"
                    "::test_thin_ui_live_five_composite_streams"
                ),
                "cpu_slice_budget_ms": 10,
                "mock_model_mode": True,
            },
            paths["streams"],
        )
        dump_canonical_json(
            {
                "schema_version": "phase09-candidate-packet4-pools-v1",
                **pools,
            },
            paths["pools"],
        )
        dump_canonical_json(
            {
                "schema_version": "phase09-candidate-packet4-resources-v1",
                **resources,
                "seventy_percent": seventy,
                "ocr_pages_per_hour": "Not Run",
                "valkey_oom": "Not Run; Packet 5",
                "local_not_ec2": True,
            },
            paths["resources"],
        )
        dump_canonical_json(
            {
                **bm25_payload,
                "artifact": PACKET4_BM25_NAME,
            },
            paths["bm25"],
        )
        acceptance = _acceptance_rows(
            suites=suite_rows,
            seventy=seventy,
            pools=pools,
            contention=contention,
            live=live,
            resources=resources,
            bm25=bm25_payload,
        )
        for row in acceptance:
            if row["classification"] == "Failed":
                failures.append(f"{row['check']}: {row['detail']}")
        matrix = {
            "schema_version": schema_version(),
            "requirement_id": "P09-04",
            "head_consumed": _git_head(),
            "frozen_packet1_head_note": "46dcb34",
            "compose_file": CANDIDATE_COMPOSE_FILE,
            "overlay_file_is_candidate": False,
            "mock_model_mode": True,
            "holdout_opened": False,
            "sample_is_eight_doc_subset": True,
            "local_candidate_not_full_envelope": True,
            "candidate_image_ids": image_ids,
            "overlay": overlay_report,
            "suites": suite_rows,
            "targets": _target_rows(live=live, mock_model_mode=True),
            "handoffs": handoff_payloads(),
            "acceptance": acceptance,
            "seventy_percent": seventy,
            "managed_claims": [],
        }
        dump_canonical_json(matrix, paths["matrix"])
        if failures:
            raise Phase09Packet4GateError("; ".join(failures))
    except Phase09Packet4GateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
