"""Bounded synthetic envelope for dedicated online-evaluation root traces.

Normal application traces stay redacted. Only
``query.agent.eval.online.v1`` on ``smart-rag-agent-eval-online`` may carry
question, answer, reference, and short synthetic excerpts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from smart_rag_core.evaluation.agent_eval import (
    AgentEvalOutput,
    AgentEvalReference,
    AgentEvalSelectedEvidence,
    case_to_reference,
)
from smart_rag_core.evaluation.online import AGENT_ONLINE_EVAL_SCHEMA_VERSION
from smart_rag_core.evaluation.schema import EvaluationCase

MAX_ANSWER_CHARS = 16_384
MAX_RATIONALE_CHARS = 240
MAX_EXCERPT_CHARS = 600
MAX_SELECTED_EVIDENCE = 12
MAX_ACCEPTABLE_ANSWERS = 8
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_API_KEY_RE = re.compile(r"(?:sk-|lsv2_|xox)[A-Za-z0-9_\-]{8,}")
_DSN_RE = re.compile(r"(?:postgres(?:ql)?|mysql|mongodb)://", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SIGNED_URL_RE = re.compile(r"[?&](?:X-Amz-|signature=|token=)", re.IGNORECASE)


class OnlineEnvelopeError(ValueError):
    """Raised when an online envelope is oversized, secret-bearing, or unsynthetic."""


class OnlineEvalInputs(BaseModel):
    """Root-trace inputs for one synthetic online evaluation case.

    Attributes:
        case_id: Frozen development case identifier.
        question: Synthetic question text.
        language: Query language code.
        query_class: Canonical query class.
        schema_version: Envelope schema.
        redaction_class: Must remain ``synthetic``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=8, max_length=64)
    question: str = Field(min_length=1, max_length=2000)
    language: Literal["en", "ar", "mixed"]
    query_class: str = Field(min_length=1, max_length=64)
    schema_version: Literal["agent-online-eval-v1"] = AGENT_ONLINE_EVAL_SCHEMA_VERSION
    redaction_class: Literal["synthetic"] = "synthetic"


class OnlineEvalReference(BaseModel):
    """Bounded synthetic reference copied onto the dedicated root outputs.

    Attributes:
        acceptable_answers: At most eight gold variants.
        expected_route: Labeled route.
        refusal_kind: Explicit refusal or limitation kind.
        visible_chunk_ids: Actor-visible passage identifiers.
        visible_table_ids: Actor-visible table identifiers.
        forbidden_evidence_ids: Invisible or forbidden evidence identifiers.
        expected_profile_fields: Stable profile fields required for scoring.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    acceptable_answers: tuple[str, ...] = Field(
        default=(), max_length=MAX_ACCEPTABLE_ANSWERS
    )
    expected_route: str = Field(min_length=1, max_length=64)
    refusal_kind: str = Field(min_length=1, max_length=64)
    visible_chunk_ids: tuple[str, ...] = ()
    visible_table_ids: tuple[str, ...] = ()
    forbidden_evidence_ids: tuple[str, ...] = ()
    expected_profile_fields: dict[str, object] = Field(default_factory=dict)

    @field_validator("acceptable_answers")
    @classmethod
    def _bound_answers(cls, answers: tuple[str, ...]) -> tuple[str, ...]:
        """Cap acceptable answers and individual lengths.

        Args:
            answers: Gold variants.

        Returns:
            At most eight answers, each at most ``MAX_ANSWER_CHARS``.
        """

        return tuple(
            item[:MAX_ANSWER_CHARS] for item in answers[:MAX_ACCEPTABLE_ANSWERS]
        )


class OnlineEvalOutputs(BaseModel):
    """Root-trace outputs for one synthetic online evaluation case.

    Attributes:
        completed: Whether the target produced a valid terminal output.
        failure_kind: Named infrastructure or scoring failure, if any.
        answer_text: Bounded synthetic answer.
        answer_status: ``complete``, ``partial``, ``refused``, or empty.
        requested_route: Envelope family reserved at admit.
        effective_route: Planner-selected family.
        corrected_route: Family after the one correction, if any.
        cited_chunk_ids: Passage ids cited in the answer.
        cited_table_ids: Table ids cited in the answer.
        selected_evidence: At most twelve synthetic evidence records.
        observed_profile_fields: Structured preparation fields.
        remaining_model_calls: Remaining counted gateway calls, or None.
        remaining_tool_calls: Remaining tool executions, or None.
        remaining_corrections: Remaining correction slots, or None.
        remaining_subquestions: Remaining subquestion slots, or None.
        remaining_recursion_steps: Remaining graph supersteps, or None.
        deadline_exceeded: True when the run exhausted its deadline.
        latency_ms: End-to-end latency.
        reference: Frozen synthetic reference used by hosted evaluators.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    completed: bool = False
    failure_kind: str | None = None
    answer_text: str = Field(default="", max_length=MAX_ANSWER_CHARS)
    answer_status: str = ""
    requested_route: str | None = None
    effective_route: str | None = None
    corrected_route: str | None = None
    cited_chunk_ids: tuple[str, ...] = ()
    cited_table_ids: tuple[str, ...] = ()
    selected_evidence: tuple[AgentEvalSelectedEvidence, ...] = Field(
        default=(),
        max_length=MAX_SELECTED_EVIDENCE,
    )
    observed_profile_fields: dict[str, object] = Field(default_factory=dict)
    remaining_model_calls: int | None = None
    remaining_tool_calls: int | None = None
    remaining_corrections: int | None = None
    remaining_subquestions: int | None = None
    remaining_recursion_steps: int | None = None
    deadline_exceeded: bool = False
    latency_ms: int | None = None
    reference: OnlineEvalReference


