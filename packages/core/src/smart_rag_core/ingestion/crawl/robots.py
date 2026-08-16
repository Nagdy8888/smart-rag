"""RFC 9309 robots.txt evaluation after security checks."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from smart_rag_core.ingestion.crawl.exceptions import CrawlPolicyError
from smart_rag_core.ingestion.crawl.policy import NormalizedUrl


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    """Outcome of robots policy evaluation for one URL."""

    allowed: bool
    robots_url: str
    reason: str
    crawl_delay: float | None = None


def evaluate_robots(
    robots_body: str,
    robots_url: str,
    target: NormalizedUrl,
    *,
    user_agent: str = "SmartRagCrawler/1.0",
) -> RobotsDecision:
    """Evaluate whether ``target`` may be fetched per robots.txt content.

    Args:
        robots_body: Raw robots.txt bytes decoded as UTF-8 with errors replaced.
        robots_url: Canonical robots URL used for relative rule resolution.
        target: Normalized page URL under test.
        user_agent: Crawler user agent token.

    Returns:
        Allow/deny decision with safe diagnostics.

    Raises:
        CrawlPolicyError: When robots content is unusable (fail closed).
    """

    parser = RobotFileParser()
    parser.parse(robots_body.splitlines())
    allowed = parser.can_fetch(user_agent, target.normalized)
    delay = _crawl_delay_seconds(parser, user_agent)
    if not allowed:
        return RobotsDecision(
            allowed=False,
            robots_url=robots_url,
            reason="robots_disallow",
            crawl_delay=delay,
        )
    return RobotsDecision(
        allowed=True,
        robots_url=robots_url,
        reason="robots_allow",
        crawl_delay=delay,
    )


def robots_url_for(origin: NormalizedUrl) -> str:
    """Build the robots.txt URL for an origin."""

    base = f"{origin.scheme}://{origin.host}"
    if origin.port not in {80, 443}:
        base = f"{base}:{origin.port}"
    return urljoin(f"{base}/", "/robots.txt")


def require_robots_allowed(decision: RobotsDecision) -> None:
    """Fail closed when robots evaluation denies access.

    Args:
        decision: Parsed robots decision.

    Raises:
        CrawlPolicyError: When robots denies the fetch.
    """

    if not decision.allowed:
        raise CrawlPolicyError(decision.reason, code="robots_denied")


def _crawl_delay_seconds(parser: RobotFileParser, user_agent: str) -> float | None:
    """Return robots.txt crawl-delay as seconds.

    ``urllib.robotparser.RobotFileParser.crawl_delay`` is stubbed as
    ``str | None`` while CPython stores a float. ``float(raw)`` is identity
    for both a numeric string and an actual float.

    Args:
        parser: Parsed robots.txt handler.
        user_agent: Crawler user agent token.

    Returns:
        Delay in seconds, or None when the parser has no delay.

    Raises:
        TypeError: If the delay cannot be converted to float.
        ValueError: If a string delay is not numeric.
    """

    raw = parser.crawl_delay(user_agent)
    if raw is None:
        return None
    return float(raw)
