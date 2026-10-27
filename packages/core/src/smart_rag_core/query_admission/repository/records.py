"""Query-run and citation record loaders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.gateways.cost_reporting import CostReporting
from smart_rag_core.query_admission.context import (
    AuthorizedRuntimeContext,
    requested_search_scope_from_row,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.repository.errors import raise_admission
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import CallerContext, UserRole


@dataclass(frozen=True, slots=True)
class QueryRunRecord:
    """Authorized run fetch payload.

    Attributes:
        run_id: Run primary key.
        conversation_id: Owning conversation.
        creator_user_id: Run owner.
        status: Durable ``app.run_status`` text.
        reservation_id: Run-local reservation when present.
        requested_search_scope: Source preference stored at admit.
        created_at: Insert timestamp when returned.
    """

    run_id: UUID
    conversation_id: UUID
    creator_user_id: UUID
    status: str
    reservation_id: UUID | None
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RunCitationRecord:
    """Citation identifiers plus the ACL-checked excerpt when authorized.

    Attributes:
        citation_id: Citation row.
        citation_index: Display index.
        chunk_id: Canonical chunk when present.
        provenance: JSON object without source HTML. Locator keys such as
            page number, heading path, and document title are included when
            the cited chunk is still authorized. Web rows include url, title,
            and content_hash only. Excerpt is never stored here.
        source_unavailable: True when the cited source was deleted.
        source_kind: ``company_document`` or ``web``.
        web_source_id: Web source UUID when ``source_kind`` is ``web``.
        paragraph_index: Owning paragraph, or ``None`` on legacy/Web rows.
        document_title: Live authorized document title.
        pdf_page_number: 1-based PDF viewer page from locator ``page_index``.
        evidence_excerpt: Exact span still present in live canonical text.
    """

    citation_id: UUID
    citation_index: int
    chunk_id: UUID | None
    provenance: dict[str, object]
    source_unavailable: bool = False
    source_kind: str = "company_document"
    web_source_id: UUID | None = None
    paragraph_index: int | None = None
    document_title: str | None = None
    pdf_page_number: int | None = None
    evidence_excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class RunCitationDetail:
    """One citation with ACL-checked excerpt metadata for the detail GET.

    Attributes:
        citation: Identifier and excerpt payload. Excerpt is omitted when
            unauthorized or the Web URL is not safe HTTPS.
        source_url: Validated HTTPS URL for Web rows, else None.
        document_id: Company document when the live chunk is readable.
        version_id: Current version id for restricted-read audit.
        document_visibility: Live visibility, or None for Web/unavailable.
    """

    citation: RunCitationRecord
    source_url: str | None = None
    document_id: UUID | None = None
    version_id: UUID | None = None
    document_visibility: str | None = None


@dataclass(frozen=True, slots=True)
class RunUsageSummary:
    """Billed usage totals for one owned query run.

    Attributes:
        cost_usd: Sum of immutable ``app.llm_usage.cost_usd`` rows.
        prompt_tokens: Sum of provider prompt tokens.
        completion_tokens: Sum of provider completion tokens.
        usage_rows: Number of billed rows included in the sums.
    """

    cost_usd: Decimal
    prompt_tokens: int
    completion_tokens: int
    usage_rows: int
    cost_reporting: CostReporting | None = None


def get_query_run(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
) -> QueryRunRecord:
    """Fetch one run owned by the caller.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived identity.
        run_id: Run primary key.

    Returns:
        Run record. Foreign or missing runs raise ``not_found``.

    Raises:
        QueryAdmissionError: Authorization or lookup failure.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.get_query_run_v3(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("not_found")
    reservation = row.get("reservation_id")
    return QueryRunRecord(
        run_id=row["id"],
        conversation_id=row["conversation_id"],
        creator_user_id=row["creator_user_id"],
        status=str(row["status"]),
        reservation_id=reservation,
        requested_search_scope=requested_search_scope_from_row(
            row.get("requested_search_scope")
        ),
        created_at=row.get("created_at"),
    )


def load_query_run_runtime(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
) -> tuple[AuthorizedRuntimeContext, str]:
    """Rebuild authorized runtime and durable user text for resume.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Existing run.

    Returns:
        Authorized context plus the persisted user message.

    Raises:
        QueryAdmissionError: Missing run, foreign run, or missing user input.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.load_query_run_runtime_v3(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("not_found")
    message = row.get("user_message")
    if not isinstance(message, str) or not message:
        raise QueryAdmissionError("input_missing")
    context = AuthorizedRuntimeContext(
        user_id=UUID(caller.user_id),
        role=UserRole(caller.rpc_role()),
        authorization_version=caller.rpc_authorization_version(),
        session_id=caller.session_id,
        conversation_id=row["conversation_id"],
        run_id=row["run_id"],
        reservation_id=row["reservation_id"],
        reconnect=True,
        route_family=Phase6RouteFamily(str(row["route_family"])),
        requested_search_scope=requested_search_scope_from_row(
            row.get("requested_search_scope")
        ),
        deadline_at=row["deadline_at"],
        recursion_limit=int(row["recursion_limit"]),
        correction_ceiling=int(row["correction_ceiling"]),
        subquestion_ceiling=int(row["subquestion_ceiling"]),
        model_call_ceiling=int(row["model_call_ceiling"]),
        tool_ceiling=int(row["tool_ceiling"]),
        discovery_ceiling=int(row["discovery_ceiling"]),
        manifest_ceiling=int(row["manifest_ceiling"]),
        side_effect_ceiling=int(row["side_effect_ceiling"]),
        reserved_amount_usd=Decimal(str(row["reserved_amount_usd"])),
        remaining_usd=Decimal(str(row["remaining_usd"])),
        remaining_prompt_tokens=int(row["remaining_prompt_tokens"]),
        remaining_completion_tokens=int(row["remaining_completion_tokens"]),
        optimistic_version=int(row["optimistic_version"]),
        heartbeat_at=row["heartbeat_at"],
        payload_hash=str(row["request_payload_hash"]),
        status=str(row["status"]),
    )
    return context, message


def list_run_citations(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
) -> tuple[RunCitationRecord, ...]:
    """List citation IDs for an owned run. Passage text is omitted.

    Authorized current chunks overlay page, heading path, and document
    title onto ``provenance``. Unavailable sources omit those locator keys.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Run primary key.

    Returns:
        Citation identifiers and provenance maps.

    Raises:
        QueryAdmissionError: When the run is missing or not owned.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT citation_id, citation_index, chunk_id, provenance,
                       source_unavailable, source_kind, web_source_id,
                       paragraph_index, document_title, pdf_page_number,
                       evidence_excerpt
                FROM app.list_run_citations_v4(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                ),
            )
            rows = cursor.fetchall()
    except psycopg.Error as exc:
        raise_admission(exc)
    records: list[RunCitationRecord] = []
    for row in rows:
        provenance_raw = row.get("provenance")
        provenance: dict[str, object] = (
            cast(dict[str, object], provenance_raw)
            if isinstance(provenance_raw, dict)
            else {}
        )
        chunk = row.get("chunk_id")
        unavailable = bool(row.get("source_unavailable"))
        chunk_id = None if unavailable or chunk is None else UUID(str(chunk))
        web_raw = row.get("web_source_id")
        source_kind = str(row.get("source_kind") or "company_document")
        web_source_id = None if web_raw is None else UUID(str(web_raw))
        records.append(
            RunCitationRecord(
                citation_id=UUID(str(row["citation_id"])),
                citation_index=int(str(row["citation_index"])),
                chunk_id=chunk_id,
                provenance=provenance,
                source_unavailable=unavailable,
                source_kind=source_kind,
                web_source_id=web_source_id,
                paragraph_index=_optional_int(row.get("paragraph_index")),
                document_title=_optional_str(row.get("document_title")),
                pdf_page_number=_optional_int(row.get("pdf_page_number")),
                evidence_excerpt=_optional_str(row.get("evidence_excerpt")),
            )
        )
    return tuple(records)


