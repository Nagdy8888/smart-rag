"""Server-owned private-file store for the local PDF evaluation workspace.

HTTP callers never supply a filesystem path. The process owns the root.
Questions, answers, facts, excerpts, JWTs, and absolute roots are never
logged.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from smart_rag_core.evaluation.hashes import canonical_dumps, sha256_text
from smart_rag_core.evaluation.private_pdf.loader import read_private_pdf_labeled
from smart_rag_core.evaluation.private_pdf.schema import (
    PRIVATE_PDF_SCHEMA_VERSION,
    WORKSPACE_MAX_ANSWER_CHARS,
    WORKSPACE_MAX_CASES,
    WORKSPACE_MAX_FACT_CHARS,
    WORKSPACE_MAX_FACTS,
    WORKSPACE_MAX_GOLD_CHUNKS,
    WORKSPACE_MAX_QUESTION_CHARS,
    PrivatePdfLabeledCase,
)
from smart_rag_core.evaluation.private_pdf.seal import assert_holdout_path_hidden
from smart_rag_core.evaluation.private_pdf.workspace_models import (
    WorkspaceBoundsError,
    WorkspaceCasePatch,
    WorkspaceCaseSummary,
    WorkspacePathRejected,
    WorkspaceRevisionConflict,
    WorkspaceSnapshot,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_DATASET_RELATIVE = "eval-draft/draft.json"
_CONTENT_FIELDS = frozenset(
    {
        "question",
        "expected_answer",
        "atomic_facts",
        "chunk_ids",
        "page_numbers",
        "heading_paths",
    }
)


def _as_mapping(raw: object) -> dict[str, object]:
    """Coerce JSON object bytes into a string-keyed mapping.

    Args:
        raw: Parsed JSON value.

    Returns:
        String-keyed mapping.

    Raises:
        ValueError: When the value is not an object.
    """

    if not isinstance(raw, dict):
        raise ValueError("invalid_private_pdf_dataset")
    typed = cast(dict[Any, object], raw)
    return {str(key): value for key, value in typed.items()}


def resolve_workspace_path(root: Path, relative: str) -> Path:
    """Resolve a relative workspace path inside a server-owned root.

    Args:
        root: Server-owned workspace directory.
        relative: POSIX-style relative path under the root.

    Returns:
        Resolved path inside ``root``.

    Raises:
        WorkspacePathRejected: Traversal, symlink escape, absolute input,
            or a ``holdout`` path component.
    """

    if not relative or relative.startswith("/") or Path(relative).is_absolute():
        raise WorkspacePathRejected("workspace_path_rejected")
    candidate = Path(relative)
    if candidate.is_absolute() or ":" in relative.replace("\\", "/"):
        raise WorkspacePathRejected("workspace_path_rejected")
    for part in candidate.parts:
        lowered = part.lower()
        if part in {".", ""}:
            continue
        if part == ".." or lowered == "holdout":
            raise WorkspacePathRejected("workspace_path_rejected")
    root_resolved = root.resolve()
    target = (root_resolved / candidate).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise WorkspacePathRejected("workspace_path_rejected") from exc
    if "holdout" in {part.lower() for part in target.parts}:
        raise WorkspacePathRejected("workspace_path_rejected")
    assert_holdout_path_hidden(target)
    return target


def atomic_replace_bytes(path: Path, payload: bytes) -> None:
    """Write bytes to a sibling temp file then replace the destination.

    Args:
        path: Destination file.
        payload: UTF-8 JSON bytes.

    Side Effects:
        Creates parent directories. Leaves ``path`` unchanged when the
        temp write or replace raises.

    Raises:
        OSError: When the filesystem write or replace fails.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(payload)
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _validate_labeled_bounds(case: PrivatePdfLabeledCase) -> None:
    """Reject a labeled case that exceeds workspace bounds.

    Args:
        case: Labeled row.

    Raises:
        WorkspaceBoundsError: A field exceeds the local contract.
    """

    if len(case.question) > WORKSPACE_MAX_QUESTION_CHARS:
        raise WorkspaceBoundsError("workspace_question_chars")
    if len(case.expected_answer) > WORKSPACE_MAX_ANSWER_CHARS:
        raise WorkspaceBoundsError("workspace_answer_chars")
    if len(case.atomic_facts) > WORKSPACE_MAX_FACTS:
        raise WorkspaceBoundsError("workspace_fact_count")
    if any(len(item) > WORKSPACE_MAX_FACT_CHARS for item in case.atomic_facts):
        raise WorkspaceBoundsError("workspace_fact_chars")
    if not case.meta.chunk_ids or len(case.meta.chunk_ids) > WORKSPACE_MAX_GOLD_CHUNKS:
        raise WorkspaceBoundsError("workspace_gold_chunks")


