"""Fail when Phase 9 Packet 5 fault collections are empty or identity drifted."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import psycopg
from smart_rag_core.release.compose import run_compose
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    CANDIDATE_COMPOSE_FILE,
    PACKET8_OVERLAY_FILE,
    PRIVATE_COMPOSE_SERVICES,
)
from smart_rag_core.release.io import as_json_object, dump_canonical_json
from smart_rag_core.release.packet4 import (
    API_EXPECTED_JWT_ISSUER,
    LOCAL_GOTRUE_JWT_ISSUER,
    Phase09Packet4GateError,
    assert_mock_model_mode,
    assert_packet2_corpus_identity,
    classify_jwt_issuer_alignment,
    expected_image_ids,
    load_packet1_images,
)
from smart_rag_core.release.packet5 import (
    PACKET5_FAULT_NAME,
    PACKET5_MATRIX_NAME,
    PACKET5_RECONCILE_NAME,
    PYTEST_SUITES,
    Packet5Suite,
    Phase09Packet5GateError,
    assert_corpus_holdout_flag,
    assert_holdout_sealed,
    classify_counts,
    classify_p0905_a,
    classify_p0905_b,
    classify_p0905_c,
    classify_p0905_d,
    classify_p0905_e,
    counts_from_junit,
    failure_detail,
    fault_schema_version,
    handoff_payloads,
    missing_pytest_files,
    pytest_command,
    reconcile_schema_version,
    schema_version,
)
from smart_rag_core.release.packet5_faults import (
    canonical_drift,
    compose_env_value,
    compose_start,
    compose_stop,
    kill_and_restart_worker,
    parade_row_count,
    ready_payload,
    restore_services,
    snapshot_canonical,
    valkey_fill_until_reject,
    valkey_flush,
    valkey_wrong_password,
    version_mismatch,
    wait_dependency,
)
from smart_rag_core.release.ports import parse_compose_ps_text
from smart_rag_core.settings.base import get_process_environ

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUPABASE = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
WORKER_DEGRADE_PATH = "/tmp/hybrid_degrade.py"  # noqa: S108 - worker tmpfs
DEGRADE_QUERY = "INV-SR-1001 retention policy"


def _json_dict(value: Any, *, source: str) -> dict[str, object]:
    """Require a JSON object.

    Args:
        value: Decoded JSON.
        source: Path label.

    Returns:
        String-keyed object.

    Raises:
        Phase09Packet5GateError: If ``value`` is not an object.
    """

    if not isinstance(value, dict):
        raise Phase09Packet5GateError(f"{source} is not a JSON object")
    return as_json_object(cast(dict[str, object], value), source=source)


def _suite_class(suites: list[dict[str, object]], suite_id: str) -> str:
    """Return one suite classification.

    Args:
        suites: Suite rows.
        suite_id: Identifier.

    Returns:
        Classification string, or empty.
    """

    for row in suites:
        if row.get("suite_id") == suite_id:
            value = row.get("classification")
            return str(value) if value is not None else ""
    return ""


def _run_suite(suite: Packet5Suite) -> dict[str, object]:
    """Execute one fail-closed pytest suite and return its matrix row.

    Args:
        suite: Suite to run.

    Returns:
        JSON-object suite row.

    Raises:
        Phase09Packet5GateError: If JUnit output is missing.

    Side Effects:
        Runs pytest from the repository root.
    """

    with tempfile.TemporaryDirectory(prefix="smart-rag-phase09-p5-") as directory:
        report = Path(directory) / "junit.xml"
        completed = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "pytest", *pytest_command(suite, report)],
            cwd=REPO_ROOT,
            check=False,
        )
        try:
            counts = counts_from_junit(report)
        except Phase09Packet4GateError as exc:
            raise Phase09Packet5GateError(str(exc)) from exc
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
        f"phase09_packet5_{suite.suite_id} "
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
        publishers: Compose published ports.

    Returns:
        Service names that must be detached.
    """

    return [name for name in PRIVATE_COMPOSE_SERVICES if publishers.get(name)]


def _detach_overlay() -> dict[str, object]:
    """Recreate candidate compose without the Packet 8 overlay.

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


def _inject_degrade_module() -> int:
    """Copy ``hybrid_degrade.py`` onto worker tmpfs.

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
        / "hybrid_degrade.py"
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
                f"Path({WORKER_DEGRADE_PATH!r}).write_text("
                "sys.stdin.read(), encoding='utf-8')"
            ),
        ],
        timeout_seconds=60,
        input_text=text,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout)
    return completed.returncode


