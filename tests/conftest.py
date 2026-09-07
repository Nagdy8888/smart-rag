"""Shared test defaults that keep runtime settings fail-closed."""

from __future__ import annotations

import pytest
from smart_rag_core.settings.base import setdefault_process_environ

_TEST_SUPABASE_FIXTURE_URL = "http://127.0.0.1:54321"

# ``smart_rag_api.main`` constructs the FastAPI app at import. Pytest
# fixtures run after collection, so collection-time imports fail in CI
# when ``SUPABASE_URL`` is unset. Do not set ``APP_ENV=test`` here:
# CORS and identity tests require the default ``APP_ENV=local``.
setdefault_process_environ("SUPABASE_URL", _TEST_SUPABASE_FIXTURE_URL)
setdefault_process_environ("MOCK_MODEL_MODE", "true")


@pytest.fixture(autouse=True)
def default_mock_model_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit/contract constructors on deterministic mock models.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Side Effects:
        Sets ``MOCK_MODEL_MODE=true`` so a developer ``.env`` with live OpenAI
        cannot change gateway constructors. Hosted-settings tests override
        this per case.
    """

    monkeypatch.setenv("MOCK_MODEL_MODE", "true")


@pytest.fixture(autouse=True)
def explicit_supabase_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supply an explicit synthetic Auth origin for settings loads.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Side Effects:
        Sets ``SUPABASE_URL`` to the offline synthetic origin so
        ``APP_ENV=local`` constructors do not depend on a silent settings
        default. Individual tests may override or delete the variable.
        The origin is never contacted.
    """

    monkeypatch.setenv("SUPABASE_URL", _TEST_SUPABASE_FIXTURE_URL)


@pytest.fixture(autouse=True)
def isolate_host_langsmith_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep constructors on fail-closed LangSmith defaults.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Side Effects:
        Forces ``LANGSMITH_TRACING=false`` and ``LANGSMITH_EXPORT_IO=false``.
        Leftover operator flags from ``.env.compose`` otherwise make
        ``APP_ENV=test`` and hosted settings invalid. Tests that need
        tracing or I/O export set the variables themselves.
    """

    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGSMITH_EXPORT_IO", "false")


@pytest.fixture(autouse=True)
def isolate_unit_session_dsns(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drop hosted session DSNs for unit tests so they cannot open Postgres.

    Args:
        request: Current pytest item; path is used to detect ``tests/unit``.
        monkeypatch: Pytest monkeypatch fixture.

    Side Effects:
        For unit tests only, deletes ``LANGGRAPH_CHECKPOINT_URL``,
        ``LIGHTRAG_DB_URL``, and ``SUPABASE_DB_URL`` when present. Contract
        tests keep an explicit operator ``SUPABASE_DB_URL``. Individual unit
        tests may set fake DSNs.
    """

    if "/tests/unit/" not in request.path.as_posix():
        return
    monkeypatch.delenv("LANGGRAPH_CHECKPOINT_URL", raising=False)
    monkeypatch.delenv("LIGHTRAG_DB_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
