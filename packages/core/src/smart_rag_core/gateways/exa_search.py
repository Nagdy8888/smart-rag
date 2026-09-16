"""Bounded Exa REST gateway for local web research.

The provider origin is a module constant. Callers cannot replace the host.
API keys, query text, page bodies, highlights, and result URLs never enter
logs or exception messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Self, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from smart_rag_core.ingestion.crawl.exceptions import CrawlPolicyError
from smart_rag_core.ingestion.crawl.policy import normalize_url
from smart_rag_core.settings.base import SharedSettings

LOGGER = logging.getLogger(__name__)

EXA_API_ORIGIN: Final[str] = "https://api.exa.ai"
EXA_SEARCH_PATH: Final[str] = "/search"
EXA_CONTENTS_PATH: Final[str] = "/contents"
EXA_MAX_RESULTS: Final[int] = 12
EXA_MAX_CONTENTS_URLS: Final[int] = 6
EXA_MAX_TEXT_CHARS: Final[int] = 8000
EXA_MAX_HIGHLIGHT_CHARS: Final[int] = 4000
EXA_MAX_QUERY_CHARS: Final[int] = 512
EXA_MAX_ATTEMPTS: Final[int] = 2
EXA_RETRY_STATUSES: Final[frozenset[int]] = frozenset({429, 502, 503, 504})
EXA_RETRY_BACKOFF_SECONDS: Final[float] = 0.25
EXA_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0
EXA_READ_TIMEOUT_SECONDS: Final[float] = 20.0
EXA_WRITE_TIMEOUT_SECONDS: Final[float] = 10.0
EXA_POOL_TIMEOUT_SECONDS: Final[float] = 5.0
EXA_DOCS_SEARCH_URL: Final[str] = "https://docs.exa.ai/reference/search"
EXA_DOCS_CONTENTS_URL: Final[str] = "https://docs.exa.ai/reference/get-contents"
EXA_OPENAPI_VERSION: Final[str] = "2.0.0"
EXA_DOCS_RETRIEVED_DATE: Final[str] = "2026-09-14"

_WEB_SEARCH_REASONS: Final[frozenset[str]] = frozenset(
    {
        "web_search_disabled",
        "web_search_unconfigured",
        "web_search_auth_failed",
        "web_search_quota_exhausted",
        "web_search_rate_limited",
        "web_search_timeout",
        "web_search_transport_failed",
        "web_search_invalid_response",
    }
)


class ExaSearchError(RuntimeError):
    """Typed Exa failure with one safe machine-readable reason.

    Args:
        reason: Stable ``web_search_*`` code. Never includes keys, queries,
            page text, or result URLs.
    """

    def __init__(self, reason: str) -> None:
        """Store a safe reason code.

        Args:
            reason: One of the stable ``web_search_*`` codes.

        Raises:
            ValueError: If ``reason`` is not a published failure code.
        """

        if reason not in _WEB_SEARCH_REASONS:
            raise ValueError("unsupported_web_search_reason")
        super().__init__(reason)
        self.reason = reason

    def __repr__(self) -> str:
        """Return a key-free representation."""

        return f"ExaSearchError(reason={self.reason!r})"


class ExaSearchCandidate(BaseModel):
    """One bounded search hit after URL policy normalization."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=0, max_length=512)
    url: str = Field(min_length=1, max_length=2048)
    published_date: str | None = Field(default=None, max_length=64)
    text: str | None = Field(default=None, max_length=EXA_MAX_TEXT_CHARS)
    highlights: tuple[str, ...] = Field(default=())
    highlight_scores: tuple[float, ...] = Field(default=())


class ExaProviderMetadata(BaseModel):
    """Safe provider metadata that may be logged as counts and ids."""

    model_config = ConfigDict(frozen=True)

    request_id: str | None = Field(default=None, max_length=128)
    search_time_ms: float | None = Field(default=None, ge=0)
    cost_dollars: Decimal | None = None
    resolved_search_type: str | None = Field(default=None, max_length=64)


