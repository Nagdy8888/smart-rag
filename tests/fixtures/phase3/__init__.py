"""Phase 3 adversarial fixture manifest helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypedDict, cast

MANIFEST_PATH = Path(__file__).resolve().parent / "FIXTURE_MANIFEST.json"


class FixtureRecord(TypedDict, total=False):
    """One immutable Phase 3 fixture registry row."""

    id: str
    category: str
    source: str
    license: str
    sha256: str | None
    expected_status: str
    expected_elements: list[str] | None
    expected_locators: list[str] | None
    sensitivity_class: str
    external_processing_mode: str
    boundary: str
    owning_test: str
    notes: str | None


def load_manifest() -> dict[str, object]:
    """Load and parse the Phase 3 fixture manifest JSON.

    Returns:
        Parsed manifest object including ``fixtures`` list and metadata.

    Raises:
        FileNotFoundError: When ``FIXTURE_MANIFEST.json`` is missing.
        json.JSONDecodeError: When the manifest is not valid JSON.
        TypeError: When the manifest root is not a JSON object.
    """

    loaded: object = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError("manifest must be a JSON object")
    return cast(dict[str, object], loaded)


def manifest_body_bytes(manifest: dict[str, object]) -> bytes:
    """Return canonical manifest bytes excluding the self-hash field.

    Args:
        manifest: Parsed manifest object.

    Returns:
        UTF-8 JSON bytes with stable key ordering and no ``manifest_sha256``.
    """

    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_manifest_sha256(manifest: dict[str, object]) -> str:
    """Compute the immutable digest for the manifest body.

    Args:
        manifest: Parsed manifest object.

    Returns:
        Lowercase hex SHA-256 digest of the canonical manifest body.
    """

    return hashlib.sha256(manifest_body_bytes(manifest)).hexdigest()


def iter_fixtures(manifest: dict[str, object]) -> list[FixtureRecord]:
    """Return typed fixture rows from a parsed manifest.

    Args:
        manifest: Parsed manifest object.

    Returns:
        Fixture records in manifest order.
    """

    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list):
        raise TypeError("manifest.fixtures must be a list")
    records: list[FixtureRecord] = []
    items = cast(list[object], fixtures)
    for raw in items:
        if isinstance(raw, dict):
            records.append(cast(FixtureRecord, raw))
    return records
