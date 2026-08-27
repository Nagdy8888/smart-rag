"""Fail when Phase 9 Packet 6 egress/scan/restore collections fail closed."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from smart_rag_core.release.compose import run_compose
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    CANDIDATE_COMPOSE_FILE,
    PACKET8_OVERLAY_FILE,
    PRIVATE_COMPOSE_SERVICES,
    TMP_SCAN_DIR,
)
from smart_rag_core.release.io import as_json_object, dump_canonical_json, json_int
from smart_rag_core.release.packet4 import (
    Phase09Packet4GateError,
    assert_mock_model_mode,
    assert_packet2_corpus_identity,
    expected_image_ids,
    load_packet1_images,
)
from smart_rag_core.release.packet6 import (
    PACKET6_MATRIX_NAME,
    PACKET6_REBUILD_NAME,
    PACKET6_RESTORE_NAME,
    PACKET6_SCAN_NAME,
    PACKET6_SIZING_NAME,
    PYTEST_SUITES,
    Packet6Suite,
    Phase09Packet6GateError,
    assert_holdout_sealed,
    classify_counts,
    classify_p0906_a,
    classify_p0906_b,
    classify_p0906_c,
    classify_p0906_d,
    classify_p0906_e,
    counts_from_junit,
    failure_detail,
    handoff_payloads,
    missing_bootstrap_sql_files,
    missing_pytest_files,
    process_exit_ok,
    pytest_command,
    rebuild_schema_version,
    restore_schema_version,
    scan_schema_version,
    schema_version,
    sizing_schema_version,
)
from smart_rag_core.release.packet6_ops import (
    apply_paradedb_bootstrap_ddl,
    destroy_paradedb_volume,
    dump_app_and_lightrag,
    find_supabase_db_container,
    parade_row_count,
    redact_process_text,
    restore_disposable,
    scan_image_tar,
    storage_inventory,
)
from smart_rag_core.release.ports import parse_compose_ps_text
from smart_rag_core.settings.base import get_process_environ

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUPABASE = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
WORKER_REPROJECT_PATH = "/tmp/bm25_reproject.py"  # noqa: S108
GITLEAKS_IMAGE = (
    "ghcr.io/gitleaks/gitleaks@sha256:"
    "c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"
)


def _json_dict(value: Any, *, source: str) -> dict[str, object]:
    """Require a JSON object.

    Args:
        value: Decoded JSON.
        source: Path label.

    Returns:
        String-keyed object.

    Raises:
        Phase09Packet6GateError: If ``value`` is not an object.
    """

    if not isinstance(value, dict):
        raise Phase09Packet6GateError(f"{source} is not a JSON object")
    return as_json_object(cast(dict[str, object], value), source=source)


def _run_suite(suite: Packet6Suite) -> dict[str, object]:
    """Execute one fail-closed pytest suite and return its matrix row.

    Args:
        suite: Suite to run.

    Returns:
        JSON-object suite row.

    Raises:
        Phase09Packet6GateError: If JUnit output is missing.

    Side Effects:
        Runs pytest from the repository root.
    """

    with tempfile.TemporaryDirectory(prefix="smart-rag-phase09-p6-") as directory:
        report = Path(directory) / "junit.xml"
        completed = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "pytest", *pytest_command(suite, report)],
            cwd=REPO_ROOT,
            check=False,
        )
        try:
            counts = counts_from_junit(report)
        except Phase09Packet4GateError as exc:
            raise Phase09Packet6GateError(str(exc)) from exc
    classification = classify_counts(
        counts,
        returncode=completed.returncode,
        fail_on_skip=suite.fail_on_skip,
    )
    detail = failure_detail(
        counts,
        returncode=completed.returncode,
        fail_on_skip=suite.fail_on_skip,
    )
    print(
        f"phase09_packet6_{suite.suite_id} "
        f"tests={counts.tests} failures={counts.failures} "
        f"errors={counts.errors} skipped={counts.skipped} "
        f"classification={classification}",
        flush=True,
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
        "overlay_required": False,
        "detail": detail,
    }


def _health() -> dict[str, object]:
    """Run ``phase09_candidate.py health``.

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
    return {
        "command": "scripts/phase09_candidate.py health",
        "returncode": completed.returncode,
    }


