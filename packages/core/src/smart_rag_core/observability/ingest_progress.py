"""TTY ingest progress lines with ``[hybrid]`` / ``[graph]`` prefixes.

The laptop worker is one process. Demo operators split the **view** with
``Select-String`` on these prefixes. Messages carry counts and reason codes
only: no filenames, titles, bytes, or source text.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from smart_rag_core.schema.enums import JobErrorCategory

LOGGER = logging.getLogger("smart_rag.ingest_progress")

IngestPipeline = Literal["hybrid", "graph"]

_PIPELINES: frozenset[str] = frozenset({"hybrid", "graph"})
_STAGE_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REASON_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def log_ingest_progress(
    pipeline: IngestPipeline,
    stage: str,
    job_id: UUID | str,
    *,
    error_category: JobErrorCategory | str | None = None,
    reason_code: str | None = None,
    **counts: object,
) -> None:
    """Emit one JSON-log message starting with ``[hybrid]`` or ``[graph]``.

    Args:
        pipeline: ``hybrid`` (scan/parse/embed/BM25) or ``graph`` (LightRAG).
        stage: Short token such as ``scan``, ``embed_batch``, ``hybrid_ready``.
        job_id: Claimed job identifier. Bound correlation still wins in JSON.
        error_category: Optional job error category on failure lines.
        reason_code: Optional short failure token. Non-token values are
            replaced with ``invalid_reason`` so plot text cannot ride along.
        **counts: Integer or bool counters (chunks, batch_index, batch_count).
            Non-numeric values are ignored so callers cannot log filenames.

    Raises:
        ValueError: If ``pipeline`` is not ``hybrid`` or ``graph``, or if
            ``stage`` is not a safe token.

    Side Effects:
        Writes one INFO log line. Idle poll loops must not call this.
    """

    if pipeline not in _PIPELINES:
        raise ValueError("ingest_progress_pipeline_invalid")
    if _STAGE_TOKEN.fullmatch(stage) is None:
        raise ValueError("ingest_progress_stage_invalid")
    parts = [f"[{pipeline}]", f"job={job_id}", f"stage={stage}"]
    for key, value in sorted(counts.items()):
        if _STAGE_TOKEN.fullmatch(key) is None:
            continue
        if isinstance(value, bool):
            parts.append(f"{key}={int(value)}")
        elif isinstance(value, int) and not isinstance(value, bool):
            parts.append(f"{key}={value}")
    if error_category is not None:
        category_label = (
            error_category.value
            if isinstance(error_category, JobErrorCategory)
            else str(error_category)
        )
        if _REASON_TOKEN.fullmatch(category_label) is None:
            category_label = "invalid_error_category"
        parts.append(f"error_category={category_label}")
    if reason_code is not None:
        reason_label = (
            reason_code if _REASON_TOKEN.fullmatch(reason_code) else "invalid_reason"
        )
        parts.append(f"reason_code={reason_label}")
    LOGGER.info("%s", " ".join(parts))


def ingest_progress_message_is_safe(
    message: str, *, needles: Mapping[str, str] | tuple[str, ...] = ()
) -> bool:
    """Return whether a rendered progress line omits canary needles.

    Args:
        message: Formatter output or log record message.
        needles: Substrings that must never appear.

    Returns:
        True when every needle is absent.
    """

    lowered = message.lower()
    values: tuple[str, ...]
    if isinstance(needles, Mapping):
        values = tuple(str(item) for item in needles.values())
    else:
        values = needles
    return all(needle.lower() not in lowered for needle in values if needle)
