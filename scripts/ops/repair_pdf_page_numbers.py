"""Repair stored PDF ``page_number`` from locator ``page_index + 1``.

Default is dry-run. ``--apply`` writes mismatched rows. Never changes
``page_label``. Reports IDs and counts only; never title or source text.
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ops.ingest_demo_plot_slices import merged_env, require_env  # noqa: E402

_PDF_FORMATS = frozenset({"pdf", "ocr"})
_MAX_BATCH_SIZE = 500


class PageAmbiguousError(RuntimeError):
    """A representative leaf has zero or multiple distinct PDF page indices."""

    def __init__(self, chunk_id: UUID) -> None:
        """Store the failing chunk id without source text.

        Args:
            chunk_id: Canonical leaf that cannot be repaired without guessing.
        """

        super().__init__(f"page_ambiguous:{chunk_id}")
        self.chunk_id = chunk_id


def pdf_locator_page_indexes(provenance: object) -> tuple[int, ...]:
    """Return distinct locator ``page_index`` values for PDF/OCR locators.

    Args:
        provenance: Stored chunk ``provenance`` jsonb.

    Returns:
        Sorted unique zero-based page indexes. ``page_label`` is ignored.
    """

    if not isinstance(provenance, dict):
        return ()
    raw_locators = provenance.get("locators")
    if not isinstance(raw_locators, list):
        return ()
    pages: set[int] = set()
    for item in raw_locators:
        if not isinstance(item, dict):
            continue
        format_key = str(item.get("format") or "")
        if format_key not in _PDF_FORMATS:
            continue
        raw_index = item.get("page_index")
        if isinstance(raw_index, bool) or not isinstance(raw_index, int):
            continue
        if raw_index < 0:
            continue
        pages.add(raw_index)
    return tuple(sorted(pages))


def viewer_page_from_locators(provenance: object) -> int | None:
    """Return the 1-based PDF viewer page from a unique locator index.

    Args:
        provenance: Stored chunk ``provenance`` jsonb.

    Returns:
        ``page_index + 1`` when exactly one PDF/OCR index exists, else
        ``None`` when the chunk has no PDF locators.

    Raises:
        ValueError: If PDF locators exist but are missing or multi-page.
    """

    pages = pdf_locator_page_indexes(provenance)
    if not pages:
        if _has_pdf_locator(provenance):
            raise ValueError("page_ambiguous")
        return None
    if len(pages) != 1:
        raise ValueError("page_ambiguous")
    return pages[0] + 1


def _has_pdf_locator(provenance: object) -> bool:
    """Return whether provenance contains a PDF or OCR locator object.

    Args:
        provenance: Stored chunk ``provenance`` jsonb.

    Returns:
        True when at least one locator has format ``pdf`` or ``ocr``.
    """

    if not isinstance(provenance, dict):
        return False
    raw_locators = provenance.get("locators")
    if not isinstance(raw_locators, list):
        return False
    for item in raw_locators:
        if isinstance(item, dict) and str(item.get("format") or "") in _PDF_FORMATS:
            return True
    return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse operator flags.

    Args:
        argv: Optional CLI arguments.

    Returns:
        Parsed namespace.
    """

    parser = argparse.ArgumentParser(
        description="Repair document_chunks.page_number from locator page_index + 1."
    )
    parser.add_argument("--version-id", required=True, help="Target document version UUID.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Rows per fetch, maximum 500.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write mismatched page_number values. Default is dry-run.",
    )
    return parser.parse_args(argv)


def repair_version_page_numbers(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
    batch_size: int,
    apply: bool,
) -> dict[str, int | str]:
    """Scan one version and optionally update mismatched PDF page numbers.

    Args:
        connection: Operator-role connection. The caller owns commit.
        version_id: Target version.
        batch_size: Fetch size, already clamped to ``1..500``.
        apply: When false, compute counts without writing.

    Returns:
        Aggregate counts and the version id. No title or source text.

    Raises:
        PageAmbiguousError: A representative leaf cannot be repaired.
    """

    scanned = 0
    mismatched = 0
    updated = 0
    skipped_non_pdf = 0
    offset = 0
    while True:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, page_number, provenance
                FROM app.document_chunks
                WHERE version_id = %s
                  AND deleted_at IS NULL
                  AND is_search_representative IS TRUE
                ORDER BY chunk_index, id
                LIMIT %s OFFSET %s
                """,
                (version_id, batch_size, offset),
            )
            rows = cursor.fetchall()
        if not rows:
            break
        for row in rows:
            scanned += 1
            chunk_id = UUID(str(row["id"]))
            try:
                derived = viewer_page_from_locators(row.get("provenance"))
            except ValueError as exc:
                raise PageAmbiguousError(chunk_id) from exc
            if derived is None:
                skipped_non_pdf += 1
                continue
            stored = row.get("page_number")
            stored_page = int(stored) if stored is not None else None
            if stored_page == derived:
                continue
            mismatched += 1
            if not apply:
                continue
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE app.document_chunks
                    SET page_number = %s,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                      AND version_id = %s
                      AND deleted_at IS NULL
                      AND (page_number IS DISTINCT FROM %s)
                    """,
                    (derived, chunk_id, version_id, derived),
                )
                updated += cursor.rowcount
        offset += len(rows)
    return {
        "version_id": str(version_id),
        "scanned": scanned,
        "mismatched": mismatched,
        "updated": updated if apply else 0,
        "skipped_non_pdf": skipped_non_pdf,
        "apply": int(apply),
    }


def main(argv: list[str] | None = None) -> int:
    """Repair one version's stored PDF page numbers.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` on success, ``2`` on missing env, ``3`` on ambiguous locators.
    """

    args = parse_args(argv)
    batch_size = min(max(int(args.batch_size), 1), _MAX_BATCH_SIZE)
    version_id = UUID(str(args.version_id))
    env = merged_env()
    try:
        operator_url = require_env(env, "OPERATOR_SUPABASE_DB_URL")
    except RuntimeError:
        print("missing_operator_url")
        return 2
    apply = bool(args.apply)
    with psycopg.connect(operator_url) as connection:
        connection.autocommit = False
        try:
            summary = repair_version_page_numbers(
                connection,
                version_id=version_id,
                batch_size=batch_size,
                apply=apply,
            )
            if apply:
                connection.commit()
            else:
                connection.rollback()
        except PageAmbiguousError as exc:
            connection.rollback()
            print(f"page_ambiguous chunk_id={exc.chunk_id}")
            return 3
    print(f"version_id={summary['version_id']}")
    print(f"scanned={summary['scanned']}")
    print(f"mismatched={summary['mismatched']}")
    print(f"updated={summary['updated']}")
    print(f"skipped_non_pdf={summary['skipped_non_pdf']}")
    print(f"apply={bool(summary['apply'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
