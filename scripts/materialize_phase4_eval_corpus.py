#!/usr/bin/env python3
"""Materialize Phase 4 open-split compact sources and a sidecar gold-id map.

Holdout labels are never loaded. Live Hybrid Ready ingest is optional and
skips nothing in this CLI: ``--ingest`` requires an explicit
``SUPABASE_DB_URL`` (no local fixture default) and a running Packet 8
ParadeDB overlay.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# ruff: noqa: E402 — repo root must precede local package imports for CLI use.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import psycopg
from smart_rag_core.evaluation.materialize import (
    GOLD_CHUNK_MARKER,
    CompactEvalSource,
    PersistMapping,
    build_compact_source,
    build_sidecar,
    select_phase4_retrieve_cases,
    write_compact_sources,
    write_sidecar,
)
from smart_rag_core.evaluation.schema import EvaluationCase
from smart_rag_core.settings import SharedSettings, setdefault_process_environ

DEFAULT_OUTPUT = _ROOT / "tests" / "fixtures" / "evaluation" / "phase4" / "runtime"


def _load_repo_env() -> None:
    """Fill missing process env from repo ``.env`` without overriding exports.

    Side Effects:
        Reads ``.env`` keys into ``os.environ`` with ``setdefault`` so an
        explicit ``MOCK_MODEL_MODE=false`` export still wins. Values are not
        logged.
    """

    path = _ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        name = key.strip()
        if not name:
            continue
        setdefault_process_environ(name, value.strip().strip('"').strip("'"))


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
        help="Persist compact sources through Hybrid Ready (requires SUPABASE_DB_URL)",
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

    from tests.contract.hybrid_ready_driver import (
        drive_hybrid_ready,
        list_persisted_chunk_texts,
        list_persisted_table_ids,
        parse_local_bytes,
    )

    parsed = parse_local_bytes(
        source.markdown_text.encode("utf-8"),
        filename=source.markdown_filename,
        format_key="markdown",
    )
    result = drive_hybrid_ready(
        supabase_url=supabase_url,
        parade_url=parade_url,
        parse_result=parsed,
        title=f"p4-eval-{case.case_id}",
        filename=source.markdown_filename,
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
        mapping = PersistMapping(
            document_id=result.document_id,
            version_id=result.version_id,
            chunk_texts=chunk_texts,
            table_ids=table_ids,
        )
        _stamp_eval_retrieve_metadata(supabase, case, mapping)
        supabase.commit()
    return mapping


def _eval_effective_at(case: EvaluationCase) -> datetime:
    """Return a UTC effective timestamp the ``as_of`` policy can keep.

    Args:
        case: Phase-4-owned case.

    Returns:
        ``target_date`` at midnight UTC when labeled, otherwise 2024-01-01 UTC
        so ``as_of 2024-06-01`` cases remain visible.
    """

    raw = case.expected_profile.target_date.value
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw.strip())
        except ValueError:
            parsed = None
        else:
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
    return datetime(2024, 1, 1, tzinfo=UTC)


def _stamp_eval_retrieve_metadata(
    supabase: psycopg.Connection,
    case: EvaluationCase,
    mapping: PersistMapping,
) -> None:
    """Stamp version dates and gold locators for Hybrid retrieve scoring.

    Compact markdown chunks often have ``page_number`` null and empty
    ``section_path``. Ranked-ID locator scoring compares those columns to gold
    ``page`` / ``section``. ``as_of`` policies skip versions with null
    ``effective_at``.

    Args:
        supabase: Superuser-capable connection.
        case: Phase-4-owned case.
        mapping: Persist mapping with chunk texts.

    Side Effects:
        Updates ``document_versions.effective_at`` and gold chunk locators.
    """

    supabase.execute("SET ROLE postgres")
    stamp = _eval_effective_at(case)
    with supabase.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.document_versions
            SET effective_at = %s, updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (stamp, mapping.version_id),
        )
        for link in case.evidence_links:
            if not link.chunk_id:
                continue
            needle = f"{GOLD_CHUNK_MARKER}{link.chunk_id}"
            chunk_id = next(
                (
                    item_id
                    for item_id, text in mapping.chunk_texts
                    if needle in text or link.chunk_id in text
                ),
                mapping.chunk_texts[0][0] if len(mapping.chunk_texts) == 1 else None,
            )
            if chunk_id is None:
                continue
            page_raw = link.locator.get("page", "1")
            try:
                page_number = int(str(page_raw))
            except ValueError:
                page_number = 1
            section = str(link.locator.get("section") or "Overview")
            cursor.execute(
                """
                UPDATE app.document_chunks
                SET
                  page_number = %s,
                  section_path = ARRAY[%s]::text[],
                  updated_at = timezone('utc', now())
                WHERE id = %s
                """,
                (page_number, section, chunk_id),
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
    _load_repo_env()
    cases = select_phase4_retrieve_cases(split=args.split, limit=args.limit)
    write_compact_sources(cases, args.output_dir)
    persist_index: dict[str, PersistMapping] = {}
    ingest_failures: list[str] = []
    if args.ingest:
        from tests.contract.integration_support import (
            packet8_paradedb_url,
            paradedb_host_reachable,
            resolve_supabase_db_url,
            try_connect,
        )

        supabase_url = resolve_supabase_db_url()
        if supabase_url is None:
            sys.stderr.write("SUPABASE_DB_URL is required (no local fixture default)\n")
            return 2
        parade_url = packet8_paradedb_url()
        connection = try_connect(supabase_url)
        if connection is None or parade_url is None or not paradedb_host_reachable():
            sys.stderr.write(
                "Hybrid Ready ingest requires SUPABASE_DB_URL and the Packet 8 "
                "ParadeDB overlay (docker compose --env-file .env.compose "
                "-f docker-compose.yml -f docker-compose.packet8.yml).\n"
            )
            return 2
        connection.close()
        settings = SharedSettings()
        for case in cases:
            source = build_compact_source(case)
            try:
                persist_index[case.case_id] = _ingest_case(
                    case,
                    source,
                    supabase_url=supabase_url,
                    parade_url=parade_url,
                    settings=settings,
                )
            except Exception as error:
                ingest_failures.append(f"{case.case_id}:{type(error).__name__}")
                sys.stderr.write(
                    f"ingest_skipped {case.case_id} {type(error).__name__}\n"
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
                "ingest_ok": len(persist_index),
                "ingest_failures": ingest_failures if args.ingest else [],
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
