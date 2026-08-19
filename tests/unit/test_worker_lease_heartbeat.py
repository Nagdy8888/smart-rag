"""Unit tests for worker heartbeat abort and parser-sandbox startup gates."""

from __future__ import annotations

from threading import Event
from uuid import uuid4

import pytest
from smart_rag_core.jobs.exceptions import JobLeaseError, JobRepositoryError
from smart_rag_core.jobs.ingestion_repository import (
    configurable_job_lease_token,
    configurable_lease_lost,
)
from smart_rag_core.settings import WorkerSettings
from smart_rag_worker.lifecycle import (
    assert_worker_parser_sandbox,
    heartbeat_until_stopped,
    patch_checkpoint_lease_token,
)


def test_heartbeat_sets_lease_lost_and_does_not_complete() -> None:
    """Heartbeat ``JobLeaseError`` sets the shared event used to skip complete()."""

    stop = Event()
    lease_lost = Event()

    def _beat() -> None:
        """Reject the lease as the heartbeat thread would on stolen ownership."""

        raise JobLeaseError("heartbeat_rejected")

    heartbeat_until_stopped(
        stop=stop,
        lease_lost=lease_lost,
        interval_seconds=0.01,
        beat=_beat,
        job_id=uuid4(),
    )
    assert lease_lost.is_set()
    assert configurable_lease_lost({"configurable": {"lease_lost": lease_lost}}) is True
    assert configurable_lease_lost({"configurable": {"lease_lost": Event()}}) is False


def test_assert_worker_parser_sandbox_blocks_inprocess_with_storage_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In-process parse is forbidden in the same process as Storage Admin."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_INPROCESS_PARSER", "true")
    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    settings = WorkerSettings()
    monkeypatch.setattr(
        "smart_rag_worker.lifecycle.load_worker_privileged_storage_secret",
        lambda: "storage-admin-present",
    )
    with pytest.raises(
        JobRepositoryError,
        match="inprocess_parser_forbidden_with_storage_admin_secret",
    ):
        assert_worker_parser_sandbox(settings)


def test_assert_worker_parser_sandbox_requires_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workers without the in-process flag must have Docker available."""

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("ALLOW_INPROCESS_PARSER", raising=False)
    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    settings = WorkerSettings()
    monkeypatch.setattr(
        "smart_rag_worker.lifecycle.inprocess_parser_permitted",
        lambda: False,
    )
    monkeypatch.setattr(
        "smart_rag_worker.lifecycle.docker_sandbox_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "smart_rag_worker.lifecycle.load_worker_privileged_storage_secret",
        lambda: None,
    )
    with pytest.raises(JobRepositoryError, match="parser_sandbox_docker_required"):
        assert_worker_parser_sandbox(settings)


class _FakeResumeGraph:
    """Record ``update_state`` calls from checkpoint lease patching."""

    def __init__(self) -> None:
        """Initialize an empty update log."""

        self.updates: list[tuple[object, object]] = []

    def update_state(self, config: object, values: object) -> None:
        """Capture one checkpoint overlay.

        Args:
            config: Runnable config passed through by the worker.
            values: Channel overlay, expected to include ``lease_token``.
        """

        self.updates.append((config, values))


def test_configurable_job_lease_token_prefers_claimed_config() -> None:
    """Resume must present the live claim token, not checkpointed state."""

    claimed = "claimed-lease-token"
    stale = "stale-checkpoint-token"
    resolved = configurable_job_lease_token(
        {"configurable": {"job_lease_token": claimed}},
        stale,
    )
    assert resolved == claimed
    assert configurable_job_lease_token({}, stale) == stale
    assert configurable_job_lease_token({"configurable": {}}, stale) == stale


def test_patch_checkpoint_lease_token_overwrites_resumed_token() -> None:
    """``invoke(None)`` resume must not keep the failed attempt's lease token."""

    graph = _FakeResumeGraph()
    config: dict[str, object] = {"configurable": {"thread_id": "job-1"}}
    patch_checkpoint_lease_token(graph, config, "new-token")
    assert graph.updates == [(config, {"lease_token": "new-token"})]


def test_patch_checkpoint_lease_token_skips_empty_token() -> None:
    """An empty claim token must not write a checkpoint overlay."""

    graph = _FakeResumeGraph()
    patch_checkpoint_lease_token(graph, {}, "")
    assert graph.updates == []
