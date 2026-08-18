"""Local dump, disposable restore, tar Trivy, and ParadeDB rebuild helpers."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import cast

import psycopg

from smart_rag_core.release.compose import run_compose
from smart_rag_core.release.constants import TMP_SCAN_DIR
from smart_rag_core.release.io import as_json_object
from smart_rag_core.release.packet6 import (
    DISPOSABLE_RESTORE_DATABASE,
    PARADEDB_BOOTSTRAP_SQL,
    REQUIRED_STORAGE_BUCKETS,
    restore_exit_acceptable,
)
from smart_rag_core.release.scans import summarize_trivy_report, trivy_critical_ids

TRIVY_IMAGE = "aquasec/trivy:0.66.0"
TRIVY_TIMEOUT_SECONDS = 360
DUMP_TIMEOUT_SECONDS = 180
_SECRET_URL = re.compile(r"postgres(?:ql)?://\S+", re.IGNORECASE)


def redact_process_text(text: str, *, limit: int = 800) -> str:
    """Return a bounded log snippet with connection URLs removed.

    Args:
        text: Process stdout or stderr.
        limit: Maximum characters retained.

    Returns:
        Redacted snippet.
    """

    return _SECRET_URL.sub("postgresql://REDACTED", text)[-limit:]


def _run(
    command: list[str],
    *,
    timeout_seconds: int,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one host command with a hard timeout.

    Args:
        command: Argument vector.
        timeout_seconds: Timeout.
        cwd: Working directory.

    Returns:
        Completed process. Timeouts become returncode 1.
    """

    try:
        return subprocess.run(  # noqa: S603
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout="",
            stderr=f"timed out after {timeout_seconds}s",
        )


def find_supabase_db_container() -> str | None:
    """Return the local Supabase Postgres container name.

    Returns:
        Container name, or ``None``.
    """

    docker = shutil.which("docker") or "docker"
    completed = _run(
        [docker, "ps", "--format", "{{.Names}}", "--filter", "name=supabase_db"],
        timeout_seconds=30,
    )
    names = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return names[0] if names else None


def dump_app_and_lightrag(
    repo_root: Path,
    *,
    container: str,
) -> dict[str, object]:
    """Dump ``app`` and ``lightrag`` schemas into gitignored custom format.

    Args:
        repo_root: Repository root.
        container: Supabase Postgres container.

    Returns:
        Dump metadata. Connection strings are omitted.
    """

    dump_dir = repo_root / TMP_SCAN_DIR / "packet6"
    dump_dir.mkdir(parents=True, exist_ok=True)
    dump_path = dump_dir / "app_lightrag.dump"
    docker = shutil.which("docker") or "docker"
    completed = _run(
        [
            docker,
            "exec",
            container,
            "pg_dump",
            "-U",
            "postgres",
            "-Fc",
            "-d",
            "postgres",
            "-n",
            "app",
            "-n",
            "lightrag",
            "-f",
            "/tmp/phase09_p6.dump",  # noqa: S108 - container tmpfs dump
        ],
        timeout_seconds=DUMP_TIMEOUT_SECONDS,
    )
    copied = _run(
        [docker, "cp", f"{container}:/tmp/phase09_p6.dump", str(dump_path)],
        timeout_seconds=60,
    )
    size = dump_path.stat().st_size if dump_path.is_file() else 0
    return {
        "dump_returncode": completed.returncode,
        "copy_returncode": copied.returncode,
        "bytes": size,
        "relative_path": str(dump_path.relative_to(repo_root)).replace("\\", "/"),
        "live_database_overwritten": False,
        "passed": completed.returncode == 0 and copied.returncode == 0 and size > 0,
        "paradedb_used_as_canonical": False,
    }


