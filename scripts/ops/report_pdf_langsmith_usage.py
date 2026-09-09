"""Print redacted LangSmith ingest usage. Never prints source text."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from langsmith import Client  # noqa: E402

from scripts.ops.ingest_demo_plot_slices import merged_env, require_env  # noqa: E402


async def _collect() -> dict[str, object]:
    """Query today's ingest traces for names, tokens, and list-price cost.

    Returns:
        Sanitized project and per-name aggregates. Inputs/outputs omitted.

    Side Effects:
        Read-only LangSmith API calls.
    """

    env = merged_env()
    project_name = env.get("LANGSMITH_PROJECT", "smart-rag-demo-3").strip()
    client = Client(
        api_url=(env.get("LANGSMITH_ENDPOINT") or None),
        api_key=require_env(env, "LANGSMITH_API_KEY"),
        hide_inputs=True,
        hide_outputs=True,
    )
    project = await client.aread_project(project_name=project_name)
    named: dict[str, dict[str, Any]] = {}
    samples: list[dict[str, object]] = []
    scanned = 0
    async for run in client.runs.query(
        project_ids=[str(project.id)],
        min_start_time=datetime(2026, 9, 9, 10, 20, tzinfo=UTC),
        max_start_time=datetime.now(UTC),
        page_size=100,
        selects=[
            "NAME",
            "ID",
            "ERROR",
            "TOTAL_TOKENS",
            "TOTAL_COST",
            "PROMPT_TOKENS",
        ],
    ):
        name = str(run.name or "")
        scanned += 1
        rec = named.setdefault(
            name,
            {"runs": 0, "tokens": 0, "cost": Decimal("0"), "errors": 0},
        )
        rec["runs"] += 1
        if run.error:
            rec["errors"] += 1
        prompt_tokens = getattr(run, "prompt_tokens", None)
        total_tokens = getattr(run, "total_tokens", None)
        token_value = int(prompt_tokens or total_tokens or 0)
        rec["tokens"] += token_value
        rec["cost"] += Decimal(str(getattr(run, "total_cost", None) or 0))
        if name in {"openai.embeddings", "embedding.embed"} and len(samples) < 6:
            extras = getattr(run, "extra", None)
            extra_keys: list[str]
            if isinstance(extras, dict):
                extra_keys = sorted(str(key) for key in cast(dict[str, object], extras))
            else:
                extra_keys = []
            samples.append(
                {
                    "name": name,
                    "id": str(run.id),
                    "prompt_tokens": prompt_tokens,
                    "total_tokens": total_tokens,
                    "total_cost": str(getattr(run, "total_cost", None)),
                    "extra_keys": extra_keys,
                    "error": bool(run.error),
                }
            )
    rendered = {
        name: {
            "runs": rec["runs"],
            "tokens": rec["tokens"],
            "cost_usd": str(rec["cost"]),
            "errors": rec["errors"],
        }
        for name, rec in sorted(named.items())
    }
    return {
        "project_name": project_name,
        "project_id": str(project.id),
        "export_io": env.get("LANGSMITH_EXPORT_IO", ""),
        "hide_inputs": env.get("LANGSMITH_HIDE_INPUTS", ""),
        "runs_scanned": scanned,
        "by_name": rendered,
        "samples": samples,
    }


def main() -> int:
    """Print JSON usage. Exit 0 on success.

    Returns:
        Process exit code.
    """

    report = asyncio.run(_collect())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
