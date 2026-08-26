"""Frozen representative suite for hosted LangSmith online agent evaluators.

The manifest stores case identifiers only. Labels stay in the synthetic
development corpus. Holdout and qualification ids are rejected.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from smart_rag_core.evaluation.agent_eval import (
    AgentEvalError,
    AgentEvalSelection,
    select_development_cases,
)
from smart_rag_core.evaluation.hashes import canonical_dumps, sha256_text
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.loader import load_development_cases
from smart_rag_core.evaluation.online import (
    AGENT_ONLINE_EVAL_SCHEMA_VERSION,
    ONLINE_EVAL_MAX_CASES,
    ONLINE_EVAL_PROJECT,
    ONLINE_SUITE_RELATIVE_PATH,
    ONLINE_SUITE_SCHEMA_VERSION,
    QUERY_AGENT_ONLINE_EVAL_RUN,
)
from smart_rag_core.evaluation.schema import DATASET_SCHEMA_VERSION, DatasetSplit

REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_ONLINE_SUITE_PATH = REPO_ROOT / ONLINE_SUITE_RELATIVE_PATH


class OnlineSuiteError(AgentEvalError):
    """Raised when the frozen online suite is missing, drifted, or unsafe."""


class OnlineSuiteManifest(BaseModel):
    """Identifier-only online-evaluation suite.

    Attributes:
        schema_version: Suite file schema. Not the dataset schema.
        project: Dedicated tracing project. Must stay isolated.
        trace_schema_version: Envelope schema exported on root traces.
        root_run_name: Exact LangSmith root run name.
        redaction_class: Must remain ``synthetic``.
        split: Must remain ``development``.
        holdout_opened: Must remain false.
        max_cases: Hard ceiling, inclusive.
        case_ids: Ordered unique development case identifiers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["online-agent-eval-suite-v1"]
    project: Literal["smart-rag-agent-eval-online"]
    trace_schema_version: Literal["agent-online-eval-v1"]
    root_run_name: Literal["query.agent.eval.online.v1"]
    redaction_class: Literal["synthetic"]
    split: Literal["development"]
    holdout_opened: Literal[False]
    max_cases: int = Field(ge=1, le=ONLINE_EVAL_MAX_CASES)
    case_ids: tuple[str, ...] = Field(min_length=1, max_length=ONLINE_EVAL_MAX_CASES)

    @field_validator("case_ids")
    @classmethod
    def _unique_ids(cls, case_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Reject duplicate identifiers.

        Args:
            case_ids: Ordered identifiers.

        Returns:
            The unchanged tuple when every id is unique.

        Raises:
            ValueError: A duplicate id is present.
        """

        if len(set(case_ids)) != len(case_ids):
            raise ValueError("duplicate_case_id")
        return case_ids


def default_online_suite_path() -> Path:
    """Return the repository path of the frozen online suite.

    Returns:
        Absolute path under ``tests/fixtures/evaluation/phase6``.
    """

    return DEFAULT_ONLINE_SUITE_PATH


def load_online_suite_manifest(
    path: Path | None = None,
) -> OnlineSuiteManifest:
    """Load and validate the identifier-only suite file.

    Args:
        path: Optional override. Defaults to the frozen fixture.

    Returns:
        Typed suite manifest.

    Raises:
        OnlineSuiteError: The file is missing or fails the suite schema.
    """

    target = path if path is not None else default_online_suite_path()
    if not target.is_file():
        raise OnlineSuiteError("online_suite_missing")
    try:
        return OnlineSuiteManifest.model_validate_json(
            target.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise OnlineSuiteError("online_suite_invalid") from exc


def assert_online_suite_identity(manifest: OnlineSuiteManifest) -> None:
    """Fail closed when the suite points at the wrong project or split.

    Args:
        manifest: Loaded suite.

    Raises:
        OnlineSuiteError: Project, schema, split, or holdout identity drifted.
    """

    if manifest.project != ONLINE_EVAL_PROJECT:
        raise OnlineSuiteError("online_project_required")
    if manifest.trace_schema_version != AGENT_ONLINE_EVAL_SCHEMA_VERSION:
        raise OnlineSuiteError("online_schema_required")
    if manifest.root_run_name != QUERY_AGENT_ONLINE_EVAL_RUN:
        raise OnlineSuiteError("online_root_name_required")
    if manifest.schema_version != ONLINE_SUITE_SCHEMA_VERSION:
        raise OnlineSuiteError("online_suite_schema_required")
    if manifest.split != DatasetSplit.DEVELOPMENT.value:
        raise OnlineSuiteError("development_split_required")
    if manifest.holdout_opened:
        raise OnlineSuiteError("holdout_forbidden")
    if manifest.redaction_class != "synthetic":
        raise OnlineSuiteError("synthetic_content_required")


def load_online_eval_selection(
    *,
    path: Path | None = None,
    limit: int | None = None,
    case_ids: Sequence[str] = (),
    query_classes: Sequence[str] = (),
    holdout_access: HoldoutAccess | None = None,
) -> AgentEvalSelection:
    """Load the frozen suite and resolve synthetic development cases.

    Args:
        path: Optional suite override.
        limit: Optional prefix bound of the frozen order. ``None`` uses the
            whole suite.
        case_ids: Optional subset. Every id must already be in the suite.
        query_classes: Optional class filter applied after suite resolution.
        holdout_access: Must remain denied.

    Returns:
        Validated development selection. Dataset identity is unused by the
        online path and is retained only for local hashing.

    Raises:
        OnlineSuiteError: Suite identity, split, or subset checks fail.
        AgentEvalError: Development selection or holdout checks fail.
    """

    access = holdout_access if holdout_access is not None else HoldoutAccess.denied()
    if access.allowed:
        raise OnlineSuiteError("holdout_forbidden")
    manifest = load_online_suite_manifest(path)
    assert_online_suite_identity(manifest)
    frozen = tuple(manifest.case_ids)
    requested = tuple(dict.fromkeys(case_ids))
    if requested:
        unknown = [item for item in requested if item not in frozen]
        if unknown:
            raise OnlineSuiteError("online_suite_case_required")
        selected_ids = requested
    else:
        selected_ids = frozen
    if limit is not None:
        if limit < 1 or limit > ONLINE_EVAL_MAX_CASES:
            raise OnlineSuiteError("sample_exceeds_ceiling")
        selected_ids = selected_ids[:limit]
    if not selected_ids:
        raise OnlineSuiteError("sample_exceeds_ceiling")
    if len(selected_ids) > ONLINE_EVAL_MAX_CASES:
        raise OnlineSuiteError("sample_exceeds_ceiling")
    _assert_development_synthetic(selected_ids)
    return select_development_cases(
        limit=len(selected_ids),
        case_ids=selected_ids,
        query_classes=query_classes,
        holdout_access=HoldoutAccess.denied(),
    )


def online_suite_hash(manifest: OnlineSuiteManifest) -> str:
    """Hash suite identity fields and ordered case ids.

    Args:
        manifest: Loaded suite.

    Returns:
        SHA-256 hex digest. Labels are not included.
    """

    material = {
        "schema_version": manifest.schema_version,
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "project": manifest.project,
        "trace_schema_version": manifest.trace_schema_version,
        "root_run_name": manifest.root_run_name,
        "split": manifest.split,
        "case_ids": list(manifest.case_ids),
    }
    return sha256_text(canonical_dumps(material))


def _assert_development_synthetic(case_ids: Sequence[str]) -> None:
    """Reject ids that are missing, non-development, or non-synthetic.

    Args:
        case_ids: Candidate identifiers.

    Raises:
        OnlineSuiteError: An id is absent from development or not synthetic.
    """

    development = {case.case_id: case for case in load_development_cases()}
    for case_id in case_ids:
        case = development.get(case_id)
        if case is None:
            raise OnlineSuiteError("development_case_required")
        if case.split is not DatasetSplit.DEVELOPMENT:
            raise OnlineSuiteError("development_split_required")
        if case.redaction_class != "synthetic":
            raise OnlineSuiteError("synthetic_content_required")
