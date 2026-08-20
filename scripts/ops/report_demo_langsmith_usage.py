"""Report recent demo LangSmith token and cost totals without trace content.

Only run names, status, token counts, and USD fields are printed. Inputs,
outputs, prompts, and metadata are never serialized by this helper.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from langsmith import Client  # noqa: E402

from scripts.ops.ingest_demo_plot_slices import (  # noqa: E402
    merged_env,
    require_env,
)

SAFE_ROOT_NAMES = frozenset({"ingestion.graph", "ingestion.index"})
SAFE_SPAN_NAMES = frozenset(
    {
        "model.lightrag_llm",
        "embedding.embed",
        "openai.responses.lightrag_llm",
        "openai.embeddings",
    }
)
SAFE_USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "prompt_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
)


def _number(value: object) -> Decimal:
    """Convert an optional LangSmith numeric field to ``Decimal``.

    Args:
        value: Integer, float, decimal, string, or ``None``.

    Returns:
        Decimal value, or zero when absent.
    """

    if value is None:
        return Decimal("0")
    return Decimal(str(value))


async def recent_usage(
    *,
    client: Client,
    project_name: str,
    since: datetime,
) -> dict[str, object]:
    """Aggregate recent safe run metrics by stable run name.

    Args:
        client: Authenticated LangSmith client.
        project_name: Trace project to inspect.
        since: Inclusive UTC lower bound.

    Returns:
        Sanitized project summary and per-name token/cost aggregates.

    Side Effects:
        Performs read-only LangSmith project and trace query requests.
    """

    project = await client.aread_project(project_name=project_name)
    aggregates: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "traces": 0,
            "successful": 0,
            "errors": 0,
            "total_tokens": 0,
            "total_cost_usd": Decimal("0"),
        }
    )
    async for trace in client.traces.query(
        project_id=str(project.id),
        min_start_time=since,
        max_start_time=datetime.now(UTC),
        page_size=100,
        selects=[
            "NAME",
            "ERROR",
            "TOTAL_TOKENS",
            "TOTAL_COST",
        ],
    ):
        if trace.root_run is None:
            continue
        name = str(trace.root_run.name or "")
        if name not in SAFE_ROOT_NAMES:
            continue
        usage = trace.trace_aggregates
        aggregate = aggregates[name]
        aggregate["traces"] += 1
        if trace.root_run.error:
            aggregate["errors"] += 1
        else:
            aggregate["successful"] += 1
        if usage is not None:
            aggregate["total_tokens"] += int(usage.total_tokens or 0)
            aggregate["total_cost_usd"] += _number(usage.total_cost)

    rendered: dict[str, dict[str, object]] = {}
    for name, aggregate in sorted(aggregates.items()):
        rendered[name] = {
            **aggregate,
            "total_cost_usd": str(aggregate["total_cost_usd"]),
        }
    spans: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "runs": 0,
            "successful": 0,
            "errors": 0,
            **dict.fromkeys(SAFE_USAGE_FIELDS, Decimal("0")),
        }
    )
    async for run in client.runs.query(
        project_ids=[str(project.id)],
        min_start_time=since,
        max_start_time=datetime.now(UTC),
        page_size=100,
        selects=["NAME", "ERROR", "OUTPUTS"],
    ):
        name = str(run.name or "")
        if name not in SAFE_SPAN_NAMES:
            continue
        aggregate = spans[name]
        aggregate["runs"] += 1
        if run.error:
            aggregate["errors"] += 1
        else:
            aggregate["successful"] += 1
        raw_outputs: object = run.outputs
        outputs: Mapping[str, object] = (
            cast(Mapping[str, object], raw_outputs)
            if isinstance(raw_outputs, Mapping)
            else {}
        )
        nested = outputs.get("output")
        if isinstance(nested, Mapping):
            outputs = cast(Mapping[str, object], nested)
        for field in SAFE_USAGE_FIELDS:
            aggregate[field] += _number(outputs.get(field))

    rendered_spans: dict[str, dict[str, object]] = {}
    for name, aggregate in sorted(spans.items()):
        rendered_spans[name] = {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in aggregate.items()
        }
    return {
        "project": project_name,
        "since": since.isoformat(),
        "traces": rendered,
        "spans": rendered_spans,
        "cost_note": (
            "Trace totals and per-span fields overlap; do not add them. "
            "OpenAI invoice remains canonical."
        ),
    }


def main() -> int:
    """Print recent sanitized demo usage.

    Returns:
        Process exit code.
    """

    env = merged_env()
    project_name = env.get("LANGSMITH_PROJECT", "smart-rag").strip() or "smart-rag"
    endpoint = env.get("LANGSMITH_ENDPOINT", "").strip() or None
    client = Client(
        api_url=endpoint,
        api_key=require_env(env, "LANGSMITH_API_KEY"),
        hide_inputs=True,
        hide_outputs=True,
    )
    report = asyncio.run(
        recent_usage(
            client=client,
            project_name=project_name,
            since=datetime.now(UTC) - timedelta(hours=6),
        )
    )
    print(json.dumps(report, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
