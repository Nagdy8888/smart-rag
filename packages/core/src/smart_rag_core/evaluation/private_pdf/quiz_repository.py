"""Hosted quiz-case RPC wrappers. FastAPI uses ``app_api`` only."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import NoReturn, Protocol, cast
from uuid import UUID

import psycopg

from smart_rag_core.security.identity import CallerContext

_EVAL_QUIZ_CODE = re.compile(r"eval_quiz:[a-z0-9_]+")
_ALLOWED_CLASSES = frozenset(
    {
        "factual_definition",
        "exact_acronym",
        "semantic_paraphrase",
        "multi_part",
        "section_scoped",
    }
)


class QuizRepositoryError(Exception):
    """Sanitized quiz RPC failure. Message is a short code, never question text."""

    def __init__(self, code: str) -> None:
        """Bind a content-free error code.

        Args:
            code: Stable ``eval_quiz`` suffix or ``quiz_schema_missing``.
        """

        super().__init__(code)
        self.code = code


class QuizMigrationMissingError(QuizRepositoryError):
    """Raised when quiz RPCs or tables are not installed."""

    def __init__(self) -> None:
        """Mark the hosted quiz schema as absent."""

        super().__init__("quiz_schema_missing")


@dataclass(frozen=True, slots=True)
class QuizCreateResult:
    """Create or idempotent replay outcome."""

    case_id: UUID
    row_version: int
    replayed: bool


@dataclass(frozen=True, slots=True)
class QuizGoldLocator:
    """Server-derived gold locator. Client metadata is not trusted."""

    ordinal: int
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    page_number: int | None
    page_label: str | None
    section_path: tuple[str, ...]
    stale: bool


@dataclass(frozen=True, slots=True)
class QuizCaseSummary:
    """List row without question, answer, facts, or excerpts."""

    case_id: UUID
    split: str
    query_class: str
    review_status: str
    generated_only: bool
    source_family_id: str | None
    gold_chunk_count: int
    gold_stale: bool
    row_version: int


@dataclass(frozen=True, slots=True)
class QuizCaseDetail:
    """Owner/admin detail including private question fields."""

    case_id: UUID
    split: str
    query_class: str
    review_status: str
    generated_only: bool
    source_family_id: str | None
    question: str
    expected_answer: str
    atomic_facts: tuple[str, ...]
    required_terms: tuple[str, ...]
    expected_scope: str
    source_run_id: UUID | None
    document_id: UUID | None
    version_id: UUID | None
    gold: tuple[QuizGoldLocator, ...]
    gold_stale: bool
    reviewer_user_id: UUID | None
    row_version: int


@dataclass(frozen=True, slots=True)
class QuizStatusCounts:
    """Aggregate counts without questions or gold UUID lists."""

    draft_count: int
    approved_count: int
    rejected_count: int
    stale_gold_count: int
    live_count: int
    remaining_capacity: int


class QuizCaseQueries(Protocol):
    """RPC surface used by HTTP. Tests may substitute an in-memory fake."""

    def create(
        self,
        caller: CallerContext,
        *,
        source_run_id: UUID | None,
        question: str | None,
        expected_answer: str,
        atomic_facts: Sequence[str],
        query_class: str,
        required_terms: Sequence[str],
        split: str,
        source_family_id: str | None,
        generated_only: bool,
        chunk_ids: Sequence[UUID],
        idempotency_key: str,
        request_payload_hash: str,
    ) -> QuizCreateResult:
        """Create a draft quiz case."""
        ...

    def list_summaries(
        self,
        caller: CallerContext,
        *,
        split: str | None,
        review_status: str | None,
        limit: int,
        after_id: UUID | None,
    ) -> tuple[QuizCaseSummary, ...]:
        """List summaries without private fields."""
        ...

    def get(self, caller: CallerContext, *, case_id: UUID) -> QuizCaseDetail:
        """Return one case including private fields."""
        ...

    def patch(
        self,
        caller: CallerContext,
        *,
        case_id: UUID,
        row_version: int,
        question: str | None,
        expected_answer: str | None,
        atomic_facts: Sequence[str] | None,
        query_class: str | None,
        required_terms: Sequence[str] | None,
        source_family_id: str | None,
        expected_scope: str | None,
    ) -> tuple[UUID, int]:
        """CAS content edit. Resets approval."""
        ...

    def replace_gold(
        self,
        caller: CallerContext,
        *,
        case_id: UUID,
        row_version: int,
        chunk_ids: Sequence[UUID],
    ) -> tuple[UUID, int, int]:
        """Replace gold locators. Resets approval."""
        ...

    def approve(
        self, caller: CallerContext, *, case_id: UUID, row_version: int
    ) -> tuple[UUID, int]:
        """Named-human approval."""
        ...

    def reject(
        self, caller: CallerContext, *, case_id: UUID, row_version: int
    ) -> tuple[UUID, int]:
        """Named-human reject."""
        ...

    def delete(self, caller: CallerContext, *, case_id: UUID, row_version: int) -> None:
        """Immediate delete."""
        ...

    def status_counts(self, caller: CallerContext) -> QuizStatusCounts:
        """Aggregate live counts."""
        ...


def canonical_payload_hash(payload: Mapping[str, object]) -> str:
    """Return a 64-character hex digest for idempotency.

    Args:
        payload: Canonical field map. Callers must not log it when it
            contains a question.

    Returns:
        SHA-256 hex digest.
    """

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def quiz_error_code(exc: BaseException) -> str:
    """Extract a content-free quiz error code from a database exception.

    Args:
        exc: Database or wrapper exception. The raw message is not returned.

    Returns:
        ``quiz_schema_missing`` or an ``eval_quiz`` suffix.
    """

    if isinstance(
        exc, (psycopg.errors.UndefinedFunction, psycopg.errors.UndefinedTable)
    ):
        return "quiz_schema_missing"
    match = _EVAL_QUIZ_CODE.search(str(exc))
    if match is not None:
        return match.group(0).removeprefix("eval_quiz:")
    return "request_rejected"


def _raise_quiz(exc: BaseException) -> NoReturn:
    """Raise a sanitized quiz repository error.

    Args:
        exc: Database exception.

    Raises:
        QuizMigrationMissingError: Missing function or table.
        QuizRepositoryError: Other mapped failures.
    """

    code = quiz_error_code(exc)
    if code == "quiz_schema_missing":
        raise QuizMigrationMissingError() from exc
    raise QuizRepositoryError(code) from exc


def _cells(row: object) -> tuple[object, ...]:
    """Narrow one driver row to a typed cell tuple.

    Args:
        row: Driver fetch result.

    Returns:
        Cell tuple.

    Raises:
        QuizRepositoryError: When the driver did not return a row sequence.
    """

    if isinstance(row, tuple):
        return cast(tuple[object, ...], row)
    if isinstance(row, list):
        return tuple(cast(list[object], row))
    raise QuizRepositoryError("request_rejected")


def _as_int(value: object) -> int:
    """Coerce a driver cell to int.

    Args:
        value: Cell value.

    Returns:
        Integer.
    """

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return int(str(value))


def _as_uuid(value: object) -> UUID:
    """Coerce a driver cell to UUID.

    Args:
        value: Cell value.

    Returns:
        UUID.
    """

    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _as_uuid_opt(value: object) -> UUID | None:
    """Coerce an optional UUID cell.

    Args:
        value: Cell value.

    Returns:
        UUID or None.
    """

    if value is None:
        return None
    return _as_uuid(value)


def _text_tuple(value: object) -> tuple[str, ...]:
    """Return a string tuple from a Postgres array.

    Args:
        value: Array or None.

    Returns:
        String tuple.
    """

    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(item) for item in cast(list[object], value))
    if isinstance(value, tuple):
        return tuple(str(item) for item in cast(tuple[object, ...], value))
    return ()


def _parse_gold(raw: object) -> tuple[QuizGoldLocator, ...]:
    """Parse gold JSON from ``get_eval_quiz_case``.

    Args:
        raw: JSONB value.

    Returns:
        Locator tuple.
    """

    payload: object = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(payload, list):
        return ()
    locators: list[QuizGoldLocator] = []
    for item in cast(list[object], payload):
        if not isinstance(item, dict):
            continue
        mapped = cast(dict[str, object], item)
        section = mapped.get("section_path")
        path: tuple[str, ...] = ()
        if isinstance(section, list):
            path = tuple(str(part) for part in cast(list[object], section))
        page_number = mapped.get("page_number")
        page_label = mapped.get("page_label")
        ordinal = mapped.get("ordinal")
        chunk_id = mapped.get("chunk_id")
        document_id = mapped.get("document_id")
        version_id = mapped.get("version_id")
        if (
            ordinal is None
            or chunk_id is None
            or document_id is None
            or version_id is None
        ):
            continue
        locators.append(
            QuizGoldLocator(
                ordinal=_as_int(ordinal),
                chunk_id=_as_uuid(chunk_id),
                document_id=_as_uuid(document_id),
                version_id=_as_uuid(version_id),
                page_number=None if page_number is None else _as_int(page_number),
                page_label=str(page_label) if page_label else None,
                section_path=path,
                stale=bool(mapped.get("stale", False)),
            )
        )
    return tuple(locators)


@dataclass(frozen=True, slots=True)
class QuizCaseRepository:
    """One wrapper per reviewed ``app.*eval_quiz*`` RPC.

    Args:
        postgres_url: Transaction-pooled ``app_api`` DSN. Never operator.
    """

    postgres_url: str

    def _connect(self) -> psycopg.Connection:
        """Open an ``app_api`` connection.

        Returns:
            Open connection with ``SET ROLE app_api``.
        """

        connection = psycopg.connect(self.postgres_url)
        connection.execute("SET ROLE app_api")
        return connection

    def create(
        self,
        caller: CallerContext,
        *,
        source_run_id: UUID | None,
        question: str | None,
        expected_answer: str,
        atomic_facts: Sequence[str],
        query_class: str,
        required_terms: Sequence[str],
        split: str,
        source_family_id: str | None,
        generated_only: bool,
        chunk_ids: Sequence[UUID],
        idempotency_key: str,
        request_payload_hash: str,
    ) -> QuizCreateResult:
        """Create a draft quiz case.

        Args:
            caller: Server-derived owner/admin.
            source_run_id: Caller-owned completed run, or None for generated drafts.
            question: Server-generated question when no run is supplied.
            expected_answer: Expected answer text.
            atomic_facts: Bounded facts.
            query_class: Positive quiz class.
            required_terms: Bounded terms.
            split: ``development`` or ``qualification``.
            source_family_id: Optional family token.
            generated_only: True for regenerate drafts.
            chunk_ids: Zero to three current chunk IDs.
            idempotency_key: 8-128 character key.
            request_payload_hash: SHA-256 hex of the canonical payload.

        Returns:
            Case id and row version.

        Raises:
            QuizRepositoryError: Mapped RPC failure.
            QuizMigrationMissingError: Schema absent.
        """

        if query_class not in _ALLOWED_CLASSES:
            raise QuizRepositoryError("class_invalid")
        if split.lower() == "holdout":
            raise QuizRepositoryError("holdout_rejected")
        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT case_id, row_version, replayed
                    FROM app.create_eval_quiz_case(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        source_run_id,
                        question,
                        expected_answer,
                        list(atomic_facts),
                        query_class,
                        list(required_terms),
                        split,
                        source_family_id,
                        generated_only,
                        list(chunk_ids),
                        idempotency_key,
                        request_payload_hash,
                    ),
                ).fetchone()
                connection.commit()
        except psycopg.Error as exc:
            _raise_quiz(exc)
        if fetched is None:
            raise QuizRepositoryError("request_rejected")
        row = _cells(fetched)
        return QuizCreateResult(
            case_id=_as_uuid(row[0]),
            row_version=_as_int(row[1]),
            replayed=bool(row[2]),
        )

    def list_summaries(
        self,
        caller: CallerContext,
        *,
        split: str | None,
        review_status: str | None,
        limit: int,
        after_id: UUID | None,
    ) -> tuple[QuizCaseSummary, ...]:
        """List summaries without private fields.

        Args:
            caller: Server-derived owner/admin.
            split: Optional split filter.
            review_status: Optional review filter.
            limit: Page size 1-20.
            after_id: Keyset cursor.

        Returns:
            Summary page.

        Raises:
            QuizRepositoryError: Mapped RPC failure.
        """

        if split is not None and split.lower() == "holdout":
            raise QuizRepositoryError("holdout_rejected")
        fetched: object = ()
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT
                      case_id, split, query_class, review_status, generated_only,
                      source_family_id, gold_chunk_count, gold_stale, row_version
                    FROM app.list_eval_quiz_case_summaries(
                      %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        split,
                        review_status,
                        limit,
                        after_id,
                    ),
                ).fetchall()
        except psycopg.Error as exc:
            _raise_quiz(exc)
        summaries: list[QuizCaseSummary] = []
        for item in cast(list[object], fetched):
            row = _cells(item)
            family = row[5]
            summaries.append(
                QuizCaseSummary(
                    case_id=_as_uuid(row[0]),
                    split=str(row[1]),
                    query_class=str(row[2]),
                    review_status=str(row[3]),
                    generated_only=bool(row[4]),
                    source_family_id=str(family) if family is not None else None,
                    gold_chunk_count=_as_int(row[6]),
                    gold_stale=bool(row[7]),
                    row_version=_as_int(row[8]),
                )
            )
        return tuple(summaries)

    def get(self, caller: CallerContext, *, case_id: UUID) -> QuizCaseDetail:
        """Return one case including private fields.

        Args:
            caller: Server-derived owner/admin.
            case_id: Quiz case id.

        Returns:
            Detail record.

        Raises:
            QuizRepositoryError: ``not_found`` or other mapped failures.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT
                      case_id, split, query_class, review_status, generated_only,
                      source_family_id, question, expected_answer, atomic_facts,
                      required_terms, expected_scope, source_run_id, document_id,
                      version_id, gold, gold_stale, reviewer_user_id, row_version
                    FROM app.get_eval_quiz_case(%s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        case_id,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_quiz(exc)
        if fetched is None:
            raise QuizRepositoryError("not_found")
        row = _cells(fetched)
        family = row[5]
        return QuizCaseDetail(
            case_id=_as_uuid(row[0]),
            split=str(row[1]),
            query_class=str(row[2]),
            review_status=str(row[3]),
            generated_only=bool(row[4]),
            source_family_id=str(family) if family is not None else None,
            question=str(row[6]),
            expected_answer=str(row[7]),
            atomic_facts=_text_tuple(row[8]),
            required_terms=_text_tuple(row[9]),
            expected_scope=str(row[10]),
            source_run_id=_as_uuid_opt(row[11]),
            document_id=_as_uuid_opt(row[12]),
            version_id=_as_uuid_opt(row[13]),
            gold=_parse_gold(row[14]),
            gold_stale=bool(row[15]),
            reviewer_user_id=_as_uuid_opt(row[16]),
            row_version=_as_int(row[17]),
        )

    def patch(
        self,
        caller: CallerContext,
        *,
        case_id: UUID,
        row_version: int,
        question: str | None,
        expected_answer: str | None,
        atomic_facts: Sequence[str] | None,
        query_class: str | None,
        required_terms: Sequence[str] | None,
        source_family_id: str | None,
        expected_scope: str | None,
    ) -> tuple[UUID, int]:
        """CAS content edit. Resets approval.

        Args:
            caller: Server-derived owner/admin.
            case_id: Quiz case id.
            row_version: Caller-held version.
            question: Optional question replacement.
            expected_answer: Optional answer replacement.
            atomic_facts: Optional facts replacement.
            query_class: Optional class replacement.
            required_terms: Optional terms replacement.
            source_family_id: Optional family replacement.
            expected_scope: Optional scope replacement.

        Returns:
            Case id and new row version.
        """

        if query_class is not None and query_class not in _ALLOWED_CLASSES:
            raise QuizRepositoryError("class_invalid")
        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT case_id, row_version
                    FROM app.patch_eval_quiz_case(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        case_id,
                        row_version,
                        question,
                        expected_answer,
                        None if atomic_facts is None else list(atomic_facts),
                        query_class,
                        None if required_terms is None else list(required_terms),
                        source_family_id,
                        expected_scope,
                    ),
                ).fetchone()
                connection.commit()
        except psycopg.Error as exc:
            _raise_quiz(exc)
        if fetched is None:
            raise QuizRepositoryError("not_found")
        row = _cells(fetched)
        return _as_uuid(row[0]), _as_int(row[1])

    def replace_gold(
        self,
        caller: CallerContext,
        *,
        case_id: UUID,
        row_version: int,
        chunk_ids: Sequence[UUID],
    ) -> tuple[UUID, int, int]:
        """Replace gold locators from current authorized chunk IDs.

        Args:
            caller: Server-derived owner/admin.
            case_id: Quiz case id.
            row_version: Caller-held version.
            chunk_ids: Zero to three chunk IDs.

        Returns:
            Case id, new row version, gold count.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT case_id, row_version, gold_chunk_count
                    FROM app.replace_eval_quiz_gold(%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        case_id,
                        row_version,
                        list(chunk_ids),
                    ),
                ).fetchone()
                connection.commit()
        except psycopg.Error as exc:
            _raise_quiz(exc)
        if fetched is None:
            raise QuizRepositoryError("not_found")
        row = _cells(fetched)
        return _as_uuid(row[0]), _as_int(row[1]), _as_int(row[2])

    def approve(
        self, caller: CallerContext, *, case_id: UUID, row_version: int
    ) -> tuple[UUID, int]:
        """Named-human approval.

        Args:
            caller: Server-derived owner/admin.
            case_id: Quiz case id.
            row_version: Caller-held version.

        Returns:
            Case id and new row version.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT case_id, row_version
                    FROM app.approve_eval_quiz_case(%s, %s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        case_id,
                        row_version,
                    ),
                ).fetchone()
                connection.commit()
        except psycopg.Error as exc:
            _raise_quiz(exc)
        if fetched is None:
            raise QuizRepositoryError("not_found")
        row = _cells(fetched)
        return _as_uuid(row[0]), _as_int(row[1])

    def reject(
        self, caller: CallerContext, *, case_id: UUID, row_version: int
    ) -> tuple[UUID, int]:
        """Named-human reject.

        Args:
            caller: Server-derived owner/admin.
            case_id: Quiz case id.
            row_version: Caller-held version.

        Returns:
            Case id and new row version.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT case_id, row_version
                    FROM app.reject_eval_quiz_case(%s, %s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        case_id,
                        row_version,
                    ),
                ).fetchone()
                connection.commit()
        except psycopg.Error as exc:
            _raise_quiz(exc)
        if fetched is None:
            raise QuizRepositoryError("not_found")
        row = _cells(fetched)
        return _as_uuid(row[0]), _as_int(row[1])

    def delete(self, caller: CallerContext, *, case_id: UUID, row_version: int) -> None:
        """Immediate delete.

        Args:
            caller: Server-derived owner/admin.
            case_id: Quiz case id.
            row_version: Caller-held version.
        """

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    SELECT deleted
                    FROM app.delete_eval_quiz_case(%s, %s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        case_id,
                        row_version,
                    ),
                )
                connection.commit()
        except psycopg.Error as exc:
            _raise_quiz(exc)

    def status_counts(self, caller: CallerContext) -> QuizStatusCounts:
        """Aggregate live counts.

        Args:
            caller: Server-derived owner/admin.

        Returns:
            Count-only status.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT
                      draft_count, approved_count, rejected_count,
                      stale_gold_count, live_count, remaining_capacity
                    FROM app.count_eval_quiz_case_status(%s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_quiz(exc)
        if fetched is None:
            raise QuizRepositoryError("request_rejected")
        row = _cells(fetched)
        return QuizStatusCounts(
            draft_count=_as_int(row[0] or 0),
            approved_count=_as_int(row[1] or 0),
            rejected_count=_as_int(row[2] or 0),
            stale_gold_count=_as_int(row[3] or 0),
            live_count=_as_int(row[4] or 0),
            remaining_capacity=_as_int(row[5] or 0),
        )
