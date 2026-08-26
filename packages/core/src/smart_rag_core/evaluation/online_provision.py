"""Idempotent LangSmith CLI/API contracts for dedicated online evaluators.

Request bodies follow the documented LangSmith 2026 REST fields. This
module never prints API keys or provider secrets. A second run must update
the same evaluator and rule IDs.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID

from smart_rag_core.evaluation.online import (
    AGENT_ONLINE_EVAL_SCHEMA_VERSION,
    ONLINE_CODE_EVALUATOR_NAME,
    ONLINE_CODE_RULE_NAME,
    ONLINE_EVAL_MAX_USD,
    ONLINE_EVAL_PROJECT,
    ONLINE_EVAL_ROOT_FILTER,
    ONLINE_EVAL_SAMPLING_RATE,
    ONLINE_EVAL_SPEND_WINDOW,
    ONLINE_JUDGE_PROMPT_HANDLE,
    ONLINE_JUDGE_PROMPT_TAG,
    ONLINE_LLM_EVALUATOR_NAME,
    ONLINE_LLM_RULE_NAME,
    QUERY_AGENT_ONLINE_EVAL_RUN,
)
from smart_rag_core.query_answer.schemas import eval_judge_json_schema
from smart_rag_core.query_answer.versions import (
    EVAL_JUDGE_MODEL_ID,
    EVAL_JUDGE_PROMPT_SHA256,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
CODE_EVALUATOR_RELATIVE_PATH = (
    "scripts/langsmith/evaluators/smart_rag_agent_online_eval_v1.py"
)
# ``langsmith api`` prefixes ``/api/v1/``. Passing that prefix twice 404s.
EVALUATOR_CREATE_PATH = "platform/evaluators"
EVALUATOR_LIST_PATH = "platform/evaluators"
RUN_RULES_PATH = "runs/rules"
SESSIONS_PATH = "sessions"
JUDGE_VARIABLE_MAPPING = {
    "question": "inputs.question",
    "acceptable_answers": "outputs.reference.acceptable_answers",
    "answer_text": "outputs.answer_text",
    "answer_status": "outputs.answer_status",
    "selected_evidence": "outputs.selected_evidence",
}


class OnlineProvisionError(RuntimeError):
    """Raised when CLI, workspace, or evaluator identity cannot be proven."""


class LangSmithCliRunner(Protocol):
    """Authenticated LangSmith CLI used by setup and verification."""

    def run(
        self,
        args: Sequence[str],
        *,
        stdin: str | None = None,
    ) -> CliResult:
        """Run one CLI command.

        Args:
            args: Argument vector excluding the ``langsmith`` binary.
            stdin: Optional request body.

        Returns:
            Parsed CLI result. Secrets must not appear in ``stdout``.
        """

        ...


@dataclass(frozen=True)
class CliResult:
    """One CLI invocation result.

    Attributes:
        exit_code: Process exit code.
        stdout: Secret-free stdout.
        stderr: Secret-free stderr.
        payload: Parsed JSON when stdout is an object or array.
    """

    exit_code: int
    stdout: str
    stderr: str
    payload: Any = None


class FakeLangSmithCli:
    """In-memory CLI used by contract tests. No network.

    Attributes:
        handlers: Mapping of joined argv prefixes to canned results.
        calls: Recorded argument vectors.
        stdin_bodies: Recorded request bodies.
    """

    def __init__(self, handlers: dict[str, CliResult] | None = None) -> None:
        """Initialize empty call logs and optional canned handlers.

        Args:
            handlers: Optional exact or prefix argv strings to results.
        """

        self.handlers: dict[str, CliResult] = handlers or {}
        self.calls: list[tuple[str, ...]] = []
        self.stdin_bodies: list[str] = []

    def run(self, args: Sequence[str], *, stdin: str | None = None) -> CliResult:
        """Return a canned result for ``args``.

        Args:
            args: CLI arguments.
            stdin: Optional JSON body.

        Returns:
            Matching canned result, or a missing-handler failure.

        Raises:
            OnlineProvisionError: No handler matches and tests did not
                register a default.
        """

        self.calls.append(tuple(str(item) for item in args))
        if stdin is not None:
            self.stdin_bodies.append(stdin)
        key = " ".join(str(item) for item in args)
        exact = self.handlers.get(key)
        if exact is not None:
            return exact
        matches = [
            result
            for prefix, result in self.handlers.items()
            if key.startswith(f"{prefix} ")
        ]
        if len(matches) == 1:
            return matches[0]
        raise OnlineProvisionError("cli_handler_missing")


@dataclass(frozen=True)
class OnlineProvisionSummary:
    """Secret-free setup result.

    Attributes:
        project_name: Dedicated tracing project.
        project_id: Dedicated project UUID.
        application_project_id: Normal ``smart-rag`` project UUID, if present.
        code_evaluator_id: Deterministic evaluator UUID.
        llm_evaluator_id: Hosted judge UUID.
        code_rule_id: Code-evaluator run-rule UUID.
        llm_rule_id: LLM-evaluator run-rule UUID.
        prompt_handle: Pinned prompt repo handle.
        prompt_commit: Pinned prompt commit hash or tag.
        prompt_sha256: Local ``eval_judge_v1`` SHA-256.
        model_id: Hosted judge model id.
        model_configuration_id: Existing LangSmith playground settings id.
        sampling_rate: Online rule sampling rate.
        spend_limit_usd: Weekly USD cap requested for the LLM rule.
        spend_limit_enforced: False when the workspace rejects spend caps.
        backfill: Always false.
        created_new_resources: True only on the first successful create.
        duplicate_rules: Always false when idempotent.
    """

    project_name: str
    project_id: str
    application_project_id: str | None
    code_evaluator_id: str
    llm_evaluator_id: str
    code_rule_id: str
    llm_rule_id: str
    prompt_handle: str
    prompt_commit: str
    prompt_sha256: str
    model_id: str
    model_configuration_id: str
    sampling_rate: float
    spend_limit_usd: str
    spend_limit_enforced: bool
    backfill: bool
    created_new_resources: bool
    duplicate_rules: bool

    def as_json(self) -> dict[str, object]:
        """Return a JSON-serializable secret-free mapping.

        Returns:
            Summary fields only. No keys or tokens.
        """

        return {
            "project_name": self.project_name,
            "project_id": self.project_id,
            "application_project_id": self.application_project_id,
            "code_evaluator_id": self.code_evaluator_id,
            "llm_evaluator_id": self.llm_evaluator_id,
            "code_rule_id": self.code_rule_id,
            "llm_rule_id": self.llm_rule_id,
            "prompt_handle": self.prompt_handle,
            "prompt_commit": self.prompt_commit,
            "prompt_sha256": self.prompt_sha256,
            "model_id": self.model_id,
            "model_configuration_id": self.model_configuration_id,
            "sampling_rate": self.sampling_rate,
            "spend_limit_usd": self.spend_limit_usd,
            "spend_limit_enforced": self.spend_limit_enforced,
            "backfill": self.backfill,
            "created_new_resources": self.created_new_resources,
            "duplicate_rules": self.duplicate_rules,
            "root_run_name": QUERY_AGENT_ONLINE_EVAL_RUN,
            "trace_schema_version": AGENT_ONLINE_EVAL_SCHEMA_VERSION,
            "filter": ONLINE_EVAL_ROOT_FILTER,
        }


def judge_user_template() -> str:
    """Return the hosted-judge user template for bounded synthetic fields.

    Returns:
        Template mapping only question, answers, status, and evidence.
    """

    return (
        "question: {question}\n"
        "acceptable_answers: {acceptable_answers}\n"
        "answer_text: {answer_text}\n"
        "answer_status: {answer_status}\n"
        "selected_evidence: {selected_evidence}\n"
    )


def llm_evaluator_create_body(
    *,
    prompt_commit: str,
    model_configuration_id: str,
) -> dict[str, object]:
    """Build the documented create-evaluator body for the hosted judge.

    Args:
        prompt_commit: Pinned commit hash or tag.
        model_configuration_id: Existing ``gpt-4o-mini`` playground settings.

    Returns:
        JSON body for ``POST /api/v1/platform/evaluators``.
    """

    return {
        "name": ONLINE_LLM_EVALUATOR_NAME,
        "type": "llm",
        "llm_evaluator": {
            "prompt_repo_handle": ONLINE_JUDGE_PROMPT_HANDLE,
            "commit_hash_or_tag": prompt_commit,
            "playground_settings_id": model_configuration_id,
            "variable_mapping": dict(JUDGE_VARIABLE_MAPPING),
        },
    }


def llm_evaluator_update_body(
    *,
    prompt_commit: str,
    model_configuration_id: str,
) -> dict[str, object]:
    """Build the documented patch body for the hosted judge.

    Args:
        prompt_commit: Pinned commit hash or tag.
        model_configuration_id: Existing playground settings id.

    Returns:
        JSON body for ``PATCH /api/v1/platform/evaluators/{id}``.
    """

    return {
        "name": ONLINE_LLM_EVALUATOR_NAME,
        "llm_evaluator": {
            "prompt_repo_handle": ONLINE_JUDGE_PROMPT_HANDLE,
            "commit_hash_or_tag": prompt_commit,
            "playground_settings_id": model_configuration_id,
            "variable_mapping": dict(JUDGE_VARIABLE_MAPPING),
        },
    }


def run_rule_body(
    *,
    display_name: str,
    project_id: str,
    evaluator_id: str,
    include_spend_limit: bool,
    include_evaluator_id: bool = True,
) -> dict[str, object]:
    """Build one enabled online rule for the dedicated project.

    Args:
        display_name: Stable rule name.
        project_id: Dedicated project UUID.
        evaluator_id: Evaluator UUID.
        include_spend_limit: True for the hosted LLM rule.
        include_evaluator_id: False on PATCH. Re-sending the id can 400.

    Returns:
        JSON body for create or update. ``backfill_from`` is omitted.
    """

    body: dict[str, object] = {
        "display_name": display_name,
        "sampling_rate": ONLINE_EVAL_SAMPLING_RATE,
        "session_id": project_id,
        "is_enabled": True,
        "filter": ONLINE_EVAL_ROOT_FILTER,
        "dataset_id": None,
        "use_corrections_dataset": False,
    }
    if include_evaluator_id:
        body["evaluator_id"] = evaluator_id
    if include_spend_limit:
        body["spend_limit"] = {
            "limit_usd": format(ONLINE_EVAL_MAX_USD, "f"),
            "window": ONLINE_EVAL_SPEND_WINDOW,
        }
    return body


def code_evaluator_upload_args(*, profile: str | None) -> tuple[str, ...]:
    """Return the documented ``evaluator upload`` argument vector.

    Args:
        profile: Optional LangSmith profile name.

    Returns:
        Args excluding the ``langsmith`` binary.
    """

    prefix: list[str] = []
    if profile:
        prefix.extend(["--profile", profile])
    return tuple(
        [
            *prefix,
            "evaluator",
            "upload",
            str(REPO_ROOT / CODE_EVALUATOR_RELATIVE_PATH),
            "--name",
            ONLINE_CODE_EVALUATOR_NAME,
            "--function",
            "perform_eval",
            "--project",
            ONLINE_EVAL_PROJECT,
            "--sampling-rate",
            "1",
            "--replace",
            "--yes",
        ]
    )


def required_evaluator_fields() -> frozenset[str]:
    """Return unstable request/response fields this setup relies on.

    Returns:
        Field names that a contract test must keep aligned with docs.
    """

    return frozenset(
        {
            "name",
            "type",
            "id",
            "llm_evaluator",
            "prompt_repo_handle",
            "commit_hash_or_tag",
            "playground_settings_id",
            "variable_mapping",
            "run_rules",
            "session_id",
            "sampling_rate",
            "is_enabled",
            "filter",
            "evaluator_id",
            "spend_limit",
            "limit_usd",
            "window",
            "display_name",
            "backfill_from",
        }
    )


def assert_llm_create_contract(body: Mapping[str, Any]) -> None:
    """Fail when the hosted-judge create body drifts from documented fields.

    Args:
        body: Candidate request body.

    Raises:
        OnlineProvisionError: A required field is missing or unsafe.
    """

    payload = _as_mapping(body)
    if payload.get("name") != ONLINE_LLM_EVALUATOR_NAME:
        raise OnlineProvisionError("evaluator_name_mismatch")
    if payload.get("type") != "llm":
        raise OnlineProvisionError("evaluator_type_mismatch")
    evaluator = _as_mapping(payload.get("llm_evaluator"))
    if not evaluator:
        raise OnlineProvisionError("llm_evaluator_required")
    if evaluator.get("prompt_repo_handle") != ONLINE_JUDGE_PROMPT_HANDLE:
        raise OnlineProvisionError("prompt_handle_mismatch")
    if not evaluator.get("commit_hash_or_tag"):
        raise OnlineProvisionError("prompt_commit_required")
    if evaluator.get("commit_hash_or_tag") in {"latest", ""}:
        raise OnlineProvisionError("unversioned_prompt_forbidden")
    if not evaluator.get("playground_settings_id"):
        raise OnlineProvisionError("model_configuration_required")
    mapping = evaluator.get("variable_mapping")
    if mapping != JUDGE_VARIABLE_MAPPING:
        raise OnlineProvisionError("variable_mapping_mismatch")


def assert_rule_contract(
    body: Mapping[str, Any],
    *,
    project_id: str,
    require_spend_limit: bool,
) -> None:
    """Fail when a run-rule body would broaden sampling or enable backfill.

    Args:
        body: Candidate request body.
        project_id: Dedicated project UUID.
        require_spend_limit: True for the LLM rule.

    Raises:
        OnlineProvisionError: Sampling, project, filter, or spend fields fail.
    """

    payload = _as_mapping(body)
    if payload.get("session_id") != project_id:
        raise OnlineProvisionError("rule_project_mismatch")
    if payload.get("sampling_rate") != ONLINE_EVAL_SAMPLING_RATE:
        raise OnlineProvisionError("sampling_rate_mismatch")
    if payload.get("filter") != ONLINE_EVAL_ROOT_FILTER:
        raise OnlineProvisionError("filter_mismatch")
    if payload.get("is_enabled") is not True:
        raise OnlineProvisionError("rule_disabled")
    if payload.get("dataset_id") not in {None, ""}:
        raise OnlineProvisionError("dataset_attachment_forbidden")
    if "backfill_from" in payload and payload.get("backfill_from") is not None:
        raise OnlineProvisionError("backfill_forbidden")
    if require_spend_limit:
        spend = _as_mapping(payload.get("spend_limit"))
        if not spend:
            raise OnlineProvisionError("spend_limit_required")
        if Decimal(str(spend.get("limit_usd"))) != ONLINE_EVAL_MAX_USD:
            raise OnlineProvisionError("spend_limit_mismatch")
        if spend.get("window") != ONLINE_EVAL_SPEND_WINDOW:
            raise OnlineProvisionError("spend_window_mismatch")


def provision_online_evaluators(
    cli: LangSmithCliRunner,
    *,
    profile: str | None,
    model_configuration_id: str,
    prompt_commit: str,
    project_id: str,
    application_project_id: str | None,
    existing_evaluators: Sequence[Mapping[str, Any]] = (),
    existing_rules: Sequence[Mapping[str, Any]] = (),
    created_new: bool = False,
) -> OnlineProvisionSummary:
    """Create or update both dedicated evaluators and one rule each.

    Args:
        cli: Authenticated CLI runner.
        profile: Optional LangSmith profile.
        model_configuration_id: Existing ``gpt-4o-mini`` playground settings.
        prompt_commit: Pinned prompt commit hash or tag.
        project_id: Dedicated project UUID.
        application_project_id: Normal project UUID, if it exists.
        existing_evaluators: Workspace evaluators already listed.
        existing_rules: Dedicated-project rules already listed.
        created_new: True when this invocation created the project or
            an evaluator that did not previously exist.

    Returns:
        Secret-free summary.

    Raises:
        OnlineProvisionError: Identity, type, project, or bound checks fail.

    Side Effects:
        Issues CLI upload/API calls through ``cli``. Does not print secrets.
    """

    if not model_configuration_id.strip():
        raise OnlineProvisionError("model_configuration_required")
    if not prompt_commit.strip() or prompt_commit.strip() == "latest":
        raise OnlineProvisionError("unversioned_prompt_forbidden")
    if application_project_id and application_project_id == project_id:
        raise OnlineProvisionError("dedicated_project_collision")
    _assert_uuid(project_id, reason="project_id_invalid")
    code = _upsert_code_evaluator(
        cli,
        profile=profile,
        existing=existing_evaluators,
    )
    llm_body = llm_evaluator_create_body(
        prompt_commit=prompt_commit,
        model_configuration_id=model_configuration_id,
    )
    assert_llm_create_contract(llm_body)
    llm = _upsert_llm_evaluator(
        cli,
        profile=profile,
        body=llm_body,
        existing=existing_evaluators,
        prompt_commit=prompt_commit,
        model_configuration_id=model_configuration_id,
    )
    if code["type"] != "code":
        raise OnlineProvisionError("code_evaluator_type_mismatch")
    if llm["type"] != "llm":
        raise OnlineProvisionError("llm_evaluator_type_mismatch")
    code_rule = _upsert_rule(
        cli,
        profile=profile,
        display_name=ONLINE_CODE_RULE_NAME,
        project_id=project_id,
        evaluator_id=str(code["id"]),
        include_spend_limit=False,
        existing=existing_rules,
    )
    llm_rule = _upsert_rule(
        cli,
        profile=profile,
        display_name=ONLINE_LLM_RULE_NAME,
        project_id=project_id,
        evaluator_id=str(llm["id"]),
        include_spend_limit=True,
        existing=existing_rules,
    )
    spend_enforced = bool(llm_rule.get("spend_limit")) or bool(
        llm_rule.get("spend_limit_enforced")
    )
    return OnlineProvisionSummary(
        project_name=ONLINE_EVAL_PROJECT,
        project_id=project_id,
        application_project_id=application_project_id,
        code_evaluator_id=str(code["id"]),
        llm_evaluator_id=str(llm["id"]),
        code_rule_id=str(code_rule["id"]),
        llm_rule_id=str(llm_rule["id"]),
        prompt_handle=ONLINE_JUDGE_PROMPT_HANDLE,
        prompt_commit=prompt_commit,
        prompt_sha256=EVAL_JUDGE_PROMPT_SHA256,
        model_id=EVAL_JUDGE_MODEL_ID,
        model_configuration_id=model_configuration_id,
        sampling_rate=ONLINE_EVAL_SAMPLING_RATE,
        spend_limit_usd=format(ONLINE_EVAL_MAX_USD, "f"),
        spend_limit_enforced=spend_enforced,
        backfill=False,
        created_new_resources=created_new,
        duplicate_rules=False,
    )


def verify_provisioned_resources(
    *,
    summary: OnlineProvisionSummary,
    evaluators: Sequence[Mapping[str, Any]],
    rules: Sequence[Mapping[str, Any]],
    application_rules: Sequence[Mapping[str, Any]] = (),
) -> None:
    """Reread evaluators and rules and compare identity plus safety bounds.

    Args:
        summary: First-pass provision result.
        evaluators: Fresh workspace evaluator list.
        rules: Fresh dedicated-project rules.
        application_rules: Rules attached to ``smart-rag``, if listed.

    Raises:
        OnlineProvisionError: IDs drifted, a duplicate rule exists, or the
            normal project received an evaluator rule.
    """

    named = [_as_mapping(item) for item in evaluators]
    by_name = {str(item.get("name")): item for item in named}
    code = by_name.get(ONLINE_CODE_EVALUATOR_NAME)
    llm = by_name.get(ONLINE_LLM_EVALUATOR_NAME)
    if code is None or llm is None:
        raise OnlineProvisionError("evaluator_missing_after_setup")
    if str(code.get("id")) != summary.code_evaluator_id:
        raise OnlineProvisionError("code_evaluator_id_drift")
    if str(llm.get("id")) != summary.llm_evaluator_id:
        raise OnlineProvisionError("llm_evaluator_id_drift")
    if code.get("type") != "code" or llm.get("type") != "llm":
        raise OnlineProvisionError("evaluator_type_mismatch")
    llm_inner = _as_mapping(llm.get("llm_evaluator"))
    commit = llm_inner.get("commit_hash_or_tag")
    if (
        llm_inner
        and commit
        not in {
            summary.prompt_commit,
            ONLINE_JUDGE_PROMPT_TAG,
        }
        and not str(commit or "").startswith(summary.prompt_commit[:8])
    ):
        if commit != summary.prompt_commit:
            raise OnlineProvisionError("prompt_commit_drift")
    listed_rules = [_as_mapping(item) for item in rules]
    code_rules = [
        item
        for item in listed_rules
        if str(item.get("evaluator_id")) == summary.code_evaluator_id
        or str(item.get("display_name")) == ONLINE_CODE_RULE_NAME
    ]
    llm_rules = [
        item
        for item in listed_rules
        if str(item.get("evaluator_id")) == summary.llm_evaluator_id
        or str(item.get("display_name")) == ONLINE_LLM_RULE_NAME
    ]
    if len(code_rules) != 1 or len(llm_rules) != 1:
        raise OnlineProvisionError("duplicate_or_missing_rule")
    _assert_rule_matches(code_rules[0], summary.project_id, spend=False)
    _assert_rule_matches(
        llm_rules[0],
        summary.project_id,
        spend=summary.spend_limit_enforced,
    )
    if any(
        str(_as_mapping(item).get("evaluator_id"))
        in {summary.code_evaluator_id, summary.llm_evaluator_id}
        for item in application_rules
    ):
        raise OnlineProvisionError("application_project_rule_forbidden")


def structured_prompt_messages(system_text: str) -> list[tuple[str, str]]:
    """Return the pinned StructuredPrompt messages.

    Args:
        system_text: Exact registered ``eval_judge_v1`` rubric.

    Returns:
        System plus user template messages.
    """

    return [("system", system_text), ("human", judge_user_template())]


def judge_schema() -> dict[str, object]:
    """Return the existing judge JSON schema.

    Returns:
        Schema for correctness, groundedness, refusal_quality, and rationale.
    """

    return eval_judge_json_schema()


def local_prompt_sha256(text: str) -> str:
    """Hash a prompt body the same way the registry does.

    Args:
        text: Prompt markdown.

    Returns:
        SHA-256 hex digest.
    """

    return sha256(text.encode("utf-8")).hexdigest()


def _upsert_code_evaluator(
    cli: LangSmithCliRunner,
    *,
    profile: str | None,
    existing: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Upload or replace the self-contained code evaluator.

    Args:
        cli: CLI runner.
        profile: Optional profile.
        existing: Already-listed evaluators.

    Returns:
        Evaluator mapping with ``id`` and ``type``.

    Raises:
        OnlineProvisionError: A same-name evaluator has an incompatible type.
    """

    found = _find_named(existing, ONLINE_CODE_EVALUATOR_NAME)
    found_map = _as_mapping(found) if found is not None else {}
    if found_map and found_map.get("type") not in {None, "code"}:
        raise OnlineProvisionError("code_evaluator_ownership_collision")
    if found_map.get("id") and found_map.get("type") == "code":
        found_map.setdefault("name", ONLINE_CODE_EVALUATOR_NAME)
        return found_map
    result = cli.run(code_evaluator_upload_args(profile=profile))
    if result.exit_code != 0:
        raise OnlineProvisionError("code_evaluator_upload_failed")
    refreshed = found_map or None
    payload = _as_mapping(result.payload)
    if payload:
        refreshed = _as_mapping(payload.get("evaluator")) or payload
    if refreshed is None or not refreshed.get("id"):
        raise OnlineProvisionError("code_evaluator_id_missing")
    refreshed.setdefault("type", "code")
    refreshed.setdefault("name", ONLINE_CODE_EVALUATOR_NAME)
    return refreshed


