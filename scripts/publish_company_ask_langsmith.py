#!/usr/bin/env python3
"""Publish private company-Ask dual-metric results to a LangSmith experiment.

Reads gitignored gold + answers from ``.private-eval/``, syncs a versioned
dataset, and uploads an experiment with dual-metric feedback. Local
``APP_ENV`` plus ``--upload-private-content`` are required. Holdout stays
sealed. This is not a Combined +10pp quality claim.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from company_ask_langsmith_enrich import (  # noqa: E402
    enrich_diagnosis_signals,
    enrich_run_usage,
    score_results_for_enrichment,
)
from smart_rag_core.evaluation.company_ask_langsmith import (  # noqa: E402
    DEFAULT_COMPANY_ASK_LANGSMITH_PROJECT,
    CompanyAskLangSmithError,
    load_gold_and_answers,
    plan_company_ask_langsmith_publish,
    publish_company_ask_experiment,
)
from smart_rag_core.evaluation.company_ask_regression import (  # noqa: E402
    AskRegressionConfigError,
)
from smart_rag_core.settings import setdefault_process_environ  # noqa: E402


def _load_repo_env() -> None:
    """Fill missing process env from repo ``.env`` without overriding exports.

    Side Effects:
        Reads ``.env`` with ``setdefault``. Values are not logged.
    """

    path = REPO / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        name = key.strip()
        if not name:
            continue
        setdefault_process_environ(name, value.strip().strip('"').strip("'"))


def main(argv: list[str] | None = None) -> int:
    """Plan or publish a company-Ask LangSmith experiment.

    Args:
        argv: Optional CLI arguments excluding the program name.

    Returns:
        ``0`` on success, ``2`` when gates or configuration fail closed.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Publish private company-Ask dual-metric answers as a LangSmith "
            "dataset + experiment. Requires APP_ENV=local and "
            "--upload-private-content for live upload."
        )
    )
    parser.add_argument(
        "--gold",
        type=Path,
        required=True,
        help="Gitignored .private-eval gold JSON array.",
    )
    parser.add_argument(
        "--answers",
        type=Path,
        required=True,
        help="Answers JSON from run_company_ask.py --answers-out.",
    )
    parser.add_argument(
        "--stage-export",
        type=Path,
        default=None,
        help="Optional stage-export JSON overlay.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional local redacted dual-metric summary JSON.",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_COMPANY_ASK_LANGSMITH_PROJECT,
        help=(
            "LangSmith project to open in the UI "
            f"(default {DEFAULT_COMPANY_ASK_LANGSMITH_PROJECT})."
        ),
    )
    parser.add_argument(
        "--experiment-prefix",
        default=None,
        help="Optional sanitized experiment prefix suffix.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate gold/answers and print a plan; no LangSmith writes.",
    )
    parser.add_argument(
        "--upload-private-content",
        action="store_true",
        help=(
            "Required for live upload. Sends prompts, answers, and gold "
            "phrases to LangSmith. Local APP_ENV only."
        ),
    )
    args = parser.parse_args(argv)
    _load_repo_env()
    try:
        questions, answer_rows = load_gold_and_answers(
            gold_path=args.gold,
            answers_path=args.answers,
            stage_export_path=args.stage_export,
        )
    except (AskRegressionConfigError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": "load_failed", "detail": str(exc)}), file=sys.stderr)
        return 2

    if args.dry_run:
        plan = plan_company_ask_langsmith_publish(
            questions=questions,
            project_name=args.project,
            upload_private_content=args.upload_private_content,
        )
        print(json.dumps(asdict(plan), indent=2, sort_keys=True))
        return 0

    app_env = os.environ.get("APP_ENV", "").strip() or "local"
    # Experiments land in the project named here, not the Ask-trace project.
    os.environ["LANGSMITH_PROJECT"] = args.project
    os.environ["LANGCHAIN_PROJECT"] = args.project
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    try:
        from langsmith import Client

        scored = score_results_for_enrichment(questions, answer_rows)
        diagnosis = enrich_diagnosis_signals(
            questions,
            answer_rows=answer_rows,
            results=scored,
        )
        usage = enrich_run_usage(answer_rows)
        client = Client()
        summary = publish_company_ask_experiment(
            client,
            questions=questions,
            answer_rows=answer_rows,
            app_env=app_env,
            project_name=args.project,
            upload_private_content=args.upload_private_content,
            experiment_prefix=args.experiment_prefix,
            summary_out=args.out,
            diagnosis=diagnosis,
            usage=usage,
        )
    except CompanyAskLangSmithError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    except AskRegressionConfigError as exc:
        print(
            json.dumps({"error": "score_failed", "detail": str(exc)}), file=sys.stderr
        )
        return 2
    except Exception as exc:
        print(
            json.dumps({"error": "langsmith_publish_failed", "detail": str(exc)}),
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            {
                "dataset_name": summary.dataset_name,
                "project_name": summary.project_name,
                "case_count": summary.case_count,
                "gold_content_hash": summary.gold_content_hash,
                "experiment_url": summary.experiment_url,
                "strict_pass": summary.strict_pass,
                "grounded_fact_pass": summary.grounded_fact_pass,
                "deadline_failures": summary.deadline_failures,
                "total_cost_usd": summary.total_cost_usd,
                "total_tokens": summary.total_tokens,
                "dry_run": summary.dry_run,
                "open_project_hint": (
                    f"Open LangSmith project '{summary.project_name}' → "
                    "Datasets / Experiments"
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
