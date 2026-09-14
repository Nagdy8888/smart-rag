"""Local PDF evaluation workspace store: path, revision, and redaction."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from smart_rag_core.evaluation.private_pdf.draft import (
    ChunkLocator,
    build_draft_rows,
)
from smart_rag_core.evaluation.private_pdf.schema import (
    MINIMUM_SEALED_CASES,
    PrivatePdfQueryClass,
)
from smart_rag_core.evaluation.private_pdf.workspace_models import (
    WorkspaceCasePatch,
    WorkspacePathRejected,
    WorkspaceRevisionConflict,
)
from smart_rag_core.evaluation.private_pdf.workspace_store import (
    PdfEvalWorkspaceStore,
    atomic_replace_bytes,
    resolve_workspace_path,
)

_CHUNK = UUID("00000000-0000-0000-0000-000000000001")
_CASE_ID = "aaaaaaaaaaaaaaaaaaaaaaaa"


def _v1_payload(**overrides: object) -> dict[str, object]:
    """Return one v1 draft envelope with a single labeled case.

    Args:
        **overrides: Envelope-level replacements.

    Returns:
        JSON-compatible mapping. Tests must not print questions.
    """

    case: dict[str, object] = {
        "case_id": _CASE_ID,
        "split": "development",
        "source_family_id": "bbbbbbbbbbbbbbbbbbbbbbbb",
        "query_class": PrivatePdfQueryClass.FACTUAL_DEFINITION.value,
        "chunk_ids": [str(_CHUNK)],
        "page_numbers": [1],
        "heading_paths": ["Chapter 1"],
        "required_terms": ["Hybrid"],
        "expected_profile_id": "hybrid_default_v1",
        "expected_scope": "unscoped",
        "expected_refusal": False,
        "acl_actor_id": "actor-1",
        "human_approved": True,
        "generated_only": False,
        "reviewer": "reviewer-1",
        "question": "What is stated about Hybrid?",
        "expected_answer": "Agents coordinate tools.",
        "atomic_facts": ["Agents coordinate tools."],
        "question_sha256": "deadbeef",
    }
    envelope: dict[str, object] = {
        "schema_version": "private-pdf-eval-v1",
        "generated_only": False,
        "human_sealed": False,
        "holdout_opened": False,
        "version_id": "00000000-0000-0000-0000-000000000002",
        "document_id": "00000000-0000-0000-0000-000000000003",
        "content_hash": "aa" * 32,
        "openai_calls": 0,
        "cases": [case],
    }
    envelope.update(overrides)
    return envelope


def _write_v1(path: Path, payload: dict[str, object] | None = None) -> None:
    """Write a pretty-printed v1 draft file.

    Args:
        path: Destination.
        payload: Optional envelope.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or _v1_payload(), indent=2), encoding="utf-8")


def test_resolve_rejects_traversal_and_holdout(tmp_path: Path) -> None:
    """``../`` and holdout components fail closed before any read."""

    root = tmp_path / "workspace"
    root.mkdir()
    with pytest.raises(WorkspacePathRejected):
        resolve_workspace_path(root, "../secret.json")
    with pytest.raises(WorkspacePathRejected):
        resolve_workspace_path(root, "holdout/labels.json")
    with pytest.raises(WorkspacePathRejected):
        resolve_workspace_path(root, "Holdout/labels.json")
    with pytest.raises(WorkspacePathRejected):
        PdfEvalWorkspaceStore(root, relative_path="eval-draft/../holdout/x.json")


def test_v1_draft_loads_without_schema_break(tmp_path: Path) -> None:
    """Existing pretty-printed v1 drafts load, including extra hash keys."""

    root = tmp_path / "workspace"
    _write_v1(root / "eval-draft" / "draft.json")
    store = PdfEvalWorkspaceStore(root)
    snapshot = store.load()
    assert len(snapshot.cases) == 1
    assert snapshot.cases[0].meta.case_id == _CASE_ID
    assert snapshot.cases[0].meta.human_approved is True
    summaries = store.list_summaries()
    dumped = summaries[0].model_dump()
    assert "question" not in dumped
    assert "expected_answer" not in dumped


def test_stale_revision_does_not_overwrite(tmp_path: Path) -> None:
    """Compare-and-swap rejects a stale SHA-256 without mutating disk."""

    root = tmp_path / "workspace"
    path = root / "eval-draft" / "draft.json"
    _write_v1(path)
    store = PdfEvalWorkspaceStore(root)
    first = store.load()
    with pytest.raises(WorkspaceRevisionConflict):
        store.patch_case(
            _CASE_ID,
            WorkspaceCasePatch(question="Edited Hybrid question?"),
            expected_revision="0" * 64,
        )
    second = store.load()
    assert second.revision == first.revision
    assert second.cases[0].question == first.cases[0].question


