"""Backfill printed PDF page labels onto existing chunk locators.

Downloads originals from Storage, reads ``Page.get_label()``, and stamps
``page_label`` onto ``provenance.locators``. Does not log source text.
Existing Ask runs pick up labels on the next citation GET.
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import fitz
import psycopg
from psycopg.rows import dict_row

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.gateways.storage import StorageGateway  # noqa: E402
from smart_rag_core.ingestion.parser.helpers import pdf_page_label  # noqa: E402
from smart_rag_core.ingestion.provenance import attach_page_label  # noqa: E402

from scripts.ops.ingest_demo_plot_slices import merged_env, require_env  # noqa: E402

TARGET_VERSION_ID = UUID("4324c385-80fd-4464-9c97-a7568bf364db")


def _page_labels_from_pdf(payload: bytes) -> tuple[str, ...]:
    """Return printed labels aligned with zero-based page_index.

    Args:
        payload: Original PDF bytes.

    Returns:
        One label per page. Empty strings mean the file has no label.
    """

    document = fitz.open(stream=payload, filetype="pdf")
    try:
        labels: list[str] = []
        page_count = int(document.page_count)
        for page_index in range(page_count):
            page = document.load_page(page_index)
            labels.append(pdf_page_label(page))
        return tuple(labels)
    finally:
        document.close()


def _stamp_locators(
    provenance: object,
    page_labels: tuple[str, ...],
) -> tuple[dict[str, Any], int]:
    """Return updated provenance and the count of locators that gained a label.

    Args:
        provenance: Stored chunk ``provenance`` jsonb.
        page_labels: Labels aligned with ``page_index``.

    Returns:
        ``(provenance, stamped_count)``. Unchanged when locators are absent.
    """

    if not isinstance(provenance, dict):
        return {}, 0
    payload = dict(cast(dict[str, Any], provenance))
    raw_locators = payload.get("locators")
    if not isinstance(raw_locators, list):
        return payload, 0
    stamped: list[dict[str, Any]] = []
    changed = 0
    for item in cast(list[object], raw_locators):
        if not isinstance(item, dict):
            continue
        locator = attach_page_label(cast(dict[str, Any], item), page_labels)
        if locator.get("page_label") and locator.get("page_label") != item.get(
            "page_label"
        ):
            changed += 1
        stamped.append(locator)
    payload["locators"] = stamped
    return payload, changed


def main() -> int:
    """Backfill one or all PDF versions reachable from operator credentials.

    Returns:
        ``0`` on success.

    Raises:
        RuntimeError: When required env keys are missing.
    """

    env = merged_env()
    operator_url = require_env(env, "OPERATOR_SUPABASE_DB_URL")
    storage = StorageGateway(
        supabase_url=require_env(env, "SUPABASE_URL", "SUPABASE_MANAGED_URL"),
        admin_secret=require_env(
            env,
            "SUPABASE_STORAGE_ADMIN_SECRET",
            "SUPABASE_SERVICE_ROLE_KEY",
        ),
    )
    version_id = TARGET_VERSION_ID
    with psycopg.connect(operator_url) as connection:
        connection.autocommit = False
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, storage_bucket, storage_path, media_type
                FROM app.document_versions
                WHERE id = %s
                  AND deleted_at IS NULL
                """,
                (version_id,),
            )
            version = cursor.fetchone()
        if version is None:
            raise RuntimeError("version_not_found")
        bucket = str(version["storage_bucket"] or "")
        object_path = str(version["storage_path"] or "")
        if not bucket or not object_path:
            raise RuntimeError("version_missing_storage_path")
        payload = storage.download_object(bucket=bucket, object_path=object_path)
        labels = _page_labels_from_pdf(payload)
        labeled_pages = sum(1 for label in labels if label)
        distinct_from_file = 0
        for page_index, label in enumerate(labels):
            if label and label != str(page_index + 1):
                distinct_from_file += 1
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, provenance
                FROM app.document_chunks
                WHERE version_id = %s
                  AND deleted_at IS NULL
                """,
                (version_id,),
            )
            rows = cursor.fetchall()
        chunks_updated = 0
        locators_stamped = 0
        with connection.cursor() as cursor:
            for row in rows:
                provenance, stamped = _stamp_locators(row["provenance"], labels)
                if stamped == 0:
                    continue
                cursor.execute(
                    """
                    UPDATE app.document_chunks
                    SET provenance = %s::jsonb,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (json.dumps(provenance), row["id"]),
                )
                chunks_updated += 1
                locators_stamped += stamped
        connection.commit()
    print(f"version_id={version_id}")
    print(f"pdf_pages={len(labels)}")
    print(f"labeled_pages={labeled_pages}")
    print(f"labels_differ_from_file_page={distinct_from_file}")
    print(f"chunks_updated={chunks_updated}")
    print(f"locators_stamped={locators_stamped}")
    sample_index = 200
    sample_label = labels[sample_index] if sample_index < len(labels) else ""
    print(f"file_page_201_label={sample_label or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
