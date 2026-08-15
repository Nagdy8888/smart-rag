"""Unit smoke tests for package imports and entrypoints."""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest


def test_core_import() -> None:
    """Core package imports without constructing providers."""

    import smart_rag_core

    assert smart_rag_core.__version__ == "0.1.0"


def test_backend_app_import_exposes_unconfigured_readiness() -> None:
    """Backend app imports and readiness stays honestly unconfigured."""

    from smart_rag_api.main import app, ready

    assert app.title == "Smart RAG API"
    payload = ready()
    assert payload["status"] == "unconfigured"


def test_worker_main_returns_zero_without_claiming_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker main is callable and does not claim queue success."""

    from smart_rag_worker.main import main

    monkeypatch.setenv("WORKER_ONCE", "1")
    assert main() == 0


def test_entrypoints_import_without_network_or_provider_construction() -> None:
    """Fresh entrypoint imports neither open sockets nor instantiate OpenAI clients."""

    probe = textwrap.dedent(
        """
        import socket
        import sys
        import types

        class Trap:
            def __init__(self, *args, **kwargs):
                raise AssertionError("provider client constructed during import")

        def denied_socket(*args, **kwargs):
            raise AssertionError("socket constructed during import")

        fake_openai = types.ModuleType("openai")
        fake_openai.OpenAI = Trap
        fake_openai.AsyncOpenAI = Trap
        fake_openai.APIStatusError = Exception
        fake_openai.APITimeoutError = Exception
        fake_openai.AuthenticationError = Exception
        sys.modules["openai"] = fake_openai
        socket.create_connection = denied_socket
        socket.getaddrinfo = denied_socket

        import smart_rag_api.main
        import smart_rag_worker.main
        import smart_rag_agents.query.graph
        import smart_rag_agents.ingestion.graph
        """
    )
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and probe
        (sys.executable, "-c", probe),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