def restore_disposable(
    *,
    container: str,
    dump_relative: str,
    repo_root: Path,
) -> dict[str, object]:
    """Restore the dump into a disposable database, never live ``postgres``.

    Args:
        container: Supabase Postgres container.
        dump_relative: Host dump path relative to the repo.
        repo_root: Repository root.

    Returns:
        Restore metadata. The disposable database is dropped afterward.
    """

    docker = shutil.which("docker") or "docker"
    host_dump = repo_root / dump_relative
    _run(
        [docker, "cp", str(host_dump), f"{container}:/tmp/phase09_p6.dump"],
        timeout_seconds=60,
    )
    _run(
        [
            docker,
            "exec",
            container,
            "dropdb",
            "-U",
            "postgres",
            "--if-exists",
            DISPOSABLE_RESTORE_DATABASE,
        ],
        timeout_seconds=60,
    )
    create = _run(
        [
            docker,
            "exec",
            container,
            "createdb",
            "-U",
            "postgres",
            DISPOSABLE_RESTORE_DATABASE,
        ],
        timeout_seconds=60,
    )
    restore = _run(
        [
            docker,
            "exec",
            container,
            "pg_restore",
            "-U",
            "postgres",
            "--dbname",
            DISPOSABLE_RESTORE_DATABASE,
            "--no-owner",
            "--no-acl",
            "/tmp/phase09_p6.dump",  # noqa: S108 - container tmpfs dump
        ],
        timeout_seconds=DUMP_TIMEOUT_SECONDS,
    )
    count = _run(
        [
            docker,
            "exec",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            DISPOSABLE_RESTORE_DATABASE,
            "-tAc",
            (
                "SELECT "
                "(SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'app'), "
                "(SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'lightrag')"
            ),
        ],
        timeout_seconds=60,
    )
    dropped = _run(
        [
            docker,
            "exec",
            container,
            "dropdb",
            "-U",
            "postgres",
            DISPOSABLE_RESTORE_DATABASE,
        ],
        timeout_seconds=60,
    )
    raw = (count.stdout or "").strip().replace("|", " ")
    parts = raw.split()
    app_tables = int(parts[0]) if parts and parts[0].isdigit() else 0
    lightrag_tables = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    passed = (
        create.returncode == 0
        and restore_exit_acceptable(restore.returncode)
        and app_tables > 0
        and lightrag_tables > 0
        and dropped.returncode == 0
    )
    return {
        "candidate_database": DISPOSABLE_RESTORE_DATABASE,
        "runtime_database": "postgres",
        "live_database_overwritten": False,
        "create_returncode": create.returncode,
        "restore_returncode": restore.returncode,
        "app_tables": app_tables,
        "lightrag_tables": lightrag_tables,
        "dropped_after": dropped.returncode == 0,
        "passed": passed,
    }


