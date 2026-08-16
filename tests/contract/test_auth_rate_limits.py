"""Auth rate-limit ownership contract tests (Phase 2 Packet 4)."""

from __future__ import annotations

import uuid

import pytest
from smart_rag_api.services.auth_rate_limits import (
    AuthRateLimitExceededError,
    check_auth_rate_limit,
)
from smart_rag_core.settings.base import SecretStr

# Documented gate: local tests must not claim hosted Supabase Auth throttling.
LOCAL_AUTH_THROTTLING_PROVEN = False


def test_local_auth_throttling_not_claimed_as_hosted_proof() -> None:
    """Hosted browser-direct Auth throttle proof remains false locally."""

    assert LOCAL_AUTH_THROTTLING_PROVEN is False


@pytest.mark.parametrize("flag_name", ["local_auth_throttling_proven"])
def test_documentation_flag_blocks_hosted_throttle_claim(flag_name: str) -> None:
    """Contract flag name matches ownership doc expectation."""

    assert flag_name == "local_auth_throttling_proven"
    assert LOCAL_AUTH_THROTTLING_PROVEN is False


def test_postgres_degraded_bucket_enforces_limit() -> None:
    """FastAPI Postgres path exhausts invitation-accept bucket."""

    from tests.contract.integration_support import resolve_supabase_db_url, try_connect

    url = resolve_supabase_db_url()
    if try_connect(url) is None:
        pytest.skip(f"Postgres unreachable at {url}")

    bucket = f"invitation-accept:{uuid.uuid4()}"
    postgres = SecretStr(url)
    for _ in range(3):
        decision = check_auth_rate_limit(
            bucket_key=bucket,
            max_attempts=3,
            window_seconds=60,
            postgres_url=postgres,
        )
        assert decision.owner == "fastapi_postgres_degraded"
        assert decision.allowed is True

    with pytest.raises(AuthRateLimitExceededError):
        check_auth_rate_limit(
            bucket_key=bucket,
            max_attempts=3,
            window_seconds=60,
            postgres_url=postgres,
        )


def test_missing_backends_fail_closed() -> None:
    """Sensitive ops fail closed when Postgres URL is absent."""

    from smart_rag_api.services.auth_rate_limits import AuthRateLimitUnavailableError

    with pytest.raises(AuthRateLimitUnavailableError):
        check_auth_rate_limit(
            bucket_key="missing-backend",
            max_attempts=1,
            window_seconds=60,
            postgres_url=None,
        )


def test_valkey_unset_cost_mutation_uses_postgres_not_fail_open() -> None:
    """Valkey unset still requires Postgres; skipping the limiter fails the test."""

    from smart_rag_api.services.auth_rate_limits import (
        AuthRateLimitUnavailableError,
        RateLimitKind,
    )

    with pytest.raises(AuthRateLimitUnavailableError):
        check_auth_rate_limit(
            bucket_key="cost-no-backends",
            max_attempts=3,
            window_seconds=60,
            postgres_url=None,
            valkey_client=None,
            kind=RateLimitKind.COST_MUTATION,
        )


def test_dual_valkey_postgres_outage_fail_closed() -> None:
    """Bound Valkey timeout plus missing Postgres is 503, never allow."""

    from smart_rag_api.services.auth_rate_limits import (
        AuthRateLimitUnavailableError,
        RateLimitKind,
    )
    from smart_rag_core.runtime.valkey import MemoryValkeyClient

    client = MemoryValkeyClient(fail_closed=True)
    with pytest.raises(AuthRateLimitUnavailableError):
        check_auth_rate_limit(
            bucket_key="dual-outage",
            max_attempts=3,
            window_seconds=60,
            postgres_url=None,
            valkey_client=client,
            kind=RateLimitKind.COST_MUTATION,
        )


def test_valkey_fast_path_enforces_ttl_counter() -> None:
    """Valkey INCR+TTL denies the overflowing attempt."""

    from smart_rag_api.services.auth_rate_limits import (
        AuthRateLimitExceededError,
        RateLimitKind,
    )
    from smart_rag_core.runtime.valkey import MemoryValkeyClient

    client = MemoryValkeyClient()
    for _ in range(2):
        decision = check_auth_rate_limit(
            bucket_key="valkey-fast",
            max_attempts=2,
            window_seconds=60,
            postgres_url=None,
            valkey_client=client,
            kind=RateLimitKind.COST_MUTATION,
        )
        assert decision.owner == "fastapi_valkey"
        assert decision.allowed is True
    with pytest.raises(AuthRateLimitExceededError):
        check_auth_rate_limit(
            bucket_key="valkey-fast",
            max_attempts=2,
            window_seconds=60,
            postgres_url=None,
            valkey_client=client,
            kind=RateLimitKind.COST_MUTATION,
        )


def test_low_risk_read_emergency_limiter_is_audited() -> None:
    """Valkey-down reads use the emergency limiter and mark degraded."""

    from smart_rag_api.services.auth_rate_limits import RateLimitKind
    from smart_rag_core.runtime.valkey import MemoryValkeyClient

    flags: list[str] = []
    client = MemoryValkeyClient(fail_closed=True)
    decision = check_auth_rate_limit(
        bucket_key=f"read-{uuid.uuid4()}",
        max_attempts=3,
        window_seconds=60,
        postgres_url=None,
        valkey_client=client,
        kind=RateLimitKind.LOW_RISK_READ,
        on_degraded=lambda: flags.append("rate_limit_degraded"),
    )
    assert decision.degraded is True
    assert decision.owner == "fastapi_emergency"
    assert flags == ["rate_limit_degraded"]
