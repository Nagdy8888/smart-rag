"""Unit tests for the bounded Exa REST gateway."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import threading
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from smart_rag_core.gateways.exa_search import (
    EXA_API_ORIGIN,
    EXA_MAX_RESULTS,
    ExaSearchError,
    ExaSearchGateway,
    ExaSearchResponse,
    create_exa_search_gateway,
)
from smart_rag_core.settings.base import SharedSettings

CANARY_KEY = "exa-unit-canary-key-do-not-log"


def _gateway(handler: Callable[[httpx.Request], httpx.Response]) -> ExaSearchGateway:
    """Build a gateway with a MockTransport.

    Args:
        handler: httpx MockTransport callback.

    Returns:
        Gateway bound to the fixed Exa origin.
    """

    return ExaSearchGateway(
        api_key=SecretStr(CANARY_KEY),
        transport=httpx.MockTransport(handler),
    )


def _success_payload() -> dict[str, Any]:
    """Return a bounded official-shaped search envelope.

    Returns:
        Provider JSON object.
    """

    return {
        "requestId": "b5947044c4b78efa9552a7c89b306d95",
        "results": [
            {
                "title": "A Comprehensive Overview of Large Language Models",
                "url": "https://arxiv.org/pdf/2307.06435.pdf",
                "publishedDate": "2023-11-16T01:36:32.547Z",
                "text": "Abstract " + ("x" * 9000),
                "highlights": ["Such requirements have limited their adoption..."],
                "highlightScores": [0.46],
            }
        ],
        "resolvedSearchType": "neural",
        "searchTime": 120.5,
        "costDollars": {"total": 0.007},
    }


async def _search(gateway: ExaSearchGateway, **kwargs: Any) -> Any:
    """Run search then close the client.

    Args:
        gateway: Exa gateway.
        **kwargs: Extra search arguments.

    Returns:
        Search response.
    """

    try:
        return await gateway.search(
            query="Latest research in LLMs",
            remaining_deadline_seconds=5.0,
            **kwargs,
        )
    finally:
        await gateway.aclose()


def test_constructor_rejects_caller_base_url() -> None:
    """The provider host is a module constant, not a constructor argument."""

    assert "base_url" not in inspect.signature(ExaSearchGateway.__init__).parameters
    assert EXA_API_ORIGIN == "https://api.exa.ai"


def test_canary_key_is_absent_from_repr_and_errors() -> None:
    """Credentials never appear in repr or exception text."""

    gateway = _gateway(lambda request: httpx.Response(200, json=_success_payload()))
    text = repr(gateway) + str(ExaSearchError("web_search_auth_failed"))
    assert CANARY_KEY not in text
    assert "web_search_auth_failed" in repr(ExaSearchError("web_search_auth_failed"))
    asyncio.run(gateway.aclose())


def test_happy_path_returns_bounded_immutable_dtos() -> None:
    """Official-shaped results clamp text and freeze DTOs."""

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        captured.append(request)
        return httpx.Response(200, json=_success_payload())

    gateway = _gateway(handler)
    response = asyncio.run(_search(gateway, include_text=True, num_results=12))
    assert len(response.candidates) == 1
    candidate = response.candidates[0]
    assert candidate.url == "https://arxiv.org/pdf/2307.06435.pdf"
    assert candidate.text is not None
    assert len(candidate.text) == 8000
    assert candidate.highlights == ("Such requirements have limited their adoption...",)
    assert response.metadata.request_id == "b5947044c4b78efa9552a7c89b306d95"
    assert str(response.metadata.cost_dollars) == "0.007"
    body = json.loads(captured[0].content.decode("utf-8"))
    assert body["type"] == "auto"
    assert body["moderation"] is True
    assert body["numResults"] == 12
    assert captured[0].headers["x-api-key"] == CANARY_KEY
    assert str(captured[0].url).startswith(EXA_API_ORIGIN)
    with pytest.raises(ValidationError):
        candidate.title = "mutated"  # type: ignore[misc]


def test_nullable_metadata_is_accepted() -> None:
    """Missing optional provider fields stay None."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        return httpx.Response(
            200,
            json={
                "results": [{"title": None, "url": "https://example.com/a"}],
            },
        )

    response = asyncio.run(_search(_gateway(handler)))
    assert response.candidates[0].title == ""
    assert response.candidates[0].published_date is None
    assert response.metadata.request_id is None
    assert response.metadata.cost_dollars is None


