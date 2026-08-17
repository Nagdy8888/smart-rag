"""CLI entry for Phase 9 Packet 1 freeze and seed (host or worker)."""

from __future__ import annotations

import argparse
from pathlib import Path

from smart_rag_core.release.constants import ARTIFACT_DIR
from smart_rag_core.release.health import query_pg_search_version
from smart_rag_core.release.identity import (
    assert_identity_fields,
    collect_identity_freeze,
)
from smart_rag_core.release.io import as_json_object, dump_canonical_json
from smart_rag_core.release.migrations import (
    collect_migration_inventory,
    load_applied_versions,
)
from smart_rag_core.release.seed import seed_candidate_corpus
from smart_rag_core.settings.base import get_process_environ

DEFAULT_SUPABASE_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def _repo_root() -> Path:
    """Return the repository root from this module location.

    Returns:
        Repository root path.
    """

    return Path(__file__).resolve().parents[5]


def cmd_freeze(repo_root: Path, output: Path) -> int:
    """Write the identity freeze JSON.

    Args:
        repo_root: Repository root.
        output: Destination JSON path.

    Returns:
        Process exit code.
    """

    pg_search = "unverified_runtime"
    try:
        pg_search = query_pg_search_version(repo_root)
    except (OSError, TimeoutError):
        pg_search = "unverified_runtime"
    freeze = collect_identity_freeze(repo_root, pg_search_version=pg_search)
    assert_identity_fields(freeze)
    dump_canonical_json(as_json_object(freeze.model_dump(mode="json")), output)
    return 0


def cmd_seed(output_dir: Path, *, supabase_url: str, parade_url: str) -> int:
    """Seed the approved corpus and write corpus/readiness artifacts.

    Args:
        output_dir: Directory for JSON artifacts.
        supabase_url: Postgres URL.
        parade_url: ParadeDB writer URL.

    Returns:
        Process exit code.
    """

    outcome = seed_candidate_corpus(
        supabase_url=supabase_url,
        parade_url=parade_url,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    dump_canonical_json(
        as_json_object(outcome.corpus.model_dump(mode="json")),
        output_dir / "candidate-corpus-manifest.json",
    )
    dump_canonical_json(
        as_json_object(outcome.readiness.model_dump(mode="json")),
        output_dir / "candidate-readiness-export.json",
    )
    dump_canonical_json(
        {
            "seeded_document_versions": outcome.seeded_document_versions,
            "seeded_chunks": outcome.seeded_chunks,
            "seeded_graph_eligible_versions": outcome.seeded_graph_eligible_versions,
            "blockers": list(outcome.blockers),
            "missing_states": list(outcome.readiness.missing_states),
        },
        output_dir / "candidate-seed-counts.json",
    )
    if outcome.blockers or outcome.readiness.missing_states:
        return 1
    return 0


def cmd_migrations(repo_root: Path, output: Path, *, supabase_url: str | None) -> int:
    """Write the migration inventory, failing on applied drift.

    Args:
        repo_root: Repository root.
        output: Destination JSON path.
        supabase_url: Optional live Postgres URL.

    Returns:
        Process exit code.
    """

    applied: tuple[str, ...] | None = None
    if supabase_url:
        import psycopg

        with psycopg.connect(supabase_url) as connection:
            applied = load_applied_versions(connection)
    inventory = collect_migration_inventory(repo_root, applied_versions=applied)
    dump_canonical_json(as_json_object(inventory.model_dump(mode="json")), output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the Packet 1 CLI parser.

    Returns:
        Argument parser.
    """

    parser = argparse.ArgumentParser(
        description="Phase 9 Packet 1 candidate freeze and seed"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze", help="Write identity freeze JSON")
    freeze.add_argument("--output", type=Path, default=None)
    seed = sub.add_parser("seed", help="Seed approved corpus and drive states")
    seed.add_argument("--output-dir", type=Path, default=None)
    seed.add_argument("--supabase-url", default=None)
    seed.add_argument("--parade-url", default=None)
    migrations = sub.add_parser("migrations", help="Write migration inventory")
    migrations.add_argument("--output", type=Path, default=None)
    migrations.add_argument("--supabase-url", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one Packet 1 CLI command.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        Process exit code.
    """

    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = _repo_root()
    artifact_dir = repo_root / ARTIFACT_DIR
    if args.command == "freeze":
        output = args.output or artifact_dir / "candidate-identity-freeze.json"
        return cmd_freeze(repo_root, output)
    if args.command == "seed":
        output_dir = args.output_dir or artifact_dir
        supabase_url = (
            args.supabase_url
            or get_process_environ("SUPABASE_DB_URL")
            or DEFAULT_SUPABASE_DB_URL
        )
        parade_url = args.parade_url or get_process_environ("PARADEDB_URL")
        if not parade_url:
            parser.error("PARADEDB_URL or --parade-url is required for seed")
        return cmd_seed(output_dir, supabase_url=supabase_url, parade_url=parade_url)
    if args.command == "migrations":
        output = args.output or artifact_dir / "candidate-migrations.json"
        supabase_url = args.supabase_url or get_process_environ("SUPABASE_DB_URL")
        return cmd_migrations(repo_root, output, supabase_url=supabase_url)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
