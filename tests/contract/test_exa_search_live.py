"""Skip-by-default live Exa search. Never logs keys, queries, or URLs."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import pytest
from pydantic import SecretStr
from smart_rag_core.gateways.exa_search import ExaSearchGateway
from smart_rag_core.release.phase10_constants import PROVIDER_EGRESS_ALLOWLIST_FILE

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = REPO_ROOT / PROVIDER_EGRESS_ALLOWLIST_FILE
LIVE_QUERY = "public large language model overview"


def test_web_search_live_unset_does_not_call_exa() -> None:
    """CI and default developer runs skip live Exa."""

    if os.environ.get("WEB_SEARCH_LIVE") == "1":
        pytest.skip("WEB_SEARCH_LIVE=1; the gated live search runs instead")
    assert os.environ.get("WEB_SEARCH_LIVE", "") != "1"


def test_provider_egress_allowlist_omits_exa() -> None:
    """Managed provider-egress must not include api.exa.ai."""

    text = ALLOWLIST.read_text(encoding="utf-8")
    assert "exa.ai" not in text
    assert "api.exa.ai" not in text


@pytest.mark.skipif(
    os.environ.get("WEB_SEARCH_LIVE") != "1",
    reason="WEB_SEARCH_LIVE unset",
)
def test_exa_search_live_local_only(caplog: pytest.LogCaptureFixture) -> None:
    """One local search when explicitly gated. Bodies and keys stay out of logs.

    Raises:
        ExaSearchError: Mapped provider failure. Message is a reason code only.
    """

    if os.environ.get("APP_ENV") != "local":
        pytest.skip("live Exa requires APP_ENV=local")
    raw = os.environ.get("EXA_API_KEY", "").strip()
    if not raw:
        pytest.skip("EXA_API_KEY unset")
    caplog.set_level(logging.DEBUG)
    gateway = ExaSearchGateway(api_key=SecretStr(raw))

    async def _run() -> int:
        try:
            response = await gateway.search(
                query=LIVE_QUERY,
                remaining_deadline_seconds=20.0,
                num_results=1,
                include_text=False,
            )
        finally:
            await gateway.aclose()
        https_hits = sum(
            1
            for candidate in response.candidates
            if candidate.url.startswith(("https://", "http://"))
        )
        return https_hits

    https_hits = asyncio.run(_run())
    assert https_hits >= 1
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert raw not in joined
    assert LIVE_QUERY not in joined