def test_malformed_json_maps_to_invalid_response() -> None:
    """Non-JSON 200 bodies fail closed."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        return httpx.Response(200, content=b"not-json")

    with pytest.raises(ExaSearchError, match="web_search_invalid_response"):
        asyncio.run(_search(_gateway(handler)))


def test_unsupported_url_is_dropped() -> None:
    """Loopback and credentialed URLs never become candidates."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "http://127.0.0.1/secret"},
                    {"url": "https://user:pass@example.com/x"},
                    {"url": "https://example.com/ok"},
                ]
            },
        )

    response = asyncio.run(_search(_gateway(handler)))
    assert [item.url for item in response.candidates] == ["https://example.com/ok"]


def test_too_many_results_are_clamped() -> None:
    """A thirteenth hit is dropped."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        results = [
            {"url": f"https://example.com/r{index}"}
            for index in range(EXA_MAX_RESULTS + 3)
        ]
        return httpx.Response(200, json={"results": results})

    response = asyncio.run(_search(_gateway(handler)))
    assert len(response.candidates) == EXA_MAX_RESULTS


def test_error_envelopes_do_not_leak_into_exceptions() -> None:
    """Both documented error shapes map to status reasons without bodies."""

    def error_handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        return httpx.Response(400, json={"error": "Invalid request"})

    def message_handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        return httpx.Response(402, json={"message": "Payment required"})

    with pytest.raises(ExaSearchError, match="web_search_invalid_response") as invalid:
        asyncio.run(_search(_gateway(error_handler)))
    assert "Invalid request" not in str(invalid.value)

    with pytest.raises(ExaSearchError, match="web_search_quota_exhausted") as quota:
        asyncio.run(_search(_gateway(message_handler)))
    assert "Payment" not in str(quota.value)


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (401, "web_search_auth_failed"),
        (402, "web_search_quota_exhausted"),
        (429, "web_search_rate_limited"),
        (500, "web_search_transport_failed"),
        (503, "web_search_transport_failed"),
    ],
)
def test_status_codes_map_to_stable_reasons(status: int, reason: str) -> None:
    """HTTP statuses map onto the published web_search_* codes."""

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        attempts["count"] += 1
        return httpx.Response(status, json={"error": "nope"})

    with pytest.raises(ExaSearchError, match=reason):
        asyncio.run(_search(_gateway(handler)))
    if status in {429, 503}:
        assert attempts["count"] == 2
    else:
        assert attempts["count"] == 1


def test_connect_failure_retries_once() -> None:
    """A pre-accept connect error retries exactly once."""

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        attempts["count"] += 1
        raise httpx.ConnectError("denied", request=request)

    with pytest.raises(ExaSearchError, match="web_search_transport_failed"):
        asyncio.run(_search(_gateway(handler)))
    assert attempts["count"] == 2


def test_post_send_read_timeout_does_not_retry() -> None:
    """A read timeout after send is not retried."""

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        attempts["count"] += 1
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ExaSearchError, match="web_search_timeout"):
        asyncio.run(_search(_gateway(handler)))
    assert attempts["count"] == 1


def test_exactly_one_retry_on_429_then_success() -> None:
    """429 then 200 uses two attempts and no third."""

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, json={"error": "slow down"})
        return httpx.Response(200, json=_success_payload())

    response = asyncio.run(_search(_gateway(handler)))
    assert len(response.candidates) == 1
    assert attempts["count"] == 2


def test_deadline_exhaustion_sends_no_request() -> None:
    """A non-positive deadline fails before HTTP."""

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        attempts["count"] += 1
        return httpx.Response(200, json=_success_payload())

    gateway = _gateway(handler)
    with pytest.raises(ExaSearchError, match="web_search_timeout"):
        asyncio.run(gateway.search(query="q", remaining_deadline_seconds=0))
    asyncio.run(gateway.aclose())
    assert attempts["count"] == 0


def test_cancellation_is_not_retried() -> None:
    """CancelledError propagates without a second attempt."""

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        attempts["count"] += 1
        raise asyncio.CancelledError

    async def _run() -> None:
        """Run the bounded gateway call under test."""

        gateway = _gateway(handler)
        try:
            await gateway.search(query="q", remaining_deadline_seconds=5)
        finally:
            await gateway.aclose()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_run())
    assert attempts["count"] == 1


def test_get_contents_rejects_urls_outside_allow_list() -> None:
    """Contents may only fetch current-run search URLs."""

    async def _run() -> None:
        """Run the bounded gateway call under test."""

        gateway = _gateway(
            lambda request: httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.com/ok",
                            "text": "hello",
                        }
                    ]
                },
            )
        )
        try:
            with pytest.raises(ExaSearchError, match="web_search_invalid_response"):
                await gateway.get_contents(
                    urls=("https://example.com/other",),
                    allowed_urls=frozenset({"https://example.com/ok"}),
                    remaining_deadline_seconds=5,
                )
        finally:
            await gateway.aclose()

    asyncio.run(_run())


def test_get_contents_happy_path() -> None:
    """Allowed URLs return bounded contents items."""

    async def _run() -> None:
        """Run the bounded gateway call under test."""

        gateway = _gateway(
            lambda request: httpx.Response(
                200,
                json={
                    "requestId": "e492118ccdedcba5088bfc4357a8a125",
                    "results": [
                        {
                            "title": "Page",
                            "url": "https://example.com/ok",
                            "text": "hello",
                            "highlights": ["hello"],
                            "highlightScores": [0.9],
                        }
                    ],
                    "statuses": [{"id": "https://example.com/ok", "status": "success"}],
                },
            )
        )
        try:
            result = await gateway.get_contents(
                urls=("https://example.com/ok",),
                allowed_urls=frozenset({"https://example.com/ok"}),
                remaining_deadline_seconds=5,
            )
        finally:
            await gateway.aclose()
        assert result.items[0].text == "hello"
        assert result.items[0].status == "success"

    asyncio.run(_run())


def test_client_close_prevents_further_requests() -> None:
    """Closing the client prevents further HTTP calls."""

    gateway = _gateway(lambda request: httpx.Response(200, json=_success_payload()))
    asyncio.run(gateway.aclose())
    with pytest.raises(ExaSearchError, match="web_search_transport_failed"):
        asyncio.run(gateway.search(query="q", remaining_deadline_seconds=5))


def test_search_from_worker_thread_while_caller_loop_running() -> None:
    """LangGraph web_scope runs Exa via asyncio.run on a dedicated loop.

    A process-scoped AsyncClient would stay bound to the caller loop and
    raise RuntimeError. Each request must open a client on the running loop.
    """

    gateway = _gateway(lambda request: httpx.Response(200, json=_success_payload()))

    async def _outer() -> None:
        """Drive Exa from an already-running event loop."""

        box: dict[str, object] = {}
        errors: dict[str, BaseException] = {}

        def _worker() -> None:
            """Search Exa on a dedicated worker thread."""

            try:
                box["value"] = asyncio.run(
                    gateway.search(query="q", remaining_deadline_seconds=5)
                )
            except BaseException as exc:
                errors["exc"] = exc

        thread = threading.Thread(target=_worker, name="exa-loop-test", daemon=True)
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert "exc" not in errors, errors.get("exc")
        result = box["value"]
        assert isinstance(result, ExaSearchResponse)
        assert len(result.candidates) == 1
        await gateway.aclose()

    asyncio.run(_outer())


def test_disabled_settings_build_no_live_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WEB_SEARCH_ENABLED=false returns None even when a key is present."""

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    monkeypatch.setenv("EXA_API_KEY", CANARY_KEY)
    settings = SharedSettings()
    assert create_exa_search_gateway(settings) is None


def test_logs_omit_canary_query_and_urls(caplog: pytest.LogCaptureFixture) -> None:
    """Structured extras never include the key, query, or result URL."""

    caplog.set_level(logging.INFO, logger="smart_rag_core.gateways.exa_search")

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one mocked Exa HTTP response.

        Args:
            request: Mock transport request.

        Returns:
            Synthetic HTTP response.
        """

        return httpx.Response(200, json=_success_payload())

    asyncio.run(_search(_gateway(handler)))
    combined = caplog.text + json.dumps(
        [record.__dict__ for record in caplog.records], default=str
    )
    assert CANARY_KEY not in combined
    assert "Latest research" not in combined
    assert "arxiv.org" not in combined