def list_conversation_citations(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
    run_ids: tuple[UUID, ...],
) -> tuple[tuple[UUID, RunCitationRecord], ...]:
    """Load citations for at most 50 owned run IDs on one conversation.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        conversation_id: Conversation the caller must own.
        run_ids: Candidate run primary keys. Extra IDs are ignored. More than
            50 unique IDs fail closed.

    Returns:
        ``(run_id, citation)`` pairs. Foreign runs are omitted.

    Raises:
        QueryAdmissionError: Authorization or batch-cap failure.
    """

    unique_ids = tuple(dict.fromkeys(run_ids))
    if not unique_ids:
        return ()
    if len(unique_ids) > 50:
        raise QueryAdmissionError("batch_cap")
    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT run_id, citation_id, citation_index, chunk_id, provenance,
                       source_unavailable, source_kind, web_source_id,
                       paragraph_index, document_title, pdf_page_number,
                       evidence_excerpt
                FROM app.list_conversation_citations_v1(
                  %s, %s, %s, %s::uuid, %s::uuid[]
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    str(conversation_id),
                    [str(item) for item in unique_ids],
                ),
            )
            rows = cursor.fetchall()
    except psycopg.Error as exc:
        message = str(exc)
        if "query_memory:" in message:
            raise QueryAdmissionError("not_found") from exc
        if "query_citation:batch_cap" in message:
            raise QueryAdmissionError("batch_cap") from exc
        raise_admission(exc)
    records: list[tuple[UUID, RunCitationRecord]] = []
    for row in rows:
        provenance_raw = row.get("provenance")
        provenance: dict[str, object] = (
            cast(dict[str, object], provenance_raw)
            if isinstance(provenance_raw, dict)
            else {}
        )
        chunk = row.get("chunk_id")
        unavailable = bool(row.get("source_unavailable"))
        chunk_id = None if unavailable or chunk is None else UUID(str(chunk))
        web_raw = row.get("web_source_id")
        source_kind = str(row.get("source_kind") or "company_document")
        web_source_id = None if web_raw is None else UUID(str(web_raw))
        records.append(
            (
                UUID(str(row["run_id"])),
                RunCitationRecord(
                    citation_id=UUID(str(row["citation_id"])),
                    citation_index=int(str(row["citation_index"])),
                    chunk_id=chunk_id,
                    provenance=provenance,
                    source_unavailable=unavailable,
                    source_kind=source_kind,
                    web_source_id=web_source_id,
                    paragraph_index=_optional_int(row.get("paragraph_index")),
                    document_title=_optional_str(row.get("document_title")),
                    pdf_page_number=_optional_int(row.get("pdf_page_number")),
                    evidence_excerpt=_optional_str(row.get("evidence_excerpt")),
                ),
            )
        )
    return tuple(records)


