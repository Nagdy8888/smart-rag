"""Run the laptop ingest worker on the host with packet8 loopback ports.

Compose ``worker`` is distroless and has no Docker CLI, so it cannot launch
``smart-rag-parser-sandbox:local``. Phase A ingest therefore runs this
process on the workstation (Docker + Storage Admin present) while
ParadeDB/ClamAV/API stay in Compose. Do not use this on EC2.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import quote

from smart_rag_worker.main import main as worker_main

REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from one gitignored env file.

    Args:
        path: Env file path.

    Returns:
        Mapping of keys to raw values.
    """

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def apply_laptop_ingest_environ() -> None:
    """Load ``.env.compose`` and rewrite private Docker DNS for host loopback.

    Side Effects:
        Mutates ``os.environ`` from ``.env`` then ``.env.compose`` (compose
        wins). Forces UTF-8 stdio so Docker parser stdout with plot
        punctuation does not crash cp1252. Copies ``SUPABASE_DB_URL`` into
        ``LIGHTRAG_DB_URL`` when unset so graph extract can ``SET ROLE
        app_lightrag``. Caps host-worker concurrency at 1
        and extends the job lease so hosted canonical writes are not killed
        by a blocked heartbeat. Prints hostnames and ports only, never
        passwords or Storage Admin.
    """

    root_env = _parse_env(REPO_ROOT / ".env")
    compose_env = _parse_env(REPO_ROOT / ".env.compose")
    env = {**root_env, **compose_env}
    for key, value in env.items():
        if key.startswith("VALKEY_"):
            continue
        os.environ[key] = value
    os.environ["PYTHONUNBUFFERED"] = "1"
    worker_dsn = env.get("WORKER_SUPABASE_DB_URL", "").strip()
    if worker_dsn:
        os.environ["SUPABASE_DB_URL"] = worker_dsn
    docker_bin = Path(r"C:\Program Files\Docker\Docker\resources\bin")
    if docker_bin.is_dir():
        current_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(docker_bin) + os.pathsep + current_path
    writer_user = env.get("PARADEDB_WRITER_USER", "paradedb_writer")
    writer_password = env.get("PARADEDB_WRITER_PASSWORD", "")
    paradedb_db = env.get("PARADEDB_DB", "paradedb")
    os.environ["PARADEDB_URL"] = (
        f"postgresql://{quote(writer_user, safe='')}:{quote(writer_password, safe='')}"
        f"@127.0.0.1:54329/{paradedb_db}"
    )
    worker_dsn = os.environ.get("SUPABASE_DB_URL", "").strip()
    graph_enabled = os.environ.get("WORKER_GRAPH_ENABLED", "true").strip().lower()
    graph_on = graph_enabled not in {"0", "false", "no", "off"}
    if graph_on and worker_dsn and not os.environ.get("LIGHTRAG_DB_URL", "").strip():
        os.environ["LIGHTRAG_DB_URL"] = worker_dsn
    if not graph_on:
        os.environ["WORKER_GRAPH_ENABLED"] = "false"
        os.environ.pop("LIGHTRAG_DB_URL", None)
    os.environ["CLAMAV_HOST"] = "127.0.0.1"
    os.environ["CLAMAV_PORT"] = "13310"
    os.environ["CRAWL_PROXY_URL"] = "http://127.0.0.1:18080"
    os.environ.pop("VALKEY_LIMITS_URL", None)
    os.environ.pop("VALKEY_CACHE_URL", None)
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ.setdefault("WORKER_CONCURRENCY", "1")
    os.environ.setdefault("JOB_LEASE_SECONDS", "1800")
    os.environ.setdefault("JOB_HEARTBEAT_INTERVAL_SECONDS", "30")
    storage_set = bool(env.get("SUPABASE_STORAGE_ADMIN_SECRET"))
    print("laptop_ingest_worker=host", flush=True)
    print("paradedb_host=127.0.0.1:54329", flush=True)
    print("clamav_host=127.0.0.1:13310", flush=True)
    print(f"storage_admin_present={str(storage_set).lower()}", flush=True)
    print(
        f"supabase_db_url_set={str(bool(os.environ.get('SUPABASE_DB_URL'))).lower()}",
        flush=True,
    )
    print(
        f"docker_cli_present={str(shutil.which('docker') is not None).lower()}",
        flush=True,
    )
    print(f"langsmith_tracing={os.environ.get('LANGSMITH_TRACING', '')}", flush=True)
    print(
        "langsmith_export_io=" + os.environ.get("LANGSMITH_EXPORT_IO", "false"),
        flush=True,
    )
    print(
        "subprocessor_matrix_verified="
        + os.environ.get("SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED", ""),
        flush=True,
    )
    print(f"mock_model_mode={os.environ.get('MOCK_MODEL_MODE', '')}", flush=True)
    print(
        "openai_key_present="
        + str(bool(os.environ.get("OPENAI_API_KEY", "").strip())).lower(),
        flush=True,
    )
    print(f"worker_concurrency={os.environ.get('WORKER_CONCURRENCY', '')}", flush=True)
    print(f"job_lease_seconds={os.environ.get('JOB_LEASE_SECONDS', '')}", flush=True)
    print(
        "lightrag_db_url_set="
        + str(bool(os.environ.get("LIGHTRAG_DB_URL", "").strip())).lower(),
        flush=True,
    )
    print(
        "worker_graph_enabled="
        + str(
            os.environ.get("WORKER_GRAPH_ENABLED", "true").strip().lower()
            not in {"0", "false", "no", "off"}
        ).lower(),
        flush=True,
    )


def main() -> int:
    """Apply host overrides and start the worker poll loop.

    Returns:
        Worker process exit code.
    """

    apply_laptop_ingest_environ()
    return worker_main()


if __name__ == "__main__":
    raise SystemExit(main())
