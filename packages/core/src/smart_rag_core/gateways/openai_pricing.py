"""OpenAI list-price estimates for billed usage rows.

Rates follow https://developers.openai.com/api/docs/pricing for supported models.
GPT-4.1 mini rates were verified 2026-10-22 against its official model page.
Provider invoices remain canonical; these values power Run Details and
``app.llm_usage`` when measured USD is unavailable.
"""

from __future__ import annotations

from decimal import Decimal

_ONE_MILLION = Decimal(1_000_000)

# gpt-4o-mini standard API list price (USD per 1M tokens), verified 2026-08-27.
CHAT_INPUT_USD_PER_MILLION = Decimal("0.15")
CHAT_CACHED_INPUT_USD_PER_MILLION = Decimal("0.075")
CHAT_OUTPUT_USD_PER_MILLION = Decimal("0.60")

# text-embedding-3-large list price (USD per 1M input tokens).
EMBEDDING_INPUT_USD_PER_MILLION = Decimal("0.13")


def estimate_chat_cost_usd(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    cached_prompt_tokens: int = 0,
) -> Decimal:
    """Estimate USD for one chat-style OpenAI call.

    Args:
        prompt_tokens: Total input tokens, including cached tokens.
        completion_tokens: Generated output tokens.
        cached_prompt_tokens: Input tokens billed at the cached-input rate.

    Returns:
        List-price USD estimate rounded to eight decimal places.

    Raises:
        ValueError: If counts are negative or cached input exceeds total input.
    """

    if min(prompt_tokens, completion_tokens, cached_prompt_tokens) < 0:
        raise ValueError("chat_usage_negative")
    if cached_prompt_tokens > prompt_tokens:
        raise ValueError("chat_cached_usage_exceeds_input")
    uncached_prompt_tokens = prompt_tokens - cached_prompt_tokens
    cost = (
        Decimal(uncached_prompt_tokens) * CHAT_INPUT_USD_PER_MILLION
        + Decimal(cached_prompt_tokens) * CHAT_CACHED_INPUT_USD_PER_MILLION
        + Decimal(completion_tokens) * CHAT_OUTPUT_USD_PER_MILLION
    ) / _ONE_MILLION
    return cost.quantize(Decimal("0.00000001"))


def estimate_embedding_cost_usd(*, prompt_tokens: int) -> Decimal:
    """Estimate USD for one embedding batch.

    Args:
        prompt_tokens: Provider-reported prompt tokens for the batch.

    Returns:
        List-price USD estimate rounded to eight decimal places.

    Raises:
        ValueError: If ``prompt_tokens`` is negative.
    """

    if prompt_tokens < 0:
        raise ValueError("embedding_usage_negative")
    cost = Decimal(prompt_tokens) * EMBEDDING_INPUT_USD_PER_MILLION / _ONE_MILLION
    return cost.quantize(Decimal("0.00000001"))


def estimate_usage_cost_usd(
    *,
    usage_kind: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_prompt_tokens: int = 0,
    cache_write_30m_tokens: int = 0,
    cache_write_12h_tokens: int = 0,
    service_tier: str | None = None,
) -> Decimal | None:
    """Estimate USD for one ``app.llm_usage`` row.

    Args:
        usage_kind: Allow-listed usage kind such as ``answer`` or
            ``embedding``.
        model_id: Provider model identifier recorded on the row.
        prompt_tokens: Prompt or input tokens.
        completion_tokens: Completion or output tokens.
        cached_prompt_tokens: Provider-reported cached input.
        cache_write_30m_tokens: Input tokens written with 30-minute retention.
        cache_write_12h_tokens: Input tokens written with 12-hour retention.
        service_tier: Returned processing tier; unknown tiers remain unpriced.

    Returns:
        List-price USD estimate, or None for an unknown model. The caller must
        use its conservative reserved cap instead of another model's rate.
    """

    if (
        min(
            prompt_tokens,
            completion_tokens,
            cached_prompt_tokens,
            cache_write_30m_tokens,
            cache_write_12h_tokens,
        )
        < 0
    ):
        raise ValueError("chat_usage_negative")
    if (
        cached_prompt_tokens + cache_write_30m_tokens + cache_write_12h_tokens
        > prompt_tokens
    ):
        raise ValueError("chat_cached_usage_exceeds_input")
    # GPT-6 Luna Standard text rates verified 2026-10-26 against the official
    # model page. Returned tiers and cache-write lifetimes are priced explicitly; regional premiums are excluded.
    if model_id == "gpt-6-luna" and usage_kind != "embedding":
        input_multiplier = Decimal(2) if prompt_tokens > 272_000 else Decimal(1)
        output_multiplier = Decimal("1.5") if prompt_tokens > 272_000 else Decimal(1)
        tier_multiplier = {
            None: Decimal(1),
            "default": Decimal(1),
            "standard": Decimal(1),
            "flex": Decimal("0.5"),
            "batch": Decimal("0.5"),
            "fast": Decimal(2),
        }.get(service_tier)
        if tier_multiplier is None:
            return None
        total = (
            Decimal(
                prompt_tokens
                - cached_prompt_tokens
                - cache_write_30m_tokens
                - cache_write_12h_tokens
            )
            * Decimal("0.10")
            + Decimal(cached_prompt_tokens) * Decimal("0.01")
            + Decimal(cache_write_30m_tokens) * Decimal("0.125")
            + Decimal(cache_write_12h_tokens) * Decimal("0.25")
        ) * input_multiplier + Decimal(completion_tokens) * Decimal(
            "0.50"
        ) * output_multiplier
        return (total * tier_multiplier / _ONE_MILLION).quantize(Decimal("0.00000001"))
    if (
        service_tier not in {None, "default", "standard"}
        or cache_write_30m_tokens
        or cache_write_12h_tokens
    ):
        return None
    if usage_kind == "embedding":
        if model_id != "text-embedding-3-large":
            return None
        return estimate_embedding_cost_usd(prompt_tokens=prompt_tokens)
    if model_id in {
        "gpt-4.1-mini",
        "gpt-4.1-mini-2025-04-14",
        "gpt-5.4-mini",
    }:
        if min(prompt_tokens, completion_tokens) < 0:
            raise ValueError("chat_usage_negative")
        input_rate, output_rate = (
            (Decimal("0.75"), Decimal("4.50"))
            if model_id == "gpt-5.4-mini"
            else (Decimal("0.40"), Decimal("1.60"))
        )
        return (
            (
                Decimal(prompt_tokens - cached_prompt_tokens) * input_rate
                + Decimal(cached_prompt_tokens)
                * (Decimal("0.075") if model_id == "gpt-5.4-mini" else Decimal("0.10"))
                + Decimal(completion_tokens) * output_rate
            )
            / _ONE_MILLION
        ).quantize(Decimal("0.00000001"))
    if model_id not in {"gpt-4o-mini", "gpt-4o-mini-2024-07-18"}:
        return None
    return estimate_chat_cost_usd(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_prompt_tokens=cached_prompt_tokens,
    )
