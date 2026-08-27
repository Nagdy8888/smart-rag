"""Live Compose kill/deny/fill/restart helpers for Phase 9 Packet 5.

Candidate identity is ``docker-compose.yml`` only. Helpers stop named
services, poll ``GET /health/ready``, and start them again. They do not
destroy volumes, attach the Packet 8 overlay, rebuild images, or log
secrets.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import httpx
import psycopg

from smart_rag_core.release.compose import compose_env_file, run_compose
from smart_rag_core.release.io import as_json_object

FASTAPI_READY_URL = "http://127.0.0.1:8000/health/ready"
RESTORE_SERVICES: tuple[str, ...] = (
    "paradedb",
    "valkey-limits",
    "valkey-cache",
    "worker",
    "api",
)
CANONICAL_SNAPSHOT_SQL = """
SELECT
  (SELECT count(*) FROM app.document_versions) AS versions,
  (SELECT count(*) FROM app.document_chunks) AS chunks,
  (SELECT count(*) FROM app.ingestion_jobs) AS ingestion_jobs,
  (SELECT count(*) FROM app.job_operation_ledger) AS ledger_rows,
  (SELECT count(*) FROM app.lightrag_index_jobs) AS lightrag_jobs,
  (SELECT count(*) FROM app.budget_reservations) AS budget_reservations,
  (SELECT count(*) FROM lightrag.lightrag_doc_status) AS lightrag_doc_status
