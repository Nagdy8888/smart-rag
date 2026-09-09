"""Draft a private PDF evaluation dataset. Generated rows are never gold."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.evaluation.private_pdf import (  # noqa: E402
    PRIVATE_PDF_DATASET_VERSION,
    ChunkLocator,
    build_draft_rows,
    manifest_hash,
    near_duplicate_pairs,
    read_private_pdf_payload,
)
from smart_rag_core.evaluation.private_pdf.schema import (  # noqa: E402
    PrivatePdfCase,
)

from scripts.ops.ingest_demo_plot_slices import (  # noqa: E402
    merged_env,
    require_env,
)


def _git_safe_cases(rows: tuple[dict[str, object], ...]) -> tuple[PrivatePdfCase, ...]:
    """Drop private question/answer fields before hashing.

    Args:
        rows: Private draft mappings.

    Returns:
        Git-safe cases.
    """

    cases: list[PrivatePdfCase] = []
    for row in rows:
        chunk_raw = row["chunk_ids"]
        page_raw = row["page_numbers"]
        if not isinstance(chunk_raw, (list, tuple)):
            raise ValueError("invalid_draft_chunk_ids")
        if not isinstance(page_raw, (list, tuple)):
            raise ValueError("invalid_draft_page_numbers")
        actor = row.get("acl_actor_id")
        chunk_items = cast(Sequence[object], chunk_raw)
        page_items = cast(Sequence[object], page_raw)
        chunks: list[UUID] = []
        for value in chunk_items:
            chunks.append(UUID(str(value)))
        pages: list[int] = []
        for value in page_items:
            pages.append(int(str(value)))
        cases.append(
            PrivatePdfCase(
                case_id=str(row["case_id"]),
                split=str(row["split"]),
                source_family_id=str(row["source_family_id"]),
                query_class=str(row["query_class"]),
                chunk_ids=tuple(chunks),
                page_numbers=tuple(pages),
                heading_paths=(),
                required_terms=(),
                expected_profile_id=str(row["expected_profile_id"]),
                expected_scope=str(row["expected_scope"]),
                expected_refusal=bool(row["expected_refusal"]),
                acl_actor_id=str(actor) if actor is not None else None,
                human_approved=False,
                generated_only=True,
                reviewer=None,
            )
        )
    return tuple(cases)


def _load_locators(
    *,
    operator_url: str,
    version_id: str,
) -> tuple[tuple[ChunkLocator, ...], str | None, tuple[str, ...]]:
    """Load current representative locators. Does not print text.

    Args:
        operator_url: Operator session URL.
        version_id: Ingested version id.

    Returns:
        Locators, document owner id, and alias strings.
    """

    with psycopg.connect(operator_url, connect_timeout=20) as connection:
        connection.execute("SET ROLE postgres")
        owner = connection.execute(
            """
            SELECT d.created_by::text
            FROM app.document_versions AS dv
            JOIN app.documents AS d ON d.id = dv.document_id
            WHERE dv.id = %s::uuid
            """,
            (version_id,),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT id, coalesce(page_number, 0), section_path, raw_text
            FROM app.document_chunks
            WHERE version_id = %s::uuid
              AND deleted_at IS NULL
              AND is_search_representative
            ORDER BY chunk_index
            """,
            (version_id,),
        ).fetchall()
        aliases = connection.execute(
            """
            SELECT alias
            FROM app.search_aliases
            ORDER BY created_at
            LIMIT 32
            """
        ).fetchall()
    locators: list[ChunkLocator] = []
    for row in rows:
        section_raw = row[2]
        path_parts: list[str] = []
        if isinstance(section_raw, (list, tuple)):
            for part in cast(Sequence[object], section_raw):
                path_parts.append(str(part))
        locators.append(
            ChunkLocator(
                chunk_id=UUID(str(row[0])),
                page_number=int(str(row[1])),
                section_path=tuple(path_parts),
                raw_text=str(row[3] or ""),
            )
        )
    owner_id = str(owner[0]) if owner is not None else None
    alias_values = tuple(str(row[0]) for row in aliases)
    return tuple(locators), owner_id, alias_values


def main(argv: list[str] | None = None) -> int:
    """Write a generated-only private draft. Does not self-seal.

    Args:
        argv: Optional CLI arguments.

    Returns:
        Process exit code. Stops without OpenAI when the matrix is unsigned.
    """

    parser = argparse.ArgumentParser(
        description="Draft private PDF eval cases. Does not self-seal."
    )
    parser.add_argument("--pdf-sha256", default="")
    parser.add_argument("--ids", type=Path, default=Path(".private-eval/ingest-ids.json"))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    env = merged_env()
    if env.get("SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        print("draft_blocked_provider_matrix_unverified")
        print("openai_calls=0")
        return 2
    if not args.ids.is_file():
        print("blocked=ingest_ids_missing")
        return 2
    ids = json.loads(args.ids.read_text(encoding="utf-8"))
    digest = args.pdf_sha256 or str(ids.get("content_hash", ""))
    version_id = str(ids.get("version_id", ""))
    if len(digest) < 12 or not version_id:
        print("blocked=ingest_identity_missing")
        return 2
    operator_url = require_env(env, "OPERATOR_SUPABASE_DB_URL")
    locators, owner_id, aliases = _load_locators(
        operator_url=operator_url,
        version_id=version_id,
    )
    print(f"locator_count={len(locators)}")
    try:
        rows = build_draft_rows(
            locators,
            document_hash=digest,
            aliases=aliases,
            acl_actor_id=owner_id,
        )
    except ValueError as exc:
        print(f"blocked={exc}")
        return 2
    questions = tuple(str(row["question"]) for row in rows)
    dupes = near_duplicate_pairs(questions)
    if dupes:
        print(f"blocked=near_duplicate_questions count={len(dupes)}")
        return 2
    out_dir = args.out or (
        Path(".private-eval") / digest[:12] / PRIVATE_PDF_DATASET_VERSION
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    private_path = out_dir / "draft.json"
    private_path.write_text(
        json.dumps(
            {
                "schema_version": "private-pdf-eval-v1",
                "generated_only": True,
                "human_sealed": False,
                "holdout_opened": False,
                "version_id": version_id,
                "document_id": ids.get("document_id"),
                "content_hash": digest,
                "openai_calls": 0,
                "cases": list(rows),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    safe = _git_safe_cases(rows)
    manifest = {
        "rows": [
            {
                "case_id": case.case_id,
                "source_family_id": case.source_family_id,
                "split": case.split,
                "query_class": case.query_class,
                "generated_only": True,
                "human_approved": False,
            }
            for case in safe
        ],
        "holdout_opened": False,
        "manifest_sha256": manifest_hash(safe),
        "case_count": len(safe),
    }
    (out_dir / "draft_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    split_counts = {
        name: sum(1 for case in safe if case.split == name)
        for name in ("development", "qualification", "holdout")
    }
    print(f"draft_count={len(rows)}")
    print(f"split_counts={json.dumps(split_counts, sort_keys=True)}")
    print("human_sealed=false")
    print("holdout_opened=false")
    print("openai_calls=0")
    _ = read_private_pdf_payload(private_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
