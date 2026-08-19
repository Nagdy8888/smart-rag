"""Archive expansion guards for zip bombs and nested compressed payloads."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from smart_rag_core.ingestion.parser.exceptions import ParserLimitExceeded
from smart_rag_core.ingestion.parser.limits import (
    PARSER_ARCHIVE_MAX_EXPANSION_RATIO,
    PARSER_ARCHIVE_STREAM_CHUNK_BYTES,
    PARSER_SANDBOX_MAX_EXPANDED_BYTES,
)

_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def reject_archive_bomb(payload: bytes) -> None:
    """Fail closed when a ZIP is unsafe by declared size or streamed expansion.

    Declared central-directory sizes are an advisory first gate. Members are
    then stream-extracted into a bounded counter (not onto disk) so lying
    headers cannot expand past ``PARSER_SANDBOX_MAX_EXPANDED_BYTES``. Member
    names that traverse directories are rejected. ClamAV still owns malware
    archive recursion.

    Args:
        payload: Exact object bytes. Non-ZIP payloads are ignored.

    Raises:
        ParserLimitExceeded: When expanded bytes, compression ratio, or a
            member path exceeds parser sandbox limits.
    """

    if len(payload) < 4 or payload[:4] not in _ZIP_MAGIC:
        return
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ParserLimitExceeded("archive", "unreadable zip archive") from exc
    with archive:
        members = archive.infolist()
        for info in members:
            _reject_archive_member_path(info.filename)
        uncompressed = sum(info.file_size for info in members)
        compressed = sum(info.compress_size for info in members)
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
        _reject_streamed_expansion(archive, members)


def _reject_archive_member_path(filename: str) -> None:
    """Reject ZIP member names that escape the extract root.

    Args:
        filename: Archive member path from the central directory.

    Raises:
        ParserLimitExceeded: When the name is absolute or contains ``..``.
    """

    normalized = filename.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute() or normalized.startswith("/") or ".." in path.parts:
        raise ParserLimitExceeded(
            "archive_path",
            "archive member path is absolute or parent-traversing",
        )


def _reject_streamed_expansion(
    archive: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
) -> None:
    """Decompress members into a hard byte cap without writing files.

    Args:
        archive: Open ZIP handle.
        members: Central-directory entries to stream.

    Raises:
        ParserLimitExceeded: When streamed uncompressed bytes exceed the cap,
            or a member cannot be read.
    """

    total = 0
    for info in members:
        if info.is_dir():
            continue
        try:
            with archive.open(info, "r") as member:
                while True:
                    chunk = member.read(PARSER_ARCHIVE_STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > PARSER_SANDBOX_MAX_EXPANDED_BYTES:
                        raise ParserLimitExceeded(
                            "expanded_bytes",
                            f"streamed archive expansion {total} exceeds "
                            f"{PARSER_SANDBOX_MAX_EXPANDED_BYTES}",
                        )
        except ParserLimitExceeded:
            raise
        except (RuntimeError, zipfile.BadZipFile, OSError) as exc:
            raise ParserLimitExceeded(
                "archive",
                "archive member could not be streamed under the expansion cap",
            ) from exc
