"""Unit tests for crawl proxy fetch execution."""

from __future__ import annotations

import gzip
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROXY_SERVER = REPO_ROOT / "infra" / "crawl-proxy" / "server.py"


def _load_proxy_module() -> ModuleType:
    """Load the crawl-proxy server module from its source path.

    Returns:
        Imported ``server`` module.

    Raises:
        AssertionError: If the module spec or loader is missing.
    """

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
        """Minimal FetchHandler double that records the HTTP status."""

        def __init__(self) -> None:
            """Initialize in-memory request buffers and a zero status."""

            self.path = "/legacy"
            self.headers = {"Content-Length": "0"}
            self.rfile = __import__("io").BytesIO(b"")
            self.wfile = __import__("io").BytesIO()
            self.status = 0
            self.payload: dict[str, object] | None = None

        def send_response(self, code: int, message: str | None = None) -> None:
            """Record the status code without writing a real socket.

            Args:
                code: HTTP status to store.
                message: Unused reason phrase.
            """

            self.status = code

        def send_header(self, keyword: str, value: str) -> None:
            """Ignore headers; this double only asserts status.

            Args:
                keyword: Unused header name.
                value: Unused header value.
            """

            return None

        def end_headers(self) -> None:
            """No-op; the double does not emit a wire response."""

            return None

    handler = _Handler()
    handler.do_POST()
    assert handler.status == 403


def test_proxy_peer_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live execute_fetch fails closed when the connected peer is not the pin."""

    module = _load_proxy_module()

    class _MismatchedSocket:
        """Socket double whose peer IP is never the expected pin."""

        def getpeername(self) -> tuple[str, int]:
            """Return a private address that must fail the pin check.

            Returns:
                Peer host and port that do not match the fixture pin.
            """

            return ("10.0.0.9", 80)

        def close(self) -> None:
            """No-op close for the in-memory socket double."""

            return None

        def settimeout(self, _value: float) -> None:
            """Ignore timeout; the double never blocks.

            Args:
                _value: Unused timeout seconds.
            """

            return None

    def _mismatched_connection(*_args: object, **_kwargs: object) -> _MismatchedSocket:
        """Return a socket whose peer does not match the pin.

        Args:
            *_args: Ignored ``create_connection`` positional arguments.
            **_kwargs: Ignored ``create_connection`` keyword arguments.

        Returns:
            Socket stub reporting ``10.0.0.9``.
        """

        return _MismatchedSocket()

    monkeypatch.setattr(
        module.socket,
        "create_connection",
        _mismatched_connection,
    )
    with pytest.raises(module.FetchError) as exc:
        module.execute_fetch(
            {
                "url": "http://example.com/",
                "host_header": "example.com",
                "pin_ip": "127.0.0.1",
                "port": 80,
                "use_tls": False,
            }
        )
    assert exc.value.reason == "peer_ip_mismatch"
    assert exc.value.peer_ip == "10.0.0.9"
