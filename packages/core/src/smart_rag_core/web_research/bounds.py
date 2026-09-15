"""Hard caps for the Web research subgraph.

These numbers must stay inside the ``web_research`` envelope (50s, 5
model calls, 5 tools). They are not client authority.
"""

from __future__ import annotations

WEB_MAX_ROUNDS: int = 2
"""Initial search plus at most one follow-up round. A third round is forbidden."""

WEB_MAX_FORMULATIONS: int = 3
"""Maximum search query strings across the whole run."""

WEB_MAX_CANDIDATES_PER_ROUND: int = 12
"""Maximum Exa hits retained from one search call."""

WEB_MAX_SOURCES: int = 6
"""Maximum persisted ``web_sources`` rows."""

WEB_MAX_CITATIONS: int = 12
"""Maximum persisted ``web_citations`` rows."""

WEB_MAX_EXTERNAL_OPS: int = 5
"""Maximum search + contents + crawl-proxy fetch operations."""

WEB_MAX_EXCERPT_CHARS: int = 8000
"""Maximum stored excerpt characters per source."""

WEB_MAX_TOTAL_EXCERPT_CHARS: int = 40_000
"""Maximum combined excerpt characters across retained sources."""

WEB_DEADLINE_SECONDS: int = 50
"""Hard Web subgraph deadline in seconds."""

WEB_PROGRESS_SEARCH: str = "web_search"
"""SSE ``node_start.stage`` while Exa search runs. UI label is Searching…."""

WEB_PROGRESS_READ: str = "web_read"
"""SSE ``node_start.stage`` while contents/fetch runs. UI label is Reading…."""
