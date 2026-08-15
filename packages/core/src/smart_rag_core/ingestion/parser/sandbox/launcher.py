"""Docker no-network parser sandbox launcher."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from smart_rag_core.ingestion.parser.adapters import infer_format, parse_file
from smart_rag_core.ingestion.parser.archive import reject_archive_bomb
from smart_rag_core.ingestion.parser.exceptions import (
    ParserError,
    ParserLimitExceeded,
    ParserSandboxError,
)
from smart_rag_core.ingestion.parser.limits import (
    PARSER_SANDBOX_CPUS,
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
        """Initialize launcher with optional override config."""

        self._config = config or SandboxLaunchConfig(
            image="smart-rag-parser-sandbox:local",
            use_docker=_docker_available(),
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
            filename: Original filename for format inference.
            media_type: Optional MIME hint.
            format_key: Optional explicit format override.

        Returns:
            Closed parse result or failed disposition on bounded errors.

        Raises:
            ParserSandboxError: When sandbox cannot be launched.
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
        """Direct adapter invocation for unit tests when Docker is unavailable."""

        with tempfile.TemporaryDirectory(prefix="parser-local-") as temp_dir:
            input_path = Path(temp_dir) / filename
            input_path.write_bytes(payload)
            resolved = format_key or infer_format(input_path, media_type)
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
        """Run parser runner inside ``docker run --network none``."""

        if shutil.which("docker") is None:
            raise ParserSandboxError("docker executable not found")
        with tempfile.TemporaryDirectory(prefix="parser-sandbox-") as temp_dir:
            input_path = Path(temp_dir) / "input" / filename
            output_path = Path(temp_dir) / "output" / "result.json"
            input_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            input_path.write_bytes(payload)
            request = {
                "input_path": "/input/" + filename,
                "output_path": "/output/result.json",
                "content_hash": content_hash,
                "format_key": format_key,
                "media_type": media_type,
            }
            command = [
                "docker",
                "run",
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
                    timeout=self._config.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                _kill_container_gracefully(exc)
                return _failed_result(
                    content_hash=content_hash,
                    format_key=format_key or "unknown",
                    code="timeout",
                    detail="parser sandbox exceeded kill timeout",
                )
            if completed.returncode != 0:
                detail = (
                    completed.stderr or completed.stdout or "sandbox failed"
                ).strip()
                return _failed_result(
                    content_hash=content_hash,
                    format_key=format_key or "unknown",
                    code="sandbox_nonzero",
                    detail=detail[:500],
                )
            if not output_path.exists():
                stdout_payload = completed.stdout.strip()
                if stdout_payload:
                    return ParseResult.model_validate_json(stdout_payload)
                return _failed_result(
                    content_hash=content_hash,
                    format_key=format_key or "unknown",
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
    """Return whether Docker CLI responds to ``docker info``."""

    if shutil.which("docker") is None:
        return False
    try:
        completed = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return completed.returncode == 0


def _kill_container_gracefully(exc: subprocess.TimeoutExpired) -> None:
    """Best-effort kill for timed-out sandbox containers."""

    _ = exc


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
