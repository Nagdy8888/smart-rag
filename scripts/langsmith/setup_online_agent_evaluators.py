#!/usr/bin/env python3
"""Provision dedicated LangSmith online evaluators for synthetic agent traces.

Creates or updates the code evaluator, hosted judge, and one run rule each
on ``smart-rag-agent-eval-online``. Does not attach resources to ``smart-rag``
or any dataset. Does not print API keys or provider secrets.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TextIO, cast
from uuid import UUID

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from smart_rag_core.evaluation.online import (  # noqa: E402
    APPLICATION_LANGSMITH_PROJECT,
    ONLINE_EVAL_PROJECT,
    ONLINE_JUDGE_PROMPT_HANDLE,
    ONLINE_JUDGE_PROMPT_TAG,
)
from smart_rag_core.evaluation.online_provision import (  # noqa: E402
    CliResult,
    LangSmithCliRunner,
    OnlineProvisionError,
    parse_cli_json,
    provision_online_evaluators,
    required_evaluator_fields,
    structured_prompt_messages,
    verify_provisioned_resources,
)
from smart_rag_core.query_answer.versions import (  # noqa: E402
    EVAL_JUDGE_MODEL_ID,
    EVAL_JUDGE_PROMPT_SHA256,
    EVAL_JUDGE_PROMPT_VERSION,
)
from smart_rag_core.settings import setdefault_process_environ  # noqa: E402


class SetupCliError(RuntimeError):
    """Setup preflight failure. The message is a stable token without secrets."""


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


class SubprocessLangSmithCli:
    """Authenticated ``langsmith`` CLI wrapper that never echoes secrets."""

    def run(self, args: Sequence[str], *, stdin: str | None = None) -> CliResult:
        """Run one ``langsmith`` command.

        Args:
            args: Argument vector excluding the binary.
            stdin: Optional request body.

        Returns:
            Exit code, stdout, stderr, and parsed JSON when present.
        """

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


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse setup flags.

    Args:
        argv: Argument vector excluding the program name.

    Returns:
        Parsed namespace.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Create or update dedicated online evaluators on "
            "smart-rag-agent-eval-online. Holdout stays sealed."
        )
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="LangSmith CLI profile name. Never a secret.",
    )
    parser.add_argument(
        "--model-configuration-id",
        required=True,
        help="Existing LangSmith gpt-4o-mini playground/model configuration UUID.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate local contracts only. No CLI, SDK, or remote writes.",
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


def require_cli() -> None:
    """Fail closed when the official LangSmith CLI is not on PATH.

    Raises:
        SetupCliError: ``langsmith`` is not installed.
    """

    if shutil.which("langsmith") is None:
        raise SetupCliError("langsmith_cli_missing")


def profile_args(profile: str | None) -> list[str]:
    """Return optional ``--profile`` flags.

    Args:
        profile: Profile name.

    Returns:
        Flag list, possibly empty.
    """

    if not profile:
        return []
    return ["--profile", profile]


def api_get(
    cli: LangSmithCliRunner,
    profile: str | None,
    path: str,
) -> Any:
    """GET one LangSmith REST path through the authenticated CLI.

    Args:
        cli: CLI runner.
        profile: Optional profile.
        path: REST path without a leading slash requirement.

    Returns:
        Parsed JSON payload.

    Raises:
        SetupCliError: Non-zero exit or empty payload.
    """

    result = cli.run([*profile_args(profile), "api", path])
    if result.exit_code != 0:
        raise SetupCliError("langsmith_auth_or_api_failed")
    return result.payload


def resolve_or_create_project(project_name: str) -> tuple[str, bool]:
    """Read or create one tracing project through the pinned Python SDK.

    Args:
        project_name: Exact project name.

    Returns:
        Project id and whether this call created it.

    Raises:
        SetupCliError: The SDK cannot resolve a project id.
    """

    from langsmith import Client

    client = Client()
    created = False
    if not client.has_project(project_name=project_name):
        create_project = cast(Callable[..., object], cast(Any, client).create_project)
        create_project(
            project_name,
            description=(
                "Synthetic online agent evaluation only. Holdout sealed. "
                "Not a quality claim."
            ),
            metadata={
                "purpose": "synthetic-online-eval",
                "redaction_class": "synthetic",
                "holdout_opened": False,
            },
        )
        created = True
    project = client.read_project(project_name=project_name)
    project_id = str(getattr(project, "id", "") or "")
    if not project_id:
        raise SetupCliError("project_id_missing")
    try:
        UUID(project_id)
    except ValueError as exc:
        raise SetupCliError("project_id_invalid") from exc
    return project_id, created


def push_judge_prompt() -> str:
    """Push the pinned StructuredPrompt and return the commit hash or tag.

    Returns:
        Commit hash extracted from the prompt URL, or the pinned tag.

    Raises:
        SetupCliError: Prompt text drifted or push failed.

    Side Effects:
        Creates or updates the private prompt repo. Does not upload provider
        keys.
    """

    from langchain_core.prompts.structured import StructuredPrompt
    from langsmith import Client
    from smart_rag_agents.prompts.registry import prompt_text
    from smart_rag_core.evaluation.online_provision import (
        judge_schema,
        local_prompt_sha256,
    )

    rubric = prompt_text(EVAL_JUDGE_PROMPT_VERSION)
    digest = local_prompt_sha256(rubric)
    if digest != EVAL_JUDGE_PROMPT_SHA256:
        raise SetupCliError("judge_prompt_sha256_mismatch")
    prompt = StructuredPrompt.from_messages_and_schema(
        structured_prompt_messages(rubric),
        judge_schema(),
    )
    client = Client()
    try:
        url = client.push_prompt(
            ONLINE_JUDGE_PROMPT_HANDLE,
            object=prompt,
            is_public=False,
            description="Pinned synthetic online judge. eval_judge_v1 rubric.",
            commit_tags=[ONLINE_JUDGE_PROMPT_TAG],
            commit_description="agent-online-eval-v1 structured judge",
        )
    except Exception as exc:
        message = str(exc)
        if "Nothing to commit" in message or "409 Client Error" in message:
            return ONLINE_JUDGE_PROMPT_TAG
        raise SetupCliError("judge_prompt_push_failed") from exc
    commit = _commit_from_prompt_url(str(url))
    if not commit:
        return ONLINE_JUDGE_PROMPT_TAG
    return commit


def _commit_from_prompt_url(url: str) -> str:
    """Extract a commit hash from a LangSmith prompt URL.

    Args:
        url: Prompt URL returned by ``push_prompt``.

    Returns:
        Hash after the last colon, or empty.
    """

    if ":" not in url:
        return ""
    candidate = url.rsplit(":", 1)[-1].strip().strip("/")
    if not candidate or candidate == "latest" or " " in candidate or "/" in candidate:
        return ""
    return candidate


def _json_object(value: object) -> dict[str, Any]:
    """Copy a JSON object into a string-keyed dict.

    Args:
        value: Candidate mapping.

    Returns:
        Dict copy, or empty.
    """

    if not isinstance(value, dict):
        return {}
    typed = cast(dict[object, object], value)
    return {str(key): item for key, item in typed.items()}


def list_evaluators(
    cli: LangSmithCliRunner, profile: str | None
) -> list[dict[str, Any]]:
    """List workspace evaluators.

    Args:
        cli: CLI runner.
        profile: Optional profile.

    Returns:
        Evaluator mappings.
    """

    payload = api_get(cli, profile, "platform/evaluators?limit=100")
    if isinstance(payload, dict):
        typed = cast(dict[str, Any], payload)
        items = typed.get("evaluators")
        if isinstance(items, list):
            collected: list[dict[str, Any]] = []
            for item in cast(list[object], items):
                if isinstance(item, dict):
                    collected.append(_json_object(cast(object, item)))
            return collected
    return []


def list_rules(
    cli: LangSmithCliRunner,
    profile: str | None,
    *,
    session_id: str,
) -> list[dict[str, Any]]:
    """List run rules for one tracing project.

    Args:
        cli: CLI runner.
        profile: Optional profile.
        session_id: Project UUID.

    Returns:
        Rule mappings.
    """

    payload = api_get(cli, profile, f"runs/rules?session_id={session_id}")
    if isinstance(payload, list):
        collected: list[dict[str, Any]] = []
        for item in cast(list[object], payload):
            if isinstance(item, dict):
                collected.append(_json_object(cast(object, item)))
        return collected
    if isinstance(payload, dict):
        typed = cast(dict[str, Any], payload)
        items = typed.get("items")
        if items is None:
            items = typed.get("rules")
        if isinstance(items, list):
            collected = []
            for item in cast(list[object], items):
                if isinstance(item, dict):
                    collected.append(_json_object(cast(object, item)))
            return collected
        if typed.get("id"):
            return [typed]
    return []


def main(argv: list[str] | None = None) -> int:
    """Provision or dry-run dedicated online evaluators.

    Args:
        argv: Optional CLI arguments excluding the program name.

    Returns:
        ``0`` on success. ``2`` when auth, identity, or bounds fail closed.
    """

    args = parse_args(argv)
    try:
        load_repo_env()
        if not args.model_configuration_id.strip():
            raise SetupCliError("model_configuration_required")
        if args.dry_run:
            print_json(
                {
                    "dry_run": True,
                    "project": ONLINE_EVAL_PROJECT,
                    "application_project": APPLICATION_LANGSMITH_PROJECT,
                    "model_id": EVAL_JUDGE_MODEL_ID,
                    "prompt_handle": ONLINE_JUDGE_PROMPT_HANDLE,
                    "prompt_tag": ONLINE_JUDGE_PROMPT_TAG,
                    "prompt_sha256": EVAL_JUDGE_PROMPT_SHA256,
                    "required_fields": sorted(required_evaluator_fields()),
                    "writes": False,
                }
            )
            return 0
        require_cli()
        cli = SubprocessLangSmithCli()
        whoami = cli.run(
            [*profile_args(args.profile), "api", "info", "GET", "sessions"]
        )
        if whoami.exit_code != 0:
            raise SetupCliError("langsmith_auth_required")
        evaluators = list_evaluators(cli, args.profile)
        project_id, created_project = resolve_or_create_project(ONLINE_EVAL_PROJECT)
        application_id = None
        from langsmith import Client

        client = Client()
        if client.has_project(project_name=APPLICATION_LANGSMITH_PROJECT):
            application = client.read_project(
                project_name=APPLICATION_LANGSMITH_PROJECT
            )
            application_id = str(getattr(application, "id", "") or "") or None
            if application_id == project_id:
                raise SetupCliError("dedicated_project_collision")
        prompt_commit = push_judge_prompt()
        rules = list_rules(cli, args.profile, session_id=project_id)
        summary = provision_online_evaluators(
            cli,
            profile=args.profile,
            model_configuration_id=args.model_configuration_id,
            prompt_commit=prompt_commit,
            project_id=project_id,
            application_project_id=application_id,
            existing_evaluators=evaluators,
            existing_rules=rules,
            created_new=created_project,
        )
        verify_provisioned_resources(
            summary=summary,
            evaluators=list_evaluators(cli, args.profile),
            rules=list_rules(cli, args.profile, session_id=project_id),
            application_rules=(
                list_rules(cli, args.profile, session_id=application_id)
                if application_id
                else ()
            ),
        )
        print_json(summary.as_json())
        return 0
    except (SetupCliError, OnlineProvisionError) as exc:
        print_json({"error": str(exc)}, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
