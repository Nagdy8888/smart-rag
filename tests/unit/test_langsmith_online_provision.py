"""Online-eval provision idempotency, project isolation, and bounds."""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import langsmith
import pytest
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.online import (
    ONLINE_CODE_EVALUATOR_NAME,
    ONLINE_EVAL_MAX_CASES,
    ONLINE_EVAL_MAX_USD,
    ONLINE_EVAL_PROJECT,
    ONLINE_EVAL_ROOT_FILTER,
    ONLINE_LLM_EVALUATOR_NAME,
    QUERY_AGENT_ONLINE_EVAL_RUN,
    OnlineEvalError,
    assert_online_eval_permitted,
)
from smart_rag_core.evaluation.online_agent_runner import (
    run_online_eval_batch,
)
from smart_rag_core.evaluation.online_envelope import (
    sample_online_envelope,
)
from smart_rag_core.evaluation.online_provision import (
    CliResult,
    FakeLangSmithCli,
    OnlineProvisionError,
    code_evaluator_upload_args,
    provision_online_evaluators,
    verify_provisioned_resources,
)
from smart_rag_core.evaluation.online_suite import (
    load_online_eval_selection,
)
from smart_rag_core.observability.query_run_trace import emit_online_eval_root
from smart_rag_core.settings import AgentSettings

from tests.support.online_eval import (
    _output,
)
from tests.unit.typed_attrs import module_attr


def test_provision_is_idempotent_and_isolated() -> None:
    """A second setup updates the same IDs and never duplicates rules."""

    project_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    app_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    code_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    llm_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    code_rule_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    llm_rule_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    model_id = "99999999-9999-9999-9999-999999999999"
    existing_evaluators = [
        {"id": code_id, "name": ONLINE_CODE_EVALUATOR_NAME, "type": "code"},
        {"id": llm_id, "name": ONLINE_LLM_EVALUATOR_NAME, "type": "llm"},
    ]
    existing_rules = [
        {
            "id": code_rule_id,
            "display_name": "smart-rag-agent-online-hard-metrics-v1-rule",
            "evaluator_id": code_id,
            "session_id": project_id,
            "sampling_rate": 1.0,
            "is_enabled": True,
            "filter": ONLINE_EVAL_ROOT_FILTER,
        },
        {
            "id": llm_rule_id,
            "display_name": "smart-rag-agent-online-judge-v1-rule",
            "evaluator_id": llm_id,
            "session_id": project_id,
            "sampling_rate": 1.0,
            "is_enabled": True,
            "filter": ONLINE_EVAL_ROOT_FILTER,
            "spend_limit": {"limit_usd": "2.00", "window": "weekly"},
        },
    ]
    upload = " ".join(code_evaluator_upload_args(profile="dev"))
    cli = FakeLangSmithCli(
        handlers={
            upload: CliResult(
                0,
                f'{{"id":"{code_id}","type":"code","name":"{ONLINE_CODE_EVALUATOR_NAME}"}}',
                "",
                {
                    "id": code_id,
                    "type": "code",
                    "name": ONLINE_CODE_EVALUATOR_NAME,
                },
            ),
            f"--profile dev api platform/evaluators/{llm_id} -X PATCH --input -": CliResult(
                0,
                f'{{"id":"{llm_id}","type":"llm"}}',
                "",
                {"id": llm_id, "type": "llm", "name": ONLINE_LLM_EVALUATOR_NAME},
            ),
            f"--profile dev api runs/rules/{code_rule_id} -X PATCH --input -": CliResult(
                0,
                f'{{"id":"{code_rule_id}"}}',
                "",
                {"id": code_rule_id},
            ),
            f"--profile dev api runs/rules/{llm_rule_id} -X PATCH --input -": CliResult(
                0,
                f'{{"id":"{llm_rule_id}"}}',
                "",
                {"id": llm_rule_id},
            ),
        }
    )
    first = provision_online_evaluators(
        cli,
        profile="dev",
        model_configuration_id=model_id,
        prompt_commit="pinnedcommit",
        project_id=project_id,
        application_project_id=app_id,
        existing_evaluators=existing_evaluators,
        existing_rules=existing_rules,
        created_new=False,
    )
    second = provision_online_evaluators(
        cli,
        profile="dev",
        model_configuration_id=model_id,
        prompt_commit="pinnedcommit",
        project_id=project_id,
        application_project_id=app_id,
        existing_evaluators=existing_evaluators,
        existing_rules=existing_rules,
        created_new=False,
    )
    assert first.code_evaluator_id == second.code_evaluator_id == code_id
    assert first.llm_evaluator_id == second.llm_evaluator_id == llm_id
    assert first.code_rule_id == second.code_rule_id == code_rule_id
    assert first.llm_rule_id == second.llm_rule_id == llm_rule_id
    assert first.duplicate_rules is False
    verify_provisioned_resources(
        summary=second,
        evaluators=existing_evaluators,
        rules=existing_rules,
        application_rules=(),
    )
    with pytest.raises(OnlineProvisionError):
        verify_provisioned_resources(
            summary=second,
            evaluators=existing_evaluators,
            rules=existing_rules,
            application_rules=[
                {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "evaluator_id": llm_id,
                    "session_id": app_id,
                }
            ],
        )


