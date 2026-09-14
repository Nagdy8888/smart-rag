"""DB-backed PDF evaluation workspace HTTP service. Uses app_api only."""

from __future__ import annotations

import logging
from typing import cast
from uuid import UUID

import psycopg
from smart_rag_core.evaluation.private_pdf.draft import (
    ChunkLocator,
    build_draft_rows,
    question_hash,
)
from smart_rag_core.evaluation.private_pdf.metrics import citation_gold_overlap
from smart_rag_core.evaluation.private_pdf.quiz_repository import (
    QuizCaseDetail,
    QuizCaseQueries,
    QuizCaseRepository,
    QuizCaseSummary,
    QuizCreateResult,
    QuizMigrationMissingError,
    QuizRepositoryError,
    canonical_payload_hash,
)
from smart_rag_core.evaluation.private_pdf.schema import PrivatePdfQueryClass
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.retrieval.context_loader import (
    ChunkContext,
    list_authorized_eval_passages,
)
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.security.untrusted import isolate_untrusted_text

from smart_rag_api.services.query_runs import QueryRunService

LOGGER = logging.getLogger(__name__)

_ALLOWED_CLASSES = frozenset(
    {
        PrivatePdfQueryClass.FACTUAL_DEFINITION.value,
        PrivatePdfQueryClass.EXACT_ACRONYM.value,
        PrivatePdfQueryClass.SEMANTIC_PARAPHRASE.value,
        PrivatePdfQueryClass.MULTI_PART.value,
        PrivatePdfQueryClass.SECTION_SCOPED.value,
    }
)


def _object_seq(value: object) -> tuple[object, ...]:
    """Return a sequence of objects from a draft-row cell.

    Args:
        value: Draft cell, typically a list of IDs or strings.

    Returns:
        Object tuple.
    """

    if isinstance(value, list):
        return tuple(cast(list[object], value))
    if isinstance(value, tuple):
        return tuple(cast(tuple[object, ...], value))
    return ()


def build_quiz_repository(postgres_url: str) -> QuizCaseRepository:
    """Construct the hosted quiz RPC repository.

    Args:
        postgres_url: ``app_api`` DSN.

    Returns:
        Repository wrapper.
    """

    return QuizCaseRepository(postgres_url)


