"""Unit tests for overlay detector reviews, ingest class, and worker graph mode."""

from __future__ import annotations

import inspect
from pathlib import Path
from uuid import uuid4

import pytest
from smart_rag_core.observability.ingest_trace import ingest_content_class_for_job
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.external_processing import ContentClass
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.settings import SharedSettings, WorkerSettings, load_worker_settings
from smart_rag_worker.graph_runner import GraphWorkerLoop
from smart_rag_worker.lifecycle import WorkerLifecycle


def test_local_env_does_not_reclassify_real_company() -> None:
    """``APP_ENV=local`` is an export waiver, not a synthetic reclass."""

    settings = SharedSettings()
    resolved = ingest_content_class_for_job(
        ContentClass.REAL_COMPANY,
        settings=settings,
    )
    assert resolved is ContentClass.REAL_COMPANY
    assert (
        ingest_content_class_for_job("real_company", settings=settings)
        is ContentClass.REAL_COMPANY
    )


def test_payload_review_approved_is_not_authoritative() -> None:
    """Scan and index graphs must not honor ``payload_ref.review_approved``."""

    scan_path = (
        Path("apps")
        / "agents"
        / "src"
        / "smart_rag_agents"
        / "ingestion"
        / "scan_graph.py"
    )
    index_path = (
        Path("apps")
        / "agents"
        / "src"
        / "smart_rag_agents"
        / "ingestion"
        / "index_graph.py"
    )
    scan_src = scan_path.read_text(encoding="utf-8")
    index_src = index_path.read_text(encoding="utf-8")
    assert 'payload_ref.get("review_approved")' not in scan_src
    assert 'payload.get("review_approved") is True' not in index_src
    assert "resolve_review_approved(" in scan_src
    assert "resolve_review_approved(" in index_src


def test_member_review_finding_is_not_found() -> None:
    """Members and viewers cannot distinguish missing from unauthorized findings."""

    from smart_rag_api.services.governance_reviews_http import (
        GovernanceReviewHttpService,
    )

    service = GovernanceReviewHttpService("postgresql://unused")
    with pytest.raises(QueryAdmissionError) as caught:
        service.review_finding(
            CallerContext(
                user_id=str(uuid4()),
                role=UserRole.MEMBER,
                authorization_version=1,
            ),
            finding_id=uuid4(),
            decision="false_positive",
            reason="not a secret",
            idempotency_key="idem-key-01",
        )
    assert caught.value.reason == "not_found"


def test_worker_graph_enabled_defaults_true() -> None:
    """Other deployments keep LightRAG bind unless the flag is false."""

    settings = WorkerSettings()
    assert settings.worker_graph_enabled is True
    source = inspect.getsource(WorkerLifecycle.__init__)
    assert "worker_graph_enabled" in source
    assert "bind_process_runtime_adapter" in source


def test_worker_graph_disabled_loads(monkeypatch: object) -> None:
    """False disables graph bind without changing Hybrid defaults.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """

    from pytest import MonkeyPatch

    assert isinstance(monkeypatch, MonkeyPatch)
    monkeypatch.setenv("WORKER_GRAPH_ENABLED", "false")
    settings = load_worker_settings()
    assert settings.worker_graph_enabled is False
    source = inspect.getsource(WorkerLifecycle.run_forever)
    assert "if self._settings.worker_graph_enabled:" in source
    assert "self._bm25_loop.process_once()" in source


def test_graph_loop_noops_without_adapter() -> None:
    """Disabled workers must not claim graph jobs."""

    settings = WorkerSettings()
    loop = GraphWorkerLoop(settings, adapter=None, async_loop=None)
    assert loop.process_once() is False
