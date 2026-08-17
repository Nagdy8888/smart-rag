"""Private-port invariants for the candidate Compose file and runtime."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import cast

from smart_rag_core.release.constants import (
    LIGHTRAG_PUBLIC_PORTS,
    PRIVATE_COMPOSE_SERVICES,
)
from smart_rag_core.release.errors import CandidatePortError

_SERVICE_HEADER = "  "
_PORTS_KEY = "    ports:"


def parse_compose_publishers(payload: object) -> dict[str, tuple[int, ...]]:
    """Parse ``docker compose ps --format json`` into host published ports.

    Compose may emit a JSON array or JSON-lines objects. ``PublishedPort`` is
    treated as a host port; unpublished services yield an empty tuple.

    Args:
        payload: Decoded JSON value or a sequence of service objects.

    Returns:
        Mapping of Compose service name to host published ports.

    Raises:
        CandidatePortError: If the payload cannot be interpreted.
    """

    services = _coerce_service_list(payload)
    published: dict[str, tuple[int, ...]] = {}
    for item in services:
        name = str(item.get("Service") or item.get("Name") or "")
        if not name:
            continue
        raw_publishers = item.get("Publishers")
        ports: list[int] = []
        if isinstance(raw_publishers, list):
            for publisher in cast(list[object], raw_publishers):
                if not isinstance(publisher, dict):
                    continue
                typed_publisher = cast(dict[str, object], publisher)
                value = typed_publisher.get("PublishedPort")
                if isinstance(value, int) and value > 0:
                    ports.append(value)
                elif isinstance(value, str) and value.isdigit() and int(value) > 0:
                    ports.append(int(value))
        published[name] = tuple(ports)
    return published


def parse_compose_ps_text(text: str) -> dict[str, tuple[int, ...]]:
    """Parse Compose ``ps --format json`` stdout.

    Args:
        text: Raw stdout. May be a JSON array, JSON-lines, or empty.

    Returns:
        Service to host-port mapping.

    Raises:
        CandidatePortError: If stdout is not JSON services.
    """

    stripped = text.strip()
    if not stripped:
        return {}
    try:
        loaded: object = json.loads(stripped)
        return parse_compose_publishers(loaded)
    except json.JSONDecodeError:
        rows: list[object] = []
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CandidatePortError("compose ps output is not JSON") from exc
        return parse_compose_publishers(rows)


def compose_file_declares_host_ports(compose_text: str, service: str) -> bool:
    """Return whether the candidate Compose file publishes ports for a service.

    Args:
        compose_text: ``docker-compose.yml`` source.
        service: Compose service name.

    Returns:
        True when the service block contains a ``ports:`` key.
    """

    block = _service_block(compose_text, service)
    if block is None:
        raise CandidatePortError(f"compose service missing: {service}")
    return f"\n{_PORTS_KEY}" in f"\n{block}" or block.startswith(_PORTS_KEY)


def assert_private_services_unpublished(
    publishers: Mapping[str, Sequence[int]],
    *,
    compose_text: str | None = None,
) -> None:
    """Reject host-published ParadeDB, Valkey, crawl-proxy, or LightRAG ports.

    Args:
        publishers: Runtime Compose publishers keyed by service name.
        compose_text: Optional candidate Compose source for static ``ports:``.

    Raises:
        CandidatePortError: If a private service is missing or published, or a
            LightRAG-like public port appears.
    """

    if compose_text is not None:
        for name in PRIVATE_COMPOSE_SERVICES:
            if compose_file_declares_host_ports(compose_text, name):
                raise CandidatePortError(
                    f"candidate compose publishes host ports for {name}"
                )
        if _compose_has_lightrag_service(compose_text):
            raise CandidatePortError("candidate compose declares a LightRAG service")

    for name in PRIVATE_COMPOSE_SERVICES:
        if name not in publishers:
            raise CandidatePortError(f"required private service missing: {name}")
        ports = tuple(int(port) for port in publishers[name] if int(port) > 0)
        if ports:
            raise CandidatePortError(f"private service {name} has host ports {ports}")

    for name, ports in publishers.items():
        lowered = name.lower()
        if "lightrag" in lowered and any(int(port) > 0 for port in ports):
            raise CandidatePortError(f"LightRAG service {name} publishes host ports")
        for port in ports:
            if int(port) in LIGHTRAG_PUBLIC_PORTS:
                raise CandidatePortError(
                    f"service {name} publishes LightRAG public port {port}"
                )


def _coerce_service_list(payload: object) -> list[dict[str, object]]:
    """Narrow Compose JSON into a list of service objects."""

    if isinstance(payload, dict):
        return [cast(dict[str, object], payload)]
    if isinstance(payload, list):
        rows: list[dict[str, object]] = []
        for item in cast(list[object], payload):
            if isinstance(item, dict):
                rows.append(cast(dict[str, object], item))
        return rows
    raise CandidatePortError("compose ps payload is not a service list")


def _service_block(compose_text: str, service: str) -> str | None:
    """Return the indented block for one Compose service."""

    header = f"{_SERVICE_HEADER}{service}:"
    lines = compose_text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith(header) and (
            len(line) == len(header) or line[len(header) :].startswith(" ")
        ):
            start = index + 1
            break
    if start is None:
        return None
    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith(_SERVICE_HEADER) and not line.startswith("    "):
            if line.strip().endswith(":") and not line.startswith("    "):
                break
        collected.append(line)
    return "\n".join(collected)


def _compose_has_lightrag_service(compose_text: str) -> bool:
    """Return whether Compose declares a ``lightrag`` service."""

    for line in compose_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("lightrag:") or stripped.startswith("lightrag-"):
            if line.startswith(_SERVICE_HEADER) and not line.startswith("    "):
                return True
    return False