def get_run_citation_detail(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    citation_id: UUID,
) -> RunCitationDetail:
    """Return one owned citation with a bounded ACL-checked excerpt.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Run primary key.
        citation_id: Citation primary key on that run.

    Returns:
        Detail record. Web rows include a validated HTTPS URL only.

    Raises:
        QueryAdmissionError: ``not_found`` for missing, foreign, or
            mismatched citation IDs.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT citation_id, citation_index, chunk_id, provenance,
                       source_unavailable, source_kind, web_source_id,
                       paragraph_index, document_title, pdf_page_number,
                       evidence_excerpt, source_url, document_id, version_id,
                       document_visibility
                FROM app.get_run_citation_detail_v1(%s, %s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                    citation_id,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        message = str(exc)
        if "query_admission:not_found" in message:
            raise QueryAdmissionError("not_found") from exc
        raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("not_found")
    provenance_raw = row.get("provenance")
    provenance: dict[str, object] = (
        cast(dict[str, object], provenance_raw)
        if isinstance(provenance_raw, dict)
        else {}
    )
    unavailable = bool(row.get("source_unavailable"))
    chunk = row.get("chunk_id")
    web_raw = row.get("web_source_id")
    excerpt = _optional_str(row.get("evidence_excerpt"))
    source_url = _optional_str(row.get("source_url"))
    if excerpt is not None and len(excerpt) > 1000:
        excerpt = excerpt[:1000]
    citation = RunCitationRecord(
        citation_id=UUID(str(row["citation_id"])),
        citation_index=int(str(row["citation_index"])),
        chunk_id=None if unavailable or chunk is None else UUID(str(chunk)),
        provenance=provenance,
        source_unavailable=unavailable,
        source_kind=str(row.get("source_kind") or "company_document"),
        web_source_id=None if web_raw is None else UUID(str(web_raw)),
        paragraph_index=_optional_int(row.get("paragraph_index")),
        document_title=_optional_str(row.get("document_title")),
        pdf_page_number=_optional_int(row.get("pdf_page_number")),
        evidence_excerpt=None if unavailable else excerpt,
    )
    document_raw = row.get("document_id")
    version_raw = row.get("version_id")
    return RunCitationDetail(
        citation=citation,
        source_url=None if unavailable else source_url,
        document_id=None if document_raw is None else UUID(str(document_raw)),
        version_id=None if version_raw is None else UUID(str(version_raw)),
        document_visibility=_optional_str(row.get("document_visibility")),
    )


def _optional_int(value: object) -> int | None:
    """Parse a nullable integer column.

    Args:
        value: Driver value.

    Returns:
        Integer or ``None``.
    """

    if value is None:
        return None
    return int(str(value))


def _optional_str(value: object) -> str | None:
    """Parse a nullable text column.

    Args:
        value: Driver value.

    Returns:
        Non-empty string or ``None``.
    """

    if value is None:
        return None
    text = str(value)
    return text if text else None


def summarize_run_usage(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
) -> RunUsageSummary:
    """Return billed token and USD totals for one owned run.

    Args:
        connection: Open ``app_api`` connection on the run-scoped session.
        caller: Server-derived owner.
        run_id: Admitted query run.

    Returns:
        Aggregated ``app.llm_usage`` totals for ``run_id``.

    Raises:
        QueryAdmissionError: When the run is missing, foreign, or the RPC
            rejects the caller.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT cost_usd, prompt_tokens, completion_tokens, usage_rows
                FROM app.summarize_run_usage(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                ),
            )
            row = cursor.fetchone()
            cursor.execute(
                "SELECT app.run_usage_cost_reporting(%s,%s,%s,%s) AS reporting",
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                ),
            )
            reporting_row = cursor.fetchone()
    except psycopg.Error as exc:
        raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("database_rejected")
    reporting = (
        CostReporting.model_validate(reporting_row["reporting"])
        if reporting_row
        else None
    )
    return RunUsageSummary(
        cost_usd=Decimal(str(row["cost_usd"])),
        prompt_tokens=(reporting.measured_prompt_tokens or 0) if reporting else 0,
        completion_tokens=(reporting.measured_completion_tokens or 0)
        if reporting
        else 0,
        usage_rows=int(row["usage_rows"]),
        cost_reporting=reporting,
    )
