"""Public-Web intent and privacy-risk detectors for knowledge-scope routing."""

from __future__ import annotations

import re

_WEB_PHRASES = (
    "search the web",
    "search online",
    "search the internet",
    "look online",
    "look on the web",
    "look it up online",
    "on the internet",
    "from the web",
    "google this",
    "latest news",
    "latest headlines",
)
_TIME_SENSITIVE_WEB = re.compile(
    r"(?i)\b("
    r"today'?s\s+news|breaking\s+news|current\s+events|"
    r"today'?s\s+weather|current\s+weather|live\s+score|"
    r"stock\s+price\s+today|who\s+won\s+(last\s+night|today|yesterday)"
    r")\b"
)
_PRIVATE_HOST = re.compile(
    r"(?i)\b("
    r"localhost|127\.0\.0\.1|0\.0\.0\.0|::1|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
    r")\b"
)
_SECRETISH = re.compile(
    r"(?i)("
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b|"
    r"\bsk-[A-Za-z0-9]{16,}\b|"
    r"\bBearer\s+[A-Za-z0-9._\-]+|"
    r"X-Amz-Signature=|"
    r"/storage/v1/object/sign/|"
    r"[?&](token|sig|signature)=[A-Za-z0-9%\-_]{16,}"
    r")"
)


def has_web_intent(query: str) -> bool:
    """Return whether the query has explicit or time-sensitive public-Web intent.

    Isolated words such as ``latest`` or ``policy`` are not Web by themselves.

    Args:
        query: Original user text.

    Returns:
        True for explicit Web phrases or clearly time-sensitive public asks.
    """

    lowered = query.lower()
    if any(phrase in lowered for phrase in _WEB_PHRASES):
        return True
    return _TIME_SENSITIVE_WEB.search(query) is not None


def has_web_privacy_risk(query: str) -> bool:
    """Return whether the message must not be sent to a public Web provider.

    Args:
        query: Original user text.

    Returns:
        True for loopback/private hosts, JWTs, signed URLs, or secret-like
        tokens. Company source IDs are handled by ``has_company_phrase``.
    """

    return (
        _PRIVATE_HOST.search(query) is not None or _SECRETISH.search(query) is not None
    )