class OnlineEvalEnvelope(BaseModel):
    """Complete dedicated-root payload validated before LangSmith export.

    Attributes:
        inputs: Synthetic question envelope.
        outputs: Agent result plus frozen reference.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    inputs: OnlineEvalInputs
    outputs: OnlineEvalOutputs


def case_to_online_inputs(case: EvaluationCase) -> OnlineEvalInputs:
    """Map one synthetic development case to online-root inputs.

    Args:
        case: Development case. Must already be suite-qualified.

    Returns:
        Typed online inputs.

    Raises:
        OnlineEnvelopeError: The case is not synthetic.
    """

    if case.redaction_class != "synthetic":
        raise OnlineEnvelopeError("synthetic_content_required")
    return OnlineEvalInputs(
        case_id=case.case_id,
        question=case.query,
        language=case.language,
        query_class=case.query_class.value,
        schema_version=AGENT_ONLINE_EVAL_SCHEMA_VERSION,
        redaction_class="synthetic",
    )


def reference_to_online(reference: AgentEvalReference) -> OnlineEvalReference:
    """Bound a scorer reference for the dedicated root trace.

    Args:
        reference: Existing agent-eval reference.

    Returns:
        Envelope reference with answer and length caps applied.
    """

    return OnlineEvalReference(
        acceptable_answers=tuple(reference.acceptable_answers[:MAX_ACCEPTABLE_ANSWERS]),
        expected_route=reference.expected_route,
        refusal_kind=reference.refusal_kind,
        visible_chunk_ids=tuple(reference.visible_chunk_ids),
        visible_table_ids=tuple(reference.visible_table_ids),
        forbidden_evidence_ids=tuple(reference.forbidden_evidence_ids),
        expected_profile_fields=dict(reference.expected_profile_fields),
    )


def output_to_online(
    output: AgentEvalOutput,
    reference: AgentEvalReference,
) -> OnlineEvalOutputs:
    """Map one graph output plus reference onto the dedicated envelope.

    Args:
        output: Normalized production-graph output.
        reference: Frozen reference.

    Returns:
        Typed online outputs. Answer text and evidence are bounded.
    """

    evidence = tuple(output.selected_evidence[:MAX_SELECTED_EVIDENCE])
    if not evidence and output.selected_evidence_ids:
        evidence = tuple(
            AgentEvalSelectedEvidence(evidence_id=item, excerpt="")
            for item in output.selected_evidence_ids[:MAX_SELECTED_EVIDENCE]
        )
    return OnlineEvalOutputs(
        completed=output.completed,
        failure_kind=output.failure_kind,
        answer_text=output.answer_text[:MAX_ANSWER_CHARS],
        answer_status=output.answer_status,
        requested_route=output.requested_route,
        effective_route=output.effective_route,
        corrected_route=output.corrected_route,
        cited_chunk_ids=tuple(output.cited_chunk_ids),
        cited_table_ids=tuple(output.cited_table_ids),
        selected_evidence=evidence,
        observed_profile_fields=dict(output.profile_fields),
        remaining_model_calls=output.remaining_model_calls,
        remaining_tool_calls=output.remaining_tool_calls,
        remaining_corrections=output.remaining_corrections,
        remaining_subquestions=output.remaining_subquestions,
        remaining_recursion_steps=output.remaining_recursion_steps,
        deadline_exceeded=output.deadline_exceeded,
        latency_ms=output.latency_ms,
        reference=reference_to_online(reference),
    )


def build_online_envelope(
    case: EvaluationCase,
    output: AgentEvalOutput,
) -> OnlineEvalEnvelope:
    """Build and validate one dedicated-root envelope.

    Args:
        case: Synthetic development case.
        output: Normalized graph output.

    Returns:
        Validated envelope.

    Raises:
        OnlineEnvelopeError: Secrets, DSN, email, or non-synthetic content found.
    """

    envelope = OnlineEvalEnvelope(
        inputs=case_to_online_inputs(case),
        outputs=output_to_online(output, case_to_reference(case)),
    )
    assert_online_envelope_safe(envelope)
    return envelope


def sample_online_envelope(case: EvaluationCase) -> OnlineEvalEnvelope:
    """Build a schema-valid envelope from labels without running the agent.

    Args:
        case: Synthetic development case.

    Returns:
        Envelope with empty observed counters. Used by dry-run only.

    Raises:
        OnlineEnvelopeError: The labeled case is unsafe to export.
    """

    evidence: list[AgentEvalSelectedEvidence] = []
    for link in case.evidence_links:
        identifier = link.chunk_id or link.table_id
        if not identifier:
            continue
        evidence.append(AgentEvalSelectedEvidence(evidence_id=identifier, excerpt=""))
        if len(evidence) >= MAX_SELECTED_EVIDENCE:
            break
    output = AgentEvalOutput(
        case_id=case.case_id,
        completed=False,
        failure_kind="dry_run",
        answer_text="",
        answer_status="",
        selected_evidence=tuple(evidence),
        remaining_model_calls=0,
        remaining_tool_calls=0,
        remaining_corrections=0,
        remaining_subquestions=0,
        remaining_recursion_steps=0,
        deadline_exceeded=False,
    )
    return build_online_envelope(case, output)


def keep_online_eval_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Export only the bounded synthetic input envelope.

    Args:
        inputs: Traceable kwargs. Nested ``inputs`` is unwrapped.

    Returns:
        Validated input dump, or a fail-closed empty synthetic shell.
    """

    raw: object = inputs.get("inputs", inputs)
    if not isinstance(raw, Mapping):
        return OnlineEvalInputs(
            case_id="unknown-case",
            question="unavailable",
            language="en",
            query_class="unknown",
        ).model_dump(mode="json")
    try:
        typed = OnlineEvalInputs.model_validate(raw)
    except (TypeError, ValueError):
        return OnlineEvalInputs(
            case_id="unknown-case",
            question="unavailable",
            language="en",
            query_class="unknown",
        ).model_dump(mode="json")
    return typed.model_dump(mode="json")


