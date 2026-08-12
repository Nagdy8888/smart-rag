"""Unit smoke tests for package imports and entrypoints."""

from __future__ import annotations


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


def test_worker_main_returns_zero_without_claiming_jobs() -> None:
    """Worker main is callable and does not claim queue success."""

    from smart_rag_worker.main import main

    assert main() == 0
