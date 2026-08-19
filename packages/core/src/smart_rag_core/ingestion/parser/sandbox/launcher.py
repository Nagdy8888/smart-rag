"""Docker no-network parser sandbox launcher."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from smart_rag_core.ingestion.parser.adapters import infer_format, parse_file
from smart_rag_core.ingestion.parser.archive import reject_archive_bomb
from smart_rag_core.ingestion.parser.exceptions import (
    ParserError,
    ParserLimitExceeded,
    ParserSandboxError,
    ParserUnsupportedFormat,
)
from smart_rag_core.ingestion.parser.limits import (
    PARSER_SANDBOX_CPUS,
    PARSER_SANDBOX_INPUT_FILENAME,
    PARSER_SANDBOX_KILL_GRACE_SECONDS,
    PARSER_SANDBOX_KILL_TIMEOUT_SECONDS,
    PARSER_SANDBOX_MAX_INPUT_BYTES,
    PARSER_SANDBOX_MEMORY_MB,
    PARSER_SANDBOX_PIDS_LIMIT,
)
from smart_rag_core.ingestion.parser.types import ParseDisposition, ParseResult


@dataclass(frozen=True, slots=True)
class SandboxLaunchConfig:
    """Runtime configuration for one isolated parser invocation."""

    image: str
    use_docker: bool = True
    memory_mb: int = PARSER_SANDBOX_MEMORY_MB
    cpus: float = PARSER_SANDBOX_CPUS
    pids_limit: int = PARSER_SANDBOX_PIDS_LIMIT
    timeout_seconds: int = PARSER_SANDBOX_KILL_TIMEOUT_SECONDS
    kill_grace_seconds: int = PARSER_SANDBOX_KILL_GRACE_SECONDS


class ParserSandboxLauncher:
    """Launch parser work in a no-network, no-secret Docker sandbox."""

    def __init__(self, config: SandboxLaunchConfig | None = None) -> None:
        """Initialize launcher with optional override config.

        The default config always sets ``use_docker=True``. Missing Docker does
        not flip the launcher to in-process parsing. Callers that need
        in-process parsing (unit tests) must pass
        ``SandboxLaunchConfig(use_docker=False)`` explicitly.

        Args:
            config: Optional sandbox runtime override. ``None`` uses the
                production default (Docker required).
        """

        self._config = config or SandboxLaunchConfig(
            image="smart-rag-parser-sandbox:local",
            use_docker=True,
        )

    @property
    def config(self) -> SandboxLaunchConfig:
        """Return active sandbox configuration."""

        return self._config

    def run(
        self,
        *,
        payload: bytes,
        content_hash: str,
        filename: str,
        media_type: str | None = None,
        format_key: str | None = None,
    ) -> ParseResult:
        """Parse bytes inside sandbox boundaries.

        Args:
            payload: Exact object bytes.
            content_hash: Expected SHA-256 hex digest.
            filename: Original filename for format inference only. Bytes are
                always written as ``input.bin``; the name is never used as a
                host path.
            media_type: Optional MIME hint.
            format_key: Optional explicit format override.

        Returns:
            Closed parse result or failed disposition on bounded errors.

        Raises:
            ParserSandboxError: When Docker sandbox cannot be launched and
                in-process parsing was not explicitly configured.
        """

        if len(payload) > PARSER_SANDBOX_MAX_INPUT_BYTES:
            return _failed_result(
                content_hash=content_hash,
                format_key=format_key or "unknown",
                code="limit_exceeded:input_bytes",
                detail=f"input bytes {len(payload)} exceed max",
            )
        try:
            reject_archive_bomb(payload)
        except ParserLimitExceeded as exc:
            return _failed_result(
                content_hash=content_hash,
                format_key=format_key or "zip",
                code=exc.code,
                detail=exc.detail,
            )
        if not self._config.use_docker:
            return self._run_inprocess(
                payload=payload,
                content_hash=content_hash,
                filename=filename,
                media_type=media_type,
                format_key=format_key,
            )
        return self._run_docker(
            payload=payload,
            content_hash=content_hash,
            filename=filename,
            media_type=media_type,
            format_key=format_key,
        )

    def _run_inprocess(
        self,
        *,
        payload: bytes,
        content_hash: str,
        filename: str,
        media_type: str | None,
        format_key: str | None,
    ) -> ParseResult:
        """Direct adapter invocation when callers explicitly disable Docker.

        Args:
            payload: Exact object bytes.
            content_hash: Expected SHA-256 hex digest.
            filename: Original filename used only as a format hint.
            media_type: Optional MIME hint.
            format_key: Optional explicit format override.

        Returns:
            Closed parse result or failed disposition on adapter errors.
        """

        with tempfile.TemporaryDirectory(prefix="parser-local-") as temp_dir:
            input_path = Path(temp_dir) / PARSER_SANDBOX_INPUT_FILENAME
            input_path.write_bytes(payload)
            try:
                resolved = format_key or infer_format(
                    format_hint_path(filename), media_type
                )
            except ParserUnsupportedFormat as exc:
                return _failed_result(
                    content_hash=content_hash,
                    format_key=format_key or "unknown",
                    code=exc.code,
                    detail=exc.detail,
                )
            try:
                return parse_file(input_path, content_hash, resolved)
            except ParserError as exc:
                return _failed_result(
                    content_hash=content_hash,
                    format_key=resolved,
                    code=exc.code,
                    detail=exc.detail,
                )

    def _run_docker(
        self,
        *,
        payload: bytes,
        content_hash: str,
        filename: str,
        media_type: str | None,
        format_key: str | None,
    ) -> ParseResult:
        """Run parser runner inside ``docker run --network none``.

        Args:
            payload: Exact object bytes.
            content_hash: Expected SHA-256 hex digest.
            filename: Original filename used only as a format hint.
            media_type: Optional MIME hint.
            format_key: Optional explicit format override.

        Returns:
            Closed parse result or failed disposition on sandbox errors.

        Raises:
            ParserSandboxError: When the Docker CLI is missing or cannot start.

        Note:
            ``docker run`` stdout/stderr are decoded as UTF-8 with replacement.
            Windows locale encodings (cp1252) raise on CMU plot punctuation and
            abort the hybrid index job before ``result.json`` is read.
        """

        if shutil.which("docker") is None:
            raise ParserSandboxError("docker executable not found")
        try:
            resolved = format_key or infer_format(
                format_hint_path(filename), media_type
            )
        except ParserUnsupportedFormat as exc:
            return _failed_result(
                content_hash=content_hash,
                format_key=format_key or "unknown",
                code=exc.code,
                detail=exc.detail,
            )
        container_name = f"smart-rag-parser-{uuid4().hex}"
        with tempfile.TemporaryDirectory(prefix="parser-sandbox-") as temp_dir:
            input_path = Path(temp_dir) / "input" / PARSER_SANDBOX_INPUT_FILENAME
            output_path = Path(temp_dir) / "output" / "result.json"
            input_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            input_path.write_bytes(payload)
            request = {
                "input_path": f"/input/{PARSER_SANDBOX_INPUT_FILENAME}",
                "output_path": "/output/result.json",
                "content_hash": content_hash,
                "format_key": resolved,
                "media_type": media_type,
            }
            command = [
                "docker",
                "run",
                "--name",
                container_name,
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m",
                "--user",
                "10001:10001",
                "--memory",
                f"{self._config.memory_mb}m",
                "--cpus",
                str(self._config.cpus),
                "--pids-limit",
                str(self._config.pids_limit),
                "--security-opt",
                "no-new-privileges",
                "--cap-drop",
                "ALL",
                "--env",
                "PYTHONUNBUFFERED=1",
                "-v",
                f"{input_path.parent.resolve()}:/input:ro",
                "-v",
                f"{output_path.parent.resolve()}:/output:rw",
                self._config.image,
                "python",
                "/app/runner.py",
                json.dumps(request, separators=(",", ":")),
            ]
            started = time.monotonic()
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self._config.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                kill_sandbox_container(
                    container_name, grace_seconds=self._config.kill_grace_seconds
                )
                return _failed_result(
                    content_hash=content_hash,
                    format_key=resolved,
                    code="timeout",
                    detail="parser sandbox exceeded kill timeout",
                )
            except OSError as exc:
                raise ParserSandboxError("docker run failed to start") from exc
            if completed.returncode != 0:
                detail = (
                    completed.stderr or completed.stdout or "sandbox failed"
                ).strip()
                return _failed_result(
                    content_hash=content_hash,
                    format_key=resolved,
                    code="sandbox_nonzero",
                    detail=detail[:500],
                )
            if not output_path.exists():
                stdout_payload = completed.stdout.strip()
                if stdout_payload:
                    return ParseResult.model_validate_json(stdout_payload)
                return _failed_result(
                    content_hash=content_hash,
                    format_key=resolved,
                    code="missing_output",
                    detail="sandbox produced no result.json",
                )
            result = ParseResult.model_validate_json(
                output_path.read_text(encoding="utf-8")
            )
            metrics = result.resource_metrics.model_copy(
                update={"wall_seconds": time.monotonic() - started}
            )
            return result.model_copy(update={"resource_metrics": metrics})


def _docker_available() -> bool:
    """Compatibility alias for contract tests that probe Docker presence."""

    return docker_sandbox_available()


def docker_sandbox_available() -> bool:
    """Return whether Docker CLI responds to ``docker info``.

    Returns:
        ``True`` when ``docker`` is on PATH and ``docker info`` exits 0.
    """

    if shutil.which("docker") is None:
        return False
    try:
        completed = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return completed.returncode == 0


def inprocess_parser_permitted() -> bool:
    """Return whether env explicitly allows in-process parsing for tests.

    Returns:
        ``True`` only when ``ALLOW_INPROCESS_PARSER`` is truthy and
        ``APP_ENV`` is ``test``. Production and local workers must not
        rely on this path.
    """

    flag = os.environ.get("ALLOW_INPROCESS_PARSER", "").strip().lower()
    env = os.environ.get("APP_ENV", "").strip().lower()
    return flag in {"1", "true", "yes"} and env == "test"


def format_hint_path(filename: str) -> Path:
    """Return a basename-only path used for format inference.

    Args:
        filename: Caller-supplied original filename. Path components and
            parent traversal are discarded.

    Returns:
        A single-component ``Path`` suitable for suffix/MIME inference.
    """

    name = Path(str(filename).replace("\\", "/")).name
    if not name or name in {".", ".."}:
        return Path(PARSER_SANDBOX_INPUT_FILENAME)
    return Path(name)


def kill_sandbox_container(container_name: str, *, grace_seconds: int) -> None:
    """Send ``docker kill`` then ``docker rm -f`` for a timed-out sandbox.

    Args:
        container_name: Unique ``docker run --name`` assigned to the attempt.
        grace_seconds: Kill/rm subprocess timeout.

    Side Effects:
        Best-effort Docker CLI calls. Failures are swallowed so the caller
        can still return a failed parse disposition.
    """

    if shutil.which("docker") is None:
        return
    timeout = max(int(grace_seconds), 1)
    for command in (
        ["docker", "kill", container_name],
        ["docker", "rm", "-f", container_name],
    ):
        try:
            subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue


def _failed_result(
    *,
    content_hash: str,
    format_key: str,
    code: str,
    detail: str,
) -> ParseResult:
    """Build a failed parse result without partial elements."""

    from smart_rag_core.ingestion.parser.limits import (
        CLEANING_POLICY_VERSION,
        PARSER_CONFIG_VERSION,
    )
    from smart_rag_core.ingestion.parser.types import (
        CoverageAccounting,
        ParserResourceMetrics,
    )

    return ParseResult(
        disposition=ParseDisposition.FAILED,
        format=format_key,
        content_hash=content_hash,
        parser_version=PARSER_CONFIG_VERSION,
        cleaning_version=CLEANING_POLICY_VERSION,
        config_hash=ParseResult.stable_config_hash(
            PARSER_CONFIG_VERSION,
            CLEANING_POLICY_VERSION,
        ),
        coverage=CoverageAccounting(
            total_elements=0,
            text_elements=0,
            media_only_elements=0,
            removed_nodes=0,
            unsupported_regions=0,
            char_coverage_ratio=0.0,
        ),
        resource_metrics=ParserResourceMetrics(wall_seconds=0.0),
        warnings=(),
        detail=f"{code}: {detail}",
    )
