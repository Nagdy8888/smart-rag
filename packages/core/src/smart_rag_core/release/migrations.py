"""Migration file inventory versus applied Supabase versions."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel, ConfigDict

from smart_rag_core.release.constants import MIGRATION_SCHEMA_VERSION
from smart_rag_core.release.errors import CandidateMigrationDriftError
from smart_rag_core.release.identity import MigrationFileRecord, list_migration_records


class CandidateMigrationInventory(BaseModel):
    """Repository files versus applied local migration versions.

    Attributes:
        schema_version: Frozen inventory schema.
        files: Repository SQL files and hashes.
        applied_versions: Versions recorded by local Supabase.
        drift: True when file prefixes and applied versions differ.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["phase09-candidate-migrations-v1"] = (
        MIGRATION_SCHEMA_VERSION
    )
    files: tuple[MigrationFileRecord, ...]
    applied_versions: tuple[str, ...]
    drift: bool


def file_version_prefixes(files: tuple[MigrationFileRecord, ...]) -> tuple[str, ...]:
    """Return timestamp prefixes from migration filenames.

    Args:
        files: Repository migration records.

    Returns:
        Sorted unique version prefixes.
    """

    prefixes: list[str] = []
    for record in files:
        prefix = record.filename.split("_", 1)[0]
        prefixes.append(prefix)
    return tuple(prefixes)


def load_applied_versions(connection: psycopg.Connection) -> tuple[str, ...]:
    """Read applied migration versions from local Supabase.

    Args:
        connection: Postgres connection.

    Returns:
        Applied version strings.

    Raises:
        CandidateMigrationDriftError: If the migrations table is missing.
    """

    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT version
            FROM supabase_migrations.schema_migrations
            ORDER BY version
            """
        )
        rows = cursor.fetchall()
    return tuple(str(row[0]) for row in rows)


def collect_migration_inventory(
    repo_root: Path,
    *,
    applied_versions: tuple[str, ...] | None,
) -> CandidateMigrationInventory:
    """Compare repository migration files to optional applied versions.

    Args:
        repo_root: Repository root.
        applied_versions: Applied versions, or none when Supabase is down.

    Returns:
        Inventory with ``drift`` set when applied versions are present and
        differ from file prefixes.

    Raises:
        CandidateMigrationDriftError: If applied versions drift from files.
    """

    files = tuple(list_migration_records(repo_root))
    prefixes = file_version_prefixes(files)
    applied = applied_versions or ()
    drift = False
    if applied:
        if tuple(applied) != prefixes:
            drift = True
            raise CandidateMigrationDriftError(
                "applied migrations drifted from repository files: "
                f"applied={list(applied)} files={list(prefixes)}"
            )
    return CandidateMigrationInventory(
        files=files,
        applied_versions=applied,
        drift=drift,
    )
