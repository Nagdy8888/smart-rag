"""Phase 3 Packet 4 crawl operational limits (see INGESTION_LIMITS.md)."""

from __future__ import annotations

CRAWL_POLICY_VERSION = "crawl_v1"

# URL / host
CRAWL_MAX_URL_LENGTH = 2048
CRAWL_ALLOWED_PORTS = frozenset({80, 443})
CRAWL_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Redirect / depth / pages
CRAWL_MAX_REDIRECTS = 5
CRAWL_MAX_DEPTH_DEFAULT = 2
CRAWL_MAX_PAGES_DEFAULT = 50
CRAWL_MAX_PAGES_HARD = 200
CRAWL_MAX_DEPTH_HARD = 5

# Bytes
CRAWL_MAX_WIRE_BYTES_PER_PAGE = 2_097_152  # 2 MiB wire per response
CRAWL_MAX_DECODED_BYTES_PER_PAGE = 5_242_880  # 5 MiB decoded body
CRAWL_MAX_DECOMPRESSION_RATIO = 50
CRAWL_MAX_WIRE_BYTES_TOTAL = 52_428_800  # 50 MiB per crawl run
CRAWL_MAX_DECODED_BYTES_TOTAL = 104_857_600  # 100 MiB per crawl run

# Headers / robots
CRAWL_MAX_HEADER_BYTES = 32_768
CRAWL_ROBOTS_FETCH_TIMEOUT_SECONDS = 15.0
CRAWL_ROBOTS_MAX_BYTES = 524_288  # 512 KiB robots.txt

# Timeouts (seconds)
CRAWL_DNS_TIMEOUT_SECONDS = 5.0
CRAWL_CONNECT_TIMEOUT_SECONDS = 10.0
CRAWL_TLS_TIMEOUT_SECONDS = 15.0
CRAWL_FIRST_BYTE_TIMEOUT_SECONDS = 20.0
CRAWL_READ_TIMEOUT_SECONDS = 30.0
CRAWL_TOTAL_TIMEOUT_SECONDS = 300.0

# Concurrency
CRAWL_MAX_CONCURRENT_REQUESTS = 2

# MIME allowlist (prefix or exact)
CRAWL_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/html",
        "text/plain",
        "application/xhtml+xml",
    }
)

# Storage
WEB_SNAPSHOTS_BUCKET = "web-snapshots"
