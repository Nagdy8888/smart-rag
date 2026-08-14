"""Archive expansion guards for zip bombs and nested compressed payloads."""

from __future__ import annotations

import io
import zipfile

from smart_rag_core.ingestion.parser.exceptions import ParserLimitExceeded
from smart_rag_core.ingestion.parser.limits import (
    PARSER_ARCHIVE_MAX_EXPANSION_RATIO,
    PARSER_SANDBOX_MAX_EXPANDED_BYTES,
)

_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def reject_archive_bomb(payload: bytes) -> None:
    """Fail closed when a ZIP declares unsafe uncompressed size or ratio.

    Inspects central-directory sizes without extracting members. This is the
    parser-side expansion gate; ClamAV still owns malware archive recursion.

    Args:
        payload: Exact object bytes. Non-ZIP payloads are ignored.

    Raises:
        ParserLimitExceeded: When expanded bytes or compression ratio exceed
            the parser sandbox limits.
    """

    if len(payload) < 4 or payload[:4] not in _ZIP_MAGIC:
        return
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ParserLimitExceeded("archive", "unreadable zip archive") from exc
    with archive:
        uncompressed = sum(info.file_size for info in archive.infolist())
        compressed = sum(info.compress_size for info in archive.infolist())
    if uncompressed > PARSER_SANDBOX_MAX_EXPANDED_BYTES:
        raise ParserLimitExceeded(
            "expanded_bytes",
            f"archive uncompressed {uncompressed} exceeds "
            f"{PARSER_SANDBOX_MAX_EXPANDED_BYTES}",
        )
    ratio_base = compressed if compressed > 0 else 1
    ratio = uncompressed / ratio_base
    if ratio > PARSER_ARCHIVE_MAX_EXPANSION_RATIO:
        raise ParserLimitExceeded(
            "archive_expansion_ratio",
            f"archive expansion ratio {ratio:.1f} exceeds "
            f"{PARSER_ARCHIVE_MAX_EXPANSION_RATIO}",
        )
