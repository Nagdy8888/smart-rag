"""Immutable LightRAG pin verification against the lockfile and install.

This module may import LightRAG. Application, agent, backend, and worker
source trees must not.
"""

from __future__ import annotations

import importlib
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import cast

from smart_rag_core.retrieval.graph import (
    FORBIDDEN_AGE_GRAPH_STORAGE,
    LIGHTRAG_PACKAGE_NAME,
    LIGHTRAG_PINNED_VERSION,
    LIGHTRAG_SDIST_SHA256,
    LIGHTRAG_WHEEL_SHA256,
    SELECTED_DOC_STATUS_STORAGE,
    SELECTED_GRAPH_STORAGE,
    SELECTED_KV_STORAGE,
    SELECTED_VECTOR_STORAGE,
)

TRANSITIVE_HARD_DEPENDENCIES: tuple[str, ...] = (
    "aiohttp",
    "configparser",
    "google-api-core",
    "google-genai",
    "json-repair",
    "nano-vectordb",
    "networkx",
    "numpy",
    "packaging",
    "pandas",
    "pipmaster",
    "pydantic",
    "pypinyin",
    "python-dotenv",
    "pyyaml",
    "setuptools",
    "tenacity",
    "tiktoken",
    "xlsxwriter",
)

REQUIRED_IMPORTS: tuple[tuple[str, str], ...] = (
    ("lightrag", "LightRAG"),
    ("lightrag", "QueryParam"),
    ("lightrag.kg.pgtable_impl", "PGTableGraphStorage"),
    ("lightrag.kg.postgres_impl", "PGKVStorage"),
    ("lightrag.kg.postgres_impl", "PGVectorStorage"),
    ("lightrag.kg.postgres_impl", "PGDocStatusStorage"),
    ("lightrag.kg.postgres_impl", "PGGraphStorage"),
    ("lightrag.utils", "EmbeddingFunc"),
    ("lightrag.base", "DeletionResult"),
)


class LightRagPinError(RuntimeError):
    """Raised when the installed or locked LightRAG artifact does not match."""


@dataclass(frozen=True, slots=True)
class LightRagPinRecord:
    """Verified pin metadata for evidence and contract tests.

    Attributes:
        package_name: Distribution name.
        version: Installed and expected version.
        wheel_sha256: Lockfile wheel digest without the ``sha256:`` prefix.
        sdist_sha256: Lockfile sdist digest without the ``sha256:`` prefix.
        license_name: Distribution license string.
        selected_graph_storage: Plain-table storage class name.
        forbidden_age_storage: AGE storage class that must not be selected.
    """

    package_name: str
    version: str
    wheel_sha256: str
    sdist_sha256: str
    license_name: str
    selected_graph_storage: str
    forbidden_age_storage: str


def _string_object(value: object, *, label: str) -> dict[str, object]:
    """Narrow an untrusted TOML value to a string-keyed object.

    Args:
        value: Parsed TOML node.
        label: Field name used in the mismatch error.

    Returns:
        String-keyed mapping.

    Raises:
        LightRagPinError: If ``value`` is not a string-keyed object.
    """

    if not isinstance(value, dict):
        raise LightRagPinError(f"{label} is not an object")
    untyped = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in untyped):
        raise LightRagPinError(f"{label} contains a non-string key")
    return cast(dict[str, object], untyped)


def _lock_packages(lock_path: Path) -> list[Mapping[str, object]]:
    """Return ``uv.lock`` package tables as string-keyed mappings.

    Args:
        lock_path: Repository ``uv.lock`` path.

    Returns:
        Package entries from the lockfile.

    Raises:
        LightRagPinError: If the lockfile is missing package tables.
    """

    payload = _string_object(
        tomllib.loads(lock_path.read_text(encoding="utf-8")),
        label="uv.lock",
    )
    packages = payload.get("package")
    if not isinstance(packages, list):
        raise LightRagPinError("uv.lock is missing package entries")
    entries: list[Mapping[str, object]] = []
    for raw_item in cast(list[object], packages):
        if isinstance(raw_item, dict):
            entries.append(
                _string_object(cast(object, raw_item), label="uv.lock package")
            )
    return entries


def wheel_sha256_from_lock(lock_path: Path, *, package_name: str) -> str:
    """Read the locked wheel SHA-256 for one distribution.

    Args:
        lock_path: Repository ``uv.lock`` path.
        package_name: Distribution name such as ``lightrag-hku``.

    Returns:
        Lowercase hex digest without a ``sha256:`` prefix.

    Raises:
        LightRagPinError: If the package or wheel hash is missing.
    """

    for item in _lock_packages(lock_path):
        if item.get("name") != package_name:
            continue
        wheels = item.get("wheels")
        if not isinstance(wheels, list) or not wheels:
            raise LightRagPinError(f"{package_name} has no locked wheel")
        first = _string_object(cast(object, wheels[0]), label=f"{package_name} wheel")
        digest = first.get("hash")
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise LightRagPinError(f"{package_name} wheel hash is missing")
        return digest.removeprefix("sha256:").lower()
    raise LightRagPinError(f"{package_name} is not present in uv.lock")