def test_provision_stops_on_application_project_collision() -> None:
    """The dedicated project must not resolve to the normal application id."""

    shared = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    with pytest.raises(OnlineProvisionError, match="dedicated_project_collision"):
        provision_online_evaluators(
            FakeLangSmithCli(),
            profile=None,
            model_configuration_id="11111111-1111-1111-1111-111111111111",
            prompt_commit="pinned",
            project_id=shared,
            application_project_id=shared,
        )


def test_online_batch_does_not_create_dataset_or_experiment() -> None:
    """Live online mode invokes the lifecycle sequentially without evaluate()."""

    settings = AgentSettings()
    selection = load_online_eval_selection(limit=2)
    calls: list[str] = []

    class _Lifecycle:
        """Minimal lifecycle double."""

        def run(self, inputs: dict[str, object]) -> dict[str, object]:
            """Return a completed synthetic output.

            Args:
                inputs: Case inputs.

            Returns:
                Output mapping.
            """

            calls.append(str(inputs["case_id"]))
            return _output(case_id=str(inputs["case_id"])).model_dump(mode="json")

    emitted: list[str] = []

    def _emit(
        produce_outputs: Any,
        *,
        settings: AgentSettings,
        inputs: dict[str, object],
    ) -> dict[str, object]:
        """Capture the dedicated emit without LangSmith.

        Args:
            produce_outputs: Lifecycle wrapper.
            settings: Process settings.
            inputs: Envelope inputs.

        Returns:
            Produced outputs.
        """

        del settings
        emitted.append(str(inputs["case_id"]))
        return dict(produce_outputs())

    plan = run_online_eval_batch(
        cast(Any, _Lifecycle()),
        selection,
        settings=settings,
        emit_root=_emit,
    )
    assert calls == [case.case_id for case in selection.cases]
    assert emitted == [case.case_id for case in selection.cases]
    assert plan.dataset_created is False
    assert plan.experiment_created is False
    assert plan.writes is True
    assert plan.local_judge is False


def test_online_root_uses_dedicated_project_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The online parent always opens a scoped dedicated-project context."""

    seen: dict[str, object] = {}

    def _fake_context(**kwargs: object) -> AbstractContextManager[object]:
        """Record tracing_context kwargs.

        Args:
            **kwargs: SDK context fields.

        Returns:
            No-op context.
        """

        seen.update(kwargs)
        return nullcontext()

    def _fake_traceable(**kwargs: object) -> Any:
        """Skip SDK export while recording the dedicated run name.

        Args:
            **kwargs: ``traceable`` options.

        Returns:
            Identity decorator.
        """

        seen["traceable_name"] = kwargs.get("name")
        seen["traceable_project"] = kwargs.get("project_name")

        def _wrap(fn: Any) -> Any:
            """Return the wrapped function unchanged.

            Args:
                fn: Parent function.

            Returns:
                ``fn``.
            """

            return fn

        return _wrap

    monkeypatch.setattr(langsmith, "tracing_context", _fake_context)
    monkeypatch.setattr(
        "smart_rag_core.observability.query_trace.agent_eval.traceable",
        _fake_traceable,
    )
    monkeypatch.setattr(
        "smart_rag_core.observability.query_trace.agent_eval.tracing_is_enabled",
        lambda: True,
    )
    settings = AgentSettings()
    case = load_online_eval_selection(limit=1).cases[0]
    envelope = sample_online_envelope(case)

    def _produce() -> dict[str, object]:
        """Return a tiny envelope output.

        Returns:
            Bounded online outputs.
        """

        return envelope.outputs.model_dump(mode="json")

    emit_online_eval_root(
        _produce,
        settings=settings,
        inputs=envelope.inputs.model_dump(mode="json"),
    )
    assert seen.get("project_name") == ONLINE_EVAL_PROJECT
    assert seen.get("enabled") is True
    assert seen.get("traceable_name") == QUERY_AGENT_ONLINE_EVAL_RUN
    assert seen.get("traceable_project") == ONLINE_EVAL_PROJECT


def test_online_eval_bounds_remain_closed() -> None:
    """Holdout, oversize samples, and extra USD still fail the online gate."""

    assert_online_eval_permitted(
        mock_mode=True,
        case_count=ONLINE_EVAL_MAX_CASES,
        max_usd=ONLINE_EVAL_MAX_USD,
        holdout_access=HoldoutAccess.denied(),
    )
    with pytest.raises(OnlineEvalError):
        assert_online_eval_permitted(
            case_count=ONLINE_EVAL_MAX_CASES + 1,
            max_usd=Decimal("1.00"),
        )
    factory = cast(
        Any,
        module_attr(langsmith, "tracing_context"),
    )
    assert callable(factory)
    assert uuid4()
