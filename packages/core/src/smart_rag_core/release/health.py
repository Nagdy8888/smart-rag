"""Candidate health and private-port proof against ``docker-compose.yml`` only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from urllib.error import URLError
from urllib.request import urlopen

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.release.compose import run_compose
from smart_rag_core.release.constants import HEALTH_SCHEMA_VERSION
from smart_rag_core.release.errors import CandidateReleaseError
from smart_rag_core.release.ports import (
    assert_private_services_unpublished,
    parse_compose_ps_text,
)


class CandidateHealthReport(BaseModel):
    """Health and private-port proof for the candidate stack.

    Attributes:
        schema_version: Frozen health schema.
        api_live: API ``/health/live`` classification.
        frontend_live: Frontend classification.
        pg_search: ParadeDB extension via Compose exec.
        valkey_limits_auth: Limits instance authenticated ping.
        valkey_cache_auth: Cache instance authenticated ping.
        private_ports: Private-port invariant classification.
        mock_model_mode: API container ``MOCK_MODEL_MODE``.
        overlay_used: Always false for candidate identity.
        detail: Bounded notes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["phase09-candidate-health-v1"] = HEALTH_SCHEMA_VERSION
    api_live: Literal["passed", "failed", "blocked", "not_run"]
    frontend_live: Literal["passed", "failed", "blocked", "not_run"]
    pg_search: Literal["passed", "failed", "blocked", "not_run"]
    valkey_limits_auth: Literal["passed", "failed", "blocked", "not_run"]
    valkey_cache_auth: Literal["passed", "failed", "blocked", "not_run"]
    private_ports: Literal["passed", "failed", "blocked", "not_run"]
    mock_model_mode: str
    overlay_used: Literal[False] = False
    detail: str = Field(default="", max_length=2000)


def http_ok(url: str, *, timeout_seconds: int = 15) -> bool:
    """Return whether an HTTP GET succeeds with status 200.

    Args:
        url: Absolute URL.
        timeout_seconds: Socket timeout.

    Returns:
        True on HTTP 200.
    """

    try:
        with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310
            status = int(getattr(response, "status", 0))
            return status == 200
    except (URLError, TimeoutError, OSError, ValueError):
        return False


def _http_status(ok: bool) -> Literal["passed", "failed"]:
    """Map a boolean HTTP probe to a health classification."""

    return "passed" if ok else "failed"


def prove_candidate_health(repo_root: Path) -> CandidateHealthReport:
    """Prove live/ready health and unpublished private ports.

    Args:
        repo_root: Repository root.

    Returns:
        Health report. Individual checks may be ``failed`` without raising so
        the evidence file can classify honestly.

    Raises:
        CandidatePortError: If private services publish host ports.
        CandidateReleaseError: If Compose cannot list services.
    """

    compose_text = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    ps = run_compose(repo_root, ["ps", "--format", "json"], timeout_seconds=60)
    if ps.returncode != 0:
        raise CandidateReleaseError("docker compose ps failed for candidate stack")
    publishers = parse_compose_ps_text(ps.stdout)
    assert_private_services_unpublished(publishers, compose_text=compose_text)

    api_live = _http_status(http_ok("http://127.0.0.1:8000/health/live"))
    frontend_live = _http_status(http_ok("http://127.0.0.1:3000"))
    pg_search = _pg_search_via_exec(repo_root)
    limits = _valkey_auth(repo_root, "valkey-limits", "VALKEY_LIMITS_PASSWORD")
    cache = _valkey_auth(repo_root, "valkey-cache", "VALKEY_CACHE_PASSWORD")
    mock = _mock_model_mode(repo_root)
    return CandidateHealthReport(
        api_live=api_live,
        frontend_live=frontend_live,
        pg_search=pg_search,
        valkey_limits_auth=limits,
        valkey_cache_auth=cache,
        private_ports="passed",
        mock_model_mode=mock,
        detail=json.dumps(
            {"publishers": {name: list(ports) for name, ports in publishers.items()}},
            sort_keys=True,
        ),
    )


def _pg_search_via_exec(
    repo_root: Path,
) -> Literal["passed", "failed", "blocked", "not_run"]:
    """Query ``pg_search`` through Compose exec, never a public port."""

    completed = run_compose(
        repo_root,
        [
            "exec",
            "-T",
            "paradedb",
            "psql",
            "-U",
            "paradedb",
            "-d",
            "paradedb",
            "-tAc",
            "SELECT extname || ':' || extversion FROM pg_extension WHERE extname='pg_search'",
        ],
        timeout_seconds=30,
    )
    if completed.returncode != 0:
        return "failed"
    return "passed" if completed.stdout.strip().startswith("pg_search:") else "failed"


def query_pg_search_version(repo_root: Path) -> str:
    """Return the runtime ``pg_search`` version or ``unverified_runtime``.

    Args:
        repo_root: Repository root.

    Returns:
        Extension version string.
    """

    completed = run_compose(
        repo_root,
        [
            "exec",
            "-T",
            "paradedb",
            "psql",
            "-U",
            "paradedb",
            "-d",
            "paradedb",
            "-tAc",
            "SELECT extversion FROM pg_extension WHERE extname='pg_search'",
        ],
        timeout_seconds=30,
    )
    version = completed.stdout.strip()
    if completed.returncode != 0 or not version:
        return "unverified_runtime"
    return version


def _valkey_auth(
    repo_root: Path,
    service: str,
    password_var: str,
) -> Literal["passed", "failed", "blocked", "not_run"]:
    """Authenticated ping plus unauthenticated NOAUTH for one Valkey service."""

    ping = run_compose(
        repo_root,
        [
            "exec",
            "-T",
            service,
            "sh",
            "-c",
            f'valkey-cli -a "${password_var}" --no-auth-warning ping',
        ],
        timeout_seconds=20,
    )
    if ping.returncode != 0 or ping.stdout.strip() != "PONG":
        return "failed"
    unauth = run_compose(
        repo_root,
        ["exec", "-T", service, "valkey-cli", "--raw", "ping"],
        timeout_seconds=20,
    )
    combined = f"{unauth.stdout}\n{unauth.stderr}"
    if "NOAUTH" not in combined:
        return "failed"
    return "passed"


def _mock_model_mode(repo_root: Path) -> str:
    """Read ``MOCK_MODEL_MODE`` from the API container."""

    completed = run_compose(
        repo_root,
        ["exec", "-T", "api", "sh", "-c", 'printf %s "$MOCK_MODEL_MODE"'],
        timeout_seconds=20,
    )
    if completed.returncode != 0:
        return "unverified"
    return completed.stdout.strip() or "unverified"
