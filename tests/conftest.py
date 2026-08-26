"""Shared test defaults that keep runtime settings fail-closed."""

from __future__ import annotations

import pytest

_TEST_SUPABASE_FIXTURE_URL = "http://127.0.0.1:54321"


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
