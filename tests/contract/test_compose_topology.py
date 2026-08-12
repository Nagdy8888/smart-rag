"""Contract tests for Compose private topology and crawl-proxy denial."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
PROXY_SERVER = REPO_ROOT / "infra" / "crawl-proxy" / "server.py"


def _mapping(value: object) -> dict[str, object]:
    """Validate and narrow one YAML mapping.

    Args:
        value: Parsed YAML value.

    Returns:
        String-keyed mapping.

    Raises:
        TypeError: If the value is not a mapping.
    """

    if not isinstance(value, dict):
        raise TypeError("Expected Compose mapping")
    return cast(dict[str, object], value)


def _string_list(value: object) -> list[str]:
    """Validate and narrow one Compose string list.

    Args:
        value: Parsed YAML value.

    Returns:
        List containing only strings.

    Raises:
        TypeError: If the value is not a string list.
    """

    if not isinstance(value, list):
        raise TypeError("Expected Compose string list")
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        raise TypeError("Expected Compose string list")
    return cast(list[str], items)


def _load_compose() -> dict[str, object]:
    """Load the local Compose file as a typed mapping."""

    loaded = cast(object, yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8")))
    return _mapping(loaded)


def _service(name: str) -> dict[str, object]:
    """Return one named Compose service mapping.

    Args:
        name: Compose service name.

    Returns:
        Validated service mapping.
    """

    services = _mapping(_load_compose()["services"])
    return _mapping(services[name])


def _load_proxy_module():
    """Load the crawl-proxy server module from its path."""

    spec = importlib.util.spec_from_file_location("crawl_proxy_server", PROXY_SERVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_private_services_have_no_host_ports() -> None:
    """ParadeDB, Valkey, and crawl-proxy must not publish host ports."""

    for name in ("paradedb", "valkey-limits", "valkey-cache", "crawl-proxy"):
        assert "ports" not in _service(name)


def test_developer_endpoints_are_explicit() -> None:
    """Only api and frontend may publish documented developer ports."""

    assert "ports" in _service("api")
    assert "ports" in _service("frontend")
    assert "ports" not in _service("worker")


def test_third_party_images_are_digest_pinned() -> None:
    """Third-party images must use immutable digests."""

    for name in ("paradedb", "valkey-limits", "valkey-cache"):
        image = _service(name)["image"]
        assert isinstance(image, str)
        assert "@sha256:" in image, f"{name} image is not digest-pinned: {image}"


def test_valkey_instances_have_distinct_policies() -> None:
    """Limits use noeviction; cache uses an evicting policy and distinct secrets."""

    limits_cmd = " ".join(_string_list(_service("valkey-limits")["command"]))
    cache_cmd = " ".join(_string_list(_service("valkey-cache")["command"]))
    assert "noeviction" in limits_cmd
    assert "allkeys-lru" in cache_cmd
    assert "VALKEY_LIMITS_PASSWORD" in limits_cmd
    assert "VALKEY_CACHE_PASSWORD" in cache_cmd


def test_paradedb_healthcheck_requires_pg_search() -> None:
    """ParadeDB health must qualify pg_search, not TCP alone."""

    healthcheck = _mapping(_service("paradedb")["healthcheck"])
    test = " ".join(_string_list(healthcheck["test"]))
    assert "pg_search" in test


def test_crawl_proxy_denies_by_default() -> None:
    """Proxy deny body and POST handler contract block all destinations."""

    module = _load_proxy_module()
    payload = json.loads(module.DenyByDefaultHandler.DENY_BODY.decode("utf-8"))
    assert payload["status"] == "denied"
    assert (
        "deny-by-default" in payload["reason"].lower() or "Phase 3" in payload["reason"]
    )

    class _Handler(module.DenyByDefaultHandler):
        """Capture status without a real socket."""

        def __init__(self) -> None:
            """Initialize in-memory request and response streams."""

            self.path = "/fetch"
            self.headers = {"Content-Length": "2"}
            self.rfile = __import__("io").BytesIO(b"{}")
            self.wfile = __import__("io").BytesIO()
            self.status = 0

        def send_response(self, code: int, message: str | None = None) -> None:
            """Capture the response status without writing a socket.

            Args:
                code: HTTP response status.
                message: Optional response reason, intentionally ignored.
            """

            self.status = code

        def send_header(self, keyword: str, value: str) -> None:
            """Accept an in-memory response header.

            Args:
                keyword: Header name.
                value: Header value.
            """

            return None

        def end_headers(self) -> None:
            """Complete the in-memory header section."""

            return None

    handler = _Handler()
    handler.do_POST()
    assert handler.status == 403
    assert handler.wfile.getvalue() == module.DenyByDefaultHandler.DENY_BODY


def test_application_images_run_as_non_root() -> None:
    """Compose pins non-root users for api and worker."""

    assert _service("api")["user"] == "10001:10001"
    assert _service("worker")["user"] == "10001:10001"
