"""Capture provider counters before parsing application output.

A mutable, attempt-local collector survives copied async/thread contexts. It
contains counters only, never prompts, answers, or credentials.
"""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True)
class ProviderUsage:
    """Validated counters returned by a single provider response."""

    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    service_tier: str | None
    cache_write_30m_tokens: int | None = None
    cache_write_12h_tokens: int | None = None


_collector: ContextVar[list[ProviderUsage] | None] = ContextVar(
    "provider_usage_collector", default=None
)


@contextmanager
def capture_provider_usage() -> Generator[list[ProviderUsage]]:
    """Isolate one counted attempt, including failures after receiving usage."""
    collected: list[ProviderUsage] = []
    token = _collector.set(collected)
    try:
        yield collected
    finally:
        _collector.reset(token)


def observe_provider_response(response: object, *, embedding: bool = False) -> None:
    """Capture valid provider counters before status or JSON validation.

    Missing or malformed usage remains unknown rather than becoming zero.
    Reasoning tokens are already included in output_tokens.
    """
    collected = _collector.get()
    if collected is None:
        return
    usage = getattr(response, "usage", None)
    prompt = getattr(usage, "prompt_tokens" if embedding else "input_tokens", None)
    output = 0 if embedding else getattr(usage, "output_tokens", None)
    details = getattr(usage, "input_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0)
    written = getattr(details, "cache_write_tokens", 0)
    if (
        not isinstance(prompt, int)
        or isinstance(prompt, bool)
        or not isinstance(output, int)
        or isinstance(output, bool)
        or not isinstance(cached, int)
        or isinstance(cached, bool)
        or not isinstance(written, int)
        or isinstance(written, bool)
        or min(prompt, output, cached, written) < 0
    ):
        return
    if cached + written > prompt:
        return
    total = getattr(usage, "total_tokens", prompt + output)
    if type(total) is not int or total != prompt + output:
        return
    tier = getattr(response, "service_tier", None)
    lifetimes = getattr(details, "cache_write_tokens_details", None)
    # SDK versions predating these fields retain the nested extra as a dict.
    # Attribute-only access discards valid counters and prices a successful
    # call as an unresolved safety allowance.
    if isinstance(lifetimes, Mapping):
        fields = cast(Mapping[str, object], lifetimes)
        short = fields.get("ttl_30m_tokens", 0 if not written else None)
        long = fields.get("ttl_12h_tokens", 0 if not written else None)
    else:
        short = getattr(lifetimes, "ttl_30m_tokens", 0 if not written else None)
        long = getattr(lifetimes, "ttl_12h_tokens", 0 if not written else None)
    if (
        type(short) is not int
        or type(long) is not int
        or min(short, long) < 0
        or short + long != written
    ):
        short = long = None
    collected.append(ProviderUsage(prompt, output, cached, written, tier, short, long))
