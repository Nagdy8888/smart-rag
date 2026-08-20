#!/usr/bin/env python3
"""Bounded LangSmith agent evaluation over synthetic development cases.

Dry-run validates selection and ceilings with no LangSmith, database, agent,
or provider work. Live execution admits the production query graph in-process.
Holdout stays sealed. This tool does not claim Combined +10pp.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TextIO, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

# ruff: noqa: E402 — repo root must precede local package imports for CLI use.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from smart_rag_core.evaluation.agent_eval import (
    AgentEvalError,
    AgentEvalOutput,
    AgentEvalReference,
    AgentJudgeResult,
    output_from_graph_state,
    select_development_cases,
)
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.langsmith_agent_runner import (
    AdmittedEvalRun,
    ReservationLifecycle,
    plan_dry_run,
    run_bounded_evaluate,
)
from smart_rag_core.evaluation.online import OnlineEvalError
from smart_rag_core.evaluation.ranked_ids import (
    load_gold_id_sidecar,
    sidecar_has_unmapped_chunks,
)
from smart_rag_core.query_answer.versions import (
    ANSWER_MODEL_ID,
    ANSWER_PROMPT_VERSION,
    EVAL_JUDGE_MODEL_ID,
    EVAL_JUDGE_PROMPT_SHA256,
    EVAL_JUDGE_PROMPT_VERSION,
    EVAL_JUDGE_USD_PER_1K_INPUT,
    EVAL_JUDGE_USD_PER_1K_OUTPUT,
)
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.settings import SharedSettings, setdefault_process_environ
from smart_rag_core.settings.backend import load_backend_settings

DEFAULT_SIDECAR = (
    _ROOT
    / "tests"
    / "fixtures"
    / "evaluation"
    / "phase4"
    / "runtime"
    / "gold_id_map.json"
)
DEFAULT_PARADE_PORT = "54329"
EXPERIMENT_NAMESPACE = uuid5(NAMESPACE_URL, "smart-rag-agent-eval")


class AgentEvalCliError(RuntimeError):
    """CLI preflight failure. The message is a stable token without secrets."""


def load_repo_env() -> None:
    """Fill missing process env from repo ``.env`` without overriding exports.

    Side Effects:
        Reads ``.env`` with ``setdefault``. Values are not logged.
    """

    path = _ROOT / ".env"
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


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse bounded agent-eval CLI flags.

    Args:
        argv: Argument vector excluding the program name.

    Returns:
        Parsed namespace.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Bounded LangSmith agent evaluation on synthetic development cases. "
            "Holdout stays sealed. Not a quality claim."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate selection and print the plan. No writes or provider calls.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum development cases (1..20). Default 3.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        dest="case_ids",
        help="Repeatable development case id. Qualification/holdout ids fail closed.",
    )
    parser.add_argument(
        "--class",
        action="append",
        default=[],
        dest="query_classes",
        help="Repeatable query-class filter. Unsupported classes fail closed.",
    )
    parser.add_argument(
        "--live-agent",
        action="store_true",
        help="Allow MOCK_MODEL_MODE=false. Required for --llm-judge.",
    )
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="One bounded judge call per case. Requires --live-agent.",
    )
    parser.add_argument(
        "--max-usd",
        default="2.00",
        help="Job USD ceiling. Default 2.00. Values below 0 or above 2.00 fail.",
    )
    parser.add_argument(
        "--allow-bm25-degraded",
        action="store_true",
        help="Permit dense+term fallback when ParadeDB is unavailable.",
    )
    parser.add_argument(
        "--experiment-prefix",
        default=None,
        help="Optional sanitized experiment suffix (alnum, hyphen, underscore).",
    )
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=DEFAULT_SIDECAR,
        help="Phase 4 gold-id sidecar path. Live runs fail if unmapped.",
    )
    return parser.parse_args(argv)


def print_json(payload: dict[str, object], *, stream: TextIO = sys.stdout) -> None:
    """Write a secret-free JSON object.

    Args:
        payload: JSON-compatible mapping.
        stream: Output stream.
    """

    stream.write(json.dumps(payload, indent=2, sort_keys=True))
    stream.write("\n")


def lookup_member_caller(connection: Any) -> CallerContext | None:
    """Load one active member-or-better caller from canonical profiles.

    Args:
        connection: Open ``psycopg`` connection.

    Returns:
        ``CallerContext`` or None when no profile exists.
    """

    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        cursor.execute("SELECT app.current_authorization_version()")
        version_row = cursor.fetchone()
        cursor.execute(
            """
            SELECT user_id::text, role::text
            FROM app.profiles
            WHERE disabled_at IS NULL
            ORDER BY CASE role::text
              WHEN 'member' THEN 0
              WHEN 'viewer' THEN 1
              WHEN 'admin' THEN 2
              ELSE 3
            END
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    if row is None or version_row is None:
        return None
    return CallerContext(
        user_id=str(row[0]),
        role=UserRole(str(row[1])),
        authorization_version=int(str(version_row[0])),
        disabled=False,
    )