def _first_profile_user_id(db_url: str) -> str | None:
    """Return one active profile id for worker-side retrieve.

    Args:
        db_url: Local Supabase URL.

    Returns:
        User id, or ``None``.
    """

    with psycopg.connect(db_url, connect_timeout=8) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id::text
                FROM app.profiles
                WHERE disabled_at IS NULL
                LIMIT 1
                """
            )
            row = cursor.fetchone()
    if row is None:
        return None
    return str(row[0])


def _worker_degrade(user_id: str) -> dict[str, object]:
    """Run injected Hybrid degrade inside the frozen worker.

    Args:
        user_id: Profile primary key.

    Returns:
        Parsed payload. Query text is not stored.
    """

    stdin = json.dumps({"user_id": user_id, "query": DEGRADE_QUERY})
    completed = run_compose(
        REPO_ROOT,
        ["exec", "-T", "worker", "python", WORKER_DEGRADE_PATH],
        timeout_seconds=180,
        input_text=stdin,
    )
    payload: dict[str, object] = {}
    stdout = completed.stdout or ""
    parsed = False
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            loaded: object = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            payload = _json_dict(loaded, source="worker-degrade")
            parsed = True
            break
    if not parsed:
        payload = {"parse_error": True, "stdout_len": len(stdout)}
    payload["worker_returncode"] = completed.returncode
    payload["query_omitted"] = True
    stderr = (completed.stderr or "").strip()
    if stderr:
        payload["stderr_tail"] = stderr[-400:]
    return payload


def _acceptance_rows(
    *,
    suites: list[dict[str, object]],
    worker: Mapping[str, object],
    drift: Mapping[str, object],
    parade_down: Mapping[str, object],
    degrade: Mapping[str, object],
    parade_recovered: bool,
    deny: Mapping[str, object],
    limits_down: Mapping[str, object],
    cache_down: Mapping[str, object],
    fill: Mapping[str, object],
    jwt_blocked: bool,
    identity_held: bool,
    health_after_passed: bool,
) -> list[dict[str, object]]:
    """Build P09-05-A through P09-05-E acceptance rows.

    Args:
        suites: Pytest suite rows.
        worker: Live worker kill/restart report.
        drift: Canonical drift report.
        parade_down: Ready poll while ParadeDB is stopped.
        degrade: Worker Hybrid degrade payload.
        parade_recovered: ParadeDB start plus row count succeeded.
        deny: Wrong-password deny report.
        limits_down: Limits outage poll.
        cache_down: Cache outage poll.
        fill: Noeviction fill report.
        jwt_blocked: Frozen API iss mismatch.
        identity_held: Image and corpus identity held.
        health_after_passed: Health after restore passed.

    Returns:
        Acceptance matrix rows.
    """

    a_pytest = _suite_class(suites, "worker_reclaim_resume") == "Passed"
    b_pytest = _suite_class(suites, "paradedb_dense_term_degrade") == "Passed"
    c_pytest = _suite_class(suites, "valkey_ownership_fail_closed") == "Passed"
    d_pytest = _suite_class(suites, "sse_resume_one_paid_run") == "Passed"
    return [
        {
            "check": "P09-05-A",
            "classification": classify_p0905_a(
                pytest_passed=a_pytest,
                worker_restart_passed=worker.get("passed") is True,
                duplicate_canonical=drift.get("duplicate_canonical") is True,
            ),
            "detail": (
                "Lease/crash pytest plus live worker kill/restart. "
                f"duplicate_canonical={drift.get('duplicate_canonical')}"
            ),
        },
        {
            "check": "P09-05-B",
            "classification": classify_p0905_b(
                pytest_passed=b_pytest,
                parade_down_visible=parade_down.get("passed") is True,
                degrade_passed=degrade.get("passed") is True,
                recovered=parade_recovered,
            ),
            "detail": (
                "ParadeDB stop visible on ready; Hybrid bm25_unavailable; "
                "volume not destroyed. "
                f"fallback={degrade.get('fallback_reason')}"
            ),
        },
        {
            "check": "P09-05-C",
            "classification": classify_p0905_c(
                pytest_passed=c_pytest,
                deny_passed=deny.get("denied") is True,
                limits_down_visible=limits_down.get("passed") is True,
                cache_down_visible=cache_down.get("passed") is True,
                fill_recovered=fill.get("passed") is True,
            ),
            "detail": (
                "requirepass deny, independent stop of limits and cache, "
                "noeviction fill then restart. Named ACL users Phase 10."
            ),
        },
        {
            "check": "P09-05-D",
            "classification": classify_p0905_d(
                pytest_passed=d_pytest,
                live_passed=False,
                jwt_blocked=jwt_blocked,
            ),
            "detail": (
                "ASGI SSE resume/heartbeat/deadline. Live docker EventSource "
                f"jwt_blocked={jwt_blocked} (Packet 7)."
            ),
        },
        {
            "check": "P09-05-E",
            "classification": classify_p0905_e(
                identity_held=identity_held,
                canonical_reconciled=drift.get("canonical_matched") is True,
                health_after_passed=health_after_passed,
                authority_transferred=drift.get("authority_transferred") is True,
            ),
            "detail": (
                "Post-recovery version/chunk counts match the pre-fault "
                "snapshot. Jobs/ledgers may reclaim. ParadeDB/Valkey remain "
                "non-authoritative."
            ),
        },
    ]


def main(argv: list[str] | None = None) -> int:
    """Run Packet 5 fault measurements and reject zero collection.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        ``0`` when suites collected tests, identity held, and A-E are not Failed.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    restored = False
    try:
        missing = missing_pytest_files(REPO_ROOT)
        if missing:
            raise Phase09Packet5GateError(
                "Packet 5 mapped pytest files are missing: " + ", ".join(missing)
            )
        assert_holdout_sealed()
        assert_corpus_holdout_flag(REPO_ROOT)
        try:
            assert_mock_model_mode(REPO_ROOT)
            assert_packet2_corpus_identity(REPO_ROOT)
        except Phase09Packet4GateError as exc:
            raise Phase09Packet5GateError(str(exc)) from exc
        image_ids = load_packet1_images(REPO_ROOT)
        if image_ids != expected_image_ids():
            raise Phase09Packet5GateError("Packet 1 image Ids drifted")
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
            if int(detach["returncode"]) != 0:
                raise Phase09Packet5GateError("overlay detach failed")
        health_before = _health()
        overlay_report["health"] = health_before
        if int(health_before["returncode"]) != 0:
            raise Phase09Packet5GateError("candidate health failed")
        if _overlay_published(_compose_publishers()):
            raise Phase09Packet5GateError("private ports still published")
        db_url = get_process_environ("SUPABASE_DB_URL") or DEFAULT_SUPABASE
        suite_rows: list[dict[str, object]] = []
        for suite in PYTEST_SUITES:
            row = _run_suite(suite)
            suite_rows.append(row)
            if row["classification"] != "Passed":
                print(f"phase09_packet5_suite_failed {suite.suite_id}: {row['detail']}")
        baseline = snapshot_canonical(db_url)
        parade_before = parade_row_count(REPO_ROOT)
        worker = kill_and_restart_worker(REPO_ROOT)
        inject_code = _inject_degrade_module()
        mismatch = version_mismatch(REPO_ROOT)
        stop_parade = compose_stop(REPO_ROOT, "paradedb")
        parade_down = wait_dependency("paradedb", "down")
        user_id = _first_profile_user_id(db_url)
        degrade: dict[str, object] = {
            "passed": False,
            "detail": "profile_missing",
        }
        if user_id is not None and inject_code == 0:
            degrade = _worker_degrade(user_id)
        start_parade = compose_start(REPO_ROOT, "paradedb")
        parade_up = wait_dependency("paradedb", "ok", timeout_seconds=90)
        parade_after = parade_row_count(REPO_ROOT)
        deny_limits = valkey_wrong_password(REPO_ROOT, service="valkey-limits")
        deny_cache = valkey_wrong_password(REPO_ROOT, service="valkey-cache")
        stop_limits = compose_stop(REPO_ROOT, "valkey-limits")
        limits_down = wait_dependency("valkey_limits", "down")
        start_limits = compose_start(REPO_ROOT, "valkey-limits")
        wait_dependency("valkey_limits", "ok", timeout_seconds=90)
        stop_cache = compose_stop(REPO_ROOT, "valkey-cache")
        cache_down = wait_dependency("valkey_cache", "down")
        start_cache = compose_start(REPO_ROOT, "valkey-cache")
        wait_dependency("valkey_cache", "ok", timeout_seconds=90)
        password = compose_env_value(REPO_ROOT, "VALKEY_LIMITS_PASSWORD")
        fill: dict[str, object] = {"passed": False, "detail": "password_missing"}
        if password:
            valkey_flush(REPO_ROOT, service="valkey-limits", password=password)
            fill = valkey_fill_until_reject(REPO_ROOT, password=password)
        fill_restart = compose_start(REPO_ROOT, "valkey-limits")
        flush: dict[str, object] = {"passed": False, "detail": "password_missing"}
        if password:
            flush = valkey_flush(REPO_ROOT, service="valkey-limits", password=password)
        fill["flush"] = flush
        restore = restore_services(REPO_ROOT)
        restored = True
        after = snapshot_canonical(db_url)
        drift = canonical_drift(baseline, after)
        health_after = _health()
        jwt = classify_jwt_issuer_alignment(
            token_iss=LOCAL_GOTRUE_JWT_ISSUER,
            api_expected_iss=API_EXPECTED_JWT_ISSUER,
        )
        jwt_blocked = jwt.get("classification") == "Blocked"
        parade_recovered = (
            int(start_parade["returncode"]) == 0
            and parade_up.get("passed") is True
            and isinstance(parade_before.get("bm25_chunks"), int)
            and parade_after.get("bm25_chunks") == parade_before.get("bm25_chunks")
        )
        fill_recovered = (
            fill.get("passed") is True and int(fill_restart["returncode"]) == 0
        )
        fill["recovered"] = fill_recovered
        fill["passed"] = fill_recovered
        deny = {
            "denied": deny_limits.get("denied") is True
            and deny_cache.get("denied") is True,
            "limits": deny_limits,
            "cache": deny_cache,
            "named_acl_users": False,
        }
        identity_held = image_ids == expected_image_ids()
        health_after_passed = int(health_after["returncode"]) == 0
        acceptance = _acceptance_rows(
            suites=suite_rows,
            worker=worker,
            drift=drift,
            parade_down=parade_down,
            degrade=degrade,
            parade_recovered=parade_recovered,
            deny=deny,
            limits_down=limits_down,
            cache_down=cache_down,
            fill=fill,
            jwt_blocked=jwt_blocked,
            identity_held=identity_held,
            health_after_passed=health_after_passed,
        )
        faults = {
            "schema_version": fault_schema_version(),
            "compose_file": CANDIDATE_COMPOSE_FILE,
            "overlay_file_is_candidate": False,
            "volume_destroyed": False,
            "image_rebuilt": False,
            "holdout_opened": False,
            "worker": worker,
            "inject_degrade_returncode": inject_code,
            "version_mismatch": mismatch,
            "stop_paradedb": stop_parade,
            "paradedb_down": parade_down,
            "hybrid_degrade": degrade,
            "start_paradedb": start_parade,
            "paradedb_up": parade_up,
            "parade_rows_before": parade_before,
            "parade_rows_after": parade_after,
            "deny": deny,
            "stop_valkey_limits": stop_limits,
            "valkey_limits_down": limits_down,
            "start_valkey_limits": start_limits,
            "stop_valkey_cache": stop_cache,
            "valkey_cache_down": cache_down,
            "start_valkey_cache": start_cache,
            "fill": fill,
            "restore": restore,
            "ready_sample": ready_payload(),
        }
        reconcile = {
            "schema_version": reconcile_schema_version(),
            "before": baseline,
            "after": after,
            "drift": drift,
            "health_before": health_before,
            "health_after": health_after,
            "jwt": jwt,
            "identity_held": identity_held,
            "overlay": overlay_report,
        }
        matrix = {
            "schema_version": schema_version(),
            "compose_file": CANDIDATE_COMPOSE_FILE,
            "overlay_file_is_candidate": False,
            "holdout_opened": False,
            "mock_model_mode": True,
            "image_ids": image_ids,
            "suites": suite_rows,
            "acceptance": acceptance,
            "handoffs": handoff_payloads(),
            "jwt": jwt,
        }
        artifact_dir = REPO_ROOT / ARTIFACT_DIR
        dump_canonical_json(matrix, artifact_dir / PACKET5_MATRIX_NAME)
        dump_canonical_json(faults, artifact_dir / PACKET5_FAULT_NAME)
        dump_canonical_json(reconcile, artifact_dir / PACKET5_RECONCILE_NAME)
        failed = [
            row["check"] for row in acceptance if row.get("classification") == "Failed"
        ]
        if failed:
            raise Phase09Packet5GateError(
                "Packet 5 Failed checks: " + ", ".join(str(item) for item in failed)
            )
        print("phase09_packet5_ok")
        return 0
    except Phase09Packet5GateError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    finally:
        if not restored:
            restore_services(REPO_ROOT)
            _health()


if __name__ == "__main__":
    raise SystemExit(main())
