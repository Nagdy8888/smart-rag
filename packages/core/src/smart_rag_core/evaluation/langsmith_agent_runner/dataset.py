"""Drift-safe LangSmith dataset identity and sync."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from smart_rag_core.evaluation.agent_eval import (
    AGENT_EVAL_SCHEMA_VERSION,
    AgentEvalError,
    AgentEvalSelection,
    case_to_example_metadata,
    case_to_input,
    case_to_reference,
)
from smart_rag_core.evaluation.langsmith_agent_runner.types import (
    ALLOWED_EVALUATOR_KEYS,
    DATASET_METADATA_KEYS,
    REPO_ROOT,
    LangSmithEvalClient,
)
from smart_rag_core.evaluation.schema import (
    DATASET_SCHEMA_VERSION,
    LABEL_REVISION,
    DatasetSplit,
    EvaluationCase,
)


def dataset_identity_metadata(selection: AgentEvalSelection) -> dict[str, object]:
    """Return LangSmith dataset metadata that must match on every rerun.

    Args:
        selection: Validated development selection.

    Returns:
        Identity metadata. Extra evaluator bindings are omitted on purpose.
    """

    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "label_revision": LABEL_REVISION,
        "split": DatasetSplit.DEVELOPMENT.value,
        "manifest_hash": selection.manifest_hash,
        "agent_eval_schema_version": AGENT_EVAL_SCHEMA_VERSION,
        "redaction_class": "synthetic",
        "holdout_opened": False,
    }


def experiment_git_metadata(*, repo_root: Path | None = None) -> dict[str, object]:
    """Capture git commit and dirty-tree state without printing secrets.

    Args:
        repo_root: Repository root. Defaults to this file's repo.

    Returns:
        ``git_commit`` hex and ``git_dirty`` boolean. Unknown git is dirty.
    """

    root = repo_root if repo_root is not None else REPO_ROOT
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        dirty_text = subprocess.check_output(
            ["git", "status", "--porcelain"],  # noqa: S607
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": "unknown", "git_dirty": True}
    return {"git_commit": commit, "git_dirty": bool(dirty_text.strip())}


def sync_langsmith_dataset(
    client: LangSmithEvalClient,
    selection: AgentEvalSelection,
) -> None:
    """Create or verify the versioned dataset. Extra remote IDs fail closed.

    Args:
        client: LangSmith client subset.
        selection: Validated development selection.

    Raises:
        AgentEvalError: Metadata drift, extra examples, hash mismatch,
            unbudgeted dataset evaluators, or unverified 409 conflict.
    """

    metadata = dataset_identity_metadata(selection)
    name = selection.dataset_name
    if not client.has_dataset(dataset_name=name):
        client.create_dataset(
            name,
            description=(
                "Synthetic development agent-eval cases. Holdout sealed. "
                "Not a quality claim."
            ),
            metadata=dict(metadata),
        )
    existing = client.read_dataset(dataset_name=name)
    remote_meta = _object_mapping(getattr(existing, "metadata", None))
    for key in DATASET_METADATA_KEYS:
        if remote_meta.get(key) != metadata[key]:
            raise AgentEvalError("langsmith_dataset_drift")
    _assert_no_unbudgeted_evaluators(remote_meta)
    desired = {
        str(selection.example_ids[case.case_id]): selection.case_hashes[case.case_id]
        for case in selection.cases
    }
    remote_by_id = _index_remote_examples(client.list_examples(dataset_name=name))
    extra = set(remote_by_id) - set(desired)
    if extra:
        raise AgentEvalError("langsmith_dataset_drift")
    for example_id, case_hash in desired.items():
        remote = remote_by_id.get(example_id)
        if remote is None:
            continue
        if remote != case_hash:
            raise AgentEvalError("langsmith_dataset_drift")
    missing_ids = [item for item in desired if item not in remote_by_id]
    if not missing_ids:
        return
    examples = [
        _example_create_payload(selection, case)
        for case in selection.cases
        if str(selection.example_ids[case.case_id]) in missing_ids
    ]
    try:
        client.create_examples(dataset_name=name, examples=examples, max_concurrency=1)
    except Exception as exc:
        if not _is_conflict(exc):
            raise
        reread = _index_remote_examples(client.list_examples(dataset_name=name))
        for example_id, case_hash in desired.items():
            if reread.get(example_id) != case_hash:
                raise AgentEvalError("langsmith_dataset_drift") from exc
        return
    verified = _index_remote_examples(client.list_examples(dataset_name=name))
    for example_id, case_hash in desired.items():
        if verified.get(example_id) != case_hash:
            raise AgentEvalError("langsmith_dataset_drift")


def _example_create_payload(
    selection: AgentEvalSelection, case: EvaluationCase
) -> dict[str, Any]:
    """Build one LangSmith ``create_examples`` payload.

    Args:
        selection: Validated selection.
        case: Development case.

    Returns:
        Example mapping with stable id, inputs, reference outputs, metadata.
    """

    case_hash = selection.case_hashes[case.case_id]
    return {
        "id": str(selection.example_ids[case.case_id]),
        "inputs": case_to_input(case).model_dump(mode="json"),
        "outputs": case_to_reference(case).model_dump(mode="json"),
        "metadata": case_to_example_metadata(
            case, case_hash=case_hash, manifest_hash=selection.manifest_hash
        ),
    }


def _index_remote_examples(examples: Iterator[object]) -> dict[str, str]:
    """Index remote examples by id to case-content hash.

    Args:
        examples: LangSmith examples.

    Returns:
        Mapping of example id string to ``case_content_hash``.
    """

    indexed: dict[str, str] = {}
    for example in examples:
        example_id = _example_id(example)
        metadata = _object_mapping(getattr(example, "metadata", None))
        if not metadata and isinstance(example, Mapping):
            example_map = cast(Mapping[object, object], example)
            metadata = _object_mapping(example_map.get("metadata"))
            if not example_id:
                example_id = str(example_map.get("id") or "")
        hashed = str(metadata.get("case_content_hash") or "")
        if example_id:
            indexed[example_id] = hashed
    return indexed


def _example_id(example: object) -> str:
    """Return the example id as a string.

    Args:
        example: LangSmith example.

    Returns:
        UUID string, or empty.
    """

    raw: object = getattr(example, "id", None)
    if raw is None and isinstance(example, Mapping):
        raw = cast(Mapping[object, object], example).get("id")
    if raw is None:
        return ""
    if isinstance(raw, UUID):
        return str(raw)
    return str(raw)


def _object_mapping(value: object) -> dict[str, Any]:
    """Coerce dataset or example metadata to a string-keyed dict.

    Args:
        value: Mapping or None.

    Returns:
        Dict copy.
    """

    if isinstance(value, Mapping):
        typed = cast(Mapping[object, object], value)
        return {str(key): item for key, item in typed.items()}
    return {}


def _is_conflict(exc: BaseException) -> bool:
    """Return whether an exception represents HTTP 409.

    Args:
        exc: Raised error.

    Returns:
        True when status 409 or a conflict message is present.
    """

    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    if status == 409:
        return True
    text = str(exc).lower()
    return "409" in text or "conflict" in text


def _assert_no_unbudgeted_evaluators(metadata: Mapping[str, Any]) -> None:
    """Fail when the dataset binds unknown extra evaluators.

    Args:
        metadata: Dataset metadata.

    Raises:
        AgentEvalError: Unbudgeted evaluator names are present.
    """

    bound: list[str] = []
    for key in ("evaluators", "dataset_evaluators", "workspace_evaluators"):
        raw = metadata.get(key)
        if isinstance(raw, str) and raw:
            bound.append(raw)
        elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            bound.extend(str(item) for item in cast(Sequence[object], raw) if item)
    unknown = [item for item in bound if item not in ALLOWED_EVALUATOR_KEYS]
    if unknown:
        raise AgentEvalError("unbudgeted_dataset_evaluators")