class PdfEvalWorkspaceService:
    """Owner/admin evaluation workspace operations against hosted RPCs.

    Args:
        repository: Quiz RPC wrappers or a test fake.
        postgres_url: ``app_api`` DSN. Never an operator DSN.
        query_runs: Caller-owned run fetch/citation service.
    """

    def __init__(
        self,
        *,
        repository: QuizCaseQueries,
        postgres_url: str,
        query_runs: QueryRunService,
    ) -> None:
        """Bind repository, app_api DSN, and run service.

        Args:
            repository: Quiz queries.
            postgres_url: Transaction-pooled ``app_api`` URL.
            query_runs: Owned-run citation loader.
        """

        self._repository = repository
        self._postgres_url = postgres_url
        self._query_runs = query_runs

    def status(self, caller: CallerContext) -> dict[str, object]:
        """Return aggregate counts. Missing schema is a 503, not empty.

        Args:
            caller: Authenticated owner/admin.

        Returns:
            Status without questions or filesystem paths.
        """

        counts = self._repository.status_counts(caller)
        return {
            "enabled": True,
            "schema_ready": True,
            "holdout_opened": False,
            "draft_count": counts.draft_count,
            "approved_count": counts.approved_count,
            "rejected_count": counts.rejected_count,
            "stale_gold_count": counts.stale_gold_count,
            "live_count": counts.live_count,
            "remaining_capacity": counts.remaining_capacity,
        }

    def list_cases(
        self,
        caller: CallerContext,
        *,
        split: str | None,
        review_status: str | None,
        after_case_id: UUID | None,
        limit: int,
    ) -> tuple[QuizCaseSummary, ...]:
        """Return a page of summaries. Holdout split queries are rejected.

        Args:
            caller: Authenticated owner/admin.
            split: Optional split filter. ``holdout`` is rejected.
            review_status: Optional ``draft``, ``approved``, or ``rejected``.
            after_case_id: Keyset cursor.
            limit: Page size.

        Returns:
            Summary page.
        """

        return self._repository.list_summaries(
            caller,
            split=split,
            review_status=review_status,
            limit=limit,
            after_id=after_case_id,
        )

    def get_case(self, caller: CallerContext, case_id: UUID) -> QuizCaseDetail:
        """Return one labeled case.

        Args:
            caller: Authenticated owner/admin.
            case_id: Case identifier.

        Returns:
            Detail with HTML-escaped private fields for JSON.
        """

        detail = self._repository.get(caller, case_id=case_id)
        return QuizCaseDetail(
            case_id=detail.case_id,
            split=detail.split,
            query_class=detail.query_class,
            review_status=detail.review_status,
            generated_only=detail.generated_only,
            source_family_id=detail.source_family_id,
            question=isolate_untrusted_text(detail.question),
            expected_answer=isolate_untrusted_text(detail.expected_answer),
            atomic_facts=tuple(
                isolate_untrusted_text(item) for item in detail.atomic_facts
            ),
            required_terms=tuple(
                isolate_untrusted_text(item) for item in detail.required_terms
            ),
            expected_scope=detail.expected_scope,
            source_run_id=detail.source_run_id,
            document_id=detail.document_id,
            version_id=detail.version_id,
            gold=detail.gold,
            gold_stale=detail.gold_stale,
            reviewer_user_id=detail.reviewer_user_id,
            row_version=detail.row_version,
        )

    def create_case(
        self,
        caller: CallerContext,
        *,
        source_run_id: UUID,
        expected_answer: str,
        atomic_facts: tuple[str, ...],
        query_class: str,
        required_terms: tuple[str, ...],
        split: str,
        source_family_id: str | None,
        chunk_ids: tuple[UUID, ...],
        idempotency_key: str,
    ) -> QuizCreateResult:
        """Create a draft from a caller-owned completed run.

        Args:
            caller: Authenticated owner/admin.
            source_run_id: Completed owned run. Browser question text is ignored.
            expected_answer: Expected answer.
            atomic_facts: Bounded facts.
            query_class: Positive class.
            required_terms: Bounded terms.
            split: ``development`` or ``qualification``.
            source_family_id: Optional family.
            chunk_ids: Zero to three gold chunk IDs.
            idempotency_key: Client idempotency key.

        Returns:
            Create result.
        """

        payload = {
            "source_run_id": str(source_run_id),
            "expected_answer": expected_answer,
            "atomic_facts": list(atomic_facts),
            "query_class": query_class,
            "required_terms": list(required_terms),
            "split": split,
            "source_family_id": source_family_id,
            "chunk_ids": [str(item) for item in chunk_ids],
        }
        result = self._repository.create(
            caller,
            source_run_id=source_run_id,
            question=None,
            expected_answer=expected_answer,
            atomic_facts=atomic_facts,
            query_class=query_class,
            required_terms=required_terms,
            split=split,
            source_family_id=source_family_id,
            generated_only=False,
            chunk_ids=chunk_ids,
            idempotency_key=idempotency_key,
            request_payload_hash=canonical_payload_hash(payload),
        )
        LOGGER.info(
            "pdf_eval_case_created replayed=%s gold_count=%s",
            result.replayed,
            len(chunk_ids),
        )
        return result

    def patch_case(
        self,
        caller: CallerContext,
        case_id: UUID,
        *,
        expected_row_version: int,
        question: str | None,
        expected_answer: str | None,
        atomic_facts: tuple[str, ...] | None,
        query_class: str | None,
        required_terms: tuple[str, ...] | None,
        source_family_id: str | None,
        expected_scope: str | None,
    ) -> tuple[UUID, int]:
        """Apply an edit and reset approval.

        Args:
            caller: Authenticated owner/admin.
            case_id: Case identifier.
            expected_row_version: Caller-held version.
            question: Optional question.
            expected_answer: Optional answer.
            atomic_facts: Optional facts.
            query_class: Optional class.
            required_terms: Optional terms.
            source_family_id: Optional family.
            expected_scope: Optional scope.

        Returns:
            Case id and new row version.
        """

        return self._repository.patch(
            caller,
            case_id=case_id,
            row_version=expected_row_version,
            question=question,
            expected_answer=expected_answer,
            atomic_facts=atomic_facts,
            query_class=query_class,
            required_terms=required_terms,
            source_family_id=source_family_id,
            expected_scope=expected_scope,
        )

    def replace_gold(
        self,
        caller: CallerContext,
        case_id: UUID,
        *,
        expected_row_version: int,
        chunk_ids: tuple[UUID, ...],
    ) -> tuple[UUID, int, int]:
        """Replace gold locators.

        Args:
            caller: Authenticated owner/admin.
            case_id: Case identifier.
            expected_row_version: Caller-held version.
            chunk_ids: Zero to three chunk IDs.

        Returns:
            Case id, new version, gold count.
        """

        return self._repository.replace_gold(
            caller,
            case_id=case_id,
            row_version=expected_row_version,
            chunk_ids=chunk_ids,
        )

    def approve(
        self, caller: CallerContext, case_id: UUID, *, expected_row_version: int
    ) -> tuple[UUID, int]:
        """Approve a case. Reviewer is the server-derived caller.

        Args:
            caller: Authenticated owner/admin.
            case_id: Case identifier.
            expected_row_version: Caller-held version.

        Returns:
            Case id and new row version.
        """

        return self._repository.approve(
            caller, case_id=case_id, row_version=expected_row_version
        )

    def reject(
        self, caller: CallerContext, case_id: UUID, *, expected_row_version: int
    ) -> tuple[UUID, int]:
        """Reject a case after named-human inspection.

        Args:
            caller: Authenticated owner/admin.
            case_id: Case identifier.
            expected_row_version: Caller-held version.

        Returns:
            Case id and new row version.
        """

        return self._repository.reject(
            caller, case_id=case_id, row_version=expected_row_version
        )

    def delete(
        self, caller: CallerContext, case_id: UUID, *, expected_row_version: int
    ) -> None:
        """Delete a case immediately.

        Args:
            caller: Authenticated owner/admin.
            case_id: Case identifier.
            expected_row_version: Caller-held version.
        """

        self._repository.delete(
            caller, case_id=case_id, row_version=expected_row_version
        )

    def current_version_id(self, caller: CallerContext, *, document_id: UUID) -> UUID:
        """Return the current version of a caller-readable document.

        Args:
            caller: Authenticated owner/admin.
            document_id: Document id.

        Returns:
            Current version id.

        Raises:
            QueryAdmissionError: Missing or unauthorized document.
            QuizMigrationMissingError: Document RPC missing.
        """

        fetched: object | None = None
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                fetched = connection.execute(
                    """
                    SELECT current_version_id
                    FROM app.get_visible_document(
                      %s::uuid, %s::text, %s::bigint, %s::uuid
                    )
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        document_id,
                    ),
                ).fetchone()
        except psycopg.errors.UndefinedFunction as exc:
            raise QuizMigrationMissingError() from exc
        except psycopg.Error as exc:
            raise QueryAdmissionError("not_found") from exc
        if not isinstance(fetched, (list, tuple)) or fetched[0] is None:
            raise QueryAdmissionError("not_found")
        return UUID(str(fetched[0]))

    def list_passages(
        self,
        caller: CallerContext,
        *,
        document_id: UUID,
        limit: int,
        after_chunk_id: UUID | None,
        page_number: int | None = None,
    ) -> tuple[ChunkContext, ...]:
        """List ACL/current representative passages for one selected document.

        Args:
            caller: Authenticated owner/admin.
            document_id: Caller-readable document.
            limit: Page size.
            after_chunk_id: Keyset cursor.
            page_number: Optional exact page filter on the returned page.

        Returns:
            Authorized passages.

        Raises:
            QueryAdmissionError: Document missing or unauthorized.
        """

        version_id = self.current_version_id(caller, document_id=document_id)
        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            items = list_authorized_eval_passages(
                connection,
                caller,
                version_id=version_id,
                limit=limit,
                after_chunk_id=after_chunk_id,
            )
        if page_number is None:
            return items
        return tuple(item for item in items if item.page_number == page_number)

    def regenerate_drafts(self, caller: CallerContext, *, document_id: UUID) -> int:
        """Insert generated-only drafts for one document up to remaining capacity.

        Args:
            caller: Authenticated owner/admin.
            document_id: Caller-readable document.

        Returns:
            Number of inserted drafts. Never self-approves.

        Raises:
            ValueError: Too few locators.
            QuizRepositoryError: Capacity or RPC failure.
        """

        counts = self._repository.status_counts(caller)
        remaining = counts.remaining_capacity
        if remaining <= 0:
            raise QuizRepositoryError("capacity_exceeded")
        locators: list[ChunkLocator] = []
        after: UUID | None = None
        while len(locators) < 60:
            page = self.list_passages(
                caller, document_id=document_id, limit=60, after_chunk_id=after
            )
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
            document_hash=document_id.hex,
            aliases=(),
            acl_actor_id=caller.user_id,
        )
        existing_families: set[str] = set()
        after_existing: UUID | None = None
        while True:
            page_summaries = self._repository.list_summaries(
                caller,
                split=None,
                review_status=None,
                limit=20,
                after_id=after_existing,
            )
            for item in page_summaries:
                if item.source_family_id:
                    existing_families.add(item.source_family_id)
            if len(page_summaries) < 20:
                break
            after_existing = page_summaries[-1].case_id
        inserted = 0
        for index, row in enumerate(rows):
            if inserted >= remaining:
                break
            query_class = str(row["query_class"])
            if query_class not in _ALLOWED_CLASSES:
                continue
            split = str(row["split"])
            if split == "holdout":
                continue
            family = str(row["source_family_id"])
            if family in existing_families:
                continue
            question = str(row["question"])
            chunk_ids = tuple(UUID(str(item)) for item in _object_seq(row["chunk_ids"]))
            digest = question_hash(question)
            try:
                self._repository.create(
                    caller,
                    source_run_id=None,
                    question=question,
                    expected_answer=str(row["expected_answer"]),
                    atomic_facts=tuple(
                        str(item) for item in _object_seq(row["atomic_facts"])
                    ),
                    query_class=query_class,
                    required_terms=tuple(
                        str(item) for item in _object_seq(row["required_terms"])
                    ),
                    split=split,
                    source_family_id=family,
                    generated_only=True,
                    chunk_ids=chunk_ids,
                    idempotency_key=f"regen-{document_id.hex[:12]}-{index:02d}",
                    request_payload_hash=canonical_payload_hash(
                        {
                            "document_id": str(document_id),
                            "digest": digest,
                            "split": split,
                            "query_class": query_class,
                        }
                    ),
                )
            except QuizRepositoryError as exc:
                if exc.code == "capacity_exceeded":
                    break
                if exc.code in {"idempotency_collision", "family_split_conflict"}:
                    continue
                raise
            existing_families.add(family)
            inserted += 1
        LOGGER.info("pdf_eval_workspace_regenerated case_count=%s", inserted)
        return inserted

    def latest_report(self) -> dict[str, object]:
        """Return an empty count-only report until exam packets persist one.

        HTTP never reads ``.private-eval/``.

        Returns:
            ``present=false`` and ``holdout_opened=false``.
        """

        return {"present": False, "holdout_opened": False}

    def compare_run(
        self,
        caller: CallerContext,
        *,
        case_id: UUID,
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
            QuizRepositoryError: Unknown case.
            QueryAdmissionError: Run missing or not owned.
        """

        case = self._repository.get(caller, case_id=case_id)
        if case.split == "holdout":
            raise QuizRepositoryError("holdout_rejected")
        record = self._query_runs.get(caller, run_id=run_id)
        if record.creator_user_id != UUID(caller.user_id):
            raise QueryAdmissionError("not_found")
        if record.status not in {"completed", "succeeded"}:
            raise QueryAdmissionError("not_found")
        citations = self._query_runs.citations(caller, run_id=run_id)
        gold_ids = tuple(item.chunk_id for item in case.gold)
        overlap = citation_gold_overlap(
            gold_ids=gold_ids,
            citation_chunk_ids=tuple(item.chunk_id for item in citations),
        )
        LOGGER.info(
            "pdf_eval_workspace_compared run_id=%s intersection=%s",
            run_id,
            overlap["intersection"],
        )
        return {
            "case_id": str(case_id),
            "split": case.split,
            "run_id": run_id,
            "manual_ai_test": True,
            **overlap,
        }