def _upsert_llm_evaluator(
    cli: LangSmithCliRunner,
    *,
    profile: str | None,
    body: Mapping[str, Any],
    existing: Sequence[Mapping[str, Any]],
    prompt_commit: str,
    model_configuration_id: str,
) -> dict[str, Any]:
    """Create or patch the hosted LLM judge by exact name.

    Args:
        cli: CLI runner.
        profile: Optional profile.
        body: Create body.
        existing: Already-listed evaluators.
        prompt_commit: Pinned commit.
        model_configuration_id: Playground settings id.

    Returns:
        Evaluator mapping.

    Raises:
        OnlineProvisionError: Type collision or API failure.
    """

    found = _find_named(existing, ONLINE_LLM_EVALUATOR_NAME)
    found_map = _as_mapping(found) if found is not None else {}
    if found_map and found_map.get("type") not in {None, "llm"}:
        raise OnlineProvisionError("llm_evaluator_ownership_collision")
    if not found_map:
        result = _api_json(
            cli,
            profile,
            ["api", EVALUATOR_CREATE_PATH, "--input", "-"],
            stdin=json.dumps(dict(body)),
        )
    else:
        update = llm_evaluator_update_body(
            prompt_commit=prompt_commit,
            model_configuration_id=model_configuration_id,
        )
        result = _api_json(
            cli,
            profile,
            [
                "api",
                f"{EVALUATOR_CREATE_PATH}/{found_map['id']}",
                "-X",
                "PATCH",
                "--input",
                "-",
            ],
            stdin=json.dumps(update),
        )
    evaluator = _unwrap_evaluator(result.payload, fallback=found)
    if not evaluator.get("id"):
        raise OnlineProvisionError("llm_evaluator_id_missing")
    evaluator.setdefault("type", "llm")
    evaluator.setdefault("name", ONLINE_LLM_EVALUATOR_NAME)
    return evaluator