def require_sidecar(path: Path) -> None:
    """Fail closed when the Phase 4 sidecar is missing or unmapped.

    Args:
        path: Sidecar JSON path.

    Raises:
        AgentEvalCliError: Sidecar is missing or has null chunk UUIDs.
    """

    if not path.is_file():
        raise AgentEvalCliError("sidecar_missing")
    sidecar = load_gold_id_sidecar(path)
    if sidecar_has_unmapped_chunks(sidecar):
        raise AgentEvalCliError("sidecar_unmapped")


def paradedb_reachable(settings: SharedSettings) -> bool:
    """Return whether ParadeDB accepts a short Postgres probe.

    Args:
        settings: Shared process settings.

    Returns:
        True when ``paradedb_url`` connects.
    """

    url = settings.paradedb_url
    if url is None:
        return False
    try:
        import psycopg

        with psycopg.connect(str(url), connect_timeout=8) as connection:
            connection.execute("SELECT 1")
    except Exception:
        return False
    return True


def gateway_judge(
    *,
    settings: SharedSettings,
    cases_by_id: dict[str, Any],
) -> Any:
    """Build a one-call-per-case judge that uses the shared model gateway.

    Args:
        settings: Process settings.
        cases_by_id: Development cases keyed by id, used only for the query.

    Returns:
        Callable compatible with ``OncePerCaseJudge``.
    """

    from smart_rag_agents.prompts.registry import prompt_text
    from smart_rag_core.gateways.model import (
        EvalJudgeModelRequest,
        create_model_gateway,
    )

    gateway = create_model_gateway(settings)
    instructions = prompt_text(EVAL_JUDGE_PROMPT_VERSION)

    def judge(
        output: AgentEvalOutput, reference: AgentEvalReference
    ) -> AgentJudgeResult:
        """Invoke one bounded judge call for ``output.case_id``.

        Args:
            output: Graph output.
            reference: Frozen reference.

        Returns:
            Typed judge result. Failures are named, never raised.
        """

        case = cases_by_id.get(output.case_id)
        question = str(getattr(case, "query", "") or output.case_id)
        try:
            request = EvalJudgeModelRequest(
                prompt_version=EVAL_JUDGE_PROMPT_VERSION,
                prompt_sha256=EVAL_JUDGE_PROMPT_SHA256,
                prompt_text=instructions,
                model_id=EVAL_JUDGE_MODEL_ID,
                question=question[:2000],
                acceptable_answers=tuple(reference.acceptable_answers)[:8],
                answer_text=output.answer_text[:16_384],
                answer_status=output.answer_status or "complete",
                evidence_ids=tuple(output.selected_evidence_ids)[:24],
                remaining_deadline_seconds=30.0,
            )
            response = asyncio.run(gateway.generate_eval_judge(request))
            payload = response.payload
            cost = Decimal(int(response.input_tokens)) / Decimal(1000) * Decimal(
                EVAL_JUDGE_USD_PER_1K_INPUT
            ) + Decimal(int(response.output_tokens)) / Decimal(1000) * Decimal(
                EVAL_JUDGE_USD_PER_1K_OUTPUT
            )
            return AgentJudgeResult(
                correctness=float(payload.get("correctness") or 0.0),
                groundedness=float(payload.get("groundedness") or 0.0),
                refusal_quality=float(payload.get("refusal_quality") or 0.0),
                rationale=str(payload.get("rationale") or "")[:240],
                cost_usd=format(cost, "f"),
                failed=False,
            )
        except Exception:
            return AgentJudgeResult(
                correctness=0.0,
                groundedness=0.0,
                refusal_quality=0.0,
                rationale="",
                cost_usd="0",
                failed=True,
                failure_kind="judge_failed",
            )

    return judge


