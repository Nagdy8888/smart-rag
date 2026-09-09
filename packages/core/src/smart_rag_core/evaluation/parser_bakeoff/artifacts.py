"""Private run-directory helpers for the parser bake-off."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from smart_rag_core.evaluation.parser_bakeoff.constants import PRIVATE_ROOT, LaneId
from smart_rag_core.evaluation.parser_bakeoff.models import (
    BakeoffError,
    BakeoffManifest,
)

TModel = TypeVar("TModel", bound=BaseModel)


def repo_root_from(start: Path) -> Path:
    """Return the repository root that contains ``pyproject.toml``.

    Args:
        start: File or directory used as a search origin.

    Returns:
        Absolute repository root.

    Raises:
        BakeoffError: When the root cannot be located.
    """

    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise BakeoffError("repo_root_missing", "repository root not found")


def run_dir(repo: Path, run_id: str) -> Path:
    """Return the private directory for one run.

    Args:
        repo: Repository root.
        run_id: Run identifier.

    Returns:
        Absolute run directory under ``.private-eval``.
    """

    return repo / PRIVATE_ROOT / run_id


def lane_dir(repo: Path, run_id: str, lane_id: LaneId) -> Path:
    """Return one lane subdirectory.

    Args:
        repo: Repository root.
        run_id: Run identifier.
        lane_id: Lane token.

    Returns:
        Absolute lane directory.
    """

    return run_dir(repo, run_id) / lane_id


def canonical_json(payload: object) -> str:
    """Serialize JSON with stable separators and sorted keys.

    Args:
        payload: JSON-compatible object.

    Returns:
        Canonical JSON text.
    """

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(payload: str) -> str:
    """Return SHA-256 hex of UTF-8 text.

    Args:
        payload: Text to hash.

    Returns:
        Lowercase hex digest.
    """

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, payload: BaseModel | dict[str, object]) -> None:
    """Write JSON atomically without logging payload contents.

    Args:
        path: Destination path.
        payload: Pydantic model or mapping.

    Side Effects:
        Creates parent directories and replaces ``path``.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, BaseModel):
        text = payload.model_dump_json()
    else:
        text = canonical_json(payload)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(path)


def read_model(path: Path, model_type: type[TModel]) -> TModel:
    """Load one frozen Pydantic model from disk.

    Args:
        path: JSON file.
        model_type: Target model class.

    Returns:
        Parsed model.

    Raises:
        BakeoffError: When the file is missing or invalid.
    """

    if not path.is_file():
        raise BakeoffError("artifact_missing", f"missing {path.name}")
    try:
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BakeoffError("artifact_invalid", f"invalid {path.name}") from exc


def load_manifest(repo: Path, run_id: str) -> BakeoffManifest:
    """Load the run manifest.

    Args:
        repo: Repository root.
        run_id: Run identifier.

    Returns:
        Manifest model.
    """

    return read_model(run_dir(repo, run_id) / "manifest.json", BakeoffManifest)


def save_manifest(repo: Path, manifest: BakeoffManifest) -> BakeoffManifest:
    """Write the manifest and stamp its content hash.

    Args:
        repo: Repository root.
        manifest: Manifest without requiring ``manifest_sha256``.

    Returns:
        Manifest including ``manifest_sha256``.
    """

    stamped = manifest.model_copy(update={"manifest_sha256": ""})
    digest = sha256_text(stamped.model_dump_json())
    final = stamped.model_copy(update={"manifest_sha256": digest})
    write_json_atomic(run_dir(repo, run_id=final.run_id) / "manifest.json", final)
    return final