def storage_inventory(db_url: str) -> dict[str, object]:
    """List durable Storage buckets and object counts.

    Args:
        db_url: Live local Supabase URL.

    Returns:
        Bucket inventory without object payloads.
    """

    with psycopg.connect(db_url, connect_timeout=8) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM storage.buckets WHERE id = ANY(%s) ORDER BY id",
                (list(REQUIRED_STORAGE_BUCKETS),),
            )
            present = [str(row[0]) for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT bucket_id, count(*)
                FROM storage.objects
                WHERE bucket_id = ANY(%s)
                GROUP BY bucket_id
                """,
                (list(REQUIRED_STORAGE_BUCKETS),),
            )
            counts = {str(row[0]): int(row[1]) for row in cursor.fetchall()}
    missing = [name for name in REQUIRED_STORAGE_BUCKETS if name not in present]
    return {
        "required_buckets": list(REQUIRED_STORAGE_BUCKETS),
        "present": present,
        "missing": missing,
        "object_counts": counts,
        "passed": not missing,
    }


def _trivy_report_object(text: str) -> dict[str, object] | None:
    """Parse Trivy JSON stdout into one report object.

    Args:
        text: Scanner stdout.

    Returns:
        Report object, or ``None`` when stdout is not JSON.
    """

    stripped = text.strip()
    if not stripped:
        return None
    start_obj = stripped.find("{")
    start_arr = stripped.find("[")
    if start_obj < 0 and start_arr < 0:
        return None
    if start_arr >= 0 and (start_obj < 0 or start_arr < start_obj):
        snippet = stripped[start_arr:]
    else:
        snippet = stripped[start_obj:]
    try:
        loaded: object = json.loads(snippet)
    except json.JSONDecodeError:
        return None
    if isinstance(loaded, dict):
        return cast(dict[str, object], loaded)
    if isinstance(loaded, list) and loaded and isinstance(loaded[0], dict):
        return cast(dict[str, object], loaded[0])
    return None


def scan_image_tar(
    *,
    repo_root: Path,
    service: str,
    image_id: str,
) -> dict[str, object]:
    """Scan one image via ``docker save`` and Trivy ``--input`` (no docker.sock).

    Args:
        repo_root: Repository root.
        service: Compose service name.
        image_id: Frozen image Id.

    Returns:
        Compact scan row. Tar files are deleted afterward.
    """

    docker = shutil.which("docker") or "docker"
    tar_dir = repo_root / TMP_SCAN_DIR / "packet6"
    tar_dir.mkdir(parents=True, exist_ok=True)
    tar_path = tar_dir / f"{service}.tar"
    saved = _run(
        [docker, "save", "-o", str(tar_path), image_id],
        timeout_seconds=180,
    )
    if saved.returncode != 0 or not tar_path.is_file():
        return {
            "service": service,
            "status": "blocked",
            "detail": "docker save failed",
            "docker_sock_mounted": False,
        }
    cache_dir = repo_root / TMP_SCAN_DIR / "trivy-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    scanned = _run(
        [
            docker,
            "run",
            "--rm",
            "-v",
            f"{tar_path.resolve()}:/scan/image.tar:ro",
            "-v",
            f"{cache_dir.resolve()}:/root/.cache/trivy",
            TRIVY_IMAGE,
            "image",
            "--input",
            "/scan/image.tar",
            "--format",
            "json",
            "--timeout",
            "5m",
            "--quiet",
        ],
        timeout_seconds=TRIVY_TIMEOUT_SECONDS,
    )
    tar_path.unlink(missing_ok=True)
    row: dict[str, object] = {
        "service": service,
        "status": "blocked",
        "docker_sock_mounted": False,
        "trivy_returncode": scanned.returncode,
        "detail": (scanned.stderr or "")[-300:],
    }
    payload = _trivy_report_object(scanned.stdout or "")
    if payload is not None:
        summary = summarize_trivy_report(
            as_json_object(payload, source="trivy"),
            image_name=service,
        )
        row.update(
            {
                "status": summary.status,
                "critical": summary.critical,
                "high": summary.high,
                "medium": summary.medium,
                "low": summary.low,
                "critical_ids": list(trivy_critical_ids(payload)),
                "detail": summary.detail,
            }
        )
    elif "timed out" in (scanned.stderr or ""):
        row["detail"] = "trivy tar scan timed out"
    return row


def destroy_paradedb_volume(repo_root: Path) -> dict[str, object]:
    """Stop ParadeDB, remove its volume, and start a fresh empty instance.

    Args:
        repo_root: Repository root.

    Returns:
        Destroy/start metadata. Canonical Supabase is untouched.
    """

    stopped = run_compose(repo_root, ["stop", "paradedb"], timeout_seconds=120)
    removed = run_compose(repo_root, ["rm", "-f", "paradedb"], timeout_seconds=60)
    docker = shutil.which("docker") or "docker"
    volumes = _run(
        [docker, "volume", "ls", "--format", "{{.Name}}"],
        timeout_seconds=30,
    )
    names = [
        line.strip()
        for line in volumes.stdout.splitlines()
        if "paradedb" in line.strip().lower()
    ]
    for name in names:
        gone = _run([docker, "volume", "rm", "-f", name], timeout_seconds=60)
        if gone.returncode != 0:
            return {
                "stop_returncode": stopped.returncode,
                "rm_returncode": removed.returncode,
                "volume_destroyed": False,
                "volumes": names,
                "detail": f"volume rm failed for {name}",
                "passed": False,
            }
    started = run_compose(
        repo_root,
        [
            "up",
            "-d",
            "--no-build",
            "--wait",
            "paradedb",
            "worker",
            "api",
            "frontend",
        ],
        timeout_seconds=300,
    )
    time.sleep(2)
    return {
        "stop_returncode": stopped.returncode,
        "rm_returncode": removed.returncode,
        "volume_destroyed": bool(names),
        "volumes": names,
        "start_returncode": started.returncode,
        "image_rebuilt": False,
        "paradedb_used_as_canonical": False,
        "passed": stopped.returncode == 0 and started.returncode == 0 and bool(names),
    }


def apply_paradedb_bootstrap_ddl(repo_root: Path) -> dict[str, object]:
    """Apply existing ParadeDB projection DDL as the bootstrap role.

    ``paradedb_writer`` has DML only. A destroyed volume has extensions and
    roles from init SQL, but not ``bm25_chunks``. Packet 6 applies the
    already-owned Phase 2/4 SQL files, then the worker re-projects.

    Args:
        repo_root: Repository root.

    Returns:
        Per-file return codes. Canonical Supabase is untouched.
    """

    rows: list[dict[str, object]] = []
    for relative in PARADEDB_BOOTSTRAP_SQL:
        path = repo_root / relative
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
            ],
            timeout_seconds=120,
            input_text=path.read_text(encoding="utf-8"),
        )
        rows.append(
            {
                "file": relative.replace("\\", "/"),
                "returncode": completed.returncode,
                "detail": (completed.stderr or "")[-200:],
            }
        )
    return {
        "files": rows,
        "passed": bool(rows) and all(int(row["returncode"]) == 0 for row in rows),
        "paradedb_used_as_canonical": False,
        "image_rebuilt": False,
    }


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
