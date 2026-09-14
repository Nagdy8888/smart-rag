"""Isolated current-parser and local-AnyDoc lanes."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager
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
    ANYDOC_SANDBOX_TIMEOUT_SECONDS,
    CURRENT_LANE,
    FORBIDDEN_SANDBOX_ENV,
    OPENAI_OCR_MAX_PAGES,
    LaneId,
)
from smart_rag_core.evaluation.parser_bakeoff.models import BakeoffError
from smart_rag_core.evaluation.parser_bakeoff.page_ocr import (
    assemble_anydoc_markdown,
    empty_text_pages,
)
from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    PARSER_CONFIG_VERSION,
    PARSER_SANDBOX_CPUS,
    PARSER_SANDBOX_INPUT_FILENAME,
    PARSER_SANDBOX_KILL_GRACE_SECONDS,
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
from smart_rag_core.settings import SettingsValidationError, SharedSettings

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

_PROBE_CACHE: dict[str, tuple[int, ...]] = {}
_EMIT_CACHE: dict[str, str] = {}


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
        "/tmp:rw,noexec,nosuid,size=256m",
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


def _anydoc_failed(content_hash: str, code: str) -> ParseResult:
    """Return a zero-element AnyDoc failure with lane extras.

    Args:
        content_hash: Source SHA-256.
        code: Sanitized failure code.

    Returns:
        Failed parse result.
    """

    return failed_lane_result(
        content_hash=content_hash,
        parser_version=ANYDOC_PARSER_VERSION,
        cleaning_version=ANYDOC_CLEANING_VERSION,
        format_key="pdf",
        code=code,
        extra=anydoc_config_extra(),
    )


@contextmanager
def _anydoc_sandbox_dirs(payload: bytes) -> Generator[tuple[Path, Path], None, None]:
    """Create host input/output directories for one AnyDoc sandbox run.

    Args:
        payload: PDF bytes written to the sandbox input filename.

    Yields:
        Input directory and output directory.
    """

    with tempfile.TemporaryDirectory(prefix="anydoc-sandbox-") as temp_dir:
        input_dir = Path(temp_dir) / "input"
        output_dir = Path(temp_dir) / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / PARSER_SANDBOX_INPUT_FILENAME).write_bytes(payload)
        yield input_dir, output_dir


def _invoke_anydoc_docker(
    *,
    input_dir: Path,
    output_dir: Path,
    request_body: dict[str, object],
) -> subprocess.CompletedProcess[str] | None:
    """Run one no-network AnyDoc container.

    Args:
        input_dir: Host input directory.
        output_dir: Host output directory.
        request_body: Runner JSON body. Must not contain secrets.

    Returns:
        Completed process, or ``None`` on launch OSError.

    Raises:
        BakeoffError: When the container exceeds ``ANYDOC_SANDBOX_TIMEOUT_SECONDS``.
    """

    container_name = f"smart-rag-anydoc-{uuid4().hex}"
    request_json = json.dumps(request_body, separators=(",", ":"))
    command = anydoc_docker_command(
        container_name=container_name,
        input_dir=input_dir,
        output_dir=output_dir,
        request_json=request_json,
    )
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=ANYDOC_SANDBOX_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        kill_sandbox_container(
            container_name, grace_seconds=PARSER_SANDBOX_KILL_GRACE_SECONDS
        )
        raise BakeoffError("timeout", "AnyDoc sandbox timed out") from None
    except OSError:
        return None


def _host_openai_api_key() -> str:
    """Load the host OpenAI key for bake-off page OCR. Never logs the value.

    Returns:
        Provider credential.

    Raises:
        BakeoffError: When live settings are missing, mock mode is on, or
            LangSmith I/O export is enabled.
    """

    try:
        settings = SharedSettings()
    except (RuntimeError, ValueError, SettingsValidationError) as exc:
        raise BakeoffError(
            "openai_required", "live OpenAI settings are required"
        ) from exc
    if settings.mock_model_mode:
        raise BakeoffError("mock_model_mode", "MOCK_MODEL_MODE must be false")
    if settings.langsmith_export_io:
        raise BakeoffError("langsmith_export_io", "LANGSMITH_EXPORT_IO must be false")
    secret = settings.openai_api_key
    if secret is None:
        raise BakeoffError("openai_required", "live OpenAI settings are required")
    return secret.get_secret_value()


def emit_anydoc_markdown_docker(path: Path) -> str:
    """Convert one PDF slice to Markdown inside the AnyDoc sandbox.

    Replay uses an in-process cache keyed by the slice SHA-256.

    Args:
        path: Host slice PDF. Hash is the slice file hash, not the book hash.

    Returns:
        Markdown string.

    Raises:
        BakeoffError: When Docker is missing or conversion fails.
    """

    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    cached = _EMIT_CACHE.get(digest)
    if cached is not None:
        return cached
    with _anydoc_sandbox_dirs(payload) as (input_dir, output_dir):
        try:
            completed = _invoke_anydoc_docker(
                input_dir=input_dir,
                output_dir=output_dir,
                request_body={
                    "input_path": f"/input/{PARSER_SANDBOX_INPUT_FILENAME}",
                    "output_path": "/output/result.json",
                    "markdown_path": "/output/anydoc.md",
                    "content_hash": digest,
                    "mode": "emit_markdown",
                },
            )
        except BakeoffError:
            raise
        if completed is None:
            raise BakeoffError("sandbox_start", "AnyDoc sandbox failed to start")
        markdown_path = output_dir / "anydoc.md"
        if completed.returncode != 0 or not markdown_path.is_file():
            raise BakeoffError("sandbox_nonzero", "AnyDoc Markdown emit failed")
        markdown = markdown_path.read_text(encoding="utf-8")
        if not markdown.strip():
            raise BakeoffError("malformed", "AnyDoc Markdown emit is empty")
        _EMIT_CACHE[digest] = markdown
        return markdown


def probe_anydoc_ocr_pages_docker(path: Path, *, content_hash: str) -> tuple[int, ...]:
    """Ask the AnyDoc sandbox which 1-indexed pages need OCR. No omit.

    Args:
        path: Original PDF already written for hashing.
        content_hash: Original SHA-256.

    Returns:
        Named pages, or empty when AnyDoc converts the file.

    Raises:
        BakeoffError: When Docker is missing or the probe fails.
    """

    cached = _PROBE_CACHE.get(content_hash)
    if cached is not None:
        return cached
    payload = path.read_bytes()
    with _anydoc_sandbox_dirs(payload) as (input_dir, output_dir):
        try:
            completed = _invoke_anydoc_docker(
                input_dir=input_dir,
                output_dir=output_dir,
                request_body={
                    "input_path": f"/input/{PARSER_SANDBOX_INPUT_FILENAME}",
                    "output_path": "/output/ocr-pages.json",
                    "content_hash": content_hash,
                    "mode": "probe_ocr_pages",
                },
            )
        except BakeoffError:
            raise
        if completed is None:
            raise BakeoffError("sandbox_start", "AnyDoc sandbox failed to start")
        output_path = output_dir / "ocr-pages.json"
        if completed.returncode != 0 or not output_path.is_file():
            raise BakeoffError("sandbox_nonzero", "AnyDoc OCR probe failed")
        try:
            payload_json = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BakeoffError(
                "malformed", "AnyDoc OCR probe output is invalid"
            ) from exc
        pages = tuple(int(page) for page in payload_json.get("pages", []))
    _PROBE_CACHE[content_hash] = pages
    return pages


def parse_anydoc_docker(request: LaneParseRequest) -> ParseResult:
    """Parse with local AnyDoc inside the dedicated no-network image.

    When AnyDoc names OCR pages or selectable text is empty, the host rasters
    those pages and calls OpenAI Vision. The API key never enters the sandbox.

    Args:
        request: Bounded parse request.

    Returns:
        Stamped AnyDoc ``ParseResult`` or a failed zero-element result.

    Raises:
        BakeoffError: When Docker is missing.
    """

    if shutil.which("docker") is None:
        raise BakeoffError("docker_missing", "docker executable not found")
    if len(request.payload) > PARSER_SANDBOX_MAX_INPUT_BYTES:
        return _anydoc_failed(request.content_hash, "limit_exceeded:input_bytes")
    expected = hashlib.sha256(request.payload).hexdigest()
    if expected != request.content_hash:
        return _anydoc_failed(request.content_hash, "hash_mismatch")
    started = time.monotonic()
    with _anydoc_sandbox_dirs(request.payload) as (input_dir, output_dir):
        source = input_dir / PARSER_SANDBOX_INPUT_FILENAME
        try:
            named = probe_anydoc_ocr_pages_docker(
                source, content_hash=request.content_hash
            )
            empty = empty_text_pages(source)
            ocr_pages = tuple(sorted(set(named) | set(empty)))
            if len(ocr_pages) > OPENAI_OCR_MAX_PAGES:
                return _anydoc_failed(request.content_hash, "openai_ocr_limit")
        except BakeoffError as exc:
            return _anydoc_failed(request.content_hash, exc.code)
        if not ocr_pages:
            request_json: dict[str, object] = {
                "input_path": f"/input/{PARSER_SANDBOX_INPUT_FILENAME}",
                "output_path": "/output/result.json",
                "content_hash": request.content_hash,
            }
            try:
                completed = _invoke_anydoc_docker(
                    input_dir=input_dir,
                    output_dir=output_dir,
                    request_body=request_json,
                )
            except BakeoffError:
                return _anydoc_failed(request.content_hash, "timeout")
            if completed is None:
                return _anydoc_failed(request.content_hash, "sandbox_start")
            output_path = output_dir / "result.json"
            if completed.returncode != 0 and not output_path.exists():
                return _anydoc_failed(request.content_hash, "sandbox_nonzero")
            if not output_path.exists():
                return _anydoc_failed(request.content_hash, "missing_output")
            result = ParseResult.model_validate_json(
                output_path.read_text(encoding="utf-8")
            )
            metrics = result.resource_metrics.model_copy(
                update={"wall_seconds": time.monotonic() - started}
            )
            return result.model_copy(update={"resource_metrics": metrics})
        try:
            api_key = _host_openai_api_key()
            print(f"openai_ocr_pages={len(ocr_pages)}")
            markdown, pages = assemble_anydoc_markdown(
                source,
                content_hash=request.content_hash,
                convert_anydoc=emit_anydoc_markdown_docker,
                api_key=api_key,
                ocr_pages=ocr_pages,
            )
            result = parse_anydoc_markdown_bytes(
                markdown,
                content_hash=request.content_hash,
                ocr_pages=len(pages),
            )
        except BakeoffError as exc:
            return _anydoc_failed(request.content_hash, exc.code)
        except UnicodeError:
            return _anydoc_failed(request.content_hash, "invalid_utf8")
        metrics = result.resource_metrics.model_copy(
            update={"wall_seconds": time.monotonic() - started, "ocr_pages": len(pages)}
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