def keep_online_eval_outputs(outputs: object) -> dict[str, Any]:
    """Export only the bounded synthetic output envelope.

    Args:
        outputs: Traceable return value.

    Returns:
        Validated output dump, or a named failure shell.
    """

    raw: object = outputs
    if isinstance(outputs, Mapping) and "outputs" in outputs:
        typed = cast(Mapping[object, object], outputs)
        mapped = {str(key): item for key, item in typed.items()}
        raw = mapped.get("outputs")
    try:
        typed = OnlineEvalOutputs.model_validate(raw)
    except (TypeError, ValueError):
        return {
            "completed": False,
            "failure_kind": "envelope_invalid",
            "answer_text": "",
            "answer_status": "",
            "selected_evidence": [],
            "observed_profile_fields": {},
            "deadline_exceeded": False,
            "reference": {
                "acceptable_answers": [],
                "expected_route": "hybrid",
                "refusal_kind": "none",
                "visible_chunk_ids": [],
                "visible_table_ids": [],
                "forbidden_evidence_ids": [],
                "expected_profile_fields": {},
            },
        }
    dumped = typed.model_dump(mode="json")
    dumped["answer_text"] = str(dumped.get("answer_text") or "")[:MAX_ANSWER_CHARS]
    return dumped


def assert_online_envelope_safe(envelope: OnlineEvalEnvelope) -> None:
    """Reject secrets, DSNs, emails, JWTs, and signed URLs.

    Args:
        envelope: Candidate export.

    Raises:
        OnlineEnvelopeError: A forbidden pattern is present.
    """

    if envelope.inputs.redaction_class != "synthetic":
        raise OnlineEnvelopeError("synthetic_content_required")
    if envelope.inputs.schema_version != AGENT_ONLINE_EVAL_SCHEMA_VERSION:
        raise OnlineEnvelopeError("online_schema_required")
    blob = envelope.model_dump_json()
    if _JWT_RE.search(blob):
        raise OnlineEnvelopeError("secret_export_forbidden")
    if _API_KEY_RE.search(blob):
        raise OnlineEnvelopeError("secret_export_forbidden")
    if _DSN_RE.search(blob):
        raise OnlineEnvelopeError("secret_export_forbidden")
    if _EMAIL_RE.search(blob):
        raise OnlineEnvelopeError("secret_export_forbidden")
    if _SIGNED_URL_RE.search(blob):
        raise OnlineEnvelopeError("secret_export_forbidden")
