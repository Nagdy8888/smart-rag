"""Unit tests for crawl proxy fetch execution."""

from __future__ import annotations

import gzip
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROXY_SERVER = REPO_ROOT / "infra" / "crawl-proxy" / "server.py"


def _load_proxy_module():
    spec = importlib.util.spec_from_file_location("crawl_proxy_server", PROXY_SERVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_execute_fetch_requires_pin_and_host() -> None:
    """Missing pin metadata fails before any socket work."""

    module = _load_proxy_module()
    with pytest.raises(ValueError):
        module.execute_fetch({"url": "https://example.com/"})


def test_decode_body_enforces_ratio_limit() -> None:
    """Compression bombs exceeding ratio fail closed."""

    module = _load_proxy_module()
    payload = gzip.compress(b"x" * 10_000)
    with pytest.raises(module.FetchError) as exc:
        module._decode_body(
            payload,
            {"Content-Encoding": "gzip"},
            max_decoded=1_000_000,
            max_ratio=2,
        )
    assert exc.value.reason == "decompression_ratio_exceeded"


def test_decode_chunked_oversize() -> None:
    """Chunked responses decode under parser control."""

    module = _load_proxy_module()
    raw = b"5\r\nhello\r\n0\r\n\r\n"
    decoded = module._decode_chunked(raw)
    assert decoded == b"hello"


def test_post_fetch_route_denies_unknown_paths() -> None:
    """Legacy POST paths remain denied."""

    module = _load_proxy_module()

    class _Handler(module.FetchHandler):
        def __init__(self) -> None:
            self.path = "/legacy"
            self.headers = {"Content-Length": "0"}
            self.rfile = __import__("io").BytesIO(b"")
            self.wfile = __import__("io").BytesIO()
            self.status = 0
            self.payload: dict[str, object] | None = None

        def send_response(self, code: int, message: str | None = None) -> None:
            self.status = code

        def send_header(self, keyword: str, value: str) -> None:
            return None

        def end_headers(self) -> None:
            return None

    handler = _Handler()
    handler.do_POST()
    assert handler.status == 403
