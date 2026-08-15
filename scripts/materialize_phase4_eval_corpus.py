#!/usr/bin/env python3
"""Materialize Phase 4 open-split compact sources and a sidecar gold-id map.

Holdout labels are never loaded. Live Hybrid Ready ingest is optional and
skips nothing in this CLI: when ``--ingest`` is set the Packet 8 ParadeDB
overlay must already be up.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ruff: noqa: E402 — repo root must precede local package imports for CLI use.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from smart_rag_core.evaluation.materialize import (
    CompactEvalSource,
    PersistMapping,
    build_compact_source,
    build_sidecar,
    select_phase4_retrieve_cases,
    write_compact_sources,
    write_sidecar,
)
from smart_rag_core.evaluation.schema import EvaluationCase
from smart_rag_core.settings import SharedSettings

DEFAULT_OUTPUT = _ROOT / "tests" / "fixtures" / "evaluation" / "phase4" / "runtime"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI flags for open-split materialization.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        Parsed namespace.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Write compact Hybrid Ready sources and a sidecar gold-id map for "
            "Phase-4-owned open splits. Holdout is not loaded."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination for sources/ and gold_id_map.json",
    )
    parser.add_argument(
        "--split",
        choices=("open", "development", "qualification"),
        default="open",
        help="Open-split selector. Never includes holdout.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional positive cap after Phase-4 retrieve filtering",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Persist compact sources through Hybrid Ready (requires Compose)",
    )
    return parser.parse_args(argv)


def _ingest_case(
    case: EvaluationCase,
    source: CompactEvalSource,
    *,
    supabase_url: str,
    parade_url: str,
    settings: SharedSettings,
) -> PersistMapping:
    """Parse one compact source and drive it to Hybrid Ready.

    Args:
        case: Phase-4-owned open-split case.
        source: Compact markdown/CSV for the case.
        supabase_url: Local Supabase Postgres URL.
        parade_url: Host ParadeDB writer URL.
        settings: Shared settings for ``create_embedding_gateway``.

    Returns:
        Persist mapping with real document/version/chunk/table UUIDs.

    Raises:
        RuntimeError: If Hybrid Ready persist fails.
    """

    import psycopg

    from tests.contract.hybrid_ready_driver import (
        drive_hybrid_ready,
        list_persisted_chunk_texts,
        list_persisted_table_ids,
        parse_local_bytes,
    )

    if source.table_csv is not None and source.table_filename is not None:
        payload = source.table_csv.encode("utf-8")
        filename = source.table_filename
        format_key = "csv"
    else:
        payload = source.markdown_text.encode("utf-8")
        filename = source.markdown_filename
        format_key = "markdown"
    parsed = parse_local_bytes(payload, filename=filename, format_key=format_key)
    result = drive_hybrid_ready(
        supabase_url=supabase_url,
        parade_url=parade_url,
        parse_result=parsed,
        title=f"p4-eval-{case.case_id}",
        filename=filename,
        settings=settings,
        visibility=source.visibility,
    )
    if not result.hybrid_ready:
        raise RuntimeError(
            f"Hybrid Ready persist failed for {case.case_id}: "
            f"{result.status}/{result.detail}"
        )
    with psycopg.connect(supabase_url) as supabase:
        chunk_texts = list_persisted_chunk_texts(supabase, result.version_id)
        table_ids = list_persisted_table_ids(supabase, result.version_id)
    return PersistMapping(
        document_id=result.document_id,
        version_id=result.version_id,
        chunk_texts=chunk_texts,
        table_ids=table_ids,
    )


def main(argv: list[str] | None = None) -> int:
    """Write compact sources and a sidecar map for Phase-4-owned open splits.

    Args:
        argv: Optional CLI arguments excluding the program name.

    Returns:
        ``0`` on success, ``2`` when ``--ingest`` cannot reach Compose.

    Side Effects:
        Writes files under ``--output-dir``. Does not mutate sealed manifests.
        Does not load holdout labels.
    """

    args = _parse_args(argv)
    cases = select_phase4_retrieve_cases(split=args.split, limit=args.limit)
    write_compact_sources(cases, args.output_dir)
    persist_index: dict[str, PersistMapping] = {}
    if args.ingest:
        from tests.contract.integration_support import (
            packet8_paradedb_url,
            paradedb_host_reachable,
            resolve_supabase_db_url,
            try_connect,
        )

        supabase_url = resolve_supabase_db_url()
        parade_url = packet8_paradedb_url()
        connection = try_connect(supabase_url)
        if connection is None or parade_url is None or not paradedb_host_reachable():
            sys.stderr.write(
                "Hybrid Ready ingest requires local Supabase and the Packet 8 "
                "ParadeDB overlay (docker compose --env-file .env.compose "
                "-f docker-compose.yml -f docker-compose.packet8.yml).\n"
            )
            return 2
        connection.close()
        settings = SharedSettings()
        for case in cases:
            source = build_compact_source(case)
            persist_index[case.case_id] = _ingest_case(
                case,
                source,
                supabase_url=supabase_url,
                parade_url=parade_url,
                settings=settings,
            )
    sidecar = build_sidecar(cases, persist_index=persist_index or None)
    path = write_sidecar(sidecar, args.output_dir)
    sys.stdout.write(
        json.dumps(
            {
                "output": str(path),
                "case_count": sidecar.case_count,
                "record_count": len(sidecar.records),
                "holdout_opened": sidecar.holdout_opened,
                "ingest": bool(args.ingest),
                "sidecar_sha256": sidecar.sidecar_sha256,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
