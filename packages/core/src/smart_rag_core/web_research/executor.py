"""Bounded iterative Web research: search, critique, contents, persist, synthesize."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

from smart_rag_core.gateways.exa_search import (
    EXA_MAX_CONTENTS_URLS,
    EXA_MAX_RESULTS,
    ExaContentItem,
    ExaSearchCandidate,
    ExaSearchError,
)
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.web_research.bounds import (
    WEB_MAX_CANDIDATES_PER_ROUND,
    WEB_MAX_EXCERPT_CHARS,
    WEB_MAX_EXTERNAL_OPS,
    WEB_MAX_ROUNDS,
    WEB_MAX_SOURCES,
    WEB_MAX_TOTAL_EXCERPT_CHARS,
    WEB_PROGRESS_READ,
    WEB_PROGRESS_SEARCH,
)
from smart_rag_core.web_research.exceptions import WebResearchError
from smart_rag_core.web_research.heading_coverage import (
    missing_level_references,
    title_mentions_reference,
)
from smart_rag_core.web_research.models import WebSourceRecord
from smart_rag_core.web_research.operations import run_recorded_operation
from smart_rag_core.web_research.planner import bound_formulations
from smart_rag_core.web_research.ports import (
    CancelCheck,
    CandidateFetchPort,
    DeadlineSeconds,
    ProgressEmitter,
    WebOperationStore,
    WebSearchPort,
)
from smart_rag_core.web_research.sanitize import sanitize_exa_query
from smart_rag_core.web_research.synthesis import mock_web_answer

CritiqueFn = Callable[[str, tuple[str, ...]], tuple[str, ...]]
SynthesizeFn = Callable[[str, tuple[WebSourceRecord, ...]], AnswerPayload]


def _hash_request(*parts: str) -> str:
    """SHA-256 a stable operation payload.

    Args:
        *parts: Canonical request fragments. Never secrets.

    Returns:
        Hex digest.
    """

    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _map_exa(exc: ExaSearchError) -> WebResearchError:
    """Preserve typed Exa reasons.

    Args:
        exc: Gateway error.

    Returns:
        Matching ``WebResearchError``.
    """

    try:
        return WebResearchError(exc.reason)
    except ValueError:
        return WebResearchError("web_search_transport_failed")


@dataclass(slots=True)
class WebResearchResult:
    """Persisted sources and a Web-origin answer draft.

    Attributes:
        sources: At most six persisted sources.
        answer: Draft with empty company citations.
        search_count: Provider search calls actually executed.
        contents_count: Provider contents calls executed.
        fetch_count: Crawl-proxy fallback calls executed.
        formulations: Search strings sent (sanitized).
    """

    sources: tuple[WebSourceRecord, ...]
    answer: AnswerPayload
    search_count: int
    contents_count: int
    fetch_count: int
    formulations: tuple[str, ...]
    limitations: tuple[str, ...] = ()


@dataclass(slots=True)
class _Counters:
    """Mutable external-operation and round counters."""

    ops: int = 0
    searches: int = 0
    contents: int = 0
    fetches: int = 0
    rounds: int = 0
    search_queries: list[str] = field(default_factory=list[str])


def run_web_research(
    *,
    user_query: str,
    search: WebSearchPort,
    store: WebOperationStore,
    fetch: CandidateFetchPort | None = None,
    remaining_deadline_seconds: DeadlineSeconds,
    cancel_check: CancelCheck | None = None,
    progress: ProgressEmitter | None = None,
    forbidden_snippets: tuple[str, ...] = (),
    critique: CritiqueFn | None = None,
    synthesize: SynthesizeFn | None = None,
) -> WebResearchResult:
    """Run at most two research rounds and persist sources before synthesis.

    Args:
        user_query: Rewritten user text only. Never memory or company
            passages.
        search: Injected Exa port.
        store: Injected P06-39 persistence.
        fetch: Optional crawl-proxy fallback.
        remaining_deadline_seconds: Remaining envelope seconds.
        cancel_check: Cooperative cancellation. Closes the HTTP client.
        progress: Emits ``web_search`` / ``web_read`` stage keys only.
        forbidden_snippets: Company/memory strings that must not appear
            in the Exa query.
        critique: Returns 0-2 follow-up queries from titles. Default is
            no follow-up.
        synthesize: Builds the Web draft. Default is extractive mock.

    Returns:
        Persisted sources and a Web-origin answer.

    Raises:
        WebResearchError: Typed fail-closed reasons. Never Hybrid-clamps.
        asyncio.CancelledError: Caller cancellation after ``aclose``.
    """

    counters = _Counters()

    def _cancel() -> None:
        """Abort remaining Exa work when the caller cancelled."""

        if cancel_check is not None and cancel_check():
            search.aclose()
            raise WebResearchError("cancelled")

    def _bump() -> None:
        """Consume one external operation slot or fail closed."""

        if counters.ops >= WEB_MAX_EXTERNAL_OPS:
            raise WebResearchError("web_round_exhausted")
        counters.ops += 1

    query = sanitize_exa_query(user_query, forbidden_snippets=forbidden_snippets)
    allowed: set[str] = set()
    candidates_by_url: dict[str, ExaSearchCandidate] = {}

    def _search_one(
        formulation: str,
        key: str,
        *,
        round_index: int,
        time_budget: float | None = None,
    ) -> None:
        """Run one recorded Exa search for a sanitized formulation.

        Args:
            formulation: Sanitized Exa query.
            key: Durable operation key.
            round_index: 1-based research round.
            time_budget: Optional share of the existing run deadline.
        """

        _cancel()
        if round_index > WEB_MAX_ROUNDS:
            raise WebResearchError("web_round_exhausted")
        _bump()
        counters.searches += 1
        counters.rounds = max(counters.rounds, round_index)
        counters.search_queries.append(formulation)
        if progress is not None:
            progress(WEB_PROGRESS_SEARCH)

        def _worker() -> None:
            """Execute one Exa search and merge allow-listed candidates."""

            try:
                response = search.search(
                    query=formulation,
                    remaining_deadline_seconds=min(
                        remaining_deadline_seconds(), time_budget
                    )
                    if time_budget is not None
                    else remaining_deadline_seconds(),
                    num_results=WEB_MAX_CANDIDATES_PER_ROUND,
                )
            except ExaSearchError as orig:
                raise _map_exa(orig) from orig
            for item in response.candidates[:EXA_MAX_RESULTS]:
                allowed.add(item.url)
                candidates_by_url.setdefault(item.url, item)
            allowed.update(response.allowed_urls)

        run_recorded_operation(
            store,
            operation_key=key,
            kind="search",
            request_hash=_hash_request("search", formulation),
            worker=_worker,
        )

    _search_one(query, "search-round-1", round_index=1)
    titles = tuple(item.title for item in candidates_by_url.values() if item.title)
    raw_follow_ups = () if critique is None else critique(query, titles)
    sanitized_follow_ups: list[str] = []
    for item in raw_follow_ups:
        try:
            cleaned = sanitize_exa_query(item, forbidden_snippets=forbidden_snippets)
        except WebResearchError as exc:
            if exc.reason == "company_passage_forbidden":
                raise
            continue
        sanitized_follow_ups.append(cleaned)
    planned = bound_formulations(query, tuple(sanitized_follow_ups))
    extra = planned[1:]
    limitations: list[str] = []
    for index, formulation in enumerate(extra):
        try:
            # Reserve shares for every remaining optional search, reading and
            # synthesis. Optional discovery must not consume the whole run.
            _search_one(
                formulation,
                f"search-round-2-{index}",
                round_index=2,
                time_budget=remaining_deadline_seconds() / (len(extra) - index + 2),
            )
        except WebResearchError as exc:
            if not candidates_by_url or exc.reason not in {
                "web_search_timeout",
                "web_search_transport_failed",
            }:
                raise
            limitations.append(exc.reason)
            break

    urls = tuple(candidates_by_url)[:EXA_MAX_CONTENTS_URLS]
    contents_by_url: dict[str, ExaContentItem] = {}
    if urls:
        _cancel()
        _bump()
        counters.contents += 1
        if progress is not None:
            progress(WEB_PROGRESS_READ)

        def _contents() -> None:
            """Fetch bounded contents for the current allow-listed URLs."""

            try:
                response = search.get_contents(
                    urls=urls,
                    allowed_urls=frozenset(allowed),
                    remaining_deadline_seconds=remaining_deadline_seconds(),
                )
            except ExaSearchError as exc:
                raise _map_exa(exc) from exc
            for item in response.items:
                contents_by_url[item.url] = item

        try:
            run_recorded_operation(
                store,
                operation_key="contents-batch-1",
                kind="contents",
                request_hash=_hash_request("contents", *urls),
                worker=_contents,
            )
        except WebResearchError as exc:
            if exc.reason not in {
                "web_search_timeout",
                "web_search_transport_failed",
                "web_search_invalid_response",
            }:
                raise

    excerpts: list[tuple[str, str, str, str | None]] = []
    total_chars = 0
    missing_levels = missing_level_references(
        query,
        tuple(
            (item.text or "")[:WEB_MAX_EXCERPT_CHARS]
            for item in contents_by_url.values()
        ),
    )
    for url in urls:
        item = contents_by_url.get(url)
        text = (item.text if item is not None else None) or ""
        title = item.title if item is not None else candidates_by_url[url].title
        published = (
            item.published_date
            if item is not None
            else candidates_by_url[url].published_date
        )
        refresh_heading = bool(
            text.strip()
            and title_mentions_reference(title, missing_levels)
            and remaining_deadline_seconds() >= 20.0
        )
        if (
            (not text.strip() or refresh_heading)
            and fetch is not None
            and counters.ops < WEB_MAX_EXTERNAL_OPS
        ):
            _cancel()
            _bump()
            counters.fetches += 1
            if progress is not None:
                progress(WEB_PROGRESS_READ)

            def _fetch(target: str = url) -> str | None:
                """Fetch one allow-listed page through the crawl proxy.

                Args:
                    target: Candidate URL.

                Returns:
                    Extracted text, or None when empty.
                """

                return fetch.fetch_text(target, allowed_urls=frozenset(allowed))

            fetched = run_recorded_operation(
                store,
                operation_key=f"fetch-{len(excerpts)}",
                kind="fetch",
                request_hash=_hash_request("fetch", url),
                worker=_fetch,
            )
            # A failed or unhelpful refresh must preserve the original evidence.
            # Only real page text with better requested-field coverage replaces it.
            if not text.strip():
                text = fetched or ""
            elif fetched:
                refreshed_missing = missing_level_references(
                    query,
                    (
                        *(
                            (entry.text or "")[:WEB_MAX_EXCERPT_CHARS]
                            for entry in contents_by_url.values()
                        ),
                        fetched,
                    ),
                )
                if refreshed_missing < missing_levels:
                    text = fetched
                    missing_levels = refreshed_missing
        excerpt = text.strip()[:WEB_MAX_EXCERPT_CHARS]
        if not excerpt:
            continue
        if total_chars + len(excerpt) > WEB_MAX_TOTAL_EXCERPT_CHARS:
            break
        total_chars += len(excerpt)
        excerpts.append((url, title, excerpt, published))
        if len(excerpts) >= WEB_MAX_SOURCES:
            break

    if not excerpts:
        if urls:
            raise WebResearchError("web_content_unavailable")
        raise WebResearchError("web_evidence_insufficient")

    sources: list[WebSourceRecord] = []
    for index, (url, title, excerpt, published) in enumerate(excerpts):
        sources.append(
            store.insert_source(
                source_index=index,
                url=url,
                title=title,
                excerpt=excerpt,
                published_date=published,
            )
        )
    source_tuple = tuple(sources)
    answer = (
        synthesize(query, source_tuple)
        if synthesize is not None
        else mock_web_answer(query=query, sources=source_tuple)
    )
    if answer.citations or answer.table_citations:
        raise WebResearchError("web_search_invalid_response")
    if limitations and answer.status == "complete":
        answer = answer.model_copy(update={"status": "partial"})
    return WebResearchResult(
        sources=source_tuple,
        answer=answer,
        search_count=counters.searches,
        contents_count=counters.contents,
        fetch_count=counters.fetches,
        formulations=tuple(counters.search_queries),
        limitations=tuple(limitations),
    )
