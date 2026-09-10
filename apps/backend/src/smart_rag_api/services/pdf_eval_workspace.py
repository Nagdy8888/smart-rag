"""Local PDF evaluation workspace HTTP service. Uses app_api only."""

from __future__ import annotations

import json
import logging
from typing import Any, cast
from uuid import UUID

import psycopg
from smart_rag_core.evaluation.private_pdf.draft import ChunkLocator, build_draft_rows
from smart_rag_core.evaluation.private_pdf.metrics import citation_gold_overlap
from smart_rag_core.evaluation.private_pdf.schema import PrivatePdfLabeledCase
from smart_rag_core.evaluation.private_pdf.workspace_models import (
    WorkspaceCasePatch,
)
from smart_rag_core.evaluation.private_pdf.workspace_store import (
    PdfEvalWorkspaceStore,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.retrieval.context_loader import (
    ChunkContext,
    list_authorized_eval_passages,
)
from smart_rag_core.security.identity import CallerContext

from smart_rag_api.services.query_runs import QueryRunService

LOGGER = logging.getLogger(__name__)

_LATEST_REPORT_RELATIVE = "eval-draft/latest-report.json"


class PdfEvalWorkspaceService:
    """Owner/admin evaluation workspace operations.

    Args:
        store: Server-owned private-file store.
        postgres_url: ``app_api`` DSN. Never an operator DSN.
        query_runs: Caller-owned run fetch/citation service.
    """

    def __init__(
        self,
        store: PdfEvalWorkspaceStore,
        *,
        postgres_url: str,
        query_runs: QueryRunService,
    ) -> None:
        """Bind store, app_api DSN, and run service.

        Args:
            store: Workspace store.
            postgres_url: Transaction-pooled ``app_api`` URL.
            query_runs: Owned-run citation loader.
        """

        self._store = store
        self._postgres_url = postgres_url
        self._query_runs = query_runs

    def status(self) -> dict[str, object]:
        """Return dataset presence without private fields.

        Returns:
            Status mapping.
        """

        try:
            snapshot = self._store.load()
        except FileNotFoundError:
            return {
                "enabled": True,
                "case_count": 0,
                "revision": None,
                "version_id": None,
                "document_id": None,
                "dataset_present": False,
            }
        return {
            "enabled": True,
            "case_count": len(snapshot.cases),
            "revision": snapshot.revision,
            "version_id": snapshot.version_id,
            "document_id": snapshot.document_id,
            "dataset_present": True,
        }

    def list_cases(
        self,
        *,
        split: str | None,
        after_case_id: str | None,
        limit: int,
    ) -> tuple[str, tuple[PrivatePdfLabeledCase, ...], str | None]:
        """Return a page of cases. Holdout split queries are rejected.

        Args:
            split: Optional split filter. ``holdout`` is rejected.
            after_case_id: Keyset cursor.
            limit: Page size 1-60.

        Returns:
            Revision, page of cases, next case id.

        Raises:
            ValueError: Holdout split query.
            FileNotFoundError: Dataset missing.
        """

        if split == "holdout":
            raise ValueError("holdout_split_query")
        snapshot = self._store.load()
        cases = snapshot.cases
        if split is not None:
            cases = tuple(case for case in cases if case.meta.split == split)
        started = 0
        if after_case_id:
            for index, case in enumerate(cases):
                if case.meta.case_id == after_case_id:
                    started = index + 1
                    break
        page = cases[started : started + limit]
        next_id = (
            cases[started + limit].meta.case_id
            if started + limit < len(cases)
            else None
        )
        return snapshot.revision, page, next_id

    def get_case(self, case_id: str) -> tuple[str, PrivatePdfLabeledCase]:
        """Return one labeled case.

        Args:
            case_id: Case identifier.

        Returns:
            Revision and case.
        """

        return self._store.get_case(case_id)

    def patch_case(
        self, case_id: str, patch: WorkspaceCasePatch, *, expected_revision: str
    ) -> str:
        """Apply an edit and reset approval on content or locator changes.

        Args:
            case_id: Case identifier.
            patch: Editable fields.
            expected_revision: Caller-held SHA-256.

        Returns:
            New revision.
        """

        return self._store.patch_case(
            case_id, patch, expected_revision=expected_revision
        )

    def set_approval(
        self, case_id: str, *, approved: bool, reviewer: str, expected_revision: str
    ) -> str:
        """Approve or reject with the server-derived caller id.

        Args:
            case_id: Case identifier.
            approved: Approve vs reject.
            reviewer: ``caller.user_id``.
            expected_revision: Caller-held SHA-256.

        Returns:
            New revision.
        """

        return self._store.set_approval(
            case_id,
            approved=approved,
            reviewer=reviewer,
            expected_revision=expected_revision,
        )

    def list_passages(
        self,
        caller: CallerContext,
        *,
        limit: int,
        after_chunk_id: UUID | None,
    ) -> tuple[ChunkContext, ...]:
        """List ACL/current representative passages for the workspace version.

        Args:
            caller: Authenticated owner/admin.
            limit: Page size.
            after_chunk_id: Keyset cursor.

        Returns:
            Authorized passages. Cross-document IDs never appear.

        Raises:
            FileNotFoundError: Dataset missing.
            ValueError: Version id missing.
        """

        snapshot = self._store.load()
        if not snapshot.version_id:
            raise ValueError("version_id_missing")
        version_id = UUID(snapshot.version_id)
        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            return list_authorized_eval_passages(
                connection,
                caller,
                version_id=version_id,
                limit=limit,
                after_chunk_id=after_chunk_id,
            )

    def regenerate_drafts(
        self,
        caller: CallerContext,
        *,
        expected_revision: str | None,
    ) -> str:
        """Rebuild generated-only rows from current authorized passages.

        Args:
            caller: Authenticated owner/admin.
            expected_revision: Current revision, or None to create.

        Returns:
            New revision.

        Raises:
            ValueError: Missing version/hash or too few locators.
        """

        snapshot = None
        try:
            snapshot = self._store.load()
        except FileNotFoundError:
            snapshot = None
        version_id = snapshot.version_id if snapshot else None
        content_hash = snapshot.content_hash if snapshot else None
        document_id = snapshot.document_id if snapshot else None
        if not version_id or not content_hash:
            raise ValueError("ingest_identity_missing")
        locators: list[ChunkLocator] = []
        after: UUID | None = None
        while len(locators) < 60:
            page = self.list_passages(caller, limit=60, after_chunk_id=after)
            if not page:
                break
            for item in page:
                locators.append(
                    ChunkLocator(
                        chunk_id=item.chunk_id,
                        page_number=item.page_number or 1,
                        section_path=item.section_path,
                        raw_text=item.raw_text,
                    )
                )
            after = page[-1].chunk_id
            if len(page) < 60:
                break
        rows = build_draft_rows(
            tuple(locators),
            document_hash=content_hash,
            aliases=(),
            acl_actor_id=caller.user_id,
        )
        LOGGER.info(
            "pdf_eval_workspace_regenerated case_count=%s",
            len(rows),
        )
        return self._store.replace_drafts(
            rows,
            expected_revision=expected_revision,
            version_id=version_id,
            document_id=document_id,
            content_hash=content_hash,
        )

    def latest_report(self) -> dict[str, object]:
        """Load a count-only latest report under the workspace root.

        Returns:
            Count-only mapping. Missing file → ``present=false``.

        Raises:
            WorkspacePathRejected: Holdout path.
            ValueError: Report contains private field names.
        """

        from smart_rag_core.evaluation.private_pdf.workspace_store import (
            resolve_workspace_path,
        )

        path = resolve_workspace_path(self._store.root, "eval-draft/latest-report.json")
        if not path.is_file():
            return {"present": False, "holdout_opened": False}
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("invalid_eval_report")
        mapping = cast(dict[str, Any], raw)
        forbidden = {
            "question",
            "expected_answer",
            "atomic_facts",
            "raw_text",
            "excerpt",
        }
        if forbidden.intersection(mapping):
            raise ValueError("report_contains_private_fields")
        return {
            "present": True,
            "holdout_opened": bool(mapping.get("holdout_opened", False)),
            "case_count": mapping.get("case_count"),
            "gates_pass": mapping.get("gates_pass"),
            "hybrid_recall_at_10": mapping.get("hybrid_recall_at_10"),
        }

    def compare_run(
        self,
        caller: CallerContext,
        *,
        case_id: str,
        run_id: UUID,
    ) -> dict[str, object]:
        """Score citation overlap for a caller-owned run.

        Args:
            caller: Authenticated owner/admin.
            case_id: Evaluation case.
            run_id: Caller-owned query run.

        Returns:
            Count-only overlap. Manual AI test, not official Recall@10.

        Raises:
            KeyError: Unknown case.
            ValueError: Holdout cases cannot run.
            QueryAdmissionError: Run missing or not owned.
        """

        _revision, case = self._store.get_case(case_id)
        if case.meta.split == "holdout":
            raise ValueError("holdout_case_cannot_run")
        record = self._query_runs.get(caller, run_id=run_id)
        if record.creator_user_id != UUID(caller.user_id):
            raise QueryAdmissionError("not_found")
        citations = self._query_runs.citations(caller, run_id=run_id)
        overlap = citation_gold_overlap(
            gold_ids=case.meta.chunk_ids,
            citation_chunk_ids=tuple(item.chunk_id for item in citations),
        )
        LOGGER.info(
            "pdf_eval_workspace_compared case_id=%s run_id=%s intersection=%s",
            case_id,
            run_id,
            overlap["intersection"],
        )
        return {
            "case_id": case_id,
            "split": case.meta.split,
            "run_id": run_id,
            "manual_ai_test": True,
            **overlap,
        }
