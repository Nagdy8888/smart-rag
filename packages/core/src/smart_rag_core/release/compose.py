"""Docker Compose helpers for the candidate stack without Packet 8 overlay."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from smart_rag_core.release.constants import CANDIDATE_COMPOSE_FILE
from smart_rag_core.release.errors import CandidateReleaseError
from smart_rag_core.release.io import as_json_list, as_json_object


def compose_env_file(repo_root: Path) -> Path:
    """Return the Compose env file, preferring ``.env.compose``.

    CI checkouts typically have only tracked ``.env.example``. Local
    ``.env.compose`` and ``.env`` still win when present.

    Args:
        repo_root: Repository root.

    Returns:
        Existing env file path.

    Raises:
        CandidateReleaseError: If no Compose env file exists.
    """

    compose_env = repo_root / ".env.compose"
    if compose_env.is_file():
        return compose_env
    local_env = repo_root / ".env"
    if local_env.is_file():
        return local_env
    example_env = repo_root / ".env.example"
    if example_env.is_file():
        return example_env
    raise CandidateReleaseError("No Compose environment file found")


def compose_command(repo_root: Path) -> list[str]:
    """Return the candidate Compose argv (no Packet 8 overlay).

    Args:
        repo_root: Repository root.

    Returns:
        ``docker compose --env-file ... -f docker-compose.yml`` prefix.
    """

    docker = shutil.which("docker") or "docker"
    return [
        docker,
        "compose",
        "--env-file",
        str(compose_env_file(repo_root)),
        "-f",
        str(repo_root / CANDIDATE_COMPOSE_FILE),
    ]


def run_compose(
    repo_root: Path,
    arguments: list[str],
    *,
    timeout_seconds: int = 120,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one candidate Compose command.

    Args:
        repo_root: Repository root.
        arguments: Arguments after the Compose prefix.
        timeout_seconds: Hard timeout.
        input_text: Optional stdin.

    Returns:
        Completed process with captured text. Timeouts become returncode 1
        so live contract tests can skip when Docker Desktop is unresponsive.
    """

    command = [*compose_command(repo_root), *arguments]
    try:
        return subprocess.run(  # noqa: S603
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            input=input_text,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout="",
            stderr=f"timed out after {timeout_seconds}s",
        )


def docker_engine_resources() -> tuple[int | None, int | None]:
    """Return Docker engine CPU count and memory bytes.

    Returns:
        ``(ncpu, mem_bytes)`` when ``docker info`` succeeds; otherwise
        ``(None, None)``.
    """

    docker = shutil.which("docker") or "docker"
    try:
        completed = subprocess.run(  # noqa: S603
            [
                docker,
                "info",
                "--format",
                "{{.NCPU}} {{.MemTotal}}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, None
    if completed.returncode != 0:
        return None, None
    parts = completed.stdout.strip().split()
    if len(parts) < 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def inspect_image(image_name: str) -> dict[str, object]:
    """Return ``docker inspect`` JSON for one image.

    Args:
        image_name: Image reference.

    Returns:
        First inspect object.

    Raises:
        CandidateReleaseError: If inspect fails or is not an object list.
    """

    docker = shutil.which("docker") or "docker"
    try:
        completed = subprocess.run(  # noqa: S603
            [docker, "inspect", image_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CandidateReleaseError(
            f"docker inspect timed out for {image_name}"
        ) from exc
    if completed.returncode != 0:
        raise CandidateReleaseError(f"docker inspect failed for {image_name}")
    loaded: object = json.loads(completed.stdout)
    try:
        rows = as_json_list(loaded, source=f"docker inspect {image_name}")
    except ValueError as exc:
        raise CandidateReleaseError(str(exc)) from exc
    if not rows:
        raise CandidateReleaseError(
            f"docker inspect returned no object for {image_name}"
        )
    try:
        return as_json_object(rows[0], source=f"docker inspect {image_name}")
    except ValueError as exc:
        raise CandidateReleaseError(
            f"docker inspect payload invalid for {image_name}"
        ) from exc
