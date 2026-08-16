"""Restore a LightRAG snapshot into a disposable database for upgrade qualification.

A second workspace in runtime schema ``lightrag`` is never upgrade proof.
Snapshot/restore is the vendor schema rollback boundary. Pointer rollback
covers only application data compatible with the current schema.

This script does not import ``lightrag``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from smart_rag_core.jobs.exceptions import GraphLifecycleError
from smart_rag_core.jobs.graph_lifecycle import assert_isolated_upgrade_environment
from smart_rag_core.jobs.limits import RUNTIME_LIGHTRAG_SCHEMA

LOCAL_ADMIN_DB = "postgres"
EXIT_REFUSED = 2
EXIT_RESTORE_UNAVAILABLE = 3


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for isolated upgrade restore.

    Args:
        argv: Optional argument list excluding the program name.

    Returns:
        Parsed arguments.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Qualify LightRAG upgrade isolation. Restore dumps only into a "
            "disposable database, never a second workspace in runtime lightrag."
        )
    )
    parser.add_argument(
        "--runtime-database",
        default=LOCAL_ADMIN_DB,
        help="Live application database name.",
    )
    parser.add_argument(
        "--runtime-schema",
        default=RUNTIME_LIGHTRAG_SCHEMA,
        help="Live vendor schema. Default lightrag.",
    )
    parser.add_argument(
        "--candidate-database",
        required=True,
        help="Disposable restore database name. Must differ from runtime for dump restore.",
    )
    parser.add_argument(
        "--candidate-schema",
        default=RUNTIME_LIGHTRAG_SCHEMA,
        help="Schema inside the disposable database.",
    )
    parser.add_argument(
        "--dump-path",
        default="",
        help="Optional pg_dump custom file. Restore requires a different database.",
    )
    parser.add_argument(
        "--admin-dsn",
        default="",
        help="Optional admin DSN. Never printed. Defaults to local 54322 when restoring.",
    )
    return parser.parse_args(argv)


def qualify_isolation(
    *,
    candidate_database: str,
    candidate_schema: str,
    runtime_database: str,
    runtime_schema: str,
) -> None:
    """Refuse same-database same-schema upgrade proof.

    Args:
        candidate_database: Restored copy database.
        candidate_schema: Restored copy schema.
        runtime_database: Live database.
        runtime_schema: Live vendor schema.

    Raises:
        GraphLifecycleError: If candidate equals runtime database+schema.
    """

    assert_isolated_upgrade_environment(
        candidate_database=candidate_database,
        candidate_schema=candidate_schema,
        runtime_database=runtime_database,
        runtime_schema=runtime_schema,
    )


def restore_dump_into_disposable_database(
    *,
    admin_dsn: str,
    candidate_database: str,
    runtime_database: str,
    dump_path: Path,
) -> None:
    """Create the candidate database and restore a dump into it.

    Args:
        admin_dsn: Privileged DSN. Never logged.
        candidate_database: New database name.
        runtime_database: Live database that must not be the restore target.
        dump_path: Existing pg_dump custom-format file.

    Raises:
        GraphLifecycleError: Same-database restore or missing dump/tools.
        RuntimeError: Create/restore process failure.
    """

    if candidate_database.strip() == runtime_database.strip():
        raise GraphLifecycleError("upgrade_restore_requires_separate_database")
    if not dump_path.is_file():
        raise GraphLifecycleError("upgrade_dump_missing")
    createdb = shutil.which("createdb")
    pg_restore = shutil.which("pg_restore")
    if createdb is None or pg_restore is None:
        raise GraphLifecycleError("upgrade_restore_tools_missing")
    create = subprocess.run(  # noqa: S603 - pinned local restore tools only.
        [createdb, "--maintenance-db", admin_dsn, candidate_database],
        check=False,
        capture_output=True,
        text=True,
    )
    if create.returncode != 0:
        diagnostic = (create.stderr or create.stdout).strip()
        if "already exists" not in diagnostic.lower():
            raise RuntimeError("createdb_failed")
    restore = subprocess.run(  # noqa: S603 - pinned local restore tools only.
        [
            pg_restore,
            "--dbname",
            admin_dsn.rsplit("/", 1)[0] + f"/{candidate_database}",
            "--no-owner",
            "--no-acl",
            str(dump_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if restore.returncode != 0:
        raise RuntimeError("pg_restore_failed")


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    Args:
        argv: Optional argument list.

    Returns:
        Process exit code. ``2`` means same-schema proof was refused.
    """

    args = parse_args(argv)
    try:
        qualify_isolation(
            candidate_database=args.candidate_database,
            candidate_schema=args.candidate_schema,
            runtime_database=args.runtime_database,
            runtime_schema=args.runtime_schema,
        )
    except GraphLifecycleError as exc:
        print(f"upgrade isolation refused: {exc.reason}")
        return EXIT_REFUSED
    dump = str(args.dump_path).strip()
    if not dump:
        print(
            "upgrade isolation qualified: restore a dump into "
            f"{args.candidate_database} (not a second workspace in "
            f"{args.runtime_database}.{args.runtime_schema})"
        )
        return 0
    admin_dsn = str(args.admin_dsn).strip() or (
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    )
    try:
        restore_dump_into_disposable_database(
            admin_dsn=admin_dsn,
            candidate_database=args.candidate_database,
            runtime_database=args.runtime_database,
            dump_path=Path(dump),
        )
    except GraphLifecycleError as exc:
        print(f"upgrade restore unavailable: {exc.reason}")
        return EXIT_RESTORE_UNAVAILABLE
    print(f"upgrade dump restored into {args.candidate_database}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
