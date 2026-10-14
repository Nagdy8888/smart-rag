"""Authorized chunk context loader for rerank excerpts and parent expansion."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

import psycopg

from smart_rag_core.retrieval.session import retrieval_transaction
from smart_rag_core.security.identity import CallerContext

CONTEXT_BATCH_LIMIT = 75


class ContextBatchError(RuntimeError):
    """Raised when a single RPC batch exceeds the 75-ID bound."""


@dataclass(frozen=True, slots=True)
class ChunkContext:
    """One authorized current chunk used as citation text.

    Attributes:
        chunk_id: Canonical chunk.
        document_id: Document.
        version_id: Current version.
        parent_chunk_id: Parent passage when present.
        chunk_index: Order within the version.
        page_number: Optional page locator from the canonical row.
        section_path: Heading path from the canonical row.
        token_count: Stored token count.
        raw_text: Canonical citation text. Never a BM25 snippet.
        is_search_representative: Whether the row is a search child.
        sheet_name: Workbook sheet from provenance locators, if any.
        range_ref: Sheet/cell range from provenance locators, if any.
        source_url: Crawl/HTML URL from provenance locators, if any.
        content_kind: ``code``, ``table``, or ``figure`` when the chunk
            was stored as that modality.
        figure_id: Stable figure id when ``content_kind`` is ``figure``.
    """

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    parent_chunk_id: UUID | None
    chunk_index: int
    page_number: int | None
    section_path: tuple[str, ...]
    token_count: int | None
    raw_text: str
    is_search_representative: bool
    sheet_name: str | None = None
    range_ref: str | None = None
    source_url: str | None = None
    content_kind: str | None = None
    figure_id: str | None = None


def modality_from_provenance(provenance: object) -> tuple[str | None, str | None]:
    """Read content kind and figure id from chunk provenance JSON.

    Args:
        provenance: JSON object stored on ``app.document_chunks.provenance``.

    Returns:
        ``(content_kind, figure_id)``. Missing keys are ``None``.
    """

    payload = _as_mapping(provenance)
    kind = payload.get("content_kind")
    figure = payload.get("figure_id")
    content_kind = (
        kind if isinstance(kind, str) and kind in {"code", "table", "figure"} else None
    )
    figure_id = figure if isinstance(figure, str) and figure else None
    return content_kind, figure_id


def locators_from_provenance(
    provenance: object,
) -> tuple[str | None, str | None, str | None]:
    """Parse sheet, range, and URL from canonical ``provenance`` locators.

    Args:
        provenance: JSON object stored on ``app.document_chunks.provenance``.
            Locators are the ``locator_to_dict`` payloads under ``locators``.

    Returns:
        ``(sheet_name, range_ref, source_url)``. Missing keys are ``None``.
        BM25 snippets are never consulted.
    """

    payload = _as_mapping(provenance)
    raw_locators = payload.get("locators")
    locators: list[object]
    if isinstance(raw_locators, list):
        locators = list(cast(list[object], raw_locators))
    elif payload.get("format"):
        locators = [payload]
    else:
        locators = []
    sheet_name: str | None = None
    range_ref: str | None = None
    source_url: str | None = None
    for item in locators:
        mapping = _as_mapping(item)
        if sheet_name is None:
            sheet_name = _optional_str(mapping.get("sheet_name"))
        if range_ref is None:
            range_ref = _optional_str(mapping.get("range_ref")) or _optional_str(
                mapping.get("cell_ref")
            )
        if source_url is None:
            source_url = _optional_str(mapping.get("source_url"))
        if sheet_name and range_ref and source_url:
            break
    return sheet_name, range_ref, source_url


def heading_inventory_from_contexts(
    contexts: tuple[ChunkContext, ...],
) -> tuple[str, ...]:
    """Return distinct authorized ``section_path`` values.

    There is no second heading-inventory table. Inventory is the distinct
    current authorized section paths from context rows.

    Args:
        contexts: Authorized chunk rows, including parents.

    Returns:
        Distinct joined section paths in first-seen order.
    """

    seen: set[str] = set()
    ordered: list[str] = []
    for item in contexts:
        if not item.section_path:
            continue
        label = "/".join(item.section_path)
        if label in seen:
            continue
        seen.add(label)
        ordered.append(label)
    return tuple(ordered)


def fetch_authorized_chunk_context(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    chunk_ids: tuple[UUID, ...],
) -> tuple[ChunkContext, ...]:
    """Load ACL-visible current rows including non-representative parents.

    The SQL RPC rejects more than 75 IDs. Fused Hybrid lists can exceed that
    (dense 100 + BM25 75 + term 30), so this adapter issues sequential 75-ID
    RPC batches on the same connection after each transaction commits.

    Args:
        connection: Login role that can become ``app_api``. Must be idle.
        caller: Server-derived identity.
        chunk_ids: Canonical IDs. Duplicates are dropped. Length may exceed 75.

    Returns:
        Authorized rows in first-seen request order. Missing/unauthorized IDs
        are omitted.

    Raises:
        ContextBatchError: If an internal RPC batch is built above 75 IDs.

    Side Effects:
        One retrieval transaction per 75-ID batch. Unauthorized IDs never
        leave the RPC.
    """

    unique: list[UUID] = []
    seen: set[UUID] = set()
    for chunk_id in chunk_ids:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        unique.append(chunk_id)
    if not unique:
        return ()
    loaded: dict[UUID, ChunkContext] = {}
    for start in range(0, len(unique), CONTEXT_BATCH_LIMIT):
        batch = tuple(unique[start : start + CONTEXT_BATCH_LIMIT])
        for row in _fetch_context_rpc_batch(
            connection,
            caller=caller,
            chunk_ids=batch,
        ):
            loaded[row.chunk_id] = row
    return tuple(loaded[item] for item in unique if item in loaded)


def _fetch_context_rpc_batch(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    chunk_ids: tuple[UUID, ...],
) -> tuple[ChunkContext, ...]:
    """Issue one ``fetch_authorized_chunk_context`` RPC of at most 75 IDs.

    Args:
        connection: Idle login connection.
        caller: Server-derived identity.
        chunk_ids: Unique IDs, length ≤ ``CONTEXT_BATCH_LIMIT``.

    Returns:
        Authorized rows returned by the RPC (unordered relative to ``chunk_ids``).

    Raises:
        ContextBatchError: If ``chunk_ids`` exceeds the RPC bound.

    Side Effects:
        One retrieval transaction.
    """

    if len(chunk_ids) > CONTEXT_BATCH_LIMIT:
        raise ContextBatchError("context_batch_exceeds_limit")
    if not chunk_ids:
        return ()
    with retrieval_transaction(
        connection,
        caller=caller,
        profile="low",
        apply_hnsw=False,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  chunk_id,
                  document_id,
                  version_id,
                  parent_chunk_id,
                  chunk_index,
                  page_number,
                  section_path,
                  token_count,
                  raw_text,
                  is_search_representative,
                  provenance
                FROM app.fetch_authorized_chunk_context(
                  %s::uuid,
                  %s::text,
                  %s::bigint,
                  %s::uuid[]
                )
                """,
                (
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    list(chunk_ids),
                ),
            )
            rows = cursor.fetchall()
    results: list[ChunkContext] = []
    for raw_row in rows:
        row = cast(Sequence[object], raw_row)
        section = row[6]
        path = (
            tuple(str(item) for item in cast(Sequence[object], section))
            if section
            else ()
        )
        provenance = row[10] if len(row) > 10 else None
        sheet_name, range_ref, source_url = locators_from_provenance(provenance)
        content_kind, figure_id = modality_from_provenance(provenance)
        results.append(
            ChunkContext(
                chunk_id=UUID(str(row[0])),
                document_id=UUID(str(row[1])),
                version_id=UUID(str(row[2])),
                parent_chunk_id=UUID(str(row[3])) if row[3] is not None else None,
                chunk_index=int(str(row[4])),
                page_number=int(str(row[5])) if row[5] is not None else None,
                section_path=path,
                token_count=int(str(row[7])) if row[7] is not None else None,
                raw_text=str(row[8]),
                is_search_representative=bool(row[9]),
                sheet_name=sheet_name,
                range_ref=range_ref,
                source_url=source_url,
                content_kind=content_kind,
                figure_id=figure_id,
            )
        )
    return tuple(results)