def _upsert_rule(
    cli: LangSmithCliRunner,
    *,
    profile: str | None,
    display_name: str,
    project_id: str,
    evaluator_id: str,
    include_spend_limit: bool,
    existing: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create or patch exactly one rule for an evaluator on the project.

    Args:
        cli: CLI runner.
        profile: Optional profile.
        display_name: Stable rule name.
        project_id: Dedicated project UUID.
        evaluator_id: Evaluator UUID.
        include_spend_limit: True for the LLM rule.
        existing: Already-listed dedicated-project rules.

    Returns:
        Rule mapping containing ``id``.

    Raises:
        OnlineProvisionError: Duplicate matching rules or API failure.
    """

    existing_maps = [_as_mapping(item) for item in existing]
    matches = [
        item
        for item in existing_maps
        if str(item.get("display_name")) == display_name
        or (
            str(item.get("evaluator_id")) == evaluator_id
            and str(item.get("session_id")) == project_id
        )
    ]
    if len(matches) > 1:
        raise OnlineProvisionError("duplicate_rule")
    if not matches:
        rule = _submit_rule(
            cli,
            profile=profile,
            display_name=display_name,
            project_id=project_id,
            evaluator_id=evaluator_id,
            include_spend_limit=include_spend_limit,
            include_evaluator_id=True,
            rule_id=None,
        )
    else:
        rule_id = str(matches[0].get("id"))
        rule = _submit_rule(
            cli,
            profile=profile,
            display_name=display_name,
            project_id=project_id,
            evaluator_id=evaluator_id,
            include_spend_limit=include_spend_limit,
            include_evaluator_id=False,
            rule_id=rule_id,
        ) or dict(matches[0])
    if not rule.get("id"):
        if matches:
            rule = dict(matches[0])
        else:
            raise OnlineProvisionError("rule_id_missing")
    return rule


def _submit_rule(
    cli: LangSmithCliRunner,
    *,
    profile: str | None,
    display_name: str,
    project_id: str,
    evaluator_id: str,
    include_spend_limit: bool,
    include_evaluator_id: bool,
    rule_id: str | None,
) -> dict[str, Any]:
    """Create or patch one run rule, falling back if spend caps are denied.

    Args:
        cli: CLI runner.
        profile: Optional profile.
        display_name: Stable rule name.
        project_id: Dedicated project UUID.
        evaluator_id: Evaluator UUID.
        include_spend_limit: Request the weekly USD 2 cap.
        include_evaluator_id: True only on create.
        rule_id: Existing rule UUID for PATCH.

    Returns:
        Rule mapping. ``spend_limit_enforced`` is set when a cap was requested.

    Raises:
        OnlineProvisionError: API failure other than missing spend entitlement.
    """

    body = run_rule_body(
        display_name=display_name,
        project_id=project_id,
        evaluator_id=evaluator_id,
        include_spend_limit=include_spend_limit,
        include_evaluator_id=include_evaluator_id,
    )
    assert_rule_contract(
        body,
        project_id=project_id,
        require_spend_limit=include_spend_limit,
    )
    args = (
        ["api", RUN_RULES_PATH, "--input", "-"]
        if rule_id is None
        else ["api", f"{RUN_RULES_PATH}/{rule_id}", "-X", "PATCH", "--input", "-"]
    )
    try:
        result = _api_json(cli, profile, args, stdin=json.dumps(body))
    except OnlineProvisionError as exc:
        if str(exc) != "spend_limit_unavailable" or not include_spend_limit:
            raise
        fallback = run_rule_body(
            display_name=display_name,
            project_id=project_id,
            evaluator_id=evaluator_id,
            include_spend_limit=False,
            include_evaluator_id=include_evaluator_id,
        )
        assert_rule_contract(
            fallback,
            project_id=project_id,
            require_spend_limit=False,
        )
        result = _api_json(cli, profile, args, stdin=json.dumps(fallback))
        mapped = _as_mapping(result.payload)
        mapped["spend_limit_enforced"] = False
        return mapped
    mapped = _as_mapping(result.payload)
    mapped["spend_limit_enforced"] = include_spend_limit
    return mapped


def _api_json(
    cli: LangSmithCliRunner,
    profile: str | None,
    args: Sequence[str],
    *,
    stdin: str | None = None,
) -> CliResult:
    """Invoke ``langsmith api`` and require a zero exit code.

    Args:
        cli: CLI runner.
        profile: Optional profile.
        args: Args after the optional profile flags.
        stdin: Optional JSON body.

    Returns:
        CLI result.

    Raises:
        OnlineProvisionError: Non-zero exit.
    """

    prefix: list[str] = []
    if profile:
        prefix.extend(["--profile", profile])
    result = cli.run([*prefix, *args], stdin=stdin)
    if result.exit_code != 0:
        blob = f"{result.stdout} {result.stderr}"
        if "Spend limits are not available" in blob:
            raise OnlineProvisionError("spend_limit_unavailable")
        path = next(
            (
                item
                for item in args
                if item not in {"api", "-X", "PATCH", "POST", "--input", "-"}
            ),
            "unknown",
        )
        raise OnlineProvisionError(f"langsmith_api_failed:{path}")
    return result


def _find_named(items: Sequence[Mapping[str, Any]], name: str) -> dict[str, Any] | None:
    """Return the first mapping with ``name``.

    Args:
        items: Candidate mappings.
        name: Exact name.

    Returns:
        Copy of the mapping, or None.
    """

    for item in items:
        mapped = _as_mapping(item)
        if str(mapped.get("name")) == name:
            return mapped
    return None


def _unwrap_evaluator(
    payload: object, *, fallback: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Extract an evaluator object from a create/patch response.

    Args:
        payload: CLI JSON payload.
        fallback: Previous listing row.

    Returns:
        Evaluator mapping.
    """

    mapped = _as_mapping(payload)
    if mapped:
        inner = _as_mapping(mapped.get("evaluator"))
        if inner:
            return inner
        if mapped.get("id"):
            return mapped
    if fallback is not None:
        return _as_mapping(fallback)
    return {}


def _as_mapping(value: object) -> dict[str, Any]:
    """Return a dict copy of a mapping.

    Args:
        value: Candidate mapping.

    Returns:
        Dict, or empty.
    """

    if isinstance(value, Mapping):
        typed = cast(Mapping[object, object], value)
        return {str(key): item for key, item in typed.items()}
    return {}


def _assert_rule_matches(
    rule: Mapping[str, Any],
    project_id: str,
    *,
    spend: bool,
) -> None:
    """Require enabled state, sampling, filter, and optional spend cap.

    Args:
        rule: Reread rule.
        project_id: Dedicated project UUID.
        spend: Whether a spend cap is required.

    Raises:
        OnlineProvisionError: A safety field drifted.
    """

    payload = _as_mapping(rule)
    if str(payload.get("session_id")) != project_id:
        raise OnlineProvisionError("rule_project_mismatch")
    if float(payload.get("sampling_rate") or 0) != ONLINE_EVAL_SAMPLING_RATE:
        raise OnlineProvisionError("sampling_rate_mismatch")
    if payload.get("is_enabled") is False:
        raise OnlineProvisionError("rule_disabled")
    if payload.get("filter") != ONLINE_EVAL_ROOT_FILTER:
        raise OnlineProvisionError("filter_mismatch")
    if spend:
        spend_obj = _as_mapping(payload.get("spend_limit"))
        if not spend_obj:
            raise OnlineProvisionError("spend_limit_required")
        if Decimal(str(spend_obj.get("limit_usd"))) > ONLINE_EVAL_MAX_USD:
            raise OnlineProvisionError("spend_limit_mismatch")
        if spend_obj.get("window") != ONLINE_EVAL_SPEND_WINDOW:
            raise OnlineProvisionError("spend_window_mismatch")


def _assert_uuid(value: str, *, reason: str) -> None:
    """Require a UUID string.

    Args:
        value: Candidate UUID.
        reason: Error token.

    Raises:
        OnlineProvisionError: The value is not a UUID.
    """

    try:
        UUID(value)
    except (TypeError, ValueError) as exc:
        raise OnlineProvisionError(reason) from exc


def parse_cli_json(stdout: str) -> Any:
    """Parse CLI stdout as JSON when possible.

    Args:
        stdout: Command output.

    Returns:
        Parsed object, or None.
    """

    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def subprocess_cli_runner(
    *,
    profile: str | None = None,
) -> Callable[[Sequence[str], str | None], CliResult]:
    """Return a real subprocess runner. Used only by the setup script.

    Args:
        profile: Unused here; callers pass profile in ``args``.

    Returns:
        Function compatible with tests that wrap ``LangSmithCliRunner``.
    """

    del profile

    def _run(args: Sequence[str], stdin: str | None = None) -> CliResult:
        """Invoke the installed ``langsmith`` binary.

        Args:
            args: CLI arguments.
            stdin: Optional body.

        Returns:
            Exit code plus parsed JSON payload.
        """

        import subprocess

        completed = subprocess.run(  # noqa: S603
            ["langsmith", *args],  # noqa: S607
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
        )
        return CliResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            payload=parse_cli_json(completed.stdout),
        )

    return _run
