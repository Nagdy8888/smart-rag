#!/usr/bin/env python3
"""Host-side Phase 9 Packet 1 candidate freeze, build, scan, health, and seed."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal, cast

from smart_rag_core.release.compose import (
    docker_engine_resources,
    inspect_image,
    run_compose,
)
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    CANDIDATE_BUILD_SERVICES,
    PARSER_SANDBOX_IMAGE,
    PRIVATE_COMPOSE_SERVICES,
    REQUIRED_IMAGE_USER,
)
from smart_rag_core.release.errors import CandidatePortError, CandidateReleaseError
from smart_rag_core.release.health import (
    CandidateHealthReport,
    prove_candidate_health,
    query_pg_search_version,
)
from smart_rag_core.release.identity import (
    assert_identity_fields,
    collect_identity_freeze,
)
from smart_rag_core.release.images import (
    CandidateImageRecord,
    ImageDigestManifest,
    image_record_from_inspect,
)
from smart_rag_core.release.io import (
    as_json_object,
    dump_canonical_json,
    json_int,
    load_json_object,
)
from smart_rag_core.release.migrations import (
    collect_migration_inventory,
    load_applied_versions,
)
from smart_rag_core.release.ports import (
    assert_private_services_unpublished,
    parse_compose_ps_text,
)
from smart_rag_core.release.scans import (
    CandidateScanSummary,
    ImageScanSummary,
    blocked_scan,
)
from smart_rag_core.release.sizing import build_sizing_baseline
from smart_rag_core.settings.base import get_process_environ

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / ARTIFACT_DIR
DEFAULT_SUPABASE = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
GITLEAKS_IMAGE = (
    "ghcr.io/gitleaks/gitleaks@sha256:"
    "c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"
)
TRIVY_HANG_DETAIL = (
    "Packet 1 attempted Trivy via aquasec/trivy docker.sock on 2026-08-17; "
    "the scan hung Docker Desktop (HTTP 500), WSL became unresponsive, and "
    "the host disk filled (Docker updater ENOSPC). Packet 1 records Blocked "
    "and does not retry docker.sock Trivy. Packet 6 re-runs full SBOM/Trivy."
)
SERVICE_IMAGE_FALLBACK = {
    "api": "smart-rag-api",
    "worker": "smart-rag-worker",
    "frontend": "smart-rag-frontend",
    "crawl-proxy": "smart-rag-crawl-proxy",
}


def _run(
    command: list[str], *, timeout_seconds: int, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one host command and capture text output.

    Args:
        command: Argument vector.
        timeout_seconds: Hard timeout.
        cwd: Working directory.

    Returns:
        Completed process.
    """

    try:
        return subprocess.run(  # noqa: S603
            command,
            cwd=cwd or REPO_ROOT,
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


def _write_json(payload: object, path: Path) -> None:
    """Write one JSON object artifact.

    Args:
        payload: JSON-object mapping or Pydantic dump.
        path: Destination path.

    Side Effects:
        Overwrites ``path``.
    """

    dump_canonical_json(as_json_object(payload), path)


def _append_command_log(name: str, exit_code: int) -> None:
    """Append one orchestrator command result to the candidate command log.

    Args:
        name: Subcommand name.
        exit_code: Process exit code.

    Side Effects:
        Creates or updates ``candidate-command-log.json``.
    """

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / "candidate-command-log.json"
    commands: list[object] = []
    if path.is_file():
        payload = load_json_object(path)
        raw = payload.get("commands")
        if isinstance(raw, list):
            commands = list(cast(list[object], raw))
    commands.append({"command": name, "exit_code": exit_code})
    _write_json({"commands": commands}, path)


def _docker_engine_healthy() -> bool:
    """Return whether ``docker info`` reports a usable engine.

    Returns:
        True when NCPU is at least 1 and the command succeeds within 20s.
    """

    docker = shutil.which("docker")
    if docker is None:
        return False
    completed = _run(
        [docker, "info", "--format", "{{.NCPU}}"],
        timeout_seconds=20,
    )
    if completed.returncode != 0:
        return False
    text = (completed.stdout or "").strip()
    try:
        return int(text) >= 1
    except ValueError:
        return False


def cmd_freeze() -> int:
    """Write the identity freeze using runtime pg_search when available."""

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    pg_search = query_pg_search_version(REPO_ROOT)
    freeze = collect_identity_freeze(REPO_ROOT, pg_search_version=pg_search)
    assert_identity_fields(freeze)
    _write_json(
        freeze.model_dump(mode="json"),
        ARTIFACTS / "candidate-identity-freeze.json",
    )
    return 0


def cmd_build() -> int:
    """Build candidate images from repo Dockerfiles and write the digest manifest."""

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    build = run_compose(
        REPO_ROOT,
        ["build", *CANDIDATE_BUILD_SERVICES],
        timeout_seconds=3600,
    )
    if build.returncode != 0:
        sys.stderr.write(build.stderr or build.stdout)
        return build.returncode
    parser = run_compose(
        REPO_ROOT,
        ["--profile", "parser-build", "build", "parser-sandbox"],
        timeout_seconds=3600,
    )
    if parser.returncode != 0:
        sys.stderr.write(parser.stderr or parser.stdout)
        return parser.returncode
    records: list[CandidateImageRecord] = []
    names = _compose_image_names()
    for service in CANDIDATE_BUILD_SERVICES:
        preferred = names.get(service, SERVICE_IMAGE_FALLBACK[service])
        image_name, payload = _inspect_named(service, preferred)
        records.append(
            image_record_from_inspect(
                service=service,
                image_name=image_name,
                payload=payload,
            )
        )
    sandbox_name, sandbox = _inspect_named("parser-sandbox", PARSER_SANDBOX_IMAGE)
    records.append(
        image_record_from_inspect(
            service="parser-sandbox",
            image_name=sandbox_name,
            payload=sandbox,
        )
    )
    for record in records:
        if not record.user.startswith(REQUIRED_IMAGE_USER):
            sys.stderr.write(
                f"{record.service} image user is {record.user}, expected {REQUIRED_IMAGE_USER}\n"
            )
            return 1
    manifest = ImageDigestManifest(
        compose_file="docker-compose.yml",
        images=tuple(records),
    )
    _write_json(
        manifest.model_dump(mode="json"),
        ARTIFACTS / "candidate-image-manifest.json",
    )
    return 0


def _inspect_named(service: str, preferred: str) -> tuple[str, dict[str, object]]:
    """Inspect one image, trying Compose name then project fallbacks.

    Args:
        service: Compose service name.
        preferred: First image reference to inspect.

    Returns:
        Resolved image name and inspect payload.

    Raises:
        CandidateReleaseError: If no candidate inspects successfully.
    """

    candidates = [preferred]
    fallback = SERVICE_IMAGE_FALLBACK.get(service)
    if fallback and fallback not in candidates:
        candidates.append(fallback)
        candidates.append(f"{fallback}:latest")
    last_error = "inspect failed"
    for name in candidates:
        try:
            return name, inspect_image(name)
        except CandidateReleaseError as exc:
            last_error = str(exc)
    raise CandidateReleaseError(f"{service}: {last_error}")


def _compose_image_names() -> dict[str, str]:
    """Return Compose service to image name from ``compose images``."""

    completed = run_compose(
        REPO_ROOT,
        ["images", "--format", "json"],
        timeout_seconds=60,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return dict(SERVICE_IMAGE_FALLBACK)
    names: dict[str, str] = dict(SERVICE_IMAGE_FALLBACK)
    try:
        loaded: object = json.loads(completed.stdout)
    except json.JSONDecodeError:
        rows: list[object] = []
        for line in completed.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                decoded: object = json.loads(line)
                rows.append(decoded)
            except json.JSONDecodeError:
                return names
        loaded = rows
    items: list[object]
    if isinstance(loaded, list):
        items = cast(list[object], loaded)
    else:
        items = [loaded]
    for item in items:
        if not isinstance(item, dict):
            continue
        row = cast(dict[str, object], item)
        service = str(row.get("Service") or "")
        repository = str(row.get("Repository") or row.get("ID") or "")
        tag = str(row.get("Tag") or "latest")
        if service and repository:
            names[service] = (
                f"{repository}:{tag}" if tag and tag != "<none>" else repository
            )
    return names


def cmd_scan() -> int:
    """Scan candidate images with Trivy when Docker can pull the scanner."""

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    manifest_path = ARTIFACTS / "candidate-image-manifest.json"
    if not manifest_path.is_file():
        sys.stderr.write("candidate-image-manifest.json missing; run build first\n")
        return 1
    payload = load_json_object(manifest_path)
    images_raw = payload.get("images")
    if not isinstance(images_raw, list):
        sys.stderr.write("image manifest missing images\n")
        return 1
    summaries: list[ImageScanSummary] = []
    engine_ok = _docker_engine_healthy()
    for item in cast(list[object], images_raw):
        if not isinstance(item, dict):
            continue
        row = cast(dict[str, object], item)
        image_name = str(row.get("image_name") or "")
        if not image_name:
            continue
        summaries.append(
            blocked_scan(
                image_name,
                tool="trivy",
                detail=TRIVY_HANG_DETAIL,
            )
        )
    pip_status = _run_pip_audit()
    pnpm_status = _run_pnpm_audit()
    gitleaks_status: Literal["passed", "failed", "blocked", "not_run"]
    if engine_ok:
        gitleaks_status = _run_gitleaks()
    else:
        gitleaks_status = "blocked"
    summary = CandidateScanSummary(
        images=tuple(summaries),
        pip_audit_status=pip_status,
        pnpm_audit_status=pnpm_status,
        gitleaks_status=gitleaks_status,
    )
    _write_json(
        summary.model_dump(mode="json"),
        ARTIFACTS / "candidate-scan-summary.json",
    )
    if any(row.status == "failed" for row in summaries):
        return 1
    if gitleaks_status == "failed":
        return 1
    if pip_status == "failed" or pnpm_status == "failed":
        return 1
    return 0


def _run_gitleaks() -> Literal["passed", "failed", "blocked", "not_run"]:
    """Run the pinned Gitleaks image against the repository.

    Returns:
        Compact classification. Packet 6 re-runs full secret scanning.
    """

    docker = shutil.which("docker")
    if docker is None:
        return "not_run"
    completed = _run(
        [
            docker,
            "run",
            "--rm",
            "-v",
            f"{REPO_ROOT}:/repo",
            GITLEAKS_IMAGE,
            "detect",
            "--source=/repo",
            "--config=/repo/.gitleaks.toml",
            "--no-banner",
            "--redact",
        ],
        timeout_seconds=180,
    )
    if completed.returncode != 0:
        return "failed" if completed.stdout or completed.stderr else "blocked"
    return "passed"


def _run_pip_audit() -> Literal["passed", "failed", "blocked", "not_run"]:
    """Run pip-audit on the frozen export when uv is available.

    Returns:
        Compact classification for the scan summary.
    """

    uv = shutil.which("uv")
    if uv is None:
        return "not_run"
    req = REPO_ROOT / ".tmp-phase09-audit-requirements.txt"
    export = _run(
        [
            uv,
            "export",
            "--frozen",
            "--all-packages",
            "--group",
            "dev",
            "--no-emit-workspace",
            "--format",
            "requirements.txt",
            "--output-file",
            str(req),
        ],
        timeout_seconds=120,
    )
    if export.returncode != 0:
        return "blocked"
    audit = _run(
        [
            uv,
            "run",
            "pip-audit",
            "--strict",
            "--ignore-vuln",
            "PYSEC-2026-113",
            "--requirement",
            str(req),
        ],
        timeout_seconds=180,
    )
    req.unlink(missing_ok=True)
    if audit.returncode != 0:
        return "failed"
    return "passed"


def _run_pnpm_audit() -> Literal["passed", "failed", "blocked", "not_run"]:
    """Run pnpm audit at high level.

    Returns:
        Compact classification for the scan summary.
    """

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        return "not_run"
    completed = _run([pnpm, "audit", "--audit-level", "high"], timeout_seconds=180)
    if completed.returncode != 0:
        return "failed"
    return "passed"


def cmd_supabase() -> int:
    """Start local Supabase with the pinned CLI when it is not already up.

    Returns:
        Process exit code. Status/start output is captured because it can
        contain ephemeral local credentials.
    """

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        sys.stderr.write("pnpm is unavailable; cannot start local Supabase\n")
        return 1
    status = _run(
        [pnpm, "exec", "supabase", "status", "-o", "json"],
        timeout_seconds=30,
    )
    if status.returncode == 0:
        return 0
    started = _run([pnpm, "exec", "supabase", "start"], timeout_seconds=240)
    if started.returncode != 0:
        sys.stderr.write("local Supabase start failed\n")
        return started.returncode
    return 0


def cmd_up() -> int:
    """Start the candidate Compose file without the Packet 8 overlay."""

    completed = run_compose(
        REPO_ROOT,
        [
            "up",
            "-d",
            "--wait",
            "--no-build",
            "--force-recreate",
            "--remove-orphans",
        ],
        timeout_seconds=900,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout)
        return completed.returncode
    return _recreate_private_if_published()


def _recreate_private_if_published() -> int:
    """Force-recreate private services that still publish host ports.

    Returns:
        Zero when private services are unpublished.
    """

    ps = run_compose(REPO_ROOT, ["ps", "--format", "json"], timeout_seconds=60)
    publishers = parse_compose_ps_text(ps.stdout)
    published = [
        name
        for name in PRIVATE_COMPOSE_SERVICES
        if any(port > 0 for port in publishers.get(name, ()))
    ]
    if not published:
        return 0
    recreated = run_compose(
        REPO_ROOT,
        ["up", "-d", "--wait", "--force-recreate", *published],
        timeout_seconds=600,
    )
    if recreated.returncode != 0:
        sys.stderr.write(recreated.stderr or recreated.stdout)
        return recreated.returncode
    return 0


def cmd_health() -> int:
    """Prove candidate health and unpublished private ports."""

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    try:
        report = prove_candidate_health(REPO_ROOT)
    except CandidatePortError as exc:
        failed = CandidateHealthReport(
            api_live="not_run",
            frontend_live="not_run",
            pg_search="not_run",
            valkey_limits_auth="not_run",
            valkey_cache_auth="not_run",
            private_ports="failed",
            mock_model_mode="unverified",
            detail=str(exc)[:2000],
        )
        _write_json(
            failed.model_dump(mode="json"),
            ARTIFACTS / "candidate-health.json",
        )
        return 1
    except CandidateReleaseError as exc:
        blocked = CandidateHealthReport(
            api_live="not_run",
            frontend_live="not_run",
            pg_search="not_run",
            valkey_limits_auth="not_run",
            valkey_cache_auth="not_run",
            private_ports="blocked",
            mock_model_mode="unverified",
            detail=str(exc)[:2000],
        )
        _write_json(
            blocked.model_dump(mode="json"),
            ARTIFACTS / "candidate-health.json",
        )
        return 1
    _write_json(report.model_dump(mode="json"), ARTIFACTS / "candidate-health.json")
    checks = (
        report.api_live,
        report.pg_search,
        report.valkey_limits_auth,
        report.valkey_cache_auth,
        report.private_ports,
    )
    if any(item != "passed" for item in checks):
        return 1
    return 0


def cmd_migrations() -> int:
    """Write migration inventory versus applied versions."""

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    url = get_process_environ("SUPABASE_DB_URL") or DEFAULT_SUPABASE
    applied: tuple[str, ...] | None = None
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=5) as connection:
            applied = load_applied_versions(connection)
    except Exception as exc:
        sys.stderr.write(f"applied migrations unavailable: {exc}\n")
        inventory = collect_migration_inventory(REPO_ROOT, applied_versions=None)
        _write_json(
            inventory.model_dump(mode="json"),
            ARTIFACTS / "candidate-migrations.json",
        )
        return 1
    inventory = collect_migration_inventory(REPO_ROOT, applied_versions=applied)
    _write_json(
        inventory.model_dump(mode="json"),
        ARTIFACTS / "candidate-migrations.json",
    )
    return 0


def _copy_worker_seed_artifact(name: str) -> int:
    """Copy one seed JSON artifact from worker tmpfs via exec.

    Docker ``compose cp`` cannot see the worker ``/tmp`` tmpfs on this host.
    ``exec`` reads the same mount the seed process wrote.

    Args:
        name: Filename under ``/tmp/phase09``. Must be one of the three seed
            artifacts; the path is not taken from operator input.

    Returns:
        Process exit code.

    Side Effects:
        Writes ``docs/deployment/phase-09/<name>`` after JSON validation.
    """

    allowed = {
        "candidate-corpus-manifest.json",
        "candidate-readiness-export.json",
        "candidate-seed-counts.json",
    }
    if name not in allowed:
        raise CandidateReleaseError(f"refusing to copy unexpected seed artifact {name}")
    completed = run_compose(
        REPO_ROOT,
        [
            "exec",
            "-T",
            "worker",
            "python",
            "-c",
            (
                "from pathlib import Path; "
                f"print(Path('/tmp/phase09/{name}').read_text(encoding='utf-8'), end='')"
            ),
        ],
        timeout_seconds=60,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout)
        return completed.returncode
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(f"worker seed artifact {name} is not valid JSON\n")
        return 1
    dump_canonical_json(as_json_object(payload), ARTIFACTS / name)
    return 0


def cmd_seed() -> int:
    """Seed through the worker container so ParadeDB stays unpublished."""

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    seed = run_compose(
        REPO_ROOT,
        [
            "exec",
            "-T",
            "worker",
            "python",
            "-m",
            "smart_rag_core.release.cli",
            "seed",
            "--output-dir",
            "/tmp/phase09",  # noqa: S108 - worker tmpfs path, not a host secret file
        ],
        timeout_seconds=1800,
    )
    if seed.returncode != 0:
        sys.stderr.write(seed.stderr or seed.stdout)
        return seed.returncode
    copy_code = 0
    for name in (
        "candidate-corpus-manifest.json",
        "candidate-readiness-export.json",
        "candidate-seed-counts.json",
    ):
        copied = _copy_worker_seed_artifact(name)
        if copied != 0:
            copy_code = copied
    return copy_code


def cmd_sizing() -> int:
    """Write the local sizing baseline from Docker limits and seed counts."""

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    counts_path = ARTIFACTS / "candidate-seed-counts.json"
    versions = 0
    chunks = 0
    graph_versions = 0
    if counts_path.is_file():
        counts = load_json_object(counts_path)
        versions = json_int(counts.get("seeded_document_versions"))
        chunks = json_int(counts.get("seeded_chunks"))
        graph_versions = json_int(counts.get("seeded_graph_eligible_versions"))
    ncpu, mem = docker_engine_resources()
    baseline = build_sizing_baseline(
        docker_ncpu=ncpu,
        docker_mem_bytes=mem,
        seeded_document_versions=versions,
        seeded_chunks=chunks,
        seeded_graph_eligible_versions=graph_versions,
    )
    _write_json(
        baseline.model_dump(mode="json"),
        ARTIFACTS / "candidate-sizing-baseline.json",
    )
    return 0


def cmd_ports_static() -> int:
    """Reject host ports on the candidate Compose file even when the stack is down."""

    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    publishers = {name: () for name in PRIVATE_COMPOSE_SERVICES}
    assert_private_services_unpublished(publishers, compose_text=compose_text)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run one host-side Packet 1 command.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        Process exit code.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "freeze",
            "build",
            "scan",
            "supabase",
            "up",
            "health",
            "migrations",
            "seed",
            "sizing",
            "ports-static",
            "all",
        ),
    )
    args = parser.parse_args(argv)
    commands = {
        "freeze": cmd_freeze,
        "build": cmd_build,
        "scan": cmd_scan,
        "supabase": cmd_supabase,
        "up": cmd_up,
        "health": cmd_health,
        "migrations": cmd_migrations,
        "seed": cmd_seed,
        "sizing": cmd_sizing,
        "ports-static": cmd_ports_static,
    }
    if args.command == "all":
        log: list[dict[str, object]] = []
        final_code = 0
        for name in (
            "ports-static",
            "freeze",
            "supabase",
            "build",
            "scan",
            "up",
            "health",
            "migrations",
            "seed",
            "sizing",
        ):
            print(f"[phase09] {name}", flush=True)
            code = commands[name]()
            log.append({"command": name, "exit_code": code})
            _write_json(
                {"commands": log},
                ARTIFACTS / "candidate-command-log.json",
            )
            if code != 0:
                final_code = code
                if name in {"ports-static", "build", "up", "migrations", "seed"}:
                    return code
        return final_code
    code = commands[args.command]()
    _append_command_log(args.command, code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
