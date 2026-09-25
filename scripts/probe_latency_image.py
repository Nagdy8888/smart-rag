"""Print which latency-repair packets are present in this Python image.

Runs inside the ``api`` container with only the installed packages (it
must not import ``scripts``). Prints one ``L<n> present`` or
``L<n> MISSING`` line per packet in ``CHECKS`` order, then
``rerank_prompt_version=<value>`` and ``event_store_pool_max=<value>``.

Usage (PowerShell, from the repo root)::

    Get-Content scripts/probe_latency_image.py -Raw | docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml exec -T api python -
"""

from __future__ import annotations

import importlib
import importlib.util

CHECKS: tuple[tuple[str, str, str, object | None], ...] = (
    ("L0", "smart_rag_core.retrieval.profiles", "HYBRID_STAGE_TIMING_KEYS", None),
    ("L1", "smart_rag_api.services.sse.constants", "ATTACH_IDLE_POLL_SECONDS", None),
    ("L2", "smart_rag_core.sse.store", "EVENT_STORE_POOL_MAX_SIZE", None),
    ("L3", "smart_rag_api.services.sse.event_writer", "RunEventWriter", None),
    ("L4", "smart_rag_core.sse.store", "EVENT_STORE_APPEND_PIPELINED", True),
    (
        "L5",
        "smart_rag_core.retrieval.rerank_versions",
        "RERANK_PROMPT_VERSION",
        "rerank_v2",
    ),
    ("L6", "smart_rag_core.settings.postgres_pool", "QUERY_DB_POOL_MAX_SIZE", None),
    ("L7", "smart_rag_core.query_answer.versions", "ANSWER_SPAN_TARGET_CHARS", None),
)


def _attribute(module: str, name: str) -> tuple[bool, object | None]:
    """Import ``module`` and read ``name``.

    Args:
        module: Dotted module path.
        name: Attribute name.

    Returns:
        ``(found, value)``. ``found`` is False when the module or the
        attribute is missing.
    """

    try:
        if importlib.util.find_spec(module) is None:
            return False, None
        loaded = importlib.import_module(module)
    except ImportError:
        return False, None
    if not hasattr(loaded, name):
        return False, None
    value: object = getattr(loaded, name)
    return True, value


def probe_lines() -> list[str]:
    """Return one line per packet, then two info lines.

    Returns:
        ``L<n> present`` when the attribute exists and, if the check names
        an expected value, equals it; otherwise ``L<n> MISSING``. Then
        ``rerank_prompt_version=<value or n/a>`` and
        ``event_store_pool_max=<value or n/a>``.
    """

    lines: list[str] = []
    for packet, module, name, expected in CHECKS:
        found, value = _attribute(module, name)
        present = found and (expected is None or value == expected)
        lines.append(f"{packet} {'present' if present else 'MISSING'}")
    found, version = _attribute(
        "smart_rag_core.retrieval.rerank_versions", "RERANK_PROMPT_VERSION"
    )
    lines.append(f"rerank_prompt_version={version if found else 'n/a'}")
    found, pool_max = _attribute(
        "smart_rag_core.sse.store", "EVENT_STORE_POOL_MAX_SIZE"
    )
    lines.append(f"event_store_pool_max={pool_max if found else 'n/a'}")
    return lines


if __name__ == "__main__":
    for line in probe_lines():
        print(line)
