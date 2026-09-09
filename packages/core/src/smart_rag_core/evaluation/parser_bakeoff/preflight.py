"""Selected-PDF preflight: path, hash, bounds, and ClamAV evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import fitz

from smart_rag_core.evaluation.parser_bakeoff.artifacts import (
    repo_root_from,
    run_dir,
    save_manifest,
    sha256_text,
)
from smart_rag_core.evaluation.parser_bakeoff.constants import (
    ANYDOC_LANE,
    ANYDOC_PARSER_VERSION,
    COMMAND_VERSION,
    CURRENT_LANE,
    HASH_CHUNK_BYTES,
    SELECTED_PDF_RELATIVE,
)
from smart_rag_core.evaluation.parser_bakeoff.models import (
    BakeoffError,
    BakeoffManifest,
    BakeoffScanEvidence,
    LaneIdentity,
    RunStage,
)
from smart_rag_core.gateways.clamav import (
    ClamAvClient,
    ClamAvError,
    ScanDisposition,
)
from smart_rag_core.ingestion.parser.helpers import as_int, vendor_attr
from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    PARSER_CONFIG_VERSION,
    PARSER_SANDBOX_MAX_INPUT_BYTES,
    PARSER_SANDBOX_MAX_PAGES,
)
from smart_rag_core.settings.base import get_process_environ

Scanner = Callable[[bytes], BakeoffScanEvidence]


def selected_pdf_path(repo: Path) -> Path:
    """Return the only PDF this experiment may ingest.

    Args:
        repo: Repository root.

    Returns:
        Absolute selected PDF path.
    """

    return (repo / SELECTED_PDF_RELATIVE).resolve()


def resolve_selected_pdf(repo: Path, pdf: Path) -> Path:
    """Reject any PDF other than the sealed book.

    Args:
        repo: Repository root.
        pdf: Caller path.

    Returns:
        Resolved selected PDF.

    Raises:
        BakeoffError: When the path is not the selected file, missing, or not a PDF.
    """

    selected = selected_pdf_path(repo)
    resolved = pdf.expanduser()
    if not resolved.is_absolute():
        resolved = (repo / resolved).resolve()
    else:
        resolved = resolved.resolve()
    try:
        resolved.relative_to(repo)
    except ValueError as exc:
        raise BakeoffError("selected_pdf_required", "path outside repository") from exc
    if resolved != selected:
        raise BakeoffError("selected_pdf_required", "only the sealed book PDF is allowed")
    if not resolved.is_file():
        raise BakeoffError("pdf_missing", "selected PDF is not a regular file")
    if resolved.suffix.lower() != ".pdf":
        raise BakeoffError("pdf_extension", "selected file is not a PDF")
    return resolved


def stream_sha256(path: Path) -> tuple[str, int]:
    """Hash a file in bounded chunks.

    Args:
        path: Readable file.

    Returns:
        ``(sha256_hex, byte_count)``.
    """

    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), total


def pdf_page_count(path: Path) -> int:
    """Read PDF page count without extracting page text.

    Args:
        path: PDF path.

    Returns:
        Page count.

    Raises:
        BakeoffError: When PyMuPDF cannot open the file.
    """

    try:
        document = fitz.open(path)
    except Exception as exc:  # noqa: BLE001 — vendor open failures are fail-closed
        raise BakeoffError("pdf_unreadable", "PDF page count unavailable") from exc
    try:
        return as_int(vendor_attr(document, "page_count"))
    finally:
        close = getattr(document, "close", None)
        if callable(close):
            close()


def clamav_scanner_from_env() -> Scanner:
    """Build a ClamAV scanner from process environment.

    Returns:
        Scanner callable.

    Raises:
        BakeoffError: When ClamAV is unreachable or the scan is not clean.
    """

    host = (get_process_environ("CLAMAV_HOST", "127.0.0.1") or "127.0.0.1").strip()
    port_raw = (get_process_environ("CLAMAV_PORT", "3310") or "3310").strip()
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise BakeoffError("scan_config", "CLAMAV_PORT is not an integer") from exc
    client = ClamAvClient(host=host, port=port)

    def _scan(payload: bytes) -> BakeoffScanEvidence:
        """Scan exact bytes and require a clean current signature.

        Args:
            payload: PDF bytes after the size gate.

        Returns:
            Manifest scan evidence.

        Raises:
            BakeoffError: When the engine is unavailable or the result is not clean.
        """

        try:
            engine = client.read_engine_info()
            result = client.scan_stream(payload, engine_info=engine)
        except ClamAvError as exc:
            raise BakeoffError("scan_unavailable", "ClamAV scan failed") from exc
        if result.disposition is not ScanDisposition.CLEAN:
            raise BakeoffError("scan_not_clean", f"scan disposition {result.disposition}")
        signature = "unknown"
        if result.signature_db_ids:
            signature = "|".join(sorted(result.signature_db_ids.values()))
        return BakeoffScanEvidence(
            disposition=result.disposition.value,
            engine_version=result.engine_info.engine_version,
            signature_version=signature,
            signature_db_ids=dict(result.signature_db_ids),
            bytes_examined=result.bytes_examined,
            detail="clean",
        )

    return _scan


def prepare_run(
    *,
    repo: Path | None = None,
    pdf: Path,
    scanner: Scanner | None = None,
    now: datetime | None = None,
) -> BakeoffManifest:
    """Create a private run directory and immutable manifest.

    Args:
        repo: Optional repository root. Defaults to this module's repo.
        pdf: Caller PDF path; must resolve to the selected book.
        scanner: Optional injected scanner. Production CLI uses ClamAV.
        now: Optional timestamp for deterministic tests.

    Returns:
        Written manifest including ``manifest_sha256``.

    Raises:
        BakeoffError: On path, size, page, or scan failures.

    Side Effects:
        Creates ``.private-eval/parser-bakeoff/<run-id>/``.
    """

    root = repo or repo_root_from(Path(__file__))
    source = resolve_selected_pdf(root, pdf)
    digest, size = stream_sha256(source)
    if size > PARSER_SANDBOX_MAX_INPUT_BYTES:
        raise BakeoffError("limit_exceeded:input_bytes", f"input bytes {size} exceed max")
    pages = pdf_page_count(source)
    if pages > PARSER_SANDBOX_MAX_PAGES:
        raise BakeoffError("limit_exceeded:pages", f"page count {pages}")
    scan_fn = scanner or clamav_scanner_from_env()
    payload = source.read_bytes()
    if len(payload) != size or hashlib.sha256(payload).hexdigest() != digest:
        raise BakeoffError("hash_mismatch", "PDF changed during preflight")
    scan = scan_fn(payload)
    stamp = (now or datetime.now(tz=UTC)).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{digest[:12]}"
    destination = run_dir(root, run_id)
    if destination.exists():
        raise BakeoffError("run_exists", "run directory already exists")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / CURRENT_LANE).mkdir(exist_ok=True)
    (destination / ANYDOC_LANE).mkdir(exist_ok=True)
    manifest = BakeoffManifest(
        run_id=run_id,
        source_basename=source.name,
        source_sha256=digest,
        source_bytes=size,
        source_pages=pages,
        scan=scan,
        lanes=(
            LaneIdentity(
                lane_id=CURRENT_LANE,
                parser_version=PARSER_CONFIG_VERSION,
                cleaning_version=CLEANING_POLICY_VERSION,
                locator_available=True,
            ),
            LaneIdentity(
                lane_id=ANYDOC_LANE,
                parser_version=ANYDOC_PARSER_VERSION,
                cleaning_version=ANYDOC_CLEANING_VERSION,
                locator_available=False,
            ),
        ),
        stage=RunStage.PREPARED,
        command_version=COMMAND_VERSION,
        created_at=stamp,
        chunking_version="chunking_v2",
    )
    written = save_manifest(root, manifest)
    _ = sha256_text(written.model_dump_json())
    return written
