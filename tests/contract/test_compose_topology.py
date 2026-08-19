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
IMAGE_DIGESTS = REPO_ROOT / "infra" / "paradedb" / "IMAGE_DIGESTS.md"
PYTHON_DISTROLESS_DOCKERFILES: tuple[str, ...] = (
    "apps/backend/Dockerfile",
    "apps/worker/Dockerfile",
    "apps/agents/Dockerfile",
    "infra/crawl-proxy/Dockerfile",
)
ALPINE_DOCKERFILES: tuple[str, ...] = (
    "apps/frontend/Dockerfile",
    "infra/parser-sandbox/Dockerfile",
)


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
    """Proxy deny body and unknown POST routes remain blocked."""

    module = _load_proxy_module()
    payload = json.loads(module.FetchHandler.DENY_BODY.decode("utf-8"))
    assert payload["status"] == "denied"

    class _Handler(module.FetchHandler):
        """Capture status without a real socket."""

        def __init__(self) -> None:
            """Bind a denied POST path and empty JSON body."""

            self.path = "/legacy"
            self.headers = {"Content-Length": "2"}
            self.rfile = __import__("io").BytesIO(b"{}")
            self.wfile = __import__("io").BytesIO()
            self.status = 0

        def send_response(self, code: int, message: str | None = None) -> None:
            """Record the HTTP status that FetchHandler would send."""

            del message
            self.status = code

        def send_header(self, keyword: str, value: str) -> None:
            """Ignore headers; only status is asserted."""

            del keyword, value

        def end_headers(self) -> None:
            """No-op header terminator."""

    handler = _Handler()
    handler.do_POST()
    assert handler.status == 403


def test_api_and_worker_use_app_runtime_not_superuser() -> None:
    """Compose API/worker DSN must be the LOGIN wrapper, not postgres."""

    api_env = _mapping(_service("api")["environment"])
    worker_env = _mapping(_service("worker")["environment"])
    api_dsn = api_env["SUPABASE_DB_URL"]
    worker_dsn = worker_env["SUPABASE_DB_URL"]
    assert isinstance(api_dsn, str)
    assert isinstance(worker_dsn, str)
    for dsn in (api_dsn, worker_dsn):
        assert "app_runtime" in dsn
        assert "APP_RUNTIME_DB_PASSWORD" in dsn
        assert "postgres:postgres" not in dsn
        assert "postgresql://postgres:" not in dsn
    assert "SUPABASE_STORAGE_ADMIN_SECRET" not in worker_env


def test_staging_api_green_requires_blue_green_profile() -> None:
    """Default staging Compose must start api-blue only."""

    path = REPO_ROOT / "infra" / "ec2" / "docker-compose.staging.yml"
    loaded = _mapping(yaml.safe_load(path.read_text(encoding="utf-8")))
    services = _mapping(loaded["services"])
    green = _mapping(services["api-green"])
    blue = _mapping(services["api-blue"])
    assert _string_list(green["profiles"]) == ["blue-green"]
    assert "profiles" not in blue


def test_application_images_run_as_non_root() -> None:
    """Compose pins non-root users for api and worker."""

    assert _service("api")["user"] == "10001:10001"
    assert _service("worker")["user"] == "10001:10001"


def test_distroless_healthchecks_use_exec_form() -> None:
    """Distroless runtimes have no /bin/sh, so healthchecks cannot use CMD-SHELL."""

    for name in ("api", "worker", "crawl-proxy"):
        healthcheck = _mapping(_service(name)["healthcheck"])
        test = _string_list(healthcheck["test"])
        assert test[0] == "CMD", f"{name} healthcheck must use exec-form CMD"
        assert test[1] == "python", f"{name} healthcheck must invoke python directly"


def _digest_pin(prefix: str) -> str:
    """Return one ``name@sha256:`` pin from IMAGE_DIGESTS.md.

    Args:
        prefix: Line prefix such as ``library/python:3.11-alpine``.

    Returns:
        The matching pin without the ``library/`` registry prefix.

    Raises:
        AssertionError: If the pin is missing or malformed.
    """

    for line in IMAGE_DIGESTS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix + "@sha256:"):
            pin = stripped.removeprefix("library/")
            assert "@sha256:" in pin
            return pin
    raise AssertionError(f"missing IMAGE_DIGESTS pin for {prefix}")


def test_application_dockerfiles_pin_current_base_digests() -> None:
    """Application Dockerfiles must match the documented official digest pins."""

    python_trixie = _digest_pin("library/python:3.11-slim-trixie")
    python_alpine = _digest_pin("library/python:3.11-alpine")
    node_pin = _digest_pin("library/node:20-alpine")
    distroless_pin = _digest_pin("gcr.io/distroless/cc-debian13:nonroot")
    for relative in PYTHON_DISTROLESS_DOCKERFILES:
        content = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert python_trixie in content, f"{relative} missing {python_trixie}"
        assert distroless_pin in content, f"{relative} missing {distroless_pin}"
        assert "ghcr.io/astral-sh/uv:0.11.23" in content or relative.startswith(
            "infra/"
        )
    parser = (REPO_ROOT / "infra/parser-sandbox/Dockerfile").read_text(encoding="utf-8")
    assert python_alpine in parser
    frontend = (REPO_ROOT / "apps/frontend/Dockerfile").read_text(encoding="utf-8")
    assert frontend.count(f"FROM {node_pin}") == 2
    assert "pnpm@9.15.0" in frontend
    assert "rm -rf /usr/local/lib/node_modules/npm" in frontend


def test_application_dockerfiles_upgrade_as_root_before_user_10001() -> None:
    """Builder OS upgrades must finish before the runtime drops to UID 10001."""

    for relative in PYTHON_DISTROLESS_DOCKERFILES:
        content = (REPO_ROOT / relative).read_text(encoding="utf-8")
        runtime_idx = content.rfind("FROM gcr.io/distroless/cc-debian13:nonroot")
        user_idx = content.find("USER 10001:10001")
        upgrade_idx = content.find("apt-get upgrade -y")
        assert runtime_idx >= 0, f"{relative} must use distroless runtime"
        assert 0 <= upgrade_idx < runtime_idx < user_idx, (
            f"{relative} must apt-get upgrade in the builder before distroless USER 10001"
        )
        runtime = content[runtime_idx:]
        assert "apt-get" not in runtime
        assert "apk " not in runtime
    for relative in ALPINE_DOCKERFILES:
        content = (REPO_ROOT / relative).read_text(encoding="utf-8")
        user_idx = content.find("USER 10001:10001")
        upgrade_idx = content.find("apk upgrade --no-cache")
        assert user_idx >= 0, f"{relative} must drop to USER 10001:10001"
        assert 0 <= upgrade_idx < user_idx, (
            f"{relative} must apk upgrade as root before USER 10001"
        )
        assert "USER 10001:10001" not in content[:upgrade_idx]


def test_distroless_venv_images_copy_extra_shared_libs() -> None:
    """API/worker/agents copy libffi and wheel .so deps without dpkg metadata."""

    for relative in (
        "apps/backend/Dockerfile",
        "apps/worker/Dockerfile",
        "apps/agents/Dockerfile",
    ):
        content = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "infra/docker/collect_runtime_shared_libs.py" in content
        runtime_idx = content.rfind("FROM gcr.io/distroless/cc-debian13:nonroot")
        runtime = content[runtime_idx:]
        assert "COPY --from=builder --chown=10001:10001 /runtime-so/ /" in runtime
        assert "/var/lib/dpkg" not in content
