"""Shared online-evaluator output, reference, and perform_eval loaders."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from smart_rag_core.evaluation.agent_eval import (
    AgentEvalOutput,
    AgentEvalReference,
)
from smart_rag_core.evaluation.online import (
    AGENT_ONLINE_EVAL_SCHEMA_VERSION,
    QUERY_AGENT_ONLINE_EVAL_RUN,
)
from smart_rag_core.evaluation.online_envelope import (
    output_to_online,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

EVALUATOR_PATH = (
    REPO_ROOT
    / "scripts"
    / "langsmith"
    / "evaluators"
    / "smart_rag_agent_online_eval_v1.py"
)

FORBIDDEN_IMPORT_PREFIXES = (
    "smart_rag",
    "langsmith",
    "openai",
    "requests",
    "httpx",
    "urllib",
    "pathlib",
)


def _load_perform_eval() -> Any:
    """Import the standalone evaluator without treating scripts as a package.

    Returns:
        ``perform_eval`` callable.
    """

    spec = importlib.util.spec_from_file_location(
        "smart_rag_agent_online_eval_v1",
        EVALUATOR_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.perform_eval


def _output(**kwargs: object) -> AgentEvalOutput:
    """Build one evaluation output with safe defaults.

    Args:
        **kwargs: Field overrides.

    Returns:
        Frozen ``AgentEvalOutput``.
    """

    payload: dict[str, object] = {
        "case_id": "p4-acl_negative-0003",
        "completed": True,
        "answer_status": "complete",
        "answer_text": "invoice INV-SR-8803 is listed",
        "effective_route": "hybrid",
        "remaining_model_calls": 2,
        "remaining_tool_calls": 2,
        "remaining_corrections": 1,
        "remaining_subquestions": 1,
        "remaining_recursion_steps": 4,
        "deadline_exceeded": False,
    }
    payload.update(kwargs)
    return AgentEvalOutput.model_validate(payload)


def _reference(**kwargs: object) -> AgentEvalReference:
    """Build one reference payload with safe defaults.

    Args:
        **kwargs: Field overrides.

    Returns:
        Frozen ``AgentEvalReference``.
    """

    payload: dict[str, object] = {
        "acceptable_answers": ("invoice INV-SR-8803 is listed",),
        "expected_route": "hybrid",
        "refusal_kind": "none",
        "visible_chunk_ids": ("chunk-a",),
        "visible_table_ids": (),
        "forbidden_evidence_ids": ("chunk-hidden",),
        "expected_profile_fields": {"language": "en"},
    }
    payload.update(kwargs)
    return AgentEvalReference.model_validate(payload)


def _eval_run(
    output: AgentEvalOutput,
    reference: AgentEvalReference,
    *,
    name: str = QUERY_AGENT_ONLINE_EVAL_RUN,
    schema_version: str = AGENT_ONLINE_EVAL_SCHEMA_VERSION,
    redaction_class: str = "synthetic",
) -> dict[str, object]:
    """Wrap one output/reference pair as a hosted code-evaluator run.

    Args:
        output: Graph output.
        reference: Frozen reference.
        name: LangSmith run name.
        schema_version: Envelope schema.
        redaction_class: Redaction class.

    Returns:
        Mapping accepted by ``perform_eval``.
    """

    envelope_outputs = output_to_online(output, reference)
    return {
        "name": name,
        "inputs": {
            "case_id": output.case_id,
            "question": "synthetic question",
            "language": "en",
            "query_class": "acl_negative",
            "schema_version": schema_version,
            "redaction_class": redaction_class,
        },
        "outputs": envelope_outputs.model_dump(mode="json"),
    }
