"""Protected LightRAG schema bootstrap CLI.

Loads ``LightRagSchemaAdminSettings`` and calls core bootstrap. This script
does not import ``lightrag`` directly.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

import psycopg
from smart_rag_core.gateways.embedding import create_embedding_gateway
from smart_rag_core.gateways.model import create_model_gateway
from smart_rag_core.retrieval.graph import DEFAULT_GRAPH_WORKSPACE
from smart_rag_core.retrieval.lightrag_bootstrap import (
    bootstrap_lightrag_schema,
    persist_capture_status,
    repeat_bootstrap_lightrag_schema,
)
from smart_rag_core.settings import SharedSettings, load_lightrag_schema_admin_settings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the protected bootstrap.

    Args:
        argv: Optional argument list excluding the program name.

    Returns:
        Parsed arguments.
    """

    parser = argparse.ArgumentParser(
        description="Run protected LightRAG initialize_storages against schema lightrag."
    )
    parser.add_argument(
        "--repeat",
        action="store_true",
        help="Run initialize a second time and require a stable fingerprint.",
    )
    parser.add_argument(
        "--workspace",
        default=DEFAULT_GRAPH_WORKSPACE,
        help="Constructor workspace. Never read from POSTGRES_WORKSPACE.",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    """Execute protected bootstrap and optional repeat.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Process exit code.

    Side Effects:
        Opens schema-admin Postgres, runs vendor initialize, updates capture
        status. Does not print passwords.
    """

    admin = load_lightrag_schema_admin_settings()
    settings = SharedSettings(mock_model_mode=True)
    embedding_gateway = create_embedding_gateway(settings)
    model_gateway = create_model_gateway(settings)
    dsn = admin.lightrag_schema_admin_dsn.get_secret_value()
    connection = psycopg.connect(dsn)
    working_dir = Path(tempfile.mkdtemp(prefix="smart-rag-lightrag-bootstrap-"))
    try:
        first = await bootstrap_lightrag_schema(
            schema_admin_dsn=admin.lightrag_schema_admin_dsn,
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=working_dir / "first",
            connection=connection,
            workspace=args.workspace,
        )
        persist_capture_status(connection, first)
        print(
            "lightrag bootstrap captured "
            f"tables={len(first.fingerprint.tables)} "
            f"digest={first.fingerprint_sha256}"
        )
        if args.repeat:
            second = await repeat_bootstrap_lightrag_schema(
                schema_admin_dsn=admin.lightrag_schema_admin_dsn,
                embedding_gateway=embedding_gateway,
                model_gateway=model_gateway,
                working_dir=working_dir / "repeat",
                connection=connection,
                first=first,
                workspace=args.workspace,
            )
            persist_capture_status(connection, second)
            print(
                f"lightrag repeat bootstrap stable digest={second.fingerprint_sha256}"
            )
        return 0
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    Args:
        argv: Optional argument list.

    Returns:
        Process exit code.
    """

    args = parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
