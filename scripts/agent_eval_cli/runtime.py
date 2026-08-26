"""Live-run helpers and CLI main for bounded LangSmith agent evaluation."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import Callable, Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any, TextIO, cast
from uuid import UUID, uuid5

from smart_rag_core.evaluation.agent_eval import (
    AgentEvalOutput,
    AgentEvalReference,
    AgentJudgeResult,
    output_from_graph_state,
)
from smart_rag_core.evaluation.langsmith_agent_runner import (
    AdmittedEvalRun,
    ReservationLifecycle,
)
from smart_rag_core.evaluation.ranked_ids import (
    load_gold_id_sidecar,
    sidecar_has_unmapped_chunks,
)
from smart_rag_core.query_answer.versions import (
    EVAL_JUDGE_MODEL_ID,
    EVAL_JUDGE_PROMPT_SHA256,
    EVAL_JUDGE_PROMPT_VERSION,
    EVAL_JUDGE_USD_PER_1K_INPUT,
    EVAL_JUDGE_USD_PER_1K_OUTPUT,
)
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.settings import SharedSettings

from agent_eval_cli.config import (
    EXPERIMENT_NAMESPACE,
    AgentEvalCliError,
)


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