def sdist_sha256_from_lock(lock_path: Path, *, package_name: str) -> str:
    """Read the locked sdist SHA-256 for one distribution.

    Args:
        lock_path: Repository ``uv.lock`` path.
        package_name: Distribution name.

    Returns:
        Lowercase hex digest without a ``sha256:`` prefix.

    Raises:
        LightRagPinError: If the sdist hash is missing.
    """

    for item in _lock_packages(lock_path):
        if item.get("name") != package_name:
            continue
        sdist = _string_object(item.get("sdist"), label=f"{package_name} sdist")
        digest = sdist.get("hash")
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise LightRagPinError(f"{package_name} sdist hash is missing")
        return digest.removeprefix("sha256:").lower()
    raise LightRagPinError(f"{package_name} is not present in uv.lock")


def _metadata_header(meta: metadata.PackageMetadata, key: str) -> str | None:
    """Read one distribution metadata header if present.

    Args:
        meta: Installed package metadata.
        key: Header name such as ``License``.

    Returns:
        Stripped header value, or ``None`` when absent/empty.
    """

    if key not in meta:
        return None
    value = meta[key].strip()
    return value or None


def _distribution_license() -> str:
    """Return the installed distribution license string.

    Returns:
        License or license-expression metadata, or ``unknown`` when absent.
    """

    meta = metadata.metadata(LIGHTRAG_PACKAGE_NAME)
    for key in ("License", "License-Expression"):
        license_name = _metadata_header(meta, key)
        if license_name is not None:
            return license_name
    return "unknown"


def import_required_symbols() -> dict[str, object]:
    """Import every required public class and fail if a symbol is missing.

    Returns:
        Mapping of qualified ``module.Class`` names to imported objects.

    Raises:
        LightRagPinError: If an import or attribute is missing.
    """

    imported: dict[str, object] = {}
    for module_name, attribute in REQUIRED_IMPORTS:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise LightRagPinError(f"missing_module:{module_name}") from exc
        if not hasattr(module, attribute):
            raise LightRagPinError(f"missing_class:{module_name}.{attribute}")
        imported[f"{module_name}.{attribute}"] = getattr(module, attribute)
    return imported


def verify_lightrag_pin(
    *,
    lock_path: Path,
    expected_version: str = LIGHTRAG_PINNED_VERSION,
    expected_wheel_sha256: str = LIGHTRAG_WHEEL_SHA256,
    expected_sdist_sha256: str = LIGHTRAG_SDIST_SHA256,
) -> LightRagPinRecord:
    """Verify installed version, lock hashes, and required class imports.

    Args:
        lock_path: Repository ``uv.lock``.
        expected_version: Immutable pin version.
        expected_wheel_sha256: Expected wheel digest.
        expected_sdist_sha256: Expected sdist digest.

    Returns:
        Verified pin record.

    Raises:
        LightRagPinError: On version, hash, or missing-class mismatch.
    """

    installed = metadata.version(LIGHTRAG_PACKAGE_NAME)
    if installed != expected_version:
        raise LightRagPinError(
            f"version_mismatch:installed={installed}:expected={expected_version}"
        )
    wheel_digest = wheel_sha256_from_lock(lock_path, package_name=LIGHTRAG_PACKAGE_NAME)
    if wheel_digest != expected_wheel_sha256.lower():
        raise LightRagPinError("wheel_hash_mismatch")
    sdist_digest = sdist_sha256_from_lock(lock_path, package_name=LIGHTRAG_PACKAGE_NAME)
    if sdist_digest != expected_sdist_sha256.lower():
        raise LightRagPinError("sdist_hash_mismatch")
    symbols = import_required_symbols()
    selected = symbols["lightrag.kg.pgtable_impl.PGTableGraphStorage"]
    forbidden = symbols["lightrag.kg.postgres_impl.PGGraphStorage"]
    if getattr(selected, "__name__", "") != SELECTED_GRAPH_STORAGE:
        raise LightRagPinError("selected_graph_storage_mismatch")
    if getattr(forbidden, "__name__", "") != FORBIDDEN_AGE_GRAPH_STORAGE:
        raise LightRagPinError("forbidden_age_storage_missing")
    if selected is forbidden:
        raise LightRagPinError("age_storage_selected")
    _ = (
        SELECTED_KV_STORAGE,
        SELECTED_VECTOR_STORAGE,
        SELECTED_DOC_STATUS_STORAGE,
    )
    return LightRagPinRecord(
        package_name=LIGHTRAG_PACKAGE_NAME,
        version=installed,
        wheel_sha256=wheel_digest,
        sdist_sha256=sdist_digest,
        license_name=_distribution_license(),
        selected_graph_storage=SELECTED_GRAPH_STORAGE,
        forbidden_age_storage=FORBIDDEN_AGE_GRAPH_STORAGE,
    )
