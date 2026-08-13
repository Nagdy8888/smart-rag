"""Hard-failing local Phase 2 integration gate with zero mandatory skips."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_ENV_CANDIDATES = (
    REPO_ROOT / ".env.compose",
    REPO_ROOT / ".env",
)
MANDATORY_TESTS = (
    "tests/contract/test_schema_reset.py",
    "tests/contract/test_rls_matrix.py",
    "tests/contract/test_jwks_auth.py",
    "tests/contract/test_invitations_auth.py",
    "tests/contract/test_auth_rate_limits.py",
    "tests/contract/test_auth_lifecycle.py",
    "tests/contract/test_local_auth_mail.py",
    "tests/contract/test_storage_buckets_rls.py",
    "tests/contract/test_upload_quota.py",
    "tests/contract/test_quarantine_cleanup.py",
    "tests/contract/test_graph_eligibility_storage.py",
    "tests/contract/test_restricted_read_audit.py",
    "tests/contract/test_storage_live_api.py",
    "tests/contract/test_audit_chain.py",
    "tests/contract/test_connection_budgets.py",
    "tests/contract/test_privileged_secrets_absent.py",
    "tests/contract/test_paradedb_bm25.py",
    "tests/contract/test_arabic_normalization_parity.py",
    (
        "tests/contract/test_pgvector_capabilities.py"
        "::test_local_pgvector_capabilities_and_selective_filter"
    ),
    (
        "tests/contract/test_pgvector_capabilities.py"
        "::test_unsupported_pgvector_version_pattern_is_fail_closed"
    ),
    (
        "tests/contract/test_pgvector_capabilities.py"
        "::test_default_local_url_constant_matches_documented_supabase_cli_port"
    ),
    "tests/contract/test_compose_topology.py",
    "tests/contract/test_local_lifecycle_scripts.py",
)
OPTIONAL_MANAGED_TESTS = (
    (
        "tests/contract/test_pgvector_capabilities.py"
        "::test_managed_pgvector_capabilities_when_configured"
    ),
    "tests/contract/test_jwks_rollover.py",
)


class Phase2GateError(RuntimeError):
    """Raised when a mandatory local Phase 2 prerequisite or test fails."""


def _required_executable(name: str) -> str:
    """Resolve a required executable.

    Args:
        name: Command name accepted by :func:`shutil.which`.

    Returns:
        Absolute executable path.

    Raises:
        Phase2GateError: If the executable is unavailable.
    """

    executable = shutil.which(name)
    if executable is None:
        raise Phase2GateError(f"required executable unavailable: {name}")
    return executable


def _run_bounded(
    command: list[str],
    *,
    label: str,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    """Run one prerequisite command without echoing credential-bearing output.

    Args:
        command: Fixed executable argument vector.
        label: Sanitized operation name.
        timeout_seconds: Hard child-process timeout.

    Returns:
        Completed process on success.

    Raises:
        Phase2GateError: If the command times out or exits non-zero.
    """

    try:
        completed = subprocess.run(  # noqa: S603 - fixed local gate commands.
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise Phase2GateError(f"{label} timed out") from exc
    if completed.returncode != 0:
        raise Phase2GateError(f"{label} failed with exit {completed.returncode}")
    return completed


def _compose_env_file() -> Path:
    """Return the existing Compose environment file.

    Returns:
        ``.env.compose`` when present, otherwise ``.env``.

    Raises:
        Phase2GateError: If neither file exists.
    """

    for candidate in COMPOSE_ENV_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise Phase2GateError("Compose environment file is missing")


def _ensure_local_supabase(pnpm: str) -> None:
    """Require the local Supabase stack, starting it when absent.

    Args:
        pnpm: Absolute workspace package-runner path.

    Side Effects:
        May start the local Supabase CLI stack. Status/start output is captured
        because it contains ephemeral local credentials.
    """

    status_command = [pnpm, "exec", "supabase", "status", "-o", "json"]
    try:
        status = subprocess.run(  # noqa: S603 - fixed local CLI command.
            status_command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise Phase2GateError("local Supabase status timed out") from exc
    if status.returncode != 0:
        _run_bounded(
            [pnpm, "exec", "supabase", "start"],
            label="local Supabase start",
            timeout_seconds=240,
        )
    _run_bounded(
        status_command,
        label="local Supabase status",
        timeout_seconds=30,
    )


def _ensure_paradedb(docker: str, env_file: Path) -> None:
    """Require healthy private ParadeDB, starting only that service if absent.

    Args:
        docker: Absolute Docker executable path.
        env_file: Existing Compose environment file.

    Side Effects:
        May start the private ParadeDB Compose service and waits for health.
    """

    compose = [docker, "compose", "--env-file", str(env_file)]
    ps = _run_bounded(
        [*compose, "ps", "--status", "running", "--quiet", "paradedb"],
        label="ParadeDB process query",
        timeout_seconds=30,
    )
    if not ps.stdout.strip():
        _run_bounded(
            [*compose, "up", "-d", "--wait", "paradedb"],
            label="ParadeDB start",
            timeout_seconds=240,
        )
    pg_search = _run_bounded(
        [
            *compose,
            "exec",
            "-T",
            "paradedb",
            "psql",
            "-U",
            "paradedb",
            "-d",
            "paradedb",
            "-tAc",
            ("SELECT extname FROM pg_extension WHERE extname = 'pg_search';"),
        ],
        label="ParadeDB pg_search health",
        timeout_seconds=30,
    )
    if pg_search.stdout.strip() != "pg_search":
        raise Phase2GateError("ParadeDB pg_search extension is unavailable")


def _junit_counts(report: Path) -> tuple[int, int, int, int]:
    """Read test/failure/error/skip totals from a pytest JUnit report.

    Args:
        report: JUnit XML path generated by pytest.

    Returns:
        ``(tests, failures, errors, skipped)`` totals.

    Raises:
        Phase2GateError: If the report is missing or malformed.
    """

    try:
        root = ET.parse(report).getroot()  # noqa: S314 - local pytest output only.
    except (ET.ParseError, OSError) as exc:
        raise Phase2GateError("mandatory pytest report is unavailable") from exc

    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise Phase2GateError("mandatory pytest report contains no test suite")

    def total(attribute: str) -> int:
        """Sum one integer JUnit attribute across suites."""

        return sum(int(suite.attrib.get(attribute, "0")) for suite in suites)

    return (
        total("tests"),
        total("failures"),
        total("errors"),
        total("skipped"),
    )


def _run_mandatory_tests(pytest: str) -> None:
    """Run the mandatory local suite and fail on any skip.

    Args:
        pytest: Absolute pytest executable path.

    Raises:
        Phase2GateError: On zero collection, skip, failure, or error.

    Side Effects:
        Runs local database, Auth, Storage, and ParadeDB integration tests.
    """

    with tempfile.TemporaryDirectory(prefix="smart-rag-phase2-") as directory:
        report = Path(directory) / "junit.xml"
        completed = subprocess.run(  # noqa: S603 - fixed local test command.
            [
                pytest,
                "-q",
                "--junitxml",
                str(report),
                *MANDATORY_TESTS,
            ],
            cwd=REPO_ROOT,
            check=False,
        )
        tests, failures, errors, skipped = _junit_counts(report)
    print(
        "phase2_local_tests "
        f"tests={tests} failures={failures} errors={errors} skipped={skipped}"
    )
    if tests == 0:
        raise Phase2GateError("mandatory Phase 2 suite collected zero tests")
    if completed.returncode != 0 or failures or errors:
        raise Phase2GateError("mandatory Phase 2 suite failed")
    if skipped:
        raise Phase2GateError("mandatory Phase 2 suite contains skipped tests")


def main() -> int:
    """Run the hard-failing local Phase 2 integration gate.

    Returns:
        ``0`` only when prerequisites are healthy and all mandatory tests pass
        without skips; otherwise ``1``.
    """

    try:
        pnpm = _required_executable("pnpm")
        docker = _required_executable("docker")
        pytest = _required_executable("pytest")
        env_file = _compose_env_file()
        _ensure_local_supabase(pnpm)
        _ensure_paradedb(docker, env_file)
        _run_mandatory_tests(pytest)
    except (OSError, Phase2GateError) as exc:
        print(f"Phase 2 integration gate failed: {exc}", file=sys.stderr)
        return 1

    optional = ", ".join(OPTIONAL_MANAGED_TESTS)
    print(
        "Phase 2 local integration gate passed; "
        f"managed-only tests not run by this gate: {optional}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