def labeled_to_mapping(case: PrivatePdfLabeledCase) -> dict[str, object]:
    """Flatten a labeled case to the v1 draft JSON object shape.

    Args:
        case: Labeled case.

    Returns:
        Mapping suitable for the ``cases`` array. Callers must not log it.
    """

    meta = case.meta.model_dump(mode="json")
    meta["question"] = case.question
    meta["expected_answer"] = case.expected_answer
    meta["atomic_facts"] = list(case.atomic_facts)
    return meta


def summary_from_case(case: PrivatePdfLabeledCase) -> WorkspaceCaseSummary:
    """Build a list row that omits private question and answer fields.

    Args:
        case: Labeled case.

    Returns:
        Summary without question, answer, facts, or excerpts.
    """

    return WorkspaceCaseSummary(
        case_id=case.meta.case_id,
        split=case.meta.split,
        query_class=case.meta.query_class,
        human_approved=case.meta.human_approved,
        generated_only=case.meta.generated_only,
        reviewer=case.meta.reviewer,
        expected_refusal=case.meta.expected_refusal,
        gold_chunk_count=len(case.meta.chunk_ids),
    )


class PdfEvalWorkspaceStore:
    """Compare-and-swap private JSON store under a server-owned root.

    Args:
        root: Absolute or relative directory owned by the API process.
        relative_path: Dataset file under the root. Callers never pass a
            client-supplied filesystem path.
    """

    def __init__(
        self,
        root: Path,
        *,
        relative_path: str = DEFAULT_DATASET_RELATIVE,
    ) -> None:
        """Bind the server-owned root and dataset relative path.

        Args:
            root: Workspace directory.
            relative_path: Dataset file relative to ``root``.

        Raises:
            WorkspacePathRejected: The relative path is unsafe.
        """

        self._root = root
        self._relative_path = relative_path
        self._path = resolve_workspace_path(root, relative_path)
        self._lock = threading.Lock()

    @property
    def relative_path(self) -> str:
        """Return the server-owned relative dataset path.

        Returns:
            Relative path string. Never an absolute root.
        """

        return self._relative_path

    @property
    def root(self) -> Path:
        """Return the server-owned workspace root.

        Returns:
            Root path. Callers must not log it.
        """

        return self._root

    def dataset_path(self) -> Path:
        """Return the resolved dataset path after holdout/traversal checks.

        Returns:
            Resolved path inside the workspace root.
        """

        return resolve_workspace_path(self._root, self._relative_path)

    def revision_for_bytes(self, payload: bytes) -> str:
        """Hash canonical JSON bytes.

        Args:
            payload: File bytes.

        Returns:
            SHA-256 hex digest.
        """

        parsed: object = json.loads(payload.decode("utf-8"))
        return sha256_text(canonical_dumps(parsed))

    def _read_envelope(
        self,
    ) -> tuple[dict[str, object], tuple[PrivatePdfLabeledCase, ...], str]:
        """Load the dataset envelope, labeled cases, and revision.

        Returns:
            Envelope mapping, labeled cases, and revision.

        Raises:
            FileNotFoundError: Dataset is missing.
            WorkspaceBoundsError: Dataset exceeds 60 cases or field bounds.
            ValueError: ``holdout_opened`` is true.
        """

        path = self.dataset_path()
        payload = path.read_bytes()
        revision = self.revision_for_bytes(payload)
        raw: object = json.loads(payload.decode("utf-8"))
        envelope = _as_mapping(raw)
        if bool(envelope.get("holdout_opened", False)):
            raise ValueError("holdout_opened")
        cases = read_private_pdf_labeled(path)
        if len(cases) > WORKSPACE_MAX_CASES:
            raise WorkspaceBoundsError("workspace_case_count")
        for case in cases:
            _validate_labeled_bounds(case)
        return envelope, cases, revision

    def load(self) -> WorkspaceSnapshot:
        """Load the labeled dataset and its SHA-256 revision.

        Returns:
            Snapshot without logging private fields.

        Raises:
            FileNotFoundError: Dataset is missing.
            WorkspacePathRejected: Path is unsafe.
        """

        with self._lock:
            envelope, cases, revision = self._read_envelope()
            document_id = envelope.get("document_id")
            version_id = envelope.get("version_id")
            content_hash = envelope.get("content_hash")
            LOGGER.info(
                "pdf_eval_workspace_loaded",
                extra={
                    "event": "pdf_eval_workspace_loaded",
                    "case_count": len(cases),
                    "revision_prefix": revision[:12],
                },
            )
            return WorkspaceSnapshot(
                revision=revision,
                relative_path=self._relative_path,
                version_id=str(version_id) if version_id else None,
                document_id=str(document_id) if document_id else None,
                content_hash=str(content_hash) if content_hash else None,
                cases=cases,
            )

    def list_summaries(self) -> tuple[WorkspaceCaseSummary, ...]:
        """List cases without returning questions or answers.

        Returns:
            Summaries in file order.
        """

        snapshot = self.load()
        return tuple(summary_from_case(case) for case in snapshot.cases)

    def get_case(self, case_id: str) -> tuple[str, PrivatePdfLabeledCase]:
        """Return one labeled case and the current revision.

        Args:
            case_id: Case identifier.

        Returns:
            Revision and labeled case.

        Raises:
            KeyError: Unknown case id.
        """

        snapshot = self.load()
        for case in snapshot.cases:
            if case.meta.case_id == case_id:
                return snapshot.revision, case
        raise KeyError("unknown_pdf_eval_case")

    def _write_envelope(
        self,
        envelope: Mapping[str, object],
        cases: tuple[PrivatePdfLabeledCase, ...],
        *,
        expected_revision: str,
    ) -> str:
        """Compare-and-swap the dataset file.

        Args:
            envelope: Existing envelope fields.
            cases: Replacement labeled cases.
            expected_revision: Caller-held SHA-256.

        Returns:
            New revision.

        Raises:
            WorkspaceRevisionConflict: Disk revision differs.
            WorkspaceBoundsError: Bounds exceeded.
        """

        if len(cases) > WORKSPACE_MAX_CASES:
            raise WorkspaceBoundsError("workspace_case_count")
        for case in cases:
            _validate_labeled_bounds(case)
        path = self.dataset_path()
        current = self.revision_for_bytes(path.read_bytes())
        if current != expected_revision:
            raise WorkspaceRevisionConflict("stale_workspace_revision")
        merged: dict[str, object] = {
            **dict(envelope),
            "schema_version": PRIVATE_PDF_SCHEMA_VERSION,
            "holdout_opened": False,
            "cases": [labeled_to_mapping(case) for case in cases],
        }
        payload = (canonical_dumps(merged) + "\n").encode("utf-8")
        atomic_replace_bytes(path, payload)
        new_revision = self.revision_for_bytes(path.read_bytes())
        LOGGER.info(
            "pdf_eval_workspace_replaced",
            extra={
                "event": "pdf_eval_workspace_replaced",
                "case_count": len(cases),
                "revision_prefix": new_revision[:12],
            },
        )
        return new_revision

    def replace_drafts(
        self,
        rows: tuple[dict[str, object], ...],
        *,
        expected_revision: str | None,
        version_id: str | None = None,
        document_id: str | None = None,
        content_hash: str | None = None,
    ) -> str:
        """Replace the dataset with generated-only rows.

        Args:
            rows: Draft mappings from ``build_draft_rows``.
            expected_revision: Current revision, or None to create the file.
            version_id: Current PDF version id.
            document_id: Document id.
            content_hash: PDF SHA-256.

        Returns:
            New revision.

        Raises:
            WorkspaceRevisionConflict: Stale expected revision.
            WorkspaceBoundsError: Bounds exceeded.

        Side Effects:
            Writes the dataset file. Never self-approves rows.
        """

        if len(rows) > WORKSPACE_MAX_CASES:
            raise WorkspaceBoundsError("workspace_case_count")
        with self._lock:
            path = self.dataset_path()
            envelope: dict[str, object] = {
                "schema_version": PRIVATE_PDF_SCHEMA_VERSION,
                "generated_only": True,
                "human_sealed": False,
                "holdout_opened": False,
                "openai_calls": 0,
            }
            if version_id:
                envelope["version_id"] = version_id
            if document_id:
                envelope["document_id"] = document_id
            if content_hash:
                envelope["content_hash"] = content_hash
            if path.exists():
                existing, _cases, current = self._read_envelope()
                if expected_revision is None or current != expected_revision:
                    raise WorkspaceRevisionConflict("stale_workspace_revision")
                envelope = {**existing, **envelope}
            elif expected_revision is not None:
                raise WorkspaceRevisionConflict("stale_workspace_revision")
            for row in rows:
                if bool(row.get("human_approved", False)) or row.get("reviewer"):
                    raise WorkspaceBoundsError("generated_rows_cannot_self_approve")
                if row.get("generated_only") is not True:
                    raise WorkspaceBoundsError("generated_rows_cannot_self_approve")
            payload = (
                canonical_dumps({**envelope, "cases": list(rows)}) + "\n"
            ).encode("utf-8")
            atomic_replace_bytes(path, payload)
            cases = read_private_pdf_labeled(path)
            for case in cases:
                _validate_labeled_bounds(case)
                if case.meta.human_approved or case.meta.reviewer:
                    raise WorkspaceBoundsError("generated_rows_cannot_self_approve")
            revision = self.revision_for_bytes(path.read_bytes())
            LOGGER.info(
                "pdf_eval_workspace_drafted",
                extra={
                    "event": "pdf_eval_workspace_drafted",
                    "case_count": len(cases),
                    "revision_prefix": revision[:12],
                },
            )
            return revision

    def patch_case(
        self,
        case_id: str,
        patch: WorkspaceCasePatch,
        *,
        expected_revision: str,
    ) -> str:
        """Apply an edit and reset approval when content or locators change.

        Args:
            case_id: Case identifier.
            patch: Editable fields. Cannot set reviewer or approval.
            expected_revision: Caller-held SHA-256.

        Returns:
            New revision.

        Raises:
            KeyError: Unknown case.
            WorkspaceRevisionConflict: Stale revision.
        """

        with self._lock:
            envelope, cases, _revision = self._read_envelope()
            updated: list[PrivatePdfLabeledCase] = []
            found = False
            for case in cases:
                if case.meta.case_id != case_id:
                    updated.append(case)
                    continue
                found = True
                updated.append(_apply_patch(case, patch))
                LOGGER.info(
                    "pdf_eval_workspace_patched case_id=%s",
                    case_id,
                )
            if not found:
                raise KeyError("unknown_pdf_eval_case")
            return self._write_envelope(
                envelope,
                tuple(updated),
                expected_revision=expected_revision,
            )

    def set_approval(
        self,
        case_id: str,
        *,
        approved: bool,
        reviewer: str,
        expected_revision: str,
    ) -> str:
        """Record a named-human approve or reject. Reviewer is server-derived.

        Args:
            case_id: Case identifier.
            approved: True to approve, False to reject after inspection.
            reviewer: ``caller.user_id``. Never a client-supplied name.
            expected_revision: Caller-held SHA-256.

        Returns:
            New revision.

        Raises:
            KeyError: Unknown case.
            WorkspaceRevisionConflict: Stale revision.
            ValueError: Reviewer is blank.
        """

        if not reviewer.strip():
            raise ValueError("named_reviewer_required")
        with self._lock:
            envelope, cases, _revision = self._read_envelope()
            updated: list[PrivatePdfLabeledCase] = []
            found = False
            for case in cases:
                if case.meta.case_id != case_id:
                    updated.append(case)
                    continue
                found = True
                meta = case.meta.model_copy(
                    update={
                        "human_approved": approved,
                        "generated_only": False,
                        "reviewer": reviewer,
                    }
                )
                updated.append(case.model_copy(update={"meta": meta}))
                LOGGER.info(
                    "pdf_eval_workspace_reviewed case_id=%s approved=%s",
                    case_id,
                    approved,
                )
            if not found:
                raise KeyError("unknown_pdf_eval_case")
            return self._write_envelope(
                envelope,
                tuple(updated),
                expected_revision=expected_revision,
            )


