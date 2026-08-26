"""CLI entry for bounded LangSmith agent evaluation."""

from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from smart_rag_core.evaluation.agent_eval import (
    AgentEvalError,
    select_development_cases,
)
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.langsmith_agent_runner import (
    plan_dry_run,
    run_bounded_evaluate,
)
from smart_rag_core.evaluation.online import OnlineEvalError
from smart_rag_core.evaluation.online_agent_runner import (
    plan_online_dry_run,
    run_online_eval_batch,
)
from smart_rag_core.evaluation.online_envelope import OnlineEnvelopeError
from smart_rag_core.evaluation.online_suite import (
    OnlineSuiteError,
    load_online_eval_selection,
)
from smart_rag_core.query_answer.versions import (
    ANSWER_MODEL_ID,
    ANSWER_PROMPT_VERSION,
    EVAL_JUDGE_MODEL_ID,
    EVAL_JUDGE_PROMPT_VERSION,
)
from smart_rag_core.settings import SharedSettings
from smart_rag_core.settings.backend import load_backend_settings

from agent_eval_cli.config import (
    DEFAULT_PARADE_PORT,
    AgentEvalCliError,
    load_repo_env,
    parse_args,
)
from agent_eval_cli.runtime import (
    gateway_judge,
    live_lifecycle,
    lookup_member_caller,
    paradedb_reachable,
    print_json,
    require_sidecar,
)


def main(argv: list[str] | None = None) -> int:
    """Run dry-run planning or a bounded LangSmith experiment.

    Args:
        argv: Optional CLI arguments excluding the program name.

    Returns:
        ``0`` on a completed plan or experiment. ``2`` when bounds, holdout,
        sidecar, or preflight checks fail closed.
    """

    args = parse_args(argv)
    load_repo_env()
    try:
        max_usd = Decimal(str(args.max_usd))
    except (InvalidOperation, ValueError):
        print_json({"error": "max_usd_invalid"}, stream=sys.stderr)
        return 2
    if args.llm_judge and not args.live_agent:
        print_json({"error": "judge_requires_live_agent"}, stream=sys.stderr)
        return 2
    if args.online_only and args.llm_judge:
        print_json({"error": "online_path_forbids_local_judge"}, stream=sys.stderr)
        return 2
    if args.online_only and args.experiment_prefix:
        print_json(
            {"error": "online_path_forbids_experiment_prefix"},
            stream=sys.stderr,
        )
        return 2
    offline_limit = args.limit if args.limit is not None else 3
    try:
        if args.online_only and args.dry_run:
            summary = plan_online_dry_run(
                limit=args.limit,
                case_ids=tuple(args.case_ids),
                query_classes=tuple(args.query_classes),
                holdout_access=HoldoutAccess.denied(),
                mock_mode=not args.live_agent,
                max_usd=max_usd,
            )
            print_json(summary.model_dump(mode="json"))
            return 0
        if args.dry_run:
            summary = plan_dry_run(
                limit=offline_limit,
                case_ids=tuple(args.case_ids),
                query_classes=tuple(args.query_classes),
                holdout_access=HoldoutAccess.denied(),
                mock_mode=not args.live_agent,
                max_usd=max_usd,
                judge_enabled=args.llm_judge,
                experiment_prefix=args.experiment_prefix,
            )
            print_json(summary.model_dump(mode="json"))
            return 0

        settings = SharedSettings()
        if args.live_agent:
            if settings.mock_model_mode:
                print_json(
                    {"error": "live_agent_requires_live_models"},
                    stream=sys.stderr,
                )
                return 2
            if not settings.openai_api_key:
                print_json({"error": "openai_api_key_required"}, stream=sys.stderr)
                return 2
            if not settings.allows_unsigned_local_live_providers():
                print_json(
                    {"error": "live_provider_waiver_required"},
                    stream=sys.stderr,
                )
                return 2
        elif not settings.mock_model_mode:
            print_json({"error": "mock_model_mode_required"}, stream=sys.stderr)
            return 2
        if args.online_only and settings.app_env != "local":
            print_json({"error": "local_environment_required"}, stream=sys.stderr)
            return 2
        if not settings.langsmith_tracing:
            print_json({"error": "langsmith_tracing_required"}, stream=sys.stderr)
            return 2
        if not settings.langsmith_api_key:
            print_json({"error": "langsmith_api_key_required"}, stream=sys.stderr)
            return 2
        if not settings.langsmith_project:
            print_json({"error": "langsmith_project_required"}, stream=sys.stderr)
            return 2
        require_sidecar(args.sidecar)
        parade_ok = paradedb_reachable(settings)
        if not parade_ok and not args.allow_bm25_degraded:
            print_json(
                {
                    "error": "paradedb_unavailable",
                    "hint": (
                        f"localhost:{DEFAULT_PARADE_PORT} or pass --allow-bm25-degraded"
                    ),
                },
                stream=sys.stderr,
            )
            return 2
        backend = load_backend_settings()
        postgres_secret = backend.supabase_db_url
        postgres_url = (
            postgres_secret.get_secret_value() if postgres_secret is not None else ""
        )
        if not postgres_url:
            print_json({"error": "supabase_unavailable"}, stream=sys.stderr)
            return 2
        import psycopg
        from langsmith import Client

        with psycopg.connect(postgres_url) as probe:
            caller = lookup_member_caller(probe)
        if caller is None:
            print_json({"error": "synthetic_member_missing"}, stream=sys.stderr)
            return 2
        experiment_id = uuid4()
        lifecycle = live_lifecycle(
            settings=settings,
            caller=caller,
            postgres_url=postgres_url,
            experiment_id=experiment_id,
            graph_degraded=False,
        )
        if args.online_only:
            selection = load_online_eval_selection(
                limit=args.limit,
                case_ids=tuple(args.case_ids),
                query_classes=tuple(args.query_classes),
                holdout_access=HoldoutAccess.denied(),
            )
            summary = run_online_eval_batch(
                lifecycle,
                selection,
                settings=settings,
                bm25_degraded=not parade_ok,
            )
            print_json(summary.model_dump(mode="json"))
            return 0
        selection = select_development_cases(
            limit=offline_limit,
            case_ids=tuple(args.case_ids),
            query_classes=tuple(args.query_classes),
            holdout_access=HoldoutAccess.denied(),
        )
        judge = None
        if args.llm_judge:
            judge = gateway_judge(
                settings=settings,
                cases_by_id={case.case_id: case for case in selection.cases},
            )
        summary, _result = run_bounded_evaluate(
            Client(),
            selection=selection,
            target=lifecycle.run,
            mock_mode=not args.live_agent,
            max_usd=max_usd,
            judge=judge,
            judge_enabled=args.llm_judge,
            experiment_prefix=args.experiment_prefix,
            bm25_degraded=not parade_ok,
            graph_degraded=False,
            remaining_judge_usd=max_usd,
            extra_metadata={
                "answer_model_id": ANSWER_MODEL_ID,
                "answer_prompt_version": ANSWER_PROMPT_VERSION,
                "eval_judge_model_id": EVAL_JUDGE_MODEL_ID,
                "eval_judge_prompt_version": EVAL_JUDGE_PROMPT_VERSION,
                "holdout_opened": False,
            },
        )
        print_json(summary.model_dump(mode="json"))
        return 0
    except (
        AgentEvalError,
        OnlineEvalError,
        OnlineSuiteError,
        OnlineEnvelopeError,
        AgentEvalCliError,
    ) as exc:
        print_json({"error": str(exc)}, stream=sys.stderr)
        return 2
