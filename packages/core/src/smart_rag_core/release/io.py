"""Hashing and canonical JSON helpers for Phase 9 Packet 1 artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of one file.

    Args:
        path: File to hash. The file is read in binary chunks.

    Returns:
        Lowercase hex digest.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    """Return the SHA-256 hex digest of UTF-8 text.

    Args:
        text: Unicode payload.

    Returns:
        Lowercase hex digest.
    """

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dump_canonical_json(payload: Mapping[str, object], path: Path) -> None:
    """Write pretty JSON without secrets and with a trailing newline.

    Args:
        payload: JSON-object mapping. Callers must omit credentials.
        path: Destination path. Parents are created.

    Side Effects:
        Overwrites ``path``.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json_object(path: Path) -> dict[str, object]:
    """Load one JSON object from disk.

    Args:
        path: JSON file.

    Returns:
        Object mapping.

    Raises:
        ValueError: If the file is not a JSON object.
    """

    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    return as_json_object(loaded, source=str(path))


def as_json_object(value: object, *, source: str = "json") -> dict[str, object]:
    """Narrow a decoded JSON value to an object mapping.

    Args:
        value: Decoded JSON value.
        source: Label used in the error message.

    Returns:
        String-keyed object.

    Raises:
        ValueError: If ``value`` is not a JSON object.
    """

    if not isinstance(value, dict):
        raise ValueError(f"{source} is not a JSON object")
    return cast(dict[str, object], value)


def as_json_list(value: object, *, source: str = "json") -> list[object]:
    """Narrow a decoded JSON value to a list.

    Args:
        value: Decoded JSON value.
        source: Label used in the error message.

    Returns:
        JSON array as a list of objects.

    Raises:
        ValueError: If ``value`` is not a JSON array.
    """

    if not isinstance(value, list):
        raise ValueError(f"{source} is not a JSON array")
    return cast(list[object], value)


def json_int(value: object, default: int = 0) -> int:
    """Return an integer JSON field or ``default``.

    Args:
        value: Decoded JSON value.
        default: Fallback when the value is not an integer.

    Returns:
        Integer value. Booleans are rejected because ``bool`` is an ``int``.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value
