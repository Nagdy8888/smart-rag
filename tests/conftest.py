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
    """Supply an explicit fixture Auth origin for settings loads.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Side Effects:
        Sets ``SUPABASE_URL`` to the local test-fixture origin so
        ``APP_ENV=local`` constructors do not depend on a silent settings
        default. Individual tests may override or delete the variable.
    """

    monkeypatch.setenv("SUPABASE_URL", _TEST_SUPABASE_FIXTURE_URL)