def live_lifecycle(
    *,
    settings: SharedSettings,
    caller: CallerContext,
    postgres_url: str,
    experiment_id: UUID,
    graph_degraded: bool,
) -> ReservationLifecycle:
    """Build admit/invoke/persist/settle closures for the production graph.

    Args:
        settings: Process settings.
        caller: Active synthetic member.
        postgres_url: app_api DSN. Never printed.
        experiment_id: Stable id for idempotency keys.
        graph_degraded: Whether graph retrieve is unbound.

    Returns:
        Reservation lifecycle used as the LangSmith target.
    """

    from smart_rag_agents.query.graph import compile_query_graph, pending_query_state
    from smart_rag_api.services.conversations import ConversationService
    from smart_rag_api.services.query_graph_runtime import (
        build_query_graph_deps,
        build_query_process_bindings,
        open_run_app_api_connection,
    )
    from smart_rag_api.services.query_runs import QueryRunService
    from smart_rag_core.observability.query_run_trace import (
        invoke_traced_query_agent_eval,
    )
    from smart_rag_core.query_admission.service import true_up_query_reservation
    from smart_rag_core.sse.store import PostgresRunEventStore

    conversations = ConversationService(postgres_url)
    runs = QueryRunService(postgres_url)
    events = PostgresRunEventStore(postgres_url)
    parade = str(settings.paradedb_url) if settings.paradedb_url is not None else None
    bindings = build_query_process_bindings(
        settings=settings,
        supabase_dsn=postgres_url,
        paradedb_url=parade,
    )
    connections: dict[str, Any] = {}

    def admit(inputs: Mapping[str, Any]) -> AdmittedEvalRun:
        """Create a conversation and admit one Composite envelope.

        Args:
            inputs: LangSmith example inputs.

        Returns:
            Admitted run handles.
        """

        case_id = str(inputs["case_id"])
        query = str(inputs["query"])
        conversation = conversations.create(caller, title=f"agent-eval {case_id}")
        idempotency = uuid5(EXPERIMENT_NAMESPACE, f"{experiment_id}:{case_id}")
        context, _path = runs.submit_auto_message(
            caller,
            conversation_id=conversation.conversation_id,
            idempotency_key=idempotency,
            message=query,
        )
        return AdmittedEvalRun(
            case_id=case_id,
            run_id=str(context.run_id),
            conversation_id=str(context.conversation_id),
            reservation_id=str(context.reservation_id),
            user_id=str(context.user_id),
            authorized_runtime=context.model_dump(mode="json"),
            query=query,
        )

    def invoke(admitted: AdmittedEvalRun) -> AgentEvalOutput:
        """Invoke the compiled production graph under a redacted parent span.

        Args:
            admitted: Admitted handles.

        Returns:
            Normalized evaluation output.
        """

        connection = open_run_app_api_connection(postgres_url)
        connections[admitted.run_id] = connection
        deps = build_query_graph_deps(
            bindings=bindings,
            connection=connection,
            cancel_check=lambda: False,
        )
        compiled = compile_query_graph(deps)
        state = pending_query_state(
            authorized_runtime=admitted.authorized_runtime,
            user_query=admitted.query,
        )
        started = time.perf_counter()

        def thunk() -> dict[str, Any]:
            """Invoke the compiled graph once.

            Returns:
                Final graph state mapping.
            """

            invoke = cast(
                Callable[[object], object],
                compiled.invoke,  # pyright: ignore[reportUnknownMemberType]
            )
            result = invoke(state)
            if isinstance(result, dict):
                return dict(cast(dict[str, Any], result))
            return {}

        final = invoke_traced_query_agent_eval(
            thunk,
            settings=settings,
            case_id=admitted.case_id,
            run_id=admitted.run_id,
            user_id=admitted.user_id,
            conversation_id=admitted.conversation_id,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        fusion_obj: object = final.get("fusion")
        bm25 = None
        degraded = graph_degraded
        if isinstance(fusion_obj, dict):
            fusion = cast(dict[str, object], fusion_obj)
            reason = fusion.get("fallback_reason")
            if isinstance(reason, str) and reason:
                bm25 = reason
                if "graph" in reason:
                    degraded = True
        return output_from_graph_state(
            admitted.case_id,
            final,
            run_id=admitted.run_id,
            conversation_id=admitted.conversation_id,
            latency_ms=elapsed_ms,
            agent_cost_usd="0",
            bm25_fallback=bm25,
            graph_degraded=degraded,
        )

    def persist(admitted: AdmittedEvalRun, output: AgentEvalOutput) -> None:
        """Append one terminal SSE event for the admitted run.

        Args:
            admitted: Admitted handles.
            output: Normalized output.
        """

        event_type = "completed"
        if output.failure_kind:
            event_type = "error"
        elif output.answer_status == "partial":
            event_type = "partial"
        events.append(
            caller,
            run_id=UUID(admitted.run_id),
            event_type=event_type,
            payload={"status": output.answer_status or event_type},
        )

    def settle(admitted: AdmittedEvalRun) -> None:
        """Always true-up the reservation and close the run connection.

        Args:
            admitted: Admitted handles.
        """

        connection = connections.pop(admitted.run_id, None)
        opened_here = False
        if connection is None:
            connection = open_run_app_api_connection(postgres_url)
            opened_here = True
        try:
            true_up_query_reservation(
                connection,
                caller=caller,
                reservation_id=UUID(admitted.reservation_id),
            )
            connection.commit()
        finally:
            if opened_here or admitted.run_id not in connections:
                connection.close()

    return ReservationLifecycle(
        admit=admit,
        invoke=invoke,
        persist=persist,
        settle=settle,
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
    try:
        if args.dry_run:
            summary = plan_dry_run(
                limit=args.limit,
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
        selection = select_development_cases(
            limit=args.limit,
            case_ids=tuple(args.case_ids),
            query_classes=tuple(args.query_classes),
            holdout_access=HoldoutAccess.denied(),
        )
        experiment_id = uuid4()
        lifecycle = live_lifecycle(
            settings=settings,
            caller=caller,
            postgres_url=postgres_url,
            experiment_id=experiment_id,
            graph_degraded=False,
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
    except (AgentEvalError, OnlineEvalError, AgentEvalCliError) as exc:
        print_json({"error": str(exc)}, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