def _apply_patch(
    case: PrivatePdfLabeledCase, patch: WorkspaceCasePatch
) -> PrivatePdfLabeledCase:
    """Return a new labeled case with content edits and approval reset.

    Args:
        case: Existing row.
        patch: Requested field replacements.

    Returns:
        Updated labeled case. Approval is cleared when Q/A/facts/locators
        change.

    Raises:
        WorkspaceBoundsError: Result exceeds bounds.
    """

    dumped = patch.model_dump(exclude_none=True)
    content_changed = bool(_CONTENT_FIELDS.intersection(dumped))
    question = patch.question if patch.question is not None else case.question
    answer = (
        patch.expected_answer
        if patch.expected_answer is not None
        else case.expected_answer
    )
    facts = patch.atomic_facts if patch.atomic_facts is not None else case.atomic_facts
    meta_update: dict[str, object] = {}
    if patch.chunk_ids is not None:
        meta_update["chunk_ids"] = patch.chunk_ids
    if patch.page_numbers is not None:
        meta_update["page_numbers"] = patch.page_numbers
    if patch.heading_paths is not None:
        meta_update["heading_paths"] = patch.heading_paths
    if patch.required_terms is not None:
        meta_update["required_terms"] = patch.required_terms
    if patch.expected_scope is not None:
        meta_update["expected_scope"] = patch.expected_scope
    if patch.expected_refusal is not None:
        meta_update["expected_refusal"] = patch.expected_refusal
    if patch.query_class is not None:
        meta_update["query_class"] = patch.query_class
    if content_changed:
        meta_update["human_approved"] = False
        meta_update["generated_only"] = True
        meta_update["reviewer"] = None
    meta = case.meta.model_copy(update=meta_update)
    updated = PrivatePdfLabeledCase(
        meta=meta,
        question=question,
        expected_answer=answer,
        atomic_facts=facts,
    )
    _validate_labeled_bounds(updated)
    return updated
