"""Private-safe company Ask regression helpers.

Credentials come from the process environment. The runner never defaults a
password or reuses one conversation across questions. Live gold files stay
under gitignored ``.private-eval/``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from smart_rag_core.evaluation.dual_metric import (
    DualMetricScore,
    RequiredFact,
    RetrievalStageAttribution,
    score_company_answer,
    summarize_scores,
)


class AskRegressionConfigError(ValueError):
    """Raised when regression configuration would embed or reuse secrets."""


@dataclass(frozen=True, slots=True)
class AskRegressionCredentials:
    """Environment-sourced Ask credentials. Never log the password.

    Attributes:
        email: Evaluator identity loaded from ``SMART_RAG_EVAL_EMAIL``.
        password: Evaluator password loaded from ``SMART_RAG_EVAL_PASSWORD``.
        base_url: Ask API origin loaded from ``SMART_RAG_EVAL_BASE_URL``.
    """

    email: str
    password: str
    base_url: str


class ConversationFactory(Protocol):
    """Creates one conversation per question."""

    def create_conversation(self) -> str:
        """Return a new conversation identifier.

        Returns:
            Opaque conversation id.
        """

        ...


@dataclass(frozen=True, slots=True)
class CompanyAskQuestion:
    """One private or synthetic company-document question.

    Attributes:
        question_id: Caller-owned identifier. Committed tests use synthetic
            ids only.
        prompt: User question text.
        facts: Required facts for dual-metric scoring.
    """

    question_id: str
    prompt: str
    facts: tuple[RequiredFact, ...]


@dataclass(frozen=True, slots=True)
class CompanyAskResult:
    """Scored Ask result for one fresh conversation.

    Attributes:
        question_id: Question identifier.
        conversation_id: Conversation created for this question only.
        score: Dual-metric score of the full answer.
    """

    question_id: str
    conversation_id: str
    score: DualMetricScore


def load_ask_regression_credentials(
    environ: Mapping[str, str],
) -> AskRegressionCredentials:
    """Load Ask credentials from the environment without defaults.

    Args:
        environ: Process environment mapping.

    Returns:
        Frozen credentials. The password is never defaulted.

    Raises:
        AskRegressionConfigError: If email, password, or base URL is missing
            or looks like an embedded placeholder.
    """

    email = environ.get("SMART_RAG_EVAL_EMAIL", "").strip()
    password = environ.get("SMART_RAG_EVAL_PASSWORD", "").strip()
    base_url = environ.get("SMART_RAG_EVAL_BASE_URL", "").strip()
    if not email or not password or not base_url:
        raise AskRegressionConfigError(
            "SMART_RAG_EVAL_EMAIL, SMART_RAG_EVAL_PASSWORD, and "
            "SMART_RAG_EVAL_BASE_URL must all be set"
        )
    placeholder = password.casefold()
    if placeholder in {"changeme", "your_password", "password", "todo", "secret"}:
        raise AskRegressionConfigError(
            "evaluator password must be loaded from a secret store"
        )
    return AskRegressionCredentials(
        email=email,
        password=password,
        base_url=base_url.rstrip("/"),
    )


def assert_fresh_conversation_policy(*, reuse_conversation_id: str | None) -> None:
    """Reject a shared conversation for a multi-question Ask regression.

    Args:
        reuse_conversation_id: Conversation id the caller wants to reuse.

    Raises:
        AskRegressionConfigError: If a conversation would be reused.
    """

    if reuse_conversation_id:
        raise AskRegressionConfigError(
            "each company Ask regression question requires a fresh conversation"
        )


def new_conversation_id(factory: ConversationFactory | None = None) -> str:
    """Return one new conversation id.

    Args:
        factory: Optional conversation creator. ``None`` uses a local UUID
            for dry-run scoring.

    Returns:
        Opaque conversation identifier.
    """

    if factory is None:
        return str(uuid4())
    return factory.create_conversation()


def score_full_answer_record(
    *,
    answer_text: str,
    facts: Sequence[RequiredFact],
    stages: RetrievalStageAttribution,
    answer_status: str | None = None,
    terminal_reason: str | None = None,
) -> DualMetricScore:
    """Score a full answer through the shared dual-metric scorer.

    Args:
        answer_text: Complete answer. Do not pass a truncated excerpt.
        facts: Required facts.
        stages: Retrieval stage attribution.
        answer_status: Optional product status.
        terminal_reason: Optional terminal reason.

    Returns:
        Dual-metric score from :func:`score_company_answer`.
    """

    return score_company_answer(
        answer_text=answer_text,
        facts=facts,
        stages=stages,
        answer_status=answer_status,
        terminal_reason=terminal_reason,
    )


def run_scored_questions(
    questions: Sequence[CompanyAskQuestion],
    *,
    answers: Mapping[str, str],
    stages: Mapping[str, RetrievalStageAttribution],
    factory: ConversationFactory | None = None,
    reuse_conversation_id: str | None = None,
    answer_status: Mapping[str, str] | None = None,
    terminal_reason: Mapping[str, str] | None = None,
) -> tuple[CompanyAskResult, ...]:
    """Score each question against its full answer with a fresh conversation.

    Args:
        questions: Ordered questions.
        answers: Full answer text keyed by question id.
        stages: Stage attribution keyed by question id.
        factory: Optional live conversation factory.
        reuse_conversation_id: Forbidden shared conversation id.
        answer_status: Optional status keyed by question id.
        terminal_reason: Optional reason keyed by question id.

    Returns:
        One scored result per question, each with its own conversation id.

    Raises:
        AskRegressionConfigError: If a shared conversation is requested or an
            answer is missing.
    """

    assert_fresh_conversation_policy(reuse_conversation_id=reuse_conversation_id)
    results: list[CompanyAskResult] = []
    statuses = answer_status or {}
    reasons = terminal_reason or {}
    seen_conversations: set[str] = set()
    for question in questions:
        conversation_id = new_conversation_id(factory)
        if conversation_id in seen_conversations:
            raise AskRegressionConfigError("conversation factory reused an identifier")
        seen_conversations.add(conversation_id)
        try:
            answer_text = answers[question.question_id]
        except KeyError as exc:
            raise AskRegressionConfigError(
                f"missing full answer for {question.question_id}"
            ) from exc
        score = score_full_answer_record(
            answer_text=answer_text,
            facts=question.facts,
            stages=stages.get(question.question_id, RetrievalStageAttribution()),
            answer_status=statuses.get(question.question_id),
            terminal_reason=reasons.get(question.question_id),
        )
        results.append(
            CompanyAskResult(
                question_id=question.question_id,
                conversation_id=conversation_id,
                score=score,
            )
        )
    return tuple(results)


def load_private_gold(path: Path) -> tuple[CompanyAskQuestion, ...]:
    """Load gitignored gold without copying it into the repository.

    Args:
        path: JSON file under ``.private-eval/``. The path must stay outside
            committed trees.

    Returns:
        Questions and facts. Canonical phrases come from the private file.

    Raises:
        AskRegressionConfigError: If the path is committed-looking or invalid.
    """

    resolved = path.resolve()
    if ".private-eval" not in {part.casefold() for part in resolved.parts}:
        raise AskRegressionConfigError(
            "private gold must live under a .private-eval directory"
        )
    payload_obj: object = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload_obj, list):
        raise AskRegressionConfigError("private gold must be a JSON array")
    questions: list[CompanyAskQuestion] = []
    for item in cast(list[object], payload_obj):
        mapping = _as_mapping(item, kind="gold item")
        question_id = str(mapping.get("id", "")).strip()
        prompt = str(mapping.get("prompt") or mapping.get("question") or "").strip()
        raw_facts: object = mapping.get("facts")
        required = mapping.get("required")
        if raw_facts is None and isinstance(required, list):
            raw_facts = [
                {"id": f"req-{index}", "canonical": [str(phrase)]}
                for index, phrase in enumerate(cast(list[object], required))
                if str(phrase).strip()
            ]
        if not question_id or not prompt or not isinstance(raw_facts, list):
            raise AskRegressionConfigError("gold item is missing id, prompt, or facts")
        facts = tuple(_fact_from_mapping(raw) for raw in cast(list[object], raw_facts))
        questions.append(
            CompanyAskQuestion(
                question_id=question_id,
                prompt=prompt,
                facts=facts,
            )
        )
    return tuple(questions)


def write_redacted_summary(
    results: Sequence[CompanyAskResult],
    destination: Path,
) -> Mapping[str, float | int]:
    """Write counts only. Never persist passwords or full gold phrases.

    Args:
        results: Scored questions.
        destination: Output JSON path.

    Returns:
        Aggregate summary also written to ``destination``.
    """

    summary = dict(summarize_scores(tuple(item.score for item in results)))
    payload = {
        "summary": summary,
        "outcomes": [
            {
                "question_id": item.question_id,
                "conversation_id": item.conversation_id,
                "outcome": item.score.outcome.value,
                "strict_pass": item.score.strict_pass,
                "grounded_fact_pass": item.score.grounded_fact_pass,
                "deadline_failure": item.score.deadline_failure,
                "verifier_refusal_after_fusion": (
                    item.score.verifier_refusal_after_fusion
                ),
                "empty_retrieval": item.score.empty_retrieval,
            }
            for item in results
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _fact_from_mapping(raw: object) -> RequiredFact:
    """Parse one private gold fact.

    Args:
        raw: JSON object.

    Returns:
        Required fact.

    Raises:
        AskRegressionConfigError: If the object is malformed.
    """

    mapping = _as_mapping(raw, kind="fact")
    fact_id = str(mapping.get("id", "")).strip()
    canonical = mapping.get("canonical", mapping.get("phrases", []))
    aliases = mapping.get("aliases", [])
    if not isinstance(canonical, list) or not canonical:
        raise AskRegressionConfigError("fact canonical phrases are required")
    if not isinstance(aliases, list):
        raise AskRegressionConfigError("fact aliases must be an array")
    return RequiredFact(
        fact_id=fact_id or "fact",
        canonical_phrases=tuple(str(item) for item in cast(list[object], canonical)),
        approved_aliases=tuple(str(item) for item in cast(list[object], aliases)),
    )


def _as_mapping(value: object, *, kind: str) -> dict[str, object]:
    """Coerce a JSON object to a string-keyed mapping.

    Args:
        value: Parsed JSON value.
        kind: Error label for a non-object.

    Returns:
        String-keyed mapping.

    Raises:
        AskRegressionConfigError: When the value is not an object.
    """

    if not isinstance(value, dict):
        raise AskRegressionConfigError(f"{kind} must be an object")
    typed = cast(dict[object, object], value)
    return {str(key): item for key, item in typed.items()}
