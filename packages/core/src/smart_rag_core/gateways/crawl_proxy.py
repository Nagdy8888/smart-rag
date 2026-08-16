"""HTTP client for the restricted crawl egress proxy."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import cast

import httpx

from smart_rag_core.ingestion.crawl.exceptions import CrawlProxyError
from smart_rag_core.ingestion.crawl.limits import (
    CRAWL_CONNECT_TIMEOUT_SECONDS,
    CRAWL_MAX_DECODED_BYTES_PER_PAGE,
    CRAWL_MAX_DECOMPRESSION_RATIO,
    CRAWL_MAX_WIRE_BYTES_PER_PAGE,
    CRAWL_READ_TIMEOUT_SECONDS,
)
from smart_rag_core.ingestion.crawl.policy import strip_sensitive_headers


@dataclass(frozen=True, slots=True)
class ProxyFetchRequest:
    """One pinned fetch executed only by the crawl proxy."""

    url: str
    method: str
    host_header: str
    pin_ip: str
    port: int
    use_tls: bool
    headers: dict[str, str]
    max_wire_bytes: int = CRAWL_MAX_WIRE_BYTES_PER_PAGE
    max_decoded_bytes: int = CRAWL_MAX_DECODED_BYTES_PER_PAGE
    max_decompression_ratio: int = CRAWL_MAX_DECOMPRESSION_RATIO
    connect_timeout_s: float = CRAWL_CONNECT_TIMEOUT_SECONDS
    read_timeout_s: float = CRAWL_READ_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class ProxyFetchResponse:
    """Normalized proxy fetch result with peer metadata."""

    status_code: int
    headers: dict[str, str]
    body: bytes
    wire_bytes: int
    decoded_bytes: int
    peer_ip: str
    content_type: str | None
    truncated: bool
    error: str | None


class CrawlProxyGateway:
    """Client that routes all crawl fetches through ``CRAWL_PROXY_URL``."""

    def __init__(
        self,
        *,
        proxy_base_url: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        """Bind a private crawl-proxy base URL.

        Args:
            proxy_base_url: Internal ``http://crawl-proxy:8080`` style base.
            timeout_seconds: Overall HTTP client timeout to the proxy.
        """

        self._base_url = proxy_base_url.rstrip("/")
        self._timeout = timeout_seconds

    def fetch(self, request: ProxyFetchRequest) -> ProxyFetchResponse:
        """Execute one pinned fetch via ``POST /fetch``.

        Args:
            request: Fully validated fetch contract.

        Returns:
            Proxy response including peer IP and bounded body bytes.

        Raises:
            CrawlProxyError: When the proxy is unreachable or returns an error
                payload.
            ValueError: When direct egress is attempted without a proxy URL.
        """

        payload: dict[str, object] = {
            "url": request.url,
            "method": request.method.upper(),
            "host_header": request.host_header,
            "pin_ip": request.pin_ip,
            "port": request.port,
            "use_tls": request.use_tls,
            "headers": strip_sensitive_headers(request.headers),
            "max_wire_bytes": request.max_wire_bytes,
            "max_decoded_bytes": request.max_decoded_bytes,
            "max_decompression_ratio": request.max_decompression_ratio,
            "connect_timeout_s": request.connect_timeout_s,
            "read_timeout_s": request.read_timeout_s,
        }
        url = f"{self._base_url}/fetch"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise CrawlProxyError(f"proxy transport failure: {exc}") from exc
        if response.status_code >= 500:
            raise CrawlProxyError(
                f"proxy server error status={response.status_code}",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise CrawlProxyError("proxy returned non-json body") from exc
        if response.status_code >= 400 and not isinstance(data, dict):
            raise CrawlProxyError(
                f"proxy denied status={response.status_code}",
                status_code=response.status_code,
            )
        if not isinstance(data, dict):
            raise CrawlProxyError("proxy returned invalid json object")
        parsed = cast(dict[str, object], data)
        error = parsed.get("error")
        if isinstance(error, str) and error:
            raise CrawlProxyError(error, status_code=response.status_code)
        body_b64 = parsed.get("body_base64")
        body = b""
        if isinstance(body_b64, str) and body_b64:
            body = base64.b64decode(body_b64.encode("ascii"))
        headers_raw = parsed.get("headers")
        headers: dict[str, str] = {}
        if isinstance(headers_raw, dict):
            untyped_headers = cast(dict[object, object], headers_raw)
            headers = {str(key): str(value) for key, value in untyped_headers.items()}
        peer_ip = str(parsed.get("peer_ip", ""))
        if not peer_ip:
            raise CrawlProxyError("proxy did not report peer_ip")
        content_type_raw = parsed.get("content_type")
        return ProxyFetchResponse(
            status_code=_json_int(parsed.get("status_code", 0)),
            headers=headers,
            body=body,
            wire_bytes=_json_int(parsed.get("wire_bytes", len(body))),
            decoded_bytes=_json_int(parsed.get("decoded_bytes", len(body))),
            peer_ip=peer_ip,
            content_type=(
                str(content_type_raw)
                if content_type_raw is not None
                else headers.get("Content-Type")
            ),
            truncated=bool(parsed.get("truncated", False)),
            error=str(error) if isinstance(error, str) else None,
        )


def _json_int(value: object) -> int:
    """Coerce a JSON numeric field to int.

    Args:
        value: JSON number, numeric string, or already an int.

    Returns:
        Integer form of ``value``.
    """

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return int(str(value))
