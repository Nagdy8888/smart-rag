"""Unit tests for the worker LightRAG event-loop reuse helper."""

from __future__ import annotations

import asyncio

from smart_rag_core.jobs.limits import (
    LOCAL_DEMO_MAX_MAPPING_ENTITIES,
    LOCAL_DEMO_MAX_MAPPING_RELATIONS,
    MAX_MAPPING_ENTITIES,
    MAX_MAPPING_RELATIONS,
)
from smart_rag_core.settings.base import Environment
from smart_rag_core.settings.worker import WorkerSettings
from smart_rag_worker.graph_runner import (
    effective_graph_mapping_limits,
    run_lightrag_coroutine,
)


async def _value() -> int:
    """Return a sentinel from an async function.

    Returns:
        Constant ``7``.
    """

    return 7


def test_run_lightrag_coroutine_reuses_open_loop() -> None:
    """Bind and job processing must not ``asyncio.run`` a second loop."""

    loop = asyncio.new_event_loop()
    try:
        first = run_lightrag_coroutine(_value(), loop=loop)
        second = run_lightrag_coroutine(_value(), loop=loop)
        assert (first, second) == (7, 7)
        assert loop.is_closed() is False
    finally:
        loop.close()


def test_run_lightrag_coroutine_without_loop_uses_asyncio_run() -> None:
    """Unconfigured workers still run a one-shot coroutine."""

    assert run_lightrag_coroutine(_value(), loop=None) == 7


def test_local_demo_mapping_override_is_synthetic_and_environment_bound() -> None:
    """Only reviewed synthetic local jobs receive the fixed larger caps."""

    local = WorkerSettings.model_construct(app_env=Environment.LOCAL)
    production = WorkerSettings.model_construct(app_env=Environment.PRODUCTION)
    approved_job = {
        "payload_ref": {
            "local_demo_mapping_override": True,
            "content_class": "synthetic",
            "review_approved": True,
        }
    }
    assert effective_graph_mapping_limits(local, approved_job) == (
        LOCAL_DEMO_MAX_MAPPING_ENTITIES,
        LOCAL_DEMO_MAX_MAPPING_RELATIONS,
    )
    assert effective_graph_mapping_limits(production, approved_job) == (
        MAX_MAPPING_ENTITIES,
        MAX_MAPPING_RELATIONS,
    )
    assert effective_graph_mapping_limits(
        local,
        {
            "payload_ref": {
                "local_demo_mapping_override": True,
                "content_class": "real_company",
                "review_approved": True,
            }
        },
    ) == (MAX_MAPPING_ENTITIES, MAX_MAPPING_RELATIONS)