def test_failed_write_leaves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replace failure leaves the previous dataset bytes in place."""

    root = tmp_path / "workspace"
    path = root / "eval-draft" / "draft.json"
    _write_v1(path)
    store = PdfEvalWorkspaceStore(root)
    before = store.load()

    def _boom(_path: Path, _payload: bytes) -> None:
        """Fail the atomic replace.

        Args:
            _path: Unused destination.
            _payload: Unused bytes.

        Raises:
            OSError: Always ``disk_full``.
        """

        raise OSError("disk_full")

    monkeypatch.setattr(
        "smart_rag_core.evaluation.private_pdf.workspace_store.atomic_replace_bytes",
        _boom,
    )
    with pytest.raises(OSError, match="disk_full"):
        store.patch_case(
            _CASE_ID,
            WorkspaceCasePatch(question="Edited Hybrid question?"),
            expected_revision=before.revision,
        )
    after = PdfEvalWorkspaceStore(root).load()
    assert after.revision == before.revision
    assert after.cases[0].question == before.cases[0].question


def test_edit_resets_approval(tmp_path: Path) -> None:
    """Editing question, answer, facts, or locators clears human approval."""

    root = tmp_path / "workspace"
    _write_v1(root / "eval-draft" / "draft.json")
    store = PdfEvalWorkspaceStore(root)
    snapshot = store.load()
    store.patch_case(
        _CASE_ID,
        WorkspaceCasePatch(question="According to Chapter 1, what is Hybrid?"),
        expected_revision=snapshot.revision,
    )
    _revision, case = store.get_case(_CASE_ID)
    assert case.meta.human_approved is False
    assert case.meta.generated_only is True
    assert case.meta.reviewer is None
    assert case.question.startswith("According")


def test_replace_drafts_never_self_approves(tmp_path: Path) -> None:
    """Generated rows stay generated-only and cannot carry a reviewer."""

    locators = tuple(
        ChunkLocator(
            chunk_id=UUID(f"00000000-0000-0000-0000-{index:012d}"),
            page_number=index + 1,
            section_path=(f"Chapter {index // 4}", f"Section {index}"),
            raw_text=f"Agents coordinate tools. Passage {index} defines Hybrid retrieval.",
        )
        for index in range(20)
    )
    rows = build_draft_rows(
        locators,
        document_hash="aa" * 32,
        aliases=("Hybrid retrieval",),
        acl_actor_id="actor-1",
    )
    poisoned = dict(rows[0])
    poisoned["human_approved"] = True
    poisoned["reviewer"] = "model"
    store = PdfEvalWorkspaceStore(tmp_path / "workspace")
    with pytest.raises(Exception, match="self_approve"):
        store.replace_drafts((poisoned,), expected_revision=None)
    revision = store.replace_drafts(rows, expected_revision=None)
    snapshot = store.load()
    assert snapshot.revision == revision
    assert len(snapshot.cases) >= MINIMUM_SEALED_CASES
    assert all(case.meta.generated_only is True for case in snapshot.cases)
    assert all(case.meta.human_approved is False for case in snapshot.cases)
    assert all(case.meta.reviewer is None for case in snapshot.cases)


def test_logs_omit_private_fields(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Store logs case ids only, never questions, answers, or absolute roots."""

    root = tmp_path / "workspace"
    unique_question = "UNIQUE_PRIVATE_QUESTION_CANARY_HYBRID"
    payload = _v1_payload()
    cases_raw = payload["cases"]
    assert isinstance(cases_raw, list)
    typed_case = cast(list[object], cases_raw)[0]
    assert isinstance(typed_case, dict)
    case_map = cast(dict[str, object], typed_case)
    case_map["question"] = unique_question
    _write_v1(root / "eval-draft" / "draft.json", payload)
    store = PdfEvalWorkspaceStore(root)
    snapshot = store.load()
    with caplog.at_level(logging.INFO):
        store.patch_case(
            _CASE_ID,
            WorkspaceCasePatch(expected_answer="Agents coordinate tools."),
            expected_revision=snapshot.revision,
        )
        store.set_approval(
            _CASE_ID,
            approved=True,
            reviewer="11111111-1111-1111-1111-111111111111",
            expected_revision=store.load().revision,
        )
    combined = caplog.text.lower()
    assert unique_question.lower() not in combined
    assert "agents coordinate tools" not in combined
    assert str(root.resolve()).lower() not in combined
    assert _CASE_ID in caplog.text


def test_atomic_replace_helper_is_durable(tmp_path: Path) -> None:
    """Successful atomic replace yields the new bytes and no leftover temp."""

    path = tmp_path / "eval-draft" / "draft.json"
    path.parent.mkdir(parents=True)
    path.write_text("old\n", encoding="utf-8")
    atomic_replace_bytes(path, b'{"ok":true}\n')
    assert path.read_text(encoding="utf-8") == '{"ok":true}\n'
    assert not path.with_name(path.name + ".tmp").exists()
