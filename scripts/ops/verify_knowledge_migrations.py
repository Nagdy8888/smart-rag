"""Reapply knowledge migrations to a new schema-only local fixture, never reset data."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from psycopg import sql
from smart_rag_core.settings.base import snapshot_process_environ

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = (
    "test_company_knowledge.py",
    "test_document_title_rpc.py",
    "test_citation_acl_recheck.py",
    "test_conversation_transcript.py",
    "test_sse_progress_replay.py",
    "test_sse_resume.py",
    "test_query_memory_deletion.py",
)


def docker(container: str, *args: str, input_bytes: bytes | None = None) -> bytes:
    """Execute a fixed local Docker command without a shell or credential output."""
    docker_binary = shutil.which("docker")
    if docker_binary is None:
        raise RuntimeError("docker_not_installed")
    result = subprocess.run(  # noqa: S603 - resolved Docker executable; validated fixture args
        [docker_binary, "exec", "-i", container, *args],
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if result.returncode:
        raise RuntimeError("local_fixture_command_failed")
    return result.stdout


def create_fixture(container: str, database: str) -> None:
    """Clone schema only and apply every forward migration to a previously absent DB."""
    if not re.fullmatch(r"supabase_db_[A-Za-z0-9_-]+", container):
        raise ValueError("local_supabase_container_required")
    if not re.fullmatch(r"knowledge_reliability_[a-z0-9_]+", database):
        raise ValueError("isolated_fixture_database_name_required")
    exists = docker(
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-Atc",
        sql.SQL("SELECT 1 FROM pg_database WHERE datname={}")
        .format(sql.Literal(database))
        .as_string(),
    )
    if exists.strip():
        raise ValueError("existing_database_preserved")
    docker(
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql.SQL("CREATE DATABASE {} TEMPLATE template0")
        .format(sql.Identifier(database))
        .as_string(),
    )
    schema = docker(
        container,
        "pg_dump",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "--schema-only",
        "--no-owner",
        "--no-privileges",
    )
    docker(
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        input_bytes=schema,
    )
    with_acl = docker(
        container,
        "pg_dump",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "--schema-only",
        "--no-owner",
    ).decode("utf-8")
    acl = "\n".join(re.findall(r"^(?:GRANT|REVOKE)\b.*?;", with_acl, re.M | re.S))
    docker(
        container,
        "psql",
        "-U",
        "supabase_admin",
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        "--single-transaction",
        input_bytes=acl.encode(),
    )
    for path in sorted((ROOT / "supabase/migrations").glob("20261025*.sql")):
        docker(
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "--single-transaction",
            input_bytes=path.read_bytes(),
        )
        print(f"migration={path.name} result=passed", flush=True)
    docker(
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "INSERT INTO app.company_settings DEFAULT VALUES ON CONFLICT DO NOTHING",
    )


def main() -> int:
    """Create an isolated fixture and optionally run only its scoped contracts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="supabase_db_smart-rag-local-dev")
    parser.add_argument("--database", required=True)
    parser.add_argument("--run-contracts", action="store_true")
    args = parser.parse_args()
    create_fixture(args.container, args.database)
    if not args.run_contracts:
        return 0
    password = docker(args.container, "printenv", "POSTGRES_PASSWORD").decode().strip()
    environment = snapshot_process_environ()
    environment["SUPABASE_DB_URL"] = (
        f"postgresql://postgres:{quote(password, safe='')}@127.0.0.1:15422/{args.database}"
    )
    evidence = ROOT / ".private-eval" / args.database
    evidence.mkdir(parents=True, exist_ok=False)
    command = [
        sys.executable,
        "-m",
        "pytest",
        *(f"tests/contract/{name}" for name in CONTRACTS),
        "--tb=short",
        f"--junitxml={evidence / 'contracts.xml'}",
    ]
    result = subprocess.run(  # noqa: S603 - fixed pytest executable and explicit contract list
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (
        (result.stdout + result.stderr).replace(password, "[redacted]")
        if password
        else result.stdout + result.stderr
    )
    (evidence / "contracts.txt").write_text(output, encoding="utf-8")
    print(output[-5000:])
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
