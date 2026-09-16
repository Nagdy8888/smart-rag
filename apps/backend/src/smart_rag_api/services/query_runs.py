"""Query-run HTTP service: admit, fetch, cancel, citations. No SSE bodies."""

from __future__ import annotations

from urllib.parse import urlsplit
from uuid import UUID

import psycopg
from pydantic import SecretStr
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.messages import append_query_message
from smart_rag_core.query_admission.service import (
    QueryRunRecord,
    RunCitationDetail,
    RunCitationRecord,
    cancel_query_run,
    fail_query_run,
    get_query_run,
    get_run_citation_detail,
    list_run_citations,
    record_run_restricted_evidence,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.runtime.valkey import ValkeyClient
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.security.untrusted import isolate_untrusted_text
from smart_rag_core.settings.postgres_connect import connect_postgres

from smart_rag_api.services.query_admission import admit_query_run_for_caller

STREAM_PATH_TEMPLATE = "/runs/{run_id}/events"


def escape_run_citation(item: RunCitationRecord) -> RunCitationRecord:
    """HTML-escape provenance, title, and excerpt strings.

    Args:
        item: Citation row from ``list_run_citations``.

    Returns:
        Escaped record. ``source_kind`` and ``web_source_id`` are preserved.
        Excerpt stays on the dedicated field and is never copied into
        ``provenance``.
    """

    provenance = {
        str(key): isolate_untrusted_text(value) if isinstance(value, str) else value
        for key, value in item.provenance.items()
    }
    title = item.document_title
    excerpt = item.evidence_excerpt
    return RunCitationRecord(
        citation_id=item.citation_id,
        citation_index=item.citation_index,
        chunk_id=item.chunk_id,
        provenance=provenance,
        source_unavailable=item.source_unavailable,
        source_kind=item.source_kind,
        web_source_id=item.web_source_id,
        paragraph_index=item.paragraph_index,
        document_title=None if title is None else isolate_untrusted_text(title),
        pdf_page_number=item.pdf_page_number,
        evidence_excerpt=None if excerpt is None else isolate_untrusted_text(excerpt),
    )


def _safe_https_url(url: str | None) -> str | None:
    """Return ``url`` only when it is a fragment-free HTTPS locator.

    Args:
        url: Candidate Web source URL.

    Returns:
        The URL, or ``None`` when the scheme is not HTTPS or the locator
        includes userinfo or a fragment.
    """

    if url is None or url == "":
        return None
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        return None
    if parsed.username or parsed.password or parsed.fragment:
        return None
    if parsed.hostname is None:
        return None
    return url


class QueryRunService:
    """Factory-injected run operations."""

    def __init__(
        self,
        postgres_url: str,
        *,
        valkey_client: ValkeyClient | None = None,
        web_search_enabled: bool = False,
        web_search_configured: bool = False,
    ) -> None:
        """Store DSN, optional limits client, and Web feature flags.

        Args:
            postgres_url: app_api URL.
            valkey_client: FastAPI-owned limits Valkey.
            web_search_enabled: ``WEB_SEARCH_ENABLED`` snapshot. Default false.
            web_search_configured: True when a non-empty Exa key is present.
        """

        self._postgres_url = postgres_url
        self._valkey_client = valkey_client
        self._web_search_enabled = web_search_enabled
        self._web_search_configured = web_search_configured

    def submit_auto_message(
        self,
        caller: CallerContext,
        *,
        conversation_id: UUID,
        idempotency_key: UUID,
        message: str,
        requested_search_scope: RequestedSearchScope,
    ) -> tuple[AuthorizedRuntimeContext, str]:
        """Admit Auto chat. Composite unless forced Web reserves WEB_RESEARCH.

        Args:
            caller: Authenticated caller.
            conversation_id: Conversation the caller must own.
            idempotency_key: Client UUID key.
            message: Untrusted user text (hashed for admission).
            requested_search_scope: Client source preference. Not authorization.

        Returns:
            Authorized context and the packet 6 stream path.

        Raises:
            QueryAdmissionError: Rate, ownership, budget, idempotency, or
                disabled/unconfigured Web.
        """

        if requested_search_scope is RequestedSearchScope.WEB:
            if not self._web_search_enabled:
                raise QueryAdmissionError("web_search_disabled")
            if not self._web_search_configured:
                raise QueryAdmissionError("web_search_unconfigured")
            route_family = Phase6RouteFamily.WEB_RESEARCH
        else:
            route_family = Phase6RouteFamily.COMPOSITE
        result = admit_query_run_for_caller(
            self._postgres_url,
            caller=caller,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            message=message,
            route_family=route_family,
            requested_search_scope=requested_search_scope,
            postgres_rate_limit_url=SecretStr(self._postgres_url),
            valkey_client=self._valkey_client,
        )
        try:
            with connect_postgres(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                append_query_message(
                    connection,
                    caller=caller,
                    conversation_id=conversation_id,
                    run_id=result.context.run_id,
                    role="user",
                    content=message,
                )
                connection.commit()
        except (psycopg.Error, QueryAdmissionError) as exc:
            with connect_postgres(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                try:
                    fail_query_run(
                        connection,
                        caller=caller,
                        run_id=result.context.run_id,
                    )
                    connection.commit()
                except QueryAdmissionError:
                    connection.rollback()
            del exc
            raise QueryAdmissionError("message_persist_failed") from None
        stream_path = STREAM_PATH_TEMPLATE.format(run_id=result.context.run_id)
        return result.context, stream_path

    def get(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
        """Fetch one owned run.

        Args:
            caller: Authenticated caller.
            run_id: Run id.

        Returns:
            Run record.

        Raises:
            QueryAdmissionError: ``not_found`` for missing or foreign runs.
        """

        with connect_postgres(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            return get_query_run(connection, caller=caller, run_id=run_id)

    def cancel(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
        """Cancel one owned run. Not SSE cancel transport.

        Args:
            caller: Authenticated caller.
            run_id: Run id.

        Returns:
            Updated run.

        Raises:
            QueryAdmissionError: Ownership or state failures.
        """

        with connect_postgres(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            record = cancel_query_run(connection, caller=caller, run_id=run_id)
            connection.commit()
        return record

    def citations(
        self, caller: CallerContext, *, run_id: UUID
    ) -> tuple[RunCitationRecord, ...]:
        """Return citation IDs with escaped provenance, title, and excerpt.

        Args:
            caller: Authenticated caller.
            run_id: Run id.

        Returns:
            Citation records. Excerpt is the dedicated ACL-checked field.
            SSE preview remains ID/ordinal metadata only.

        Raises:
            QueryAdmissionError: ``not_found`` for missing or foreign runs.
        """

        with connect_postgres(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            records = list_run_citations(connection, caller=caller, run_id=run_id)
        return tuple(escape_run_citation(item) for item in records)

    def citation_detail(
        self,
        caller: CallerContext,
        *,
        run_id: UUID,
        citation_id: UUID,
    ) -> RunCitationDetail:
        """Return one owned citation with a bounded excerpt.

        Restricted company documents append a restricted-read audit row.
        Web rows require a validated HTTPS URL.

        Args:
            caller: Authenticated caller.
            run_id: Run id.
            citation_id: Citation id on that run.

        Returns:
            Detail record. Excerpt is omitted when unauthorized or unsafe.

        Raises:
            QueryAdmissionError: ``not_found`` for missing or foreign rows.
        """

        with connect_postgres(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            detail = get_run_citation_detail(
                connection,
                caller=caller,
                run_id=run_id,
                citation_id=citation_id,
            )
            citation = escape_run_citation(detail.citation)
            source_url = _safe_https_url(detail.source_url)
            if citation.source_kind == "web" and source_url is None:
                citation = RunCitationRecord(
                    citation_id=citation.citation_id,
                    citation_index=citation.citation_index,
                    chunk_id=citation.chunk_id,
                    provenance=citation.provenance,
                    source_unavailable=True,
                    source_kind=citation.source_kind,
                    web_source_id=citation.web_source_id,
                    paragraph_index=citation.paragraph_index,
                    document_title=citation.document_title,
                    pdf_page_number=citation.pdf_page_number,
                    evidence_excerpt=None,
                )
            if (
                citation.source_kind == "company_document"
                and not citation.source_unavailable
                and citation.evidence_excerpt
                and detail.document_visibility == "restricted"
                and detail.document_id is not None
                and detail.version_id is not None
            ):
                session_id = caller.session_id or str(run_id)
                record_run_restricted_evidence(
                    connection,
                    caller=caller,
                    run_id=run_id,
                    document_id=detail.document_id,
                    version_id=detail.version_id,
                    session_id=session_id,
                    citation_id=citation.citation_id,
                    purpose="preview",
                )
            connection.commit()
        return RunCitationDetail(
            citation=citation,
            source_url=source_url if not citation.source_unavailable else None,
            document_id=detail.document_id,
            version_id=detail.version_id,
            document_visibility=detail.document_visibility,
        )