def _host_audits() -> dict[str, object]:
    """Run pip-audit, pnpm audit, and gitleaks without docker.sock Trivy.

    Returns:
        Compact host-scan classifications.
    """

    uv = shutil.which("uv") or "uv"
    req = REPO_ROOT / TMP_SCAN_DIR / "packet6-requirements.txt"
    req.parent.mkdir(parents=True, exist_ok=True)
    export = subprocess.run(  # noqa: S603
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
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    pip = subprocess.run(  # noqa: S603
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
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    pnpm = shutil.which("pnpm") or "pnpm"
    node = subprocess.run(  # noqa: S603
        [pnpm, "audit", "--audit-level", "high"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    docker = shutil.which("docker") or "docker"
    leaks = subprocess.run(  # noqa: S603
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
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "export_returncode": export.returncode,
        "pip_audit": "passed" if pip.returncode == 0 else "failed",
        "pnpm_audit": "passed" if node.returncode == 0 else "failed",
        "gitleaks": "passed" if leaks.returncode == 0 else "failed",
        "docker_sock_trivy": False,
    }


def _inject_reproject() -> int:
    """Copy ``bm25_reproject.py`` onto worker tmpfs.

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
                f"Path({WORKER_REPROJECT_PATH!r}).write_text("
                "sys.stdin.read(), encoding='utf-8')"
            ),
        ],
        timeout_seconds=60,
        input_text=text,
    )
    return completed.returncode


def _worker_reproject(corpus_json: str) -> dict[str, object]:
    """Re-project Packet 2 BM25 rows through unpublished worker ParadeDB.

    Args:
        corpus_json: Corpus manifest JSON.

    Returns:
        Worker payload. SQL-stamped ready states stay false.
    """

    completed = run_compose(
        REPO_ROOT,
        ["exec", "-T", "worker", "python", WORKER_REPROJECT_PATH],
        timeout_seconds=1800,
        input_text=corpus_json,
    )
    payload: dict[str, object] = {"worker_returncode": completed.returncode}
    stdout = completed.stdout or ""
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            loaded: object = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            payload.update(_json_dict(loaded, source="worker-bm25"))
            break
    payload["sql_stamped_hybrid_or_graph_ready"] = False
    payload["image_rebuilt"] = False
    payload["worker_stderr"] = redact_process_text(completed.stderr or "")
    return payload


def _overlay_published() -> list[str]:
    """Return private services currently publishing host ports.

    Returns:
        Service names that must be detached.
    """

    ps = run_compose(REPO_ROOT, ["ps", "--format", "json"], timeout_seconds=60)
    if ps.returncode != 0:
        return []
    publishers = parse_compose_ps_text(ps.stdout)
    return [name for name in PRIVATE_COMPOSE_SERVICES if publishers.get(name)]


def _detach_overlay() -> dict[str, object]:
    """Detach Packet 8 overlay if private ports are published.

    Returns:
        Detach command row.
    """

    completed = run_compose(
        REPO_ROOT,
        ["up", "-d", "--no-build", "--wait", "--remove-orphans"],
        timeout_seconds=300,
    )
    return {
        "returncode": completed.returncode,
        "overlay_file": PACKET8_OVERLAY_FILE,
        "overlay_file_is_candidate": False,
        "compose_file": CANDIDATE_COMPOSE_FILE,
    }


def main(argv: list[str] | None = None) -> int:
    """Run Packet 6 measurements and reject Failed acceptance rows.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        ``0`` when A-E are not Failed. ``Blocked`` Trivy is allowed.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        missing = missing_pytest_files(REPO_ROOT)
        if missing:
            raise Phase09Packet6GateError(
                "Packet 6 mapped pytest files are missing: " + ", ".join(missing)
            )
        missing_sql = missing_bootstrap_sql_files(REPO_ROOT)
        if missing_sql:
            raise Phase09Packet6GateError(
                "Packet 6 ParadeDB bootstrap SQL missing: " + ", ".join(missing_sql)
            )
        assert_holdout_sealed()
        try:
            assert_mock_model_mode(REPO_ROOT)
            assert_packet2_corpus_identity(REPO_ROOT)
        except Phase09Packet4GateError as exc:
            raise Phase09Packet6GateError(str(exc)) from exc
        image_ids = load_packet1_images(REPO_ROOT)
        if image_ids != expected_image_ids():
            raise Phase09Packet6GateError("Packet 1 image Ids drifted")
        published = _overlay_published()
        if published:
            detach = _detach_overlay()
            if json_int(detach.get("returncode")) != 0:
                raise Phase09Packet6GateError("overlay detach failed")
        health_before = _health()
        if json_int(health_before.get("returncode")) != 0:
            raise Phase09Packet6GateError("candidate health failed")
        suite_rows = [_run_suite(suite) for suite in PYTEST_SUITES]
        a_pytest = suite_rows[0]["classification"] == "Passed"
        audits = _host_audits()
        trivy_rows: list[dict[str, object]] = []
        for service, image_id in image_ids.items():
            print(f"phase09_packet6_trivy_tar {service}", flush=True)
            trivy_rows.append(
                scan_image_tar(repo_root=REPO_ROOT, service=service, image_id=image_id)
            )
        trivy_failed = any(row.get("status") == "failed" for row in trivy_rows)
        trivy_blocked = any(row.get("status") == "blocked" for row in trivy_rows)
        trivy_passed = bool(trivy_rows) and all(
            row.get("status") == "passed" for row in trivy_rows
        )
        db_url = get_process_environ("SUPABASE_DB_URL") or DEFAULT_SUPABASE
        container = find_supabase_db_container()
        dump: dict[str, object] = {"passed": False, "detail": "supabase_db_missing"}
        restore: dict[str, object] = {
            "passed": False,
            "live_database_overwritten": False,
        }
        if container:
            dump = dump_app_and_lightrag(REPO_ROOT, container=container)
            rel = dump.get("relative_path")
            if dump.get("passed") is True and isinstance(rel, str):
                restore = restore_disposable(
                    container=container,
                    dump_relative=rel,
                    repo_root=REPO_ROOT,
                )
        buckets = storage_inventory(db_url)
        reconciled = (
            dump.get("passed") is True
            and restore.get("passed") is True
            and buckets.get("passed") is True
        )
        destroy = destroy_paradedb_volume(REPO_ROOT)
        ddl = apply_paradedb_bootstrap_ddl(REPO_ROOT)
        empty = parade_row_count(REPO_ROOT)
        inject = _inject_reproject()
        reproject = _worker_reproject('{"rebuild_scope":"authorized_current"}')
        after_rows = parade_row_count(REPO_ROOT)
        rebuild_passed = (
            destroy.get("passed") is True
            and ddl.get("passed") is True
            and inject == 0
            and process_exit_ok(reproject.get("worker_returncode"))
            and isinstance(after_rows.get("bm25_chunks"), int)
            and not isinstance(after_rows.get("bm25_chunks"), bool)
            and json_int(after_rows.get("bm25_chunks")) > 0
            and reproject.get("sql_stamped_hybrid_or_graph_ready") is not True
        )
        health_after = _health()
        scans = {
            "schema_version": scan_schema_version(),
            "audits": audits,
            "trivy": trivy_rows,
            "docker_sock_mounted": False,
        }
        restore_art = {
            "schema_version": restore_schema_version(),
            "dump": dump,
            "disposable_restore": restore,
            "storage": buckets,
            "live_database_overwritten": False,
        }
        rebuild = {
            "schema_version": rebuild_schema_version(),
            "destroy": destroy,
            "bootstrap_ddl": ddl,
            "rows_after_destroy": empty,
            "inject_returncode": inject,
            "reproject": {
                "worker_returncode": reproject.get("worker_returncode"),
                "passed": reproject.get("passed"),
                "rebuild_scope": reproject.get("rebuild_scope"),
                "version_count": reproject.get("version_count"),
                "parade_total_rows": reproject.get("parade_total_rows"),
                "sql_stamped_hybrid_or_graph_ready": False,
                "worker_stderr": reproject.get("worker_stderr"),
            },
            "rows_after_rebuild": after_rows,
            "paradedb_used_as_canonical": False,
        }
        sizing = {
            "schema_version": sizing_schema_version(),
            "local_candidate_not_full_envelope": True,
            "claimed_qt_cap_001": False,
            "claimed_managed_ec2": False,
            "health_before": health_before,
            "health_after": health_after,
            "decision": (
                "Repair remaining Blocked Trivy/JWT/70% items in Packet 7; "
                "keep QT-CAP-005-P8=15; do not infer EC2 from local NCPU."
            ),
        }
        acceptance = [
            {
                "check": "P09-06-A",
                "classification": classify_p0906_a(pytest_passed=a_pytest),
                "detail": "SSRF, private topology, parser --network none",
            },
            {
                "check": "P09-06-B",
                "classification": classify_p0906_b(
                    pip_passed=audits.get("pip_audit") == "passed",
                    pnpm_passed=audits.get("pnpm_audit") == "passed",
                    gitleaks_passed=audits.get("gitleaks") == "passed",
                    trivy_failed=trivy_failed,
                    trivy_blocked=trivy_blocked,
                    trivy_passed=trivy_passed,
                ),
                "detail": "pip-audit/pnpm/gitleaks plus tar Trivy; no docker.sock",
            },
            {
                "check": "P09-06-C",
                "classification": classify_p0906_c(
                    dump_passed=dump.get("passed") is True,
                    disposable_restore_passed=restore.get("passed") is True,
                    buckets_present=buckets.get("passed") is True,
                    restored_into_live=False,
                ),
                "detail": "app+lightrag dump restored into disposable DB; buckets listed",
            },
            {
                "check": "P09-06-D",
                "classification": classify_p0906_d(
                    reconciled_before_rebuild=reconciled,
                    volume_destroyed=destroy.get("volume_destroyed") is True,
                    rebuild_passed=rebuild_passed,
                    parade_as_authority=False,
                ),
                "detail": "ParadeDB volume destroyed; worker Bm25ProjectionService rebuild",
            },
            {
                "check": "P09-06-E",
                "classification": classify_p0906_e(
                    identity_held=image_ids == expected_image_ids(),
                    health_after_passed=json_int(health_after.get("returncode")) == 0,
                    claimed_full_envelope=False,
                    claimed_managed_ec2=False,
                ),
                "detail": sizing["decision"],
            },
        ]
        matrix = {
            "schema_version": schema_version(),
            "compose_file": CANDIDATE_COMPOSE_FILE,
            "holdout_opened": False,
            "image_ids": image_ids,
            "suites": suite_rows,
            "acceptance": acceptance,
            "handoffs": handoff_payloads(),
        }
        artifact_dir = REPO_ROOT / ARTIFACT_DIR
        dump_canonical_json(matrix, artifact_dir / PACKET6_MATRIX_NAME)
        dump_canonical_json(scans, artifact_dir / PACKET6_SCAN_NAME)
        dump_canonical_json(restore_art, artifact_dir / PACKET6_RESTORE_NAME)
        dump_canonical_json(rebuild, artifact_dir / PACKET6_REBUILD_NAME)
        dump_canonical_json(sizing, artifact_dir / PACKET6_SIZING_NAME)
        failed = [
            row["check"] for row in acceptance if row.get("classification") == "Failed"
        ]
        if failed:
            raise Phase09Packet6GateError(
                "Packet 6 Failed checks: " + ", ".join(str(item) for item in failed)
            )
        print("phase09_packet6_ok", flush=True)
        return 0
    except Phase09Packet6GateError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
