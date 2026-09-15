"""Pinned Exa REST contract fixtures against official 2026-09-14 docs."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr
from smart_rag_core.gateways.exa_search import (
    EXA_API_ORIGIN,
    EXA_DOCS_CONTENTS_URL,
    EXA_DOCS_RETRIEVED_DATE,
    EXA_DOCS_SEARCH_URL,
    EXA_OPENAPI_VERSION,
    ExaSearchGateway,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "exa"
FIXTURE_SHA256 = {
    "contents_success.json": (
        "a3678e1b78411c9c170372d39fb0ed06a113c5f349879275c83f4f11d610e06c"
    ),
    "error_error_field.json": (
        "04a49c65dbd3e28ed4e8e89d56aa989c22e8771e5e112f46557d48aea011d084"
    ),
    "error_message_field.json": (
        "5339bd8282677fd08a34242651924d969ae253976ea1928d8b888bf817a65843"
    ),
    "search_success.json": (
        "c5dc6abbb5ce4a2857a7340c72c8982f213404ac1c7f8b2a6091086dd381b19a"
    ),
}


def _sha256(path: Path) -> str:
    """Return the LF-normalized hex digest of a fixture file.

    Git may check the same JSON out with CRLF on Windows. The pin is the
    committed LF bytes so Linux CI and local Windows agree.

    Args:
        path: Fixture path.

    Returns:
        SHA-256 hex digest of LF-normalized bytes.
    """

    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_official_docs_pins_are_current() -> None:
    """Contract tests name the retrieved Exa OpenAPI docs."""

    assert EXA_DOCS_SEARCH_URL == "https://docs.exa.ai/reference/search"
    assert EXA_DOCS_CONTENTS_URL == "https://docs.exa.ai/reference/get-contents"
    assert EXA_OPENAPI_VERSION == "2.0.0"
    assert EXA_DOCS_RETRIEVED_DATE == "2026-09-14"


def test_search_fixture_matches_official_envelope() -> None:
    """The happy-path search fixture keeps requestId, results, and costDollars."""

    payload = json.loads((FIXTURES / "search_success.json").read_text(encoding="utf-8"))
    assert "requestId" in payload
    assert isinstance(payload["results"], list)
    assert payload["results"][0]["url"].startswith("https://")
    assert "costDollars" in payload


def test_contents_fixture_matches_official_envelope() -> None:
    """The contents fixture keeps statuses and per-item text."""

    payload = json.loads(
        (FIXTURES / "contents_success.json").read_text(encoding="utf-8")
    )
    assert payload["statuses"][0]["status"] == "success"
    assert "text" in payload["results"][0]


def test_both_error_envelope_shapes_are_pinned() -> None:
    """Exa documents both ``error`` and ``message`` bodies."""

    error_shape = json.loads(
        (FIXTURES / "error_error_field.json").read_text(encoding="utf-8")
    )
    message_shape = json.loads(
        (FIXTURES / "error_message_field.json").read_text(encoding="utf-8")
    )
    assert "error" in error_shape
    assert "message" in message_shape


def test_search_request_body_matches_documented_fields() -> None:
    """POST /search sends type=auto, moderation, and a 12-result cap."""

    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a mocked Exa HTTP response."""
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        payload = json.loads(
            (FIXTURES / "search_success.json").read_text(encoding="utf-8")
        )
        return httpx.Response(200, json=payload)

    async def _run() -> None:
        """Exercise one mocked gateway call."""
        gateway = ExaSearchGateway(
            api_key=SecretStr("contract-key"),
            transport=httpx.MockTransport(handler),
        )
        try:
            await gateway.search(
                query="Latest research in LLMs",
                remaining_deadline_seconds=5,
                include_text=True,
            )
        finally:
            await gateway.aclose()

    asyncio.run(_run())
    assert captured["url"] == f"{EXA_API_ORIGIN}/search"
    body = captured["body"]
    assert body["type"] == "auto"
    assert body["moderation"] is True
    assert body["numResults"] == 12
    assert body["contents"]["text"]["maxCharacters"] == 8000
    assert body["contents"]["highlights"]["maxCharacters"] == 4000


def test_fixture_hashes_are_stable() -> None:
    """Record SHA-256 of the committed Exa envelopes for evidence."""

    hashes = {path.name: _sha256(path) for path in sorted(FIXTURES.glob("*.json"))}
    assert hashes == FIXTURE_SHA256
