"""Isolated current-parser and local-AnyDoc lanes."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from smart_rag_core.evaluation.parser_bakeoff.anydoc import (
    MarkdownConverter,
    anydoc_config_extra,
    convert_with_anydoc,
    failed_lane_result,
    map_anydoc_exception,
    parse_anydoc_markdown_bytes,
    stamp_anydoc_parse,
)
from smart_rag_core.evaluation.parser_bakeoff.constants import (
    ANYDOC_CLEANING_VERSION,
    ANYDOC_IMAGE,
    ANYDOC_LANE,
    ANYDOC_PARSER_VERSION,
    CURRENT_LANE,
    FORBIDDEN_SANDBOX_ENV,
    LaneId,
)
from smart_rag_core.evaluation.parser_bakeoff.models import BakeoffError
from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    PARSER_CONFIG_VERSION,
    PARSER_SANDBOX_CPUS,
    PARSER_SANDBOX_INPUT_FILENAME,
    PARSER_SANDBOX_KILL_GRACE_SECONDS,
    PARSER_SANDBOX_KILL_TIMEOUT_SECONDS,
    PARSER_SANDBOX_MAX_INPUT_BYTES,
    PARSER_SANDBOX_MEMORY_MB_HARD,
    PARSER_SANDBOX_PIDS_LIMIT,
)
from smart_rag_core.ingestion.parser.sandbox.launcher import (
    ParserSandboxLauncher,
    SandboxLaunchConfig,
    kill_sandbox_container,
)
from smart_rag_core.ingestion.parser.types import ParseResult

__all__ = [
    "LaneParseRequest",
    "MarkdownConverter",
    "anydoc_config_extra",
    "anydoc_docker_command",
    "convert_with_anydoc",
    "failed_lane_result",
    "map_anydoc_exception",
    "parse_anydoc_docker",
    "parse_anydoc_inprocess",
    "parse_anydoc_markdown_bytes",
    "parse_current_lane",
    "parse_lane",
    "stamp_anydoc_parse",
]


@dataclass(frozen=True, slots=True)
class LaneParseRequest:
    """One bounded parse request for a bake-off lane."""

    payload: bytes
    content_hash: str
    filename: str
    media_type: str | None
    lane_id: LaneId
    run_id: str
    use_docker: bool = True


def anydoc_docker_command(
    *,
    container_name: str,
    input_dir: Path,
    output_dir: Path,
    request_json: str,
    image: str = ANYDOC_IMAGE,
) -> list[str]:
    """Build the no-network AnyDoc ``docker run`` argv.

    Args:
        container_name: Unique container name.
        input_dir: Host input directory mounted read-only.
        output_dir: Host output directory.
        request_json: Runner JSON request.
        image: Image tag.

    Returns:
        Argument vector. Contains no secret values.
    """

    for forbidden in FORBIDDEN_SANDBOX_ENV:
        if forbidden in request_json:
            raise BakeoffError("sandbox_secret", "request must not carry secrets")
    return [
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
        f"{PARSER_SANDBOX_MEMORY_MB_HARD}m",
        "--cpus",
        str(PARSER_SANDBOX_CPUS),
        "--pids-limit",
        str(PARSER_SANDBOX_PIDS_LIMIT),
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "--env",
        "PYTHONUNBUFFERED=1",
        "--env",
        "RAYON_NUM_THREADS=1",
        "-v",
        f"{input_dir.resolve()}:/input:ro",
        "-v",
        f"{output_dir.resolve()}:/output:rw",
        image,
        "python",
        "/app/runner.py",
        request_json,
    ]


def parse_current_lane(request: LaneParseRequest) -> ParseResult:
    """Parse through the production Docker parser sandbox.

    Args:
        request: Bounded parse request.

    Returns:
        Production ``ParseResult``. Hash mismatches fail closed.

    Raises:
        BakeoffError: When Docker is required and missing.
    """

    if request.lane_id != CURRENT_LANE:
        raise BakeoffError("lane_mismatch", "current lane required")
    if len(request.payload) > PARSER_SANDBOX_MAX_INPUT_BYTES:
        return failed_lane_result(
            content_hash=request.content_hash,
            parser_version=PARSER_CONFIG_VERSION,
            cleaning_version=CLEANING_POLICY_VERSION,
            format_key="pdf",
            code="limit_exceeded:input_bytes",
        )
    expected = hashlib.sha256(request.payload).hexdigest()
    if expected != request.content_hash:
        return failed_lane_result(
            content_hash=request.content_hash,
            parser_version=PARSER_CONFIG_VERSION,
            cleaning_version=CLEANING_POLICY_VERSION,
            format_key="pdf",
            code="hash_mismatch",
        )
    launcher = ParserSandboxLauncher(
        config=SandboxLaunchConfig(
            image="smart-rag-parser-sandbox:local",
            use_docker=request.use_docker,
        )
    )
    result = launcher.run(
        payload=request.payload,
        content_hash=request.content_hash,
        filename=request.filename,
        media_type=request.media_type or "application/pdf",
        format_key="pdf",
    )
    if result.content_hash != request.content_hash:
        return failed_lane_result(
            content_hash=request.content_hash,
            parser_version=PARSER_CONFIG_VERSION,
            cleaning_version=CLEANING_POLICY_VERSION,
            format_key="pdf",
            code="hash_mismatch",
        )
    return result


def parse_anydoc_inprocess(
    request: LaneParseRequest,
    *,
    converter: MarkdownConverter | None = None,
) -> ParseResult:
    """Parse with local AnyDoc in-process (tests and explicit callers only).

    Args:
        request: Bounded parse request.
        converter: Optional Markdown converter override.

    Returns:
        Stamped AnyDoc ``ParseResult`` or a failed zero-element result.
    """

    extra = anydoc_config_extra()
    if len(request.payload) > PARSER_SANDBOX_MAX_INPUT_BYTES:
        return failed_lane_result(
            content_hash=request.content_hash,
            parser_version=ANYDOC_PARSER_VERSION,
            cleaning_version=ANYDOC_CLEANING_VERSION,
            format_key="pdf",
            code="limit_exceeded:input_bytes",
            extra=extra,
        )
    expected = hashlib.sha256(request.payload).hexdigest()
    if expected != request.content_hash:
        return failed_lane_result(
            content_hash=request.content_hash,
            parser_version=ANYDOC_PARSER_VERSION,
            cleaning_version=ANYDOC_CLEANING_VERSION,
            format_key="pdf",
            code="hash_mismatch",
            extra=extra,
        )
    convert = converter or convert_with_anydoc
    with tempfile.TemporaryDirectory(prefix="anydoc-src-") as temp_dir:
        source = Path(temp_dir) / "source.pdf"
        source.write_bytes(request.payload)
        try:
            markdown = convert(source)
        except BakeoffError as exc:
            return failed_lane_result(
                content_hash=request.content_hash,
                parser_version=ANYDOC_PARSER_VERSION,
                cleaning_version=ANYDOC_CLEANING_VERSION,
                format_key="pdf",
                code=exc.code,
                extra=extra,
            )
        except Exception as exc:
            return failed_lane_result(
                content_hash=request.content_hash,
                parser_version=ANYDOC_PARSER_VERSION,
                cleaning_version=ANYDOC_CLEANING_VERSION,
                format_key="pdf",
                code=map_anydoc_exception(exc),
                extra=extra,
            )
    if not markdown.strip():
        return failed_lane_result(
            content_hash=request.content_hash,
            parser_version=ANYDOC_PARSER_VERSION,
            cleaning_version=ANYDOC_CLEANING_VERSION,
            format_key="pdf",
            code="malformed",
            extra=extra,
        )
    try:
        return parse_anydoc_markdown_bytes(markdown, content_hash=request.content_hash)
    except UnicodeError:
        return failed_lane_result(
            content_hash=request.content_hash,
            parser_version=ANYDOC_PARSER_VERSION,
            cleaning_version=ANYDOC_CLEANING_VERSION,
            format_key="pdf",
            code="invalid_utf8",
            extra=extra,
        )


def parse_anydoc_docker(request: LaneParseRequest) -> ParseResult:
    """Parse with local AnyDoc inside the dedicated no-network image.

    Args:
        request: Bounded parse request.

    Returns:
        Stamped AnyDoc ``ParseResult`` or a failed zero-element result.

    Raises:
        BakeoffError: When Docker is missing.
    """

    extra = anydoc_config_extra()
    if shutil.which("docker") is None:
        raise BakeoffError("docker_missing", "docker executable not found")
    if len(request.payload) > PARSER_SANDBOX_MAX_INPUT_BYTES:
        return failed_lane_result(
            content_hash=request.content_hash,
            parser_version=ANYDOC_PARSER_VERSION,
            cleaning_version=ANYDOC_CLEANING_VERSION,
            format_key="pdf",
            code="limit_exceeded:input_bytes",
            extra=extra,
        )
    container_name = f"smart-rag-anydoc-{uuid4().hex}"
    with tempfile.TemporaryDirectory(prefix="anydoc-sandbox-") as temp_dir:
        input_dir = Path(temp_dir) / "input"
        output_dir = Path(temp_dir) / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / PARSER_SANDBOX_INPUT_FILENAME).write_bytes(request.payload)
        request_json = json.dumps(
            {
                "input_path": f"/input/{PARSER_SANDBOX_INPUT_FILENAME}",
                "output_path": "/output/result.json",
                "content_hash": request.content_hash,
            },
            separators=(",", ":"),
        )
        command = anydoc_docker_command(
            container_name=container_name,
            input_dir=input_dir,
            output_dir=output_dir,
            request_json=request_json,
        )
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=PARSER_SANDBOX_KILL_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            kill_sandbox_container(
                container_name, grace_seconds=PARSER_SANDBOX_KILL_GRACE_SECONDS
            )
            return failed_lane_result(
                content_hash=request.content_hash,
                parser_version=ANYDOC_PARSER_VERSION,
                cleaning_version=ANYDOC_CLEANING_VERSION,
                format_key="pdf",
                code="timeout",
                extra=extra,
            )
        except OSError:
            return failed_lane_result(
                content_hash=request.content_hash,
                parser_version=ANYDOC_PARSER_VERSION,
                cleaning_version=ANYDOC_CLEANING_VERSION,
                format_key="pdf",
                code="sandbox_start",
                extra=extra,
            )
        output_path = output_dir / "result.json"
        if completed.returncode != 0 and not output_path.exists():
            return failed_lane_result(
                content_hash=request.content_hash,
                parser_version=ANYDOC_PARSER_VERSION,
                cleaning_version=ANYDOC_CLEANING_VERSION,
                format_key="pdf",
                code="sandbox_nonzero",
                extra=extra,
            )
        if not output_path.exists():
            return failed_lane_result(
                content_hash=request.content_hash,
                parser_version=ANYDOC_PARSER_VERSION,
                cleaning_version=ANYDOC_CLEANING_VERSION,
                format_key="pdf",
                code="missing_output",
                extra=extra,
            )
        result = ParseResult.model_validate_json(output_path.read_text(encoding="utf-8"))
        metrics = result.resource_metrics.model_copy(
            update={"wall_seconds": time.monotonic() - started}
        )
        return result.model_copy(update={"resource_metrics": metrics})


def parse_lane(
    request: LaneParseRequest,
    *,
    converter: MarkdownConverter | None = None,
) -> ParseResult:
    """Dispatch one bake-off lane.

    Args:
        request: Bounded parse request.
        converter: Optional in-process AnyDoc converter for tests.

    Returns:
        Closed ``ParseResult``.
    """

    if request.lane_id == CURRENT_LANE:
        return parse_current_lane(request)
    if request.lane_id != ANYDOC_LANE:
        raise BakeoffError("unknown_lane", "unsupported lane")
    if request.use_docker:
        return parse_anydoc_docker(request)
    return parse_anydoc_inprocess(request, converter=converter)