def _as_mapping(value: object) -> dict[str, object]:
    """Coerce JSONB or JSON text to a dictionary.

    Args:
        value: Driver-decoded JSON or a JSON string.

    Returns:
        A dictionary, or empty when the value is not an object.
    """

    if isinstance(value, dict):
        return cast(dict[str, object], value)
    if isinstance(value, str) and value.strip():
        try:
            loaded: object = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(loaded, dict):
            return cast(dict[str, object], loaded)
    return {}


def _optional_str(value: object) -> str | None:
    """Return a non-empty string or ``None``.

    Args:
        value: JSON field.

    Returns:
        Stripped text, or ``None`` when missing/blank.
    """

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def fetch_authorized_heading_inventory(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    version_id: UUID,
) -> tuple[str, ...]:
    """Return authorized major section paths for one current version.

    Args:
        connection: Idle login connection.
        caller: Server-derived identity.
        version_id: Current document version.

    Returns:
        Distinct joined section paths in first-seen order. Missing,
        unauthorized, stale, or deleted versions return empty.
    """

    with retrieval_transaction(
        connection,
        caller=caller,
        profile="low",
        apply_hnsw=False,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT section_path, page_start, page_end
                FROM app.retrieve_heading_inventory(
                  %s::uuid,
                  %s::text,
                  %s::bigint,
                  %s::uuid
                )
                """,
                (
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    version_id,
                ),
            )
            rows = cursor.fetchall()
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_row in rows:
        row = cast(Sequence[object], raw_row)
        section = row[0]
        path = (
            tuple(str(item) for item in cast(Sequence[object], section))
            if section
            else ()
        )
        if not path:
            continue
        label = "/".join(path)
        if label in seen:
            continue
        seen.add(label)
        ordered.append(label)
    return tuple(ordered)


EVAL_PASSAGE_LIMIT = 60


def list_authorized_eval_passages(
    connection: psycopg.Connection,
    caller: CallerContext,
    *,
    version_id: UUID,
    limit: int = 40,
    after_chunk_id: UUID | None = None,
) -> tuple[ChunkContext, ...]:
    """List current authorized representative passages for one PDF version.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived identity.
        version_id: Current document version.
        limit: Page size, capped at 60.
        after_chunk_id: Keyset cursor. None starts at the first child.

    Returns:
        Authorized current representative chunks. Cross-document IDs
        are omitted by the RPC.

    Raises:
        ContextBatchError: Limit exceeds 60.
    """

    bounded = min(max(limit, 1), EVAL_PASSAGE_LIMIT)
    if limit > EVAL_PASSAGE_LIMIT:
        raise ContextBatchError("eval_passage_limit")
    with retrieval_transaction(
        connection,
        caller=caller,
        profile="low",
        apply_hnsw=False,
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  chunk_id,
                  document_id,
                  version_id,
                  page_number,
                  section_path,
                  raw_text,
                  is_search_representative
                FROM app.list_authorized_eval_passages(
                  %s::uuid,
                  %s::text,
                  %s::bigint,
                  %s::uuid,
                  %s::integer,
                  %s::uuid
                )
                """,
                (
                    caller.rpc_user_id(),
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    version_id,
                    bounded,
                    after_chunk_id,
                ),
            )
            rows = cursor.fetchall()
    results: list[ChunkContext] = []
    for raw_row in rows:
        row = cast(Sequence[object], raw_row)
        section = row[4]
        path = (
            tuple(str(item) for item in cast(Sequence[object], section))
            if section
            else ()
        )
        results.append(
            ChunkContext(
                chunk_id=UUID(str(row[0])),
                document_id=UUID(str(row[1])),
                version_id=UUID(str(row[2])),
                parent_chunk_id=None,
                chunk_index=0,
                page_number=int(str(row[3])) if row[3] is not None else None,
                section_path=path,
                token_count=None,
                raw_text=str(row[5]),
                is_search_representative=bool(row[6]),
            )
        )
    return tuple(results)