class ExaSearchResponse(BaseModel):
    """Immutable search result set with allowed contents URLs."""

    model_config = ConfigDict(frozen=True)

    candidates: tuple[ExaSearchCandidate, ...] = Field(max_length=EXA_MAX_RESULTS)
    allowed_urls: frozenset[str]
    metadata: ExaProviderMetadata


class ExaContentItem(BaseModel):
    """One bounded contents result."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=0, max_length=512)
    url: str = Field(min_length=1, max_length=2048)
    published_date: str | None = Field(default=None, max_length=64)
    text: str | None = Field(default=None, max_length=EXA_MAX_TEXT_CHARS)
    highlights: tuple[str, ...] = Field(default=())
    highlight_scores: tuple[float, ...] = Field(default=())
    status: str | None = Field(default=None, max_length=64)


class ExaContentsResponse(BaseModel):
    """Immutable contents batch."""

    model_config = ConfigDict(frozen=True)

    items: tuple[ExaContentItem, ...] = Field(max_length=EXA_MAX_CONTENTS_URLS)
    metadata: ExaProviderMetadata


def _clamp_text(value: object, *, limit: int) -> str | None:
    """Return a truncated string or ``None``.

    Args:
        value: Provider field.
        limit: Inclusive character cap.

    Returns:
        Clamped text, or ``None`` when missing/blank.
    """

    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:limit]


def _mapping(value: object) -> dict[str, object] | None:
    """Return a string-keyed mapping when ``value`` is a dict.

    Args:
        value: Decoded JSON value.

    Returns:
        A ``dict[str, object]`` or ``None``.
    """

    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value)


def _object_list(value: object) -> list[object]:
    """Return a typed object list when ``value`` is a list.

    Args:
        value: Decoded JSON value.

    Returns:
        A ``list[object]``, possibly empty.
    """

    if not isinstance(value, list):
        return []
    return cast(list[object], value)


def _clamp_highlights(value: object) -> tuple[str, ...]:
    """Clamp highlight strings.

    Args:
        value: Provider highlight list.

    Returns:
        Bounded highlight tuple.
    """

    highlights: list[str] = []
    for item in _object_list(value)[:12]:
        clamped = _clamp_text(item, limit=EXA_MAX_HIGHLIGHT_CHARS)
        if clamped is not None:
            highlights.append(clamped)
    return tuple(highlights)


def _clamp_scores(value: object, *, count: int) -> tuple[float, ...]:
    """Clamp highlight scores to the highlight count.

    Args:
        value: Provider score list.
        count: Number of kept highlights.

    Returns:
        Bounded float tuple.
    """

    if not isinstance(value, list) or count <= 0:
        return ()
    scores: list[float] = []
    for item in cast(list[object], value)[:count]:
        if not isinstance(item, (int, float, str, Decimal)):
            continue
        try:
            scores.append(float(item))
        except (TypeError, ValueError, InvalidOperation):
            continue
    return tuple(scores)


def _parse_cost(payload: object) -> Decimal | None:
    """Parse ``costDollars.total`` when present.

    Args:
        payload: Provider JSON object.

    Returns:
        Non-negative Decimal or ``None``.
    """

    mapped = _mapping(payload)
    if mapped is None:
        return None
    cost = _mapping(mapped.get("costDollars"))
    if cost is None:
        return None
    total = cost.get("total")
    try:
        parsed = Decimal(str(total))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _parse_metadata(payload: dict[str, object]) -> ExaProviderMetadata:
    """Extract loggable metadata from a provider envelope.

    Args:
        payload: Decoded JSON object.

    Returns:
        Frozen metadata. Missing fields stay ``None``.
    """

    request_id = payload.get("requestId")
    request_id_text = request_id.strip()[:128] if isinstance(request_id, str) else None
    search_time = payload.get("searchTime")
    search_time_ms: float | None = None
    if isinstance(search_time, (int, float, str, Decimal)):
        try:
            parsed_time = float(search_time)
        except (TypeError, ValueError, InvalidOperation):
            parsed_time = None
        if parsed_time is not None and parsed_time >= 0:
            search_time_ms = parsed_time
    resolved = payload.get("resolvedSearchType") or payload.get("searchType")
    resolved_text = resolved.strip()[:64] if isinstance(resolved, str) else None
    return ExaProviderMetadata(
        request_id=request_id_text or None,
        search_time_ms=search_time_ms,
        cost_dollars=_parse_cost(payload),
        resolved_search_type=resolved_text,
    )


def _normalize_result_url(raw: object) -> str | None:
    """Normalize one provider URL through crawl policy.

    Args:
        raw: Provider URL field.

    Returns:
        Canonical HTTP(S) URL, or ``None`` when rejected.
    """

    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return normalize_url(raw.strip()).normalized
    except CrawlPolicyError:
        return None


def _reason_for_status(status_code: int) -> str:
    """Map an HTTP status to a stable web-search reason.

    Args:
        status_code: Provider status.

    Returns:
        ``web_search_*`` reason.
    """

    if status_code in {401, 403}:
        return "web_search_auth_failed"
    if status_code == 402:
        return "web_search_quota_exhausted"
    if status_code == 429:
        return "web_search_rate_limited"
    if status_code == 408:
        return "web_search_timeout"
    if status_code in {400, 422}:
        return "web_search_invalid_response"
    return "web_search_transport_failed"


def _log_event(
    event: str,
    *,
    request_id: str | None,
    status_code: int | None,
    attempt: int,
    result_count: int | None,
    elapsed_ms: int,
    cost: Decimal | None,
) -> None:
    """Emit a content-free Exa log line.

    Args:
        event: Stable event key.
        request_id: Provider request id when known.
        status_code: HTTP status when known.
        attempt: 1-based attempt number.
        result_count: Result count when known.
        elapsed_ms: Elapsed milliseconds.
        cost: Reported USD total when known.
    """

    LOGGER.info(
        event,
        extra={
            "event": event,
            "exa_request_id": request_id,
            "status_code": status_code,
            "attempt": attempt,
            "result_count": result_count,
            "elapsed_ms": elapsed_ms,
            "reported_cost": str(cost) if cost is not None else None,
        },
    )


class ExaSearchGateway:
    """Async Exa REST client with one retry and a fixed origin.

    Each HTTP call opens an ``httpx.AsyncClient`` on the running loop.
    LangGraph ``web_scope`` invokes search from ``asyncio.run`` in a
    worker thread; a process-scoped client would stay bound to uvicorn's
    loop and fail closed as ``web_search_transport_failed``.

    Args:
        api_key: Server-only Exa credential.
        transport: Optional httpx transport for tests.
        timeout: Optional timeout override. Must fit inside the caller
            deadline at request time.
    """

    def __init__(
        self,
        *,
        api_key: SecretStr,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        """Store credential and transport. Clients are opened per request.

        Args:
            api_key: ``EXA_API_KEY``. Stored as ``SecretStr``.
            transport: Injected MockTransport or default network transport.
            timeout: Explicit connect/read/write/pool timeouts.

        Raises:
            ExaSearchError: If the credential is empty.
        """

        secret = api_key.get_secret_value().strip()
        if not secret:
            raise ExaSearchError("web_search_unconfigured")
        self._api_key = api_key
        self._transport = transport
        self._closed = False
        self._timeout = timeout or httpx.Timeout(
            connect=EXA_CONNECT_TIMEOUT_SECONDS,
            read=EXA_READ_TIMEOUT_SECONDS,
            write=EXA_WRITE_TIMEOUT_SECONDS,
            pool=EXA_POOL_TIMEOUT_SECONDS,
        )

    def _open_client(self, *, timeout: httpx.Timeout) -> httpx.AsyncClient:
        """Open one client bound to the current running loop.

        Args:
            timeout: Per-attempt timeout clamped to the remaining deadline.

        Returns:
            A new ``AsyncClient`` targeting ``https://api.exa.ai``.
        """

        return httpx.AsyncClient(
            base_url=EXA_API_ORIGIN,
            timeout=timeout,
            transport=self._transport,
            headers={"Accept": "application/json"},
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )

    def __repr__(self) -> str:
        """Return a credential-free representation."""

        return f"ExaSearchGateway(origin={EXA_API_ORIGIN!r})"

    async def __aenter__(self) -> Self:
        """Enter the async context.

        Returns:
            This gateway.
        """

        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Close the HTTP client."""

        await self.aclose()

    async def aclose(self) -> None:
        """Mark the gateway closed so later requests fail without HTTP.

        Side Effects:
            Further ``search`` / ``get_contents`` calls raise
            ``web_search_transport_failed``. Per-request clients are closed
            by their own context managers.
        """

        self._closed = True

    async def search(
        self,
        *,
        query: str,
        remaining_deadline_seconds: float,
        num_results: int = EXA_MAX_RESULTS,
        include_text: bool = False,
    ) -> ExaSearchResponse:
        """POST ``/search`` with ``type=auto`` and moderation.

        Args:
            query: Rewritten user text only. Truncated to 512 characters.
            remaining_deadline_seconds: Caller's remaining run deadline.
            num_results: Requested hit count, clamped to 1-12.
            include_text: When true, request bounded text and highlights.

        Returns:
            Immutable candidates plus allowed contents URLs.

        Raises:
            ExaSearchError: Mapped provider, policy, timeout, or schema
                failure.
            asyncio.CancelledError: Caller cancellation. Not retried.
        """

        if remaining_deadline_seconds <= 0:
            raise ExaSearchError("web_search_timeout")
        cleaned = query.strip()[:EXA_MAX_QUERY_CHARS]
        if not cleaned:
            raise ExaSearchError("web_search_invalid_response")
        clamped_results = max(1, min(int(num_results), EXA_MAX_RESULTS))
        body: dict[str, Any] = {
            "query": cleaned,
            "type": "auto",
            "numResults": clamped_results,
            "moderation": True,
        }
        if include_text:
            body["contents"] = {
                "text": {
                    "maxCharacters": EXA_MAX_TEXT_CHARS,
                    "includeHtmlTags": False,
                },
                "highlights": {"maxCharacters": EXA_MAX_HIGHLIGHT_CHARS},
            }
        payload = await self._post_json(
            EXA_SEARCH_PATH,
            body,
            remaining_deadline_seconds=remaining_deadline_seconds,
            event="exa_search",
        )
        results_obj = payload.get("results")
        if not isinstance(results_obj, list):
            raise ExaSearchError("web_search_invalid_response")
        candidates: list[ExaSearchCandidate] = []
        allowed: list[str] = []
        for raw_item in cast(list[object], results_obj)[:EXA_MAX_RESULTS]:
            raw = _mapping(raw_item)
            if raw is None:
                continue
            url = _normalize_result_url(raw.get("url"))
            if url is None:
                continue
            highlights = _clamp_highlights(raw.get("highlights"))
            title = _clamp_text(raw.get("title"), limit=512) or ""
            published = _clamp_text(raw.get("publishedDate"), limit=64)
            candidates.append(
                ExaSearchCandidate(
                    title=title,
                    url=url,
                    published_date=published,
                    text=_clamp_text(raw.get("text"), limit=EXA_MAX_TEXT_CHARS),
                    highlights=highlights,
                    highlight_scores=_clamp_scores(
                        raw.get("highlightScores"), count=len(highlights)
                    ),
                )
            )
            allowed.append(url)
        metadata = _parse_metadata(payload)
        _log_event(
            "exa_search_complete",
            request_id=metadata.request_id,
            status_code=200,
            attempt=1,
            result_count=len(candidates),
            elapsed_ms=0,
            cost=metadata.cost_dollars,
        )
        return ExaSearchResponse(
            candidates=tuple(candidates),
            allowed_urls=frozenset(allowed),
            metadata=metadata,
        )

    async def get_contents(
        self,
        *,
        urls: tuple[str, ...],
        allowed_urls: frozenset[str],
        remaining_deadline_seconds: float,
    ) -> ExaContentsResponse:
        """POST ``/contents`` for current-run search URLs only.

        Args:
            urls: Unique HTTP(S) URLs, at most six.
            allowed_urls: URLs returned by this run's Exa search.
            remaining_deadline_seconds: Remaining run deadline.

        Returns:
            Immutable contents items.

        Raises:
            ExaSearchError: If any URL is outside the allow-list, malformed,
                or the provider fails.
            asyncio.CancelledError: Caller cancellation.
        """

        if remaining_deadline_seconds <= 0:
            raise ExaSearchError("web_search_timeout")
        unique: list[str] = []
        seen: set[str] = set()
        for raw in urls:
            normalized = _normalize_result_url(raw)
            if normalized is None:
                raise ExaSearchError("web_search_invalid_response")
            if normalized not in allowed_urls:
                raise ExaSearchError("web_search_invalid_response")
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
            if len(unique) > EXA_MAX_CONTENTS_URLS:
                raise ExaSearchError("web_search_invalid_response")
        if not unique:
            raise ExaSearchError("web_search_invalid_response")
        body = {
            "urls": unique,
            "text": {
                "maxCharacters": EXA_MAX_TEXT_CHARS,
                "includeHtmlTags": False,
            },
            "highlights": {"maxCharacters": EXA_MAX_HIGHLIGHT_CHARS},
        }
        payload = await self._post_json(
            EXA_CONTENTS_PATH,
            body,
            remaining_deadline_seconds=remaining_deadline_seconds,
            event="exa_contents",
        )
        results_obj = payload.get("results")
        if not isinstance(results_obj, list):
            raise ExaSearchError("web_search_invalid_response")
        statuses_by_url: dict[str, str] = {}
        raw_statuses = payload.get("statuses")
        if isinstance(raw_statuses, list):
            for status_item in cast(list[object], raw_statuses):
                status_map = _mapping(status_item)
                if status_map is None:
                    continue
                status_url = _normalize_result_url(
                    status_map.get("id") or status_map.get("url")
                )
                status = status_map.get("status")
                if status_url and isinstance(status, str):
                    statuses_by_url[status_url] = status[:64]
        items: list[ExaContentItem] = []
        for raw_item in cast(list[object], results_obj)[:EXA_MAX_CONTENTS_URLS]:
            raw = _mapping(raw_item)
            if raw is None:
                continue
            url = _normalize_result_url(raw.get("url"))
            if url is None or url not in allowed_urls:
                continue
            highlights = _clamp_highlights(raw.get("highlights"))
            items.append(
                ExaContentItem(
                    title=_clamp_text(raw.get("title"), limit=512) or "",
                    url=url,
                    published_date=_clamp_text(raw.get("publishedDate"), limit=64),
                    text=_clamp_text(raw.get("text"), limit=EXA_MAX_TEXT_CHARS),
                    highlights=highlights,
                    highlight_scores=_clamp_scores(
                        raw.get("highlightScores"), count=len(highlights)
                    ),
                    status=statuses_by_url.get(url),
                )
            )
        metadata = _parse_metadata(payload)
        _log_event(
            "exa_contents_complete",
            request_id=metadata.request_id,
            status_code=200,
            attempt=1,
            result_count=len(items),
            elapsed_ms=0,
            cost=metadata.cost_dollars,
        )
        return ExaContentsResponse(items=tuple(items), metadata=metadata)

    async def _post_json(
        self,
        path: str,
        body: dict[str, Any],
        *,
        remaining_deadline_seconds: float,
        event: str,
    ) -> dict[str, object]:
        """POST JSON to the fixed Exa origin with one allowed retry.

        Args:
            path: ``/search`` or ``/contents``.
            body: Request JSON. Never logged.
            remaining_deadline_seconds: Remaining deadline.
            event: Log event prefix.

        Returns:
            Decoded JSON object.

        Raises:
            ExaSearchError: Mapped HTTP, transport, timeout, or schema error.
            asyncio.CancelledError: Caller cancellation.
        """

        if self._closed:
            raise ExaSearchError("web_search_transport_failed")
        deadline = time.monotonic() + remaining_deadline_seconds
        last_reason = "web_search_transport_failed"
        for attempt in range(1, EXA_MAX_ATTEMPTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ExaSearchError("web_search_timeout")
            timeout = httpx.Timeout(
                connect=min(EXA_CONNECT_TIMEOUT_SECONDS, remaining),
                read=min(EXA_READ_TIMEOUT_SECONDS, remaining),
                write=min(EXA_WRITE_TIMEOUT_SECONDS, remaining),
                pool=min(EXA_POOL_TIMEOUT_SECONDS, remaining),
            )
            started = time.monotonic()
            try:
                async with self._open_client(timeout=self._timeout) as client:
                    try:
                        response = await client.post(
                            path,
                            json=body,
                            headers={"x-api-key": self._api_key.get_secret_value()},
                            timeout=timeout,
                        )
                    except asyncio.CancelledError:
                        raise
                    except RuntimeError:
                        last_reason = "web_search_transport_failed"
                        raise ExaSearchError(last_reason) from None
                    except httpx.ConnectError:
                        last_reason = "web_search_transport_failed"
                        elapsed_ms = int((time.monotonic() - started) * 1000)
                        _log_event(
                            f"{event}_connect_failed",
                            request_id=None,
                            status_code=None,
                            attempt=attempt,
                            result_count=None,
                            elapsed_ms=elapsed_ms,
                            cost=None,
                        )
                        if attempt < EXA_MAX_ATTEMPTS and _retry_fits(deadline):
                            await asyncio.sleep(EXA_RETRY_BACKOFF_SECONDS)
                            continue
                        raise ExaSearchError(last_reason) from None
                    except httpx.ConnectTimeout:
                        last_reason = "web_search_timeout"
                        if attempt < EXA_MAX_ATTEMPTS and _retry_fits(deadline):
                            await asyncio.sleep(EXA_RETRY_BACKOFF_SECONDS)
                            continue
                        raise ExaSearchError("web_search_timeout") from None
                    except httpx.ReadTimeout:
                        raise ExaSearchError("web_search_timeout") from None
                    except httpx.TimeoutException:
                        raise ExaSearchError("web_search_timeout") from None
                    except httpx.HTTPError:
                        raise ExaSearchError("web_search_transport_failed") from None

                    elapsed_ms = int((time.monotonic() - started) * 1000)
                    status = response.status_code
                    if status == 200:
                        try:
                            decoded: object = response.json()
                        except json.JSONDecodeError as exc:
                            raise ExaSearchError("web_search_invalid_response") from exc
                        mapped = _mapping(decoded)
                        if mapped is None:
                            raise ExaSearchError("web_search_invalid_response")
                        return mapped
                    last_reason = _reason_for_status(status)
                    _log_event(
                        f"{event}_http_error",
                        request_id=None,
                        status_code=status,
                        attempt=attempt,
                        result_count=None,
                        elapsed_ms=elapsed_ms,
                        cost=None,
                    )
                    if (
                        status in EXA_RETRY_STATUSES
                        and attempt < EXA_MAX_ATTEMPTS
                        and _retry_fits(deadline)
                    ):
                        await asyncio.sleep(EXA_RETRY_BACKOFF_SECONDS)
                        continue
                    raise ExaSearchError(last_reason)
            except ExaSearchError:
                raise
        raise ExaSearchError(last_reason)


def _retry_fits(deadline: float) -> bool:
    """Return whether the fixed backoff still fits in the deadline.

    Args:
        deadline: Monotonic deadline.

    Returns:
        True when sleeping ``EXA_RETRY_BACKOFF_SECONDS`` leaves time to send.
    """

    return (deadline - time.monotonic()) > EXA_RETRY_BACKOFF_SECONDS


def create_exa_search_gateway(
    settings: SharedSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ExaSearchGateway | None:
    """Build a live Exa gateway only when Web research is enabled.

    Args:
        settings: Validated deployable settings.
        transport: Optional test transport. Never used to change origin.

    Returns:
        ``None`` when ``WEB_SEARCH_ENABLED`` is false. Otherwise a gateway
        bound to ``https://api.exa.ai``.

    Raises:
        ExaSearchError: If enabled without a usable ``EXA_API_KEY``.
    """

    if not settings.web_search_enabled:
        return None
    secret = settings.exa_api_key
    if secret is None or not secret.get_secret_value().strip():
        raise ExaSearchError("web_search_unconfigured")
    return ExaSearchGateway(api_key=secret, transport=transport)
