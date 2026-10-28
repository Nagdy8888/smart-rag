"""Bounded Web research graph: rounds, fail-closed ops, verifier, progress."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from smart_rag_core.gateways.exa_search import (
    ExaContentItem,
    ExaContentsResponse,
    ExaProviderMetadata,
    ExaSearchCandidate,
    ExaSearchError,
    ExaSearchResponse,
)
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.models import AnswerPayload, AtomicLink
from smart_rag_core.query_fusion import fusion_config_hash
from smart_rag_core.query_fusion.models import FusionAlgorithm, FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.web_research.bounds import (
    WEB_MAX_ROUNDS,
    WEB_PROGRESS_READ,
    WEB_PROGRESS_SEARCH,
)
from smart_rag_core.web_research.exceptions import WebResearchError
from smart_rag_core.web_research.executor import run_web_research
from smart_rag_core.web_research.fetch import CrawlProxyCandidateFetch
from smart_rag_core.web_research.models import (
    WebCitation,
    WebOperationState,
    WebSourceRecord,
)
from smart_rag_core.web_research.policy import excerpt_sha256
from smart_rag_core.web_research.sanitize import sanitize_exa_query
from smart_rag_core.web_research.synthesis import citations_from_persisted_ids

_META = ExaProviderMetadata()
_PAGE = "https://example.com/news"
_PAGE_B = "https://example.org/update"
_EXCERPT = "Public agencies published the latest rainfall totals this morning."


@pytest.mark.parametrize(
    "reason", ["web_search_timeout", "web_search_transport_failed"]
)
def test_optional_search_failure_keeps_first_search_evidence(reason: str) -> None:
    """A failed optional search cannot discard valid candidates or the read budget."""
    budgets: list[float] = []

    class OptionalFailure(FakeSearch):
        """Succeed once, then simulate the recorded follow-up failure."""

        def search(
            self, *, query: str, remaining_deadline_seconds: float, num_results: int
        ) -> ExaSearchResponse:
            """Record budgets and fail only the second planned search."""
            budgets.append(remaining_deadline_seconds)
            if self.queries:
                raise ExaSearchError(reason)
            return super().search(
                query=query,
                remaining_deadline_seconds=remaining_deadline_seconds,
                num_results=num_results,
            )

    store = FakeStore()
    result = run_web_research(
        allow_mock=True,
        user_query="Search the web for public rainfall totals",
        search=OptionalFailure(),
        store=store,
        critique=lambda _query, _titles: ("public rainfall regional totals",),
        remaining_deadline_seconds=lambda: 40.0,
    )
    assert len(budgets) == result.search_count == 2
    assert budgets[1] <= budgets[0] / 2
    assert result.contents_count == 1
    assert result.sources == tuple(store.sources)
    assert result.answer.status == "partial"
    assert result.answer.web_citations
    assert result.limitations == (reason,)


def _candidate(url: str, title: str = "News") -> ExaSearchCandidate:
    """Build one search hit."""

    return ExaSearchCandidate(title=title, url=url)


def _content(url: str, text: str | None) -> ExaContentItem:
    """Build one contents item."""

    return ExaContentItem(title="News", url=url, text=text)


@dataclass
class FakeSearch:
    """Recording Exa port."""

    queries: list[str] = field(default_factory=list[str])
    closed: bool = False
    search_error: str | None = None
    contents_text: dict[str, str | None] = field(default_factory=dict[str, str | None])
    contents_error: str | None = None

    def search(
        self,
        *,
        query: str,
        remaining_deadline_seconds: float,
        num_results: int,
    ) -> ExaSearchResponse:
        """Record the sanitized query."""

        del remaining_deadline_seconds, num_results
        if "secret" in query.lower() or "sk-" in query:
            raise AssertionError("secret leaked to exa")
        if "<<untrusted" in query:
            raise AssertionError("company passage leaked to exa")
        if self.search_error:
            raise ExaSearchError(self.search_error)
        self.queries.append(query)
        hits = (_candidate(_PAGE), _candidate(_PAGE_B))
        return ExaSearchResponse(
            candidates=hits,
            allowed_urls=frozenset(item.url for item in hits),
            metadata=_META,
        )

    def get_contents(
        self,
        *,
        urls: tuple[str, ...],
        allowed_urls: frozenset[str],
        remaining_deadline_seconds: float,
    ) -> ExaContentsResponse:
        """Return configured texts for allow-listed URLs."""

        del remaining_deadline_seconds
        if self.contents_error:
            raise ExaSearchError(self.contents_error)
        items: list[ExaContentItem] = []
        for url in urls:
            if url not in allowed_urls:
                raise ExaSearchError("web_search_invalid_response")
            text = self.contents_text.get(url, _EXCERPT)
            items.append(_content(url, text))
        return ExaContentsResponse(items=tuple(items), metadata=_META)

    def aclose(self) -> None:
        """Mark the client closed."""

        self.closed = True


@dataclass
class FakeStore:
    """In-memory operation store."""

    begins: int = 0
    sent: int = 0
    completed: int = 0
    sources: list[WebSourceRecord] = field(default_factory=list[WebSourceRecord])
    ambiguous_on_sent: bool = False
    force_status: str = "planned"

    def begin(
        self,
        *,
        operation_key: str,
        kind: str,
        request_hash: str,
    ) -> WebOperationState:
        """Begin a planned operation."""

        del operation_key, kind, request_hash
        self.begins += 1
        return WebOperationState(
            operation_id=str(uuid4()),
            status=self.force_status,  # type: ignore[arg-type]
            replayed=False,
        )

    def mark_sent(self, *, operation_id: str) -> WebOperationState:
        """Mark sent or ambiguous."""

        self.sent += 1
        status = "ambiguous" if self.ambiguous_on_sent else "sent"
        return WebOperationState(operation_id=operation_id, status=status, attempts=1)

    def complete(
        self,
        *,
        operation_id: str,
        ok: bool,
        failure_reason: str | None = None,
    ) -> WebOperationState:
        """Complete the operation."""

        del ok, failure_reason
        self.completed += 1
        return WebOperationState(operation_id=operation_id, status="succeeded")

    def insert_source(
        self,
        *,
        source_index: int,
        url: str,
        title: str,
        excerpt: str,
        published_date: str | None = None,
    ) -> WebSourceRecord:
        """Persist a fake source."""

        record = WebSourceRecord(
            web_source_id=str(uuid4()),
            source_index=source_index,
            url=url,
            title=title,
            excerpt=excerpt,
            content_hash=excerpt_sha256(excerpt),
            published_date=published_date,
        )
        self.sources.append(record)
        return record


@dataclass
class FakeFetch:
    """Recording crawl-proxy fallback."""

    urls: list[str] = field(default_factory=list[str])
    text: str = "Fallback excerpt from the candidate page."

    def fetch_text(
        self,
        url: str,
        *,
        allowed_urls: frozenset[str],
        remaining_deadline_seconds: float | None = None,
    ) -> str | None:
        """Fetch only allow-listed URLs."""

        if url not in allowed_urls:
            raise WebResearchError("web_search_invalid_response")
        self.urls.append(url)
        return self.text


def test_two_round_happy_path_caps_sources_and_empty_company_citations() -> None:
    """Follow-up search stays in round two and company citations stay empty."""

    search = FakeSearch()
    store = FakeStore()
    critique_calls: list[int] = []

    def _critique(query: str, titles: tuple[str, ...]) -> tuple[str, ...]:
        """Return bounded follow-up Web formulations.

        Args:
            query: Sanitized user query.
            titles: Candidate titles.

        Returns:
            Follow-up formulations.
        """

        del query, titles
        critique_calls.append(1)
        return ("latest rainfall totals", "follow up weather desks")

    result = run_web_research(
        allow_mock=True,
        user_query="search the web for latest rainfall totals",
        search=search,
        store=store,
        remaining_deadline_seconds=lambda: 40.0,
        critique=_critique,
    )
    assert len(critique_calls) == 1
    assert result.search_count == 3
    assert max(1, result.search_count - 1) <= WEB_MAX_ROUNDS
    assert len(result.sources) <= 6
    assert len(result.answer.web_citations) <= 12
    assert result.answer.citations == ()
    assert result.answer.table_citations == ()
    assert result.answer.answer_origin is KnowledgeScope.WEB
    assert "latest rainfall totals" in search.queries[0]


def test_third_round_never_attempted() -> None:
    """Critique runs once; a fourth formulation is never searched."""

    search = FakeSearch()
    store = FakeStore()

    def _critique(query: str, titles: tuple[str, ...]) -> tuple[str, ...]:
        """Return bounded follow-up Web formulations.

        Args:
            query: Sanitized user query.
            titles: Candidate titles.

        Returns:
            Follow-up formulations.
        """

        del query, titles
        return ("follow-a", "follow-b", "follow-c", "follow-d")

    result = run_web_research(
        allow_mock=True,
        user_query="search the web for latest news",
        search=search,
        store=store,
        remaining_deadline_seconds=lambda: 40.0,
        critique=_critique,
    )
    assert result.search_count == 3
    assert "follow-c" not in search.queries
    assert "follow-d" not in search.queries


@pytest.mark.parametrize(
    "reason",
    (
        "web_search_quota_exhausted",
        "web_search_auth_failed",
        "web_search_timeout",
    ),
)
def test_provider_failures_map_to_typed_codes(reason: str) -> None:
    """Quota, auth, and timeout stay typed."""

    search = FakeSearch(search_error=reason)
    with pytest.raises(WebResearchError, match=reason):
        run_web_research(
            allow_mock=True,
            user_query="search the web for latest news",
            search=search,
            store=FakeStore(),
            remaining_deadline_seconds=lambda: 40.0,
        )


def test_ambiguous_operation_does_not_retry() -> None:
    """Ambiguous sent rows fail closed without a second provider call."""

    search = FakeSearch()
    store = FakeStore(ambiguous_on_sent=True)
    with pytest.raises(WebResearchError, match="web_operation:ambiguous"):
        run_web_research(
            allow_mock=True,
            user_query="search the web for latest news",
            search=search,
            store=store,
            remaining_deadline_seconds=lambda: 40.0,
        )
    assert store.sent == 1
    assert search.queries == []


def test_company_passage_never_sent_to_exa() -> None:
    """Company passage markers never enter the Exa query."""

    search = FakeSearch()
    passage = "Internal refund policy chunk_id=aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    with pytest.raises(WebResearchError, match="company_passage_forbidden"):
        run_web_research(
            allow_mock=True,
            user_query=f"search the web <<untrusted-source>> {passage}",
            search=search,
            store=FakeStore(),
            remaining_deadline_seconds=lambda: 40.0,
            forbidden_snippets=(passage,),
        )
    assert search.queries == []


def test_sanitize_strips_email_uuid_jwt() -> None:
    """Emails, UUIDs, and JWTs are stripped before Exa."""

    raw = (
        "search the web for news user@example.com "
        "11111111-1111-4111-8111-111111111111 "
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaaaaaaaaa.bbbbbbbbbb"
    )
    cleaned = sanitize_exa_query(raw)
    assert "user@example.com" not in cleaned
    assert "11111111-1111-4111-8111-111111111111" not in cleaned
    assert "eyJ" not in cleaned
    assert "search the web for news" in cleaned


def test_crawl_proxy_not_called_for_non_candidate() -> None:
    """Fallback fetch refuses URLs Exa did not return."""

    fetch = FakeFetch()
    with pytest.raises(WebResearchError, match="web_search_invalid_response"):
        fetch.fetch_text(
            "https://evil.example/not-a-hit", allowed_urls=frozenset({_PAGE})
        )
    assert fetch.urls == []
    proxy = CrawlProxyCandidateFetch.__new__(CrawlProxyCandidateFetch)
    with pytest.raises(WebResearchError, match="web_search_invalid_response"):
        proxy.fetch_text(
            "https://evil.example/not-a-hit", allowed_urls=frozenset({_PAGE})
        )


def test_crawl_fallback_only_for_exa_failed_candidate() -> None:
    """Empty Exa contents may fetch the same candidate URL."""

    search = FakeSearch(contents_text={_PAGE: None, _PAGE_B: None})
    fetch = FakeFetch()
    result = run_web_research(
        allow_mock=True,
        user_query="search the web for latest news",
        search=search,
        store=FakeStore(),
        fetch=fetch,
        remaining_deadline_seconds=lambda: 40.0,
    )
    assert fetch.urls
    assert set(fetch.urls) <= {_PAGE, _PAGE_B}
    assert result.fetch_count >= 1
    assert result.sources


def test_cancellation_closes_client_without_leaking_key() -> None:
    """Cancel closes the HTTP client and omits the key from repr."""

    search = FakeSearch()
    cancelled = True
    with pytest.raises(WebResearchError, match="cancelled"):
        run_web_research(
            allow_mock=True,
            user_query="search the web for latest news",
            search=search,
            store=FakeStore(),
            remaining_deadline_seconds=lambda: 40.0,
            cancel_check=lambda: cancelled,
        )
    assert search.closed is True
    assert "sk-" not in repr(search)
    assert "api_key" not in repr(search).lower()


def test_progress_payloads_omit_query_and_bodies() -> None:
    """Progress stages are keys only."""

    stages: list[str] = []
    run_web_research(
        allow_mock=True,
        user_query="search the web for latest news",
        search=FakeSearch(),
        store=FakeStore(),
        remaining_deadline_seconds=lambda: 40.0,
        progress=stages.append,
    )
    assert WEB_PROGRESS_SEARCH in stages
    assert WEB_PROGRESS_READ in stages
    assert all(item in {WEB_PROGRESS_SEARCH, WEB_PROGRESS_READ} for item in stages)


def test_verifier_rejects_invented_ids_and_non_contained_spans() -> None:
    """Invented source ids and non-substrings are dropped."""

    source = WebSourceRecord(
        web_source_id="11111111-1111-4111-8111-111111111111",
        source_index=0,
        url=_PAGE,
        title="News",
        excerpt=_EXCERPT,
        content_hash=excerpt_sha256(_EXCERPT),
    )
    kept = citations_from_persisted_ids(
        sources=(source,),
        claimed_ids=(
            "11111111-1111-4111-8111-111111111111",
            "99999999-9999-4999-8999-999999999999",
        ),
        spans=(_EXCERPT[:20], "not in the excerpt"),
    )
    assert len(kept) == 1
    assert kept[0].web_source_id == source.web_source_id
    payload = AnswerPayload(
        answer_text=_EXCERPT,
        web_citations=(
            WebCitation(web_source_id=source.web_source_id, span=_EXCERPT[:20]),
            WebCitation(
                web_source_id="99999999-9999-4999-8999-999999999999",
                span="nope",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim=_EXCERPT[:20],
                web_source_ids=(source.web_source_id,),
            ),
        ),
        answer_origin=KnowledgeScope.WEB,
    )
    checked, failures = deterministic_check_answer(
        payload,
        fusion=FusionResult(
            algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
            config_hash=fusion_config_hash(FusionAlgorithm.RESOLVED_PATH_FUSION),
            requested_route="web_research",
            effective_route="web_research",
            evidence=(),
            graph_discovered_only_ratio=0.0,
        ),
        tables=(),
        evidence_required=False,
        web_excerpts={source.web_source_id: source.excerpt},
    )
    assert checked.citations == ()
    assert len(checked.web_citations) == 1
    assert "invented_web_source" in failures or "web_span_not_contained" in failures


def test_empty_contents_without_fetch_is_content_unavailable() -> None:
    """Candidate URLs with empty Exa text fail closed when fetch is unbound."""

    search = FakeSearch(contents_text={_PAGE: None, _PAGE_B: None})
    with pytest.raises(WebResearchError, match="web_content_unavailable"):
        run_web_research(
            allow_mock=True,
            user_query="search the web for latest news",
            search=search,
            store=FakeStore(),
            remaining_deadline_seconds=lambda: 40.0,
        )


def test_follow_up_company_passage_never_searched() -> None:
    """Critique follow-ups that carry company markers fail closed."""

    search = FakeSearch()

    def _critique(query: str, titles: tuple[str, ...]) -> tuple[str, ...]:
        """Return bounded follow-up Web formulations.

        Args:
            query: Sanitized user query.
            titles: Candidate titles.

        Returns:
            Follow-up formulations.
        """

        del query, titles
        return ("latest news chunk_id=aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",)

    with pytest.raises(WebResearchError, match="company_passage_forbidden"):
        run_web_research(
            allow_mock=True,
            user_query="search the web for latest news",
            search=search,
            store=FakeStore(),
            remaining_deadline_seconds=lambda: 40.0,
            critique=_critique,
        )
    assert search.queries == ["search the web for latest news"]


def test_web_scope_disabled_never_drafts() -> None:
    """Disabled Web at the node is typed fail-closed, not a general answer."""

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.nodes.web_scope import web_scope_node
    from smart_rag_agents.query.state import pending_query_state

    state = pending_query_state(user_query="search the web for latest news")
    state["status"] = "planned"
    disabled = web_scope_node(state, QueryGraphDeps(web_search_enabled=False))
    assert disabled["status"] == "routing_rejected"
    assert disabled["detail"] == "web_search_disabled"
    assert disabled["answer"] is None
    unconfigured = web_scope_node(
        state,
        QueryGraphDeps(web_search_enabled=True, web_search_configured=False),
    )
    assert unconfigured["status"] == "routing_rejected"
    assert unconfigured["detail"] == "web_search_unconfigured"
    assert unconfigured["answer"] is None


def test_current_user_turn_is_not_a_forbidden_web_snippet() -> None:
    """The just-admitted user message must not block public Exa search."""

    from smart_rag_agents.query.nodes.web_scope import forbidden_web_memory_snippets
    from smart_rag_agents.query.state import pending_query_state

    query = "What is the Exa search API according to public documentation?"
    state = pending_query_state(user_query=query)
    state["memory_records"] = [
        {"content": query, "role": "user"},
        {"content": "Our refund period is thirty calendar days.", "role": "assistant"},
    ]
    snippets = forbidden_web_memory_snippets(state)
    assert query not in snippets
    assert "Our refund period is thirty calendar days." in snippets


def test_verify_answer_node_web_refuses_without_accounted_verifier() -> None:
    """Web verification is excerpt-bound and never calls the fusion verifier."""

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.nodes.verify import verify_answer_node
    from smart_rag_agents.query.state import pending_query_state
    from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
    from smart_rag_core.query_routing.models import (
        BranchKind,
        BranchSpec,
        RetrievalPlan,
    )

    class _MustNotCallVerifier:
        """Gateway that must stay unused on the Web path."""

        async def generate_verifier(self, request: object) -> object:
            """Fail if the model verifier runs."""

            del request
            raise AssertionError("web path must not call model verifier")

    source = WebSourceRecord(
        web_source_id="11111111-1111-4111-8111-111111111111",
        source_index=0,
        url=_PAGE,
        title="News",
        excerpt=_EXCERPT,
        content_hash=excerpt_sha256(_EXCERPT),
    )
    plan = RetrievalPlan(
        requested_route=Phase6RouteFamily.WEB_RESEARCH,
        effective_route=Phase6RouteFamily.WEB_RESEARCH,
        branches=(
            BranchSpec(
                branch_id="web-1",
                kind=BranchKind.WEB_RESEARCH,
                family=Phase6RouteFamily.WEB_RESEARCH,
                query_text="search the web for latest news",
                parallel_group=0,
            ),
        ),
        company_claim_forbidden=True,
        knowledge_scope=KnowledgeScope.WEB,
    )
    payload = AnswerPayload(
        answer_text=_EXCERPT,
        citations=(),
        web_citations=(
            WebCitation(web_source_id=source.web_source_id, span=_EXCERPT[:20]),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim=_EXCERPT[:20],
                web_source_ids=(source.web_source_id,),
            ),
        ),
        answer_origin=KnowledgeScope.WEB,
    )
    state = pending_query_state(user_query="search the web for latest news")
    state["status"] = "answered"
    state["remaining_model_calls"] = 5
    state["retrieval_plan"] = plan.model_dump(mode="json")
    state["answer"] = payload.model_dump(mode="json")
    state["web_sources"] = [source.model_dump(mode="json")]
    verified = verify_answer_node(
        state,
        QueryGraphDeps(
            model_gateway=_MustNotCallVerifier(),
            verifier_prompt_text="unused",
        ),
    )
    assert verified["status"] == "refused"
    answer = AnswerPayload.model_validate(verified["answer"])
    assert not answer.web_citations


def test_empty_search_urls_are_evidence_insufficient() -> None:
    """Zero normalized Exa URLs fail closed as insufficient evidence."""

    @dataclass
    class _EmptySearch(FakeSearch):
        """Search port that never returns candidates."""

        def search(
            self,
            *,
            query: str,
            remaining_deadline_seconds: float,
            num_results: int,
        ) -> ExaSearchResponse:
            """Return an empty candidate set.

            Args:
                query: Sanitized query.
                remaining_deadline_seconds: Remaining deadline.
                num_results: Requested hit count.

            Returns:
                Empty Exa search response.
            """

            del remaining_deadline_seconds, num_results
            self.queries.append(query)
            return ExaSearchResponse(
                candidates=(),
                allowed_urls=frozenset(),
                metadata=_META,
            )

    with pytest.raises(WebResearchError, match="web_evidence_insufficient"):
        run_web_research(
            allow_mock=True,
            user_query="search the web for latest news",
            search=_EmptySearch(),
            store=FakeStore(),
            remaining_deadline_seconds=lambda: 40.0,
        )


def test_web_scope_missing_runtime_is_not_unconfigured() -> None:
    """Missing DB/runtime context must not reuse the Exa-key detail."""

    from pydantic import SecretStr
    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.nodes.web_scope import web_scope_node
    from smart_rag_agents.query.state import pending_query_state
    from smart_rag_core.gateways.exa_search import ExaSearchGateway

    state = pending_query_state(user_query="search the web for latest news")
    state["status"] = "planned"
    gateway = ExaSearchGateway(api_key=SecretStr("test-exa-key-not-used"))
    missing_runtime = web_scope_node(
        state,
        QueryGraphDeps(
            web_search_enabled=True,
            web_search_configured=True,
            exa_search_gateway=gateway,
            connection=None,
        ),
    )
    assert missing_runtime["status"] == "routing_rejected"
    assert missing_runtime["detail"] == "web_runtime_unavailable"
    assert missing_runtime["answer"] is None


def test_synthesize_web_answer_drops_invented_ids() -> None:
    """Gateway synthesis keeps only persisted Web source IDs and spans."""

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.gateway.web_answer import synthesize_web_answer
    from smart_rag_core.gateways.model import WebAnswerModelResponse

    source = WebSourceRecord(
        web_source_id="11111111-1111-4111-8111-111111111111",
        source_index=0,
        url=_PAGE,
        title="News",
        excerpt=_EXCERPT,
        content_hash=excerpt_sha256(_EXCERPT),
    )

    class _Gateway:
        """Fixture gateway that invents one extra citation id."""

        async def generate_web_answer(self, request: object) -> WebAnswerModelResponse:
            """Return one valid and one invented citation.

            Args:
                request: Web-answer request.

            Returns:
                Structured fixture payload.
            """

            del request
            return WebAnswerModelResponse(
                mode="mock",
                payload={
                    "answer_text": _EXCERPT[:40],
                    "status": "complete",
                    "web_citations": [
                        {
                            "web_source_id": source.web_source_id,
                            "span": _EXCERPT[:20],
                        },
                        {
                            "web_source_id": "99999999-9999-4999-8999-999999999999",
                            "span": "not present",
                        },
                    ],
                    "atomic_links": [
                        {
                            "link_id": "l1",
                            "claim": _EXCERPT[:20],
                            "web_source_ids": [source.web_source_id],
                        },
                        {
                            "link_id": "l2",
                            "claim": "invented claim",
                            "web_source_ids": ["99999999-9999-4999-8999-999999999999"],
                        },
                    ],
                },
                request_id="fixture-web",
                input_tokens=1,
                output_tokens=1,
            )

    payload = synthesize_web_answer(
        QueryGraphDeps(
            model_gateway=_Gateway(),
            web_answer_prompt_text="web_answer fixture prompt",
        ),
        query="search the web for latest news",
        sources=(source,),
        context=None,
    )
    assert payload.answer_origin is KnowledgeScope.WEB
    assert payload.citations == ()
    assert payload.table_citations == ()
    assert len(payload.web_citations) == 1
    assert payload.web_citations[0].web_source_id == source.web_source_id
    assert len(payload.atomic_links) == 1
    assert payload.atomic_links[0].web_source_ids == (source.web_source_id,)


def test_synthesize_web_answer_never_mocks_provider_error() -> None:
    """Provider failures degrade to extractive mock, not Hybrid."""

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.gateway.web_answer import synthesize_web_answer

    source = WebSourceRecord(
        web_source_id="11111111-1111-4111-8111-111111111111",
        source_index=0,
        url=_PAGE,
        title="News",
        excerpt=_EXCERPT,
        content_hash=excerpt_sha256(_EXCERPT),
    )

    class _BoomGateway:
        """Gateway that always fails the Web-answer call."""

        async def generate_web_answer(self, request: object) -> object:
            """Raise before returning a payload.

            Args:
                request: Web-answer request.

            Raises:
                RuntimeError: Always.
            """

            del request
            raise RuntimeError("provider down")

    from smart_rag_core.query_answer.exceptions import AnswerError

    with pytest.raises(AnswerError):
        synthesize_web_answer(
            QueryGraphDeps(
                model_gateway=_BoomGateway(), web_answer_prompt_text="fixture"
            ),
            query="search the web for latest news",
            sources=(source,),
            context=None,
        )


def test_run_web_research_uses_injected_synthesize() -> None:
    """Executor prefers the injected synthesize callable over extractive mock."""

    search = FakeSearch()
    called: list[int] = []

    def _synthesize(query: str, sources: tuple[WebSourceRecord, ...]) -> AnswerPayload:
        """Record invocation and return a grounded Web draft.

        Args:
            query: Sanitized query.
            sources: Persisted sources.

        Returns:
            Complete Web answer.
        """

        del query
        called.append(len(sources))
        source = sources[0]
        span = source.excerpt[:20]
        return AnswerPayload(
            answer_text="Synthesized public web answer.",
            citations=(),
            web_citations=(WebCitation(web_source_id=source.web_source_id, span=span),),
            atomic_links=(
                AtomicLink(
                    link_id="web-1",
                    claim=span,
                    web_source_ids=(source.web_source_id,),
                ),
            ),
            table_citations=(),
            status="complete",
            answer_origin=KnowledgeScope.WEB,
        )

    result = run_web_research(
        allow_mock=True,
        user_query="search the web for latest news",
        search=search,
        store=FakeStore(),
        remaining_deadline_seconds=lambda: 40.0,
        synthesize=_synthesize,
    )
    assert called == [len(result.sources)]
    assert result.answer.answer_text == "Synthesized public web answer."
    assert result.answer.answer_origin is KnowledgeScope.WEB


@pytest.mark.parametrize("remaining", [40.0, 5.0])
@pytest.mark.parametrize("recovered", [True, False])
def test_missing_requested_heading_refresh_preserves_evidence(
    remaining: float, recovered: bool
) -> None:
    """Only the missing criterion gets a bounded, allow-listed page refresh."""
    from smart_rag_core.web_research.fetch import html_to_excerpt

    class CriterionSearch(FakeSearch):
        """Provider text omits a heading on the second comparison source."""

        def get_contents(self, **kwargs: object) -> ExaContentsResponse:
            """Return a complete first criterion and a body-only second one."""
            return ExaContentsResponse(
                items=(
                    ExaContentItem(
                        url=_PAGE,
                        title="Criterion 3.1.7",
                        text="3.1.7 (Level AA) Minimum 24 pixels.",
                    ),
                    ExaContentItem(
                        url=_PAGE_B,
                        title="Criterion 3.1.9",
                        text="3.1.9 Target size. Minimum 44 pixels.",
                    ),
                ),
                metadata=_META,
            )

    original = "3.1.9 Target size. Minimum 44 pixels."
    fetched = (
        html_to_excerpt(
            b"<h1>3.1.9 Target size (Level AAA)</h1><p>Minimum 44 pixels.</p>"
        )
        if recovered
        else "Page unavailable."
    )
    fetch = FakeFetch(text=fetched)
    result = run_web_research(
        allow_mock=True,
        user_query="Compare 3.1.7 and 3.1.9 target sizes and conformance levels",
        search=CriterionSearch(),
        store=FakeStore(),
        fetch=fetch,
        critique=lambda _query, _titles: (
            "criterion comparison sources",
            "criterion size levels",
        ),
        remaining_deadline_seconds=lambda: remaining,
    )
    assert result.search_count + result.contents_count + result.fetch_count <= 5
    assert fetch.urls == ([_PAGE_B] if remaining >= 20 else [])
    assert result.sources[0].excerpt == "3.1.7 (Level AA) Minimum 24 pixels."
    assert result.sources[1].excerpt == (
        fetched if recovered and remaining >= 20 else original
    )


def test_level_coverage_does_not_borrow_a_different_criterion() -> None:
    """Neighbouring numbered headings cannot fill the requested level field."""
    from smart_rag_core.web_research.heading_coverage import missing_level_references

    assert missing_level_references(
        "Compare conformance levels of 3.1.7 and 3.1.9",
        ("3.1.7 target size. 3.1.9 (Level AAA)",),
    ) == frozenset({"3.1.7"})
    assert not missing_level_references("Explain 3.1.7", ("3.1.7 text",))