"""


def compose_env_value(repo_root: Path, key: str) -> str | None:
    """Read one Compose env assignment without logging it.

    Args:
        repo_root: Repository root.
        key: Variable name.

    Returns:
        Value, or ``None`` when absent.
    """

    path = compose_env_file(repo_root)
    prefix = f"{key}="
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#") or not line.startswith(prefix):
            continue
        value = line.split("=", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value
    return None


def ready_payload(*, timeout_seconds: float = 8.0) -> dict[str, object]:
    """Fetch ``GET /health/ready`` without secrets.

    Args:
        timeout_seconds: HTTP timeout.

    Returns:
        Status mapping. ``ok`` is false on transport errors.
    """

    try:
        response = httpx.get(FASTAPI_READY_URL, timeout=timeout_seconds)
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": type(exc).__name__}
    body: object
    try:
        body = response.json()
    except ValueError:
        return {"ok": False, "status_code": response.status_code}
    if not isinstance(body, dict):
        return {"ok": False, "status_code": response.status_code}
    payload = as_json_object(cast(dict[str, object], body), source="ready")
    deps_raw = payload.get("dependencies")
    names: dict[str, str] = {}
    if isinstance(deps_raw, list):
        for item in cast(list[object], deps_raw):
            try:
                typed_item = as_json_object(item, source="ready.dep")
            except ValueError:
                continue
            name = typed_item.get("name")
            status = typed_item.get("status")
            if isinstance(name, str) and isinstance(status, str):
                names[name] = status
    return {
        "ok": response.status_code == 200,
        "status_code": response.status_code,
        "query_ready": payload.get("query_ready"),
        "status": payload.get("status"),
        "dependencies": names,
    }


def wait_dependency(
    name: str,
    expected: str,
    *,
    timeout_seconds: float = 45.0,
) -> dict[str, object]:
    """Poll readiness until one dependency matches ``expected``.

    Args:
        name: Readiness dependency name.
        expected: Desired status such as ``down`` or ``ok``.
        timeout_seconds: Poll budget.

    Returns:
        Last observed status and whether it matched.
    """

    deadline = time.monotonic() + timeout_seconds
    last = ""
    query_ready: object = None
    while time.monotonic() < deadline:
        payload = ready_payload()
        deps = payload.get("dependencies")
        try:
            mapping = as_json_object(deps, source="ready.deps")
        except ValueError:
            mapping = {}
        last = str(mapping.get(name, ""))
        query_ready = payload.get("query_ready")
        if last == expected:
            return {
                "name": name,
                "expected": expected,
                "status": last,
                "query_ready": query_ready,
                "passed": True,
            }
        time.sleep(1)
    return {
        "name": name,
        "expected": expected,
        "status": last,
        "query_ready": query_ready,
        "passed": False,
    }


def snapshot_canonical(db_url: str) -> dict[str, object]:
    """Count canonical and durable rows used for Packet 5 reconciliation.

    Args:
        db_url: Local Supabase Postgres URL.

    Returns:
        Integer counts. No row payloads or secrets.

    Raises:
        psycopg.Error: If the snapshot query fails.
    """

    with psycopg.connect(db_url, connect_timeout=8) as connection:
        with connection.cursor() as cursor:
            cursor.execute(CANONICAL_SNAPSHOT_SQL)
            row = cursor.fetchone()
    if row is None:
        return {"passed": False, "detail": "snapshot_empty"}
    keys = (
        "versions",
        "chunks",
        "ingestion_jobs",
        "ledger_rows",
        "lightrag_jobs",
        "budget_reservations",
        "lightrag_doc_status",
    )
    counts: dict[str, object] = {}
    for key, value in zip(keys, row, strict=True):
        counts[key] = (
            value if isinstance(value, int) and not isinstance(value, bool) else 0
        )
    counts["passed"] = True
    return counts


def parade_row_count(repo_root: Path) -> dict[str, object]:
    """Count derived BM25 rows via unpublished ParadeDB exec.

    Args:
        repo_root: Repository root.

    Returns:
        Count payload without connection strings.
    """

    completed = run_compose(
        repo_root,
        [
            "exec",
            "-T",
            "paradedb",
            "psql",
            "-U",
            "paradedb",
            "-d",
            "paradedb",
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


def compose_stop(repo_root: Path, service: str) -> dict[str, object]:
    """Stop one candidate service without removing its volume.

    Args:
        repo_root: Repository root.
        service: Compose service name.

    Returns:
        Exit code row. Volume destroy is forbidden here.
    """

    completed = run_compose(
        repo_root,
        ["stop", service],
        timeout_seconds=120,
    )
    return {
        "service": service,
        "action": "stop",
        "returncode": completed.returncode,
        "volume_destroyed": False,
    }


def compose_start(repo_root: Path, service: str) -> dict[str, object]:
    """Start one candidate service and wait for health.

    Args:
        repo_root: Repository root.
        service: Compose service name.

    Returns:
        Exit code row.
    """

    completed = run_compose(
        repo_root,
        ["up", "-d", "--no-build", "--wait", service],
        timeout_seconds=180,
    )
    return {
        "service": service,
        "action": "start",
        "returncode": completed.returncode,
        "image_rebuilt": False,
    }


def kill_and_restart_worker(repo_root: Path) -> dict[str, object]:
    """SIGKILL the worker, then start the same image with ``--no-build``.

    Args:
        repo_root: Repository root.

    Returns:
        Kill and start exit codes.
    """

    killed = run_compose(repo_root, ["kill", "worker"], timeout_seconds=60)
    started = compose_start(repo_root, "worker")
    return {
        "kill_returncode": killed.returncode,
        "start_returncode": started["returncode"],
        "passed": killed.returncode == 0 and started["returncode"] == 0,
        "image_rebuilt": False,
    }


def restore_services(repo_root: Path) -> dict[str, object]:
    """Bring Packet 5 fault targets back without overlay or rebuild.

    Args:
        repo_root: Repository root.

    Returns:
        Compose up exit code.
    """

    completed = run_compose(
        repo_root,
        ["up", "-d", "--no-build", "--wait", *RESTORE_SERVICES],
        timeout_seconds=300,
    )
    return {
        "services": list(RESTORE_SERVICES),
        "returncode": completed.returncode,
        "image_rebuilt": False,
        "overlay_attached": False,
    }


def version_mismatch(repo_root: Path) -> dict[str, object]:
    """Wrong ``app.bm25_normalization_version`` must fail closed in ParadeDB.

    Args:
        repo_root: Repository root.

    Returns:
        Mismatch proof without SQL secrets.
    """

    ok = run_compose(
        repo_root,
        [
            "exec",
            "-T",
            "paradedb",
            "psql",
            "-U",
            "paradedb",
            "-d",
            "paradedb",
            "-v",
            "ON_ERROR_STOP=1",
            "-tAc",
            "SELECT search.assert_arabic_normalization_version();",
        ],
        timeout_seconds=60,
    )
    mismatch = run_compose(
        repo_root,
        [
            "exec",
            "-T",
            "paradedb",
            "psql",
            "-U",
            "paradedb",
            "-d",
            "paradedb",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            (
                "SELECT set_config('app.bm25_normalization_version', "
                "'wrong_version', false);"
                "SELECT search.assert_arabic_normalization_version();"
            ),
        ],
        timeout_seconds=60,
    )
    combined = f"{mismatch.stderr or ''}{mismatch.stdout or ''}".lower()
    return {
        "ok_returncode": ok.returncode,
        "mismatch_returncode": mismatch.returncode,
        "mismatch_mentions_version": "version mismatch" in combined,
        "passed": ok.returncode == 0
        and mismatch.returncode != 0
        and "version mismatch" in combined,
        "unpublished": True,
    }


def valkey_wrong_password(
    repo_root: Path,
    *,
    service: str,
) -> dict[str, object]:
    """PING with a wrong requirepass must not succeed.

    Args:
        repo_root: Repository root.
        service: ``valkey-limits`` or ``valkey-cache``.

    Returns:
        Deny payload. The password is not recorded.
    """

    completed = run_compose(
        repo_root,
        [
            "exec",
            "-T",
            service,
            "valkey-cli",
            "-a",
            "phase09-wrong-password",
            "--no-auth-warning",
            "PING",
        ],
        timeout_seconds=30,
    )
    text = f"{completed.stdout or ''}{completed.stderr or ''}".upper()
    denied = completed.returncode != 0 or "PONG" not in text
    return {
        "service": service,
        "action": "wrong_password_ping",
        "returncode": completed.returncode,
        "denied": denied,
        "named_acl_users": False,
    }


def valkey_fill_until_reject(
    repo_root: Path,
    *,
    password: str,
) -> dict[str, object]:
    """Fill the noeviction limits instance until SET is rejected.

    Args:
        repo_root: Repository root.
        password: Limits requirepass. Not written to the result.

    Returns:
        Fill outcome. Payloads and the password are omitted.

    Side Effects:
        Writes ephemeral ``limits:p09fill:*`` keys. Caller must restart
        Valkey limits afterward so recovery does not leave OOM.
    """

    payload = "x" * 1_000_000
    rejected = False
    written = 0
    last_code = 0
    for index in range(80):
        completed = run_compose(
            repo_root,
            [
                "exec",
                "-T",
                "valkey-limits",
                "valkey-cli",
                "-a",
                password,
                "--no-auth-warning",
                "-x",
                "SET",
                f"limits:p09fill:{index}",
            ],
            timeout_seconds=30,
            input_text=payload,
        )
        last_code = completed.returncode
        text = f"{completed.stdout or ''}{completed.stderr or ''}".upper()
        if completed.returncode != 0 or "OOM" in text or "OK" not in text:
            rejected = True
            break
        written += 1
    return {
        "service": "valkey-limits",
        "action": "fill_noeviction",
        "keys_accepted": written,
        "rejected": rejected,
        "last_returncode": last_code,
        "policy": "noeviction",
        "passed": rejected,
    }


def valkey_flush(
    repo_root: Path,
    *,
    service: str,
    password: str,
) -> dict[str, object]:
    """FLUSHDB on one Valkey instance after a fill/outage drill.

    Args:
        repo_root: Repository root.
        service: ``valkey-limits`` or ``valkey-cache``.
        password: requirepass. Not written to the result.

    Returns:
        Flush outcome without the password.
    """

    completed = run_compose(
        repo_root,
        [
            "exec",
            "-T",
            service,
            "valkey-cli",
            "-a",
            password,
            "--no-auth-warning",
            "FLUSHDB",
        ],
        timeout_seconds=30,
    )
    text = (completed.stdout or "").upper()
    return {
        "service": service,
        "action": "flushdb",
        "returncode": completed.returncode,
        "passed": completed.returncode == 0 and "OK" in text,
    }


def canonical_drift(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, object]:
    """Compare canonical version/chunk counts.

    Args:
        before: Pre-fault snapshot.
        after: Post-recovery snapshot.

    Returns:
        Drift flags. Job/ledger counts may change during reclaim and are
        reported separately rather than failing canonical identity.
    """

    versions_before = before.get("versions")
    versions_after = after.get("versions")
    chunks_before = before.get("chunks")
    chunks_after = after.get("chunks")
    duplicate = (
        isinstance(versions_after, int)
        and isinstance(versions_before, int)
        and versions_after > versions_before
    ) or (
        isinstance(chunks_after, int)
        and isinstance(chunks_before, int)
        and chunks_after > chunks_before
    )
    matched = versions_before == versions_after and chunks_before == chunks_after
    return {
        "versions_before": versions_before,
        "versions_after": versions_after,
        "chunks_before": chunks_before,
        "chunks_after": chunks_after,
        "duplicate_canonical": duplicate,
        "canonical_matched": matched,
        "ingestion_jobs_before": before.get("ingestion_jobs"),
        "ingestion_jobs_after": after.get("ingestion_jobs"),
        "ledger_rows_before": before.get("ledger_rows"),
        "ledger_rows_after": after.get("ledger_rows"),
        "lightrag_doc_status_before": before.get("lightrag_doc_status"),
        "lightrag_doc_status_after": after.get("lightrag_doc_status"),
        "authority_transferred": False,
    }
