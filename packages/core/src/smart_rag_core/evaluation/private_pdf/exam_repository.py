"""Hosted exam-run RPC wrappers. FastAPI uses ``app_api`` only."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn, Protocol, cast
from uuid import UUID

import psycopg

from smart_rag_core.security.identity import CallerContext

_EVAL_EXAM_CODE = re.compile(r"eval_exam:[a-z0-9_]+")


class ExamRepositoryError(Exception):
    """Sanitized exam RPC failure. Message is a short code, never question text."""

    def __init__(self, code: str) -> None:
        """Bind a content-free error code.

        Args:
            code: Stable ``eval_exam`` suffix or ``exam_schema_missing``.
        """

        super().__init__(code)
        self.code = code


class ExamMigrationMissingError(ExamRepositoryError):
    """Raised when exam RPCs or tables are not installed."""

    def __init__(self) -> None:
        """Mark the hosted exam schema as absent."""

        super().__init__("exam_schema_missing")


@dataclass(frozen=True, slots=True)
class ClaimedExam:
    """Lease payload returned by ``claim_eval_exam``."""

    exam_run_id: UUID
    conversation_id: UUID
    split: str
    dataset_hash: str
    candidate_fingerprint: str
    case_ids: tuple[UUID, ...]
    case_count: int
    completed_case_count: int


@dataclass(frozen=True, slots=True)
class ExamRunStatus:
    """Poll row without questions or ranked IDs."""

    exam_run_id: UUID
    split: str
    status: str
    dataset_hash: str
    candidate_fingerprint: str
    case_count: int
    completed_case_count: int
    holdout_opened: bool
    conversation_id: UUID


@dataclass(frozen=True, slots=True)
class ExamPersistResult:
    """Idempotent case-result write."""

    exam_run_id: UUID
    case_id: UUID
    inserted: bool
    completed_case_count: int


@dataclass(frozen=True, slots=True)
class ExamFinalizeResult:
    """Terminal exam outcome."""

    exam_run_id: UUID
    status: str
    report_present: bool


@dataclass(frozen=True, slots=True)
class ExamLatestReport:
    """Count-only succeeded report."""

    exam_run_id: UUID
    split: str
    dataset_hash: str
    case_count: int
    hit_count: int
    hybrid_recall_at_10: float
    gates_pass: bool
    holdout_opened: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ExamEnqueueResult:
    """Enqueue or idempotent reconnect payload."""

    exam_run_id: UUID
    status: str
    dataset_hash: str
    conversation_id: UUID
    replayed: bool


@dataclass(frozen=True, slots=True)
class ExamReportCase:
    """Count-only report case row. Misses are ``hit=false``."""

    exam_run_id: UUID
    case_id: UUID
    ordinal: int
    hit: bool
    gold_count: int
    ranked_hit_count: int
    latency_ms: int | None


def exam_request_payload_hash(
    *,
    split: str,
    expected_dataset_hash: str | None,
) -> str:
    """Return the server-derived enqueue payload hash.

    Args:
        split: Requested split. Never holdout.
        expected_dataset_hash: Optional CAS hash.

    Returns:
        SHA-256 hex. Does not include questions or gold UUIDs.
    """

    encoded = json.dumps(
        {"expected_dataset_hash": expected_dataset_hash, "split": split},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ExamQueries(Protocol):
    """RPC surface used by the exam runner. Tests may substitute a fake."""

    def claim(
        self,
        caller: CallerContext,
        *,
        lease_owner: str,
        lease_seconds: int,
    ) -> ClaimedExam | None:
        """Claim one queued or expired-running exam."""
        ...

    def heartbeat(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
        lease_owner: str,
        lease_seconds: int,
    ) -> datetime:
        """Extend a live lease."""
        ...

    def reclaim(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
        lease_owner: str,
        lease_seconds: int,
    ) -> bool:
        """Take over an expired running lease."""
        ...

    def persist_case_result(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
        case_id: UUID,
        hit: bool,
        gold_count: int,
        ranked_hit_count: int,
        latency_ms: int | None,
    ) -> ExamPersistResult:
        """Insert one count-only result. Duplicates do not increment."""
        ...

    def finalize(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
        gates_pass: bool,
        error_code: str | None,
    ) -> ExamFinalizeResult:
        """Write an immutable report or fail without one."""
        ...

    def cancel(self, caller: CallerContext, *, exam_run_id: UUID) -> str:
        """Idempotent cancel of a non-terminal exam."""
        ...

    def get(self, caller: CallerContext, *, exam_run_id: UUID) -> ExamRunStatus | None:
        """Return one run without private fields."""
        ...


def exam_error_code(exc: BaseException) -> str:
    """Extract a content-free exam error code from a database exception.

    Args:
        exc: Database or wrapper exception. The raw message is not returned.

    Returns:
        ``exam_schema_missing`` or an ``eval_exam`` suffix.
    """

    if isinstance(
        exc, (psycopg.errors.UndefinedFunction, psycopg.errors.UndefinedTable)
    ):
        return "exam_schema_missing"
    match = _EVAL_EXAM_CODE.search(str(exc))
    if match is not None:
        return match.group(0).removeprefix("eval_exam:")
    return "request_rejected"


def _raise_exam(exc: BaseException) -> NoReturn:
    """Raise a sanitized exam repository error.

    Args:
        exc: Database exception.

    Raises:
        ExamMigrationMissingError: Missing function or table.
        ExamRepositoryError: Other mapped failures.
    """

    code = exam_error_code(exc)
    if code == "exam_schema_missing":
        raise ExamMigrationMissingError() from exc
    raise ExamRepositoryError(code) from exc


def _cells(row: object) -> tuple[object, ...]:
    """Narrow one driver row to a typed cell tuple.

    Args:
        row: Driver fetch result.

    Returns:
        Cell tuple.

    Raises:
        ExamRepositoryError: When the driver did not return a row sequence.
    """

    if isinstance(row, tuple):
        return tuple(cast(tuple[object, ...], row))
    if isinstance(row, list):
        return tuple(cast(list[object], row))
    raise ExamRepositoryError("request_rejected")


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


def _as_float(value: object) -> float:
    """Coerce a driver numeric cell to float.

    Args:
        value: Cell value.

    Returns:
        Float.
    """

    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


def _as_datetime(value: object) -> datetime:
    """Coerce a timestamptz cell.

    Args:
        value: Cell value.

    Returns:
        Datetime.

    Raises:
        ExamRepositoryError: Non-datetime cell.
    """

    if isinstance(value, datetime):
        return value
    raise ExamRepositoryError("request_rejected")


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


def _uuid_tuple(value: object) -> tuple[UUID, ...]:
    """Return a UUID tuple from a Postgres array.

    Args:
        value: Array or None.

    Returns:
        UUID tuple.
    """

    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(_as_uuid(item) for item in cast(list[object], value))
    if isinstance(value, tuple):
        return tuple(_as_uuid(item) for item in cast(tuple[object, ...], value))
    raise ExamRepositoryError("request_rejected")


@dataclass(frozen=True, slots=True)
class ExamRepository:
    """``app_api`` wrappers for exam claim/heartbeat/result/finalize RPCs.

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

    def claim(
        self,
        caller: CallerContext,
        *,
        lease_owner: str,
        lease_seconds: int,
    ) -> ClaimedExam | None:
        """Claim one queued or expired-running exam.

        Args:
            caller: Server-derived owner/admin.
            lease_owner: Process lease token, at least eight characters.
            lease_seconds: Bounded 5-60 second lease.

        Returns:
            Claimed exam, or None when the queue is empty.

        Raises:
            ExamRepositoryError: Mapped RPC failure.
            ExamMigrationMissingError: Schema absent.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT exam_run_id, conversation_id, split, dataset_hash,
                           candidate_fingerprint, case_ids, case_count,
                           completed_case_count
                    FROM app.claim_eval_exam(%s, %s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        lease_owner,
                        lease_seconds,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_exam(exc)
        if fetched is None:
            return None
        row = _cells(fetched)
        return ClaimedExam(
            exam_run_id=_as_uuid(row[0]),
            conversation_id=_as_uuid(row[1]),
            split=str(row[2]),
            dataset_hash=str(row[3]),
            candidate_fingerprint=str(row[4]),
            case_ids=_uuid_tuple(row[5]),
            case_count=_as_int(row[6]),
            completed_case_count=_as_int(row[7]),
        )

    def heartbeat(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
        lease_owner: str,
        lease_seconds: int,
    ) -> datetime:
        """Extend a live lease.

        Args:
            caller: Server-derived owner/admin.
            exam_run_id: Claimed exam.
            lease_owner: Process lease token.
            lease_seconds: Bounded 5-60 second lease.

        Returns:
            New lease expiry.

        Raises:
            ExamRepositoryError: Mapped RPC failure including ``lease_not_held``.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT app.heartbeat_eval_exam(%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        exam_run_id,
                        lease_owner,
                        lease_seconds,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_exam(exc)
        if fetched is None:
            raise ExamRepositoryError("lease_not_held")
        expiry = _cells(fetched)[0]
        if not isinstance(expiry, datetime):
            raise ExamRepositoryError("request_rejected")
        return expiry

    def reclaim(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
        lease_owner: str,
        lease_seconds: int,
    ) -> bool:
        """Take over an expired running lease.

        Args:
            caller: Server-derived owner/admin.
            exam_run_id: Exam to reclaim.
            lease_owner: Process lease token.
            lease_seconds: Bounded 5-60 second lease.

        Returns:
            True when reclaimed.

        Raises:
            ExamRepositoryError: Live lease or missing exam.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT exam_run_id, reclaimed
                    FROM app.reclaim_eval_exam(%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        exam_run_id,
                        lease_owner,
                        lease_seconds,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_exam(exc)
        if fetched is None:
            raise ExamRepositoryError("not_found")
        return bool(_cells(fetched)[1])

    def persist_case_result(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
        case_id: UUID,
        hit: bool,
        gold_count: int,
        ranked_hit_count: int,
        latency_ms: int | None,
    ) -> ExamPersistResult:
        """Insert one count-only result.

        Args:
            caller: Server-derived owner/admin.
            exam_run_id: Claimed exam.
            case_id: Snapshot case id.
            hit: All required gold IDs in Hybrid top 10.
            gold_count: 1-3 gold locators.
            ranked_hit_count: Gold IDs present in the top 10.
            latency_ms: First-evidence milliseconds, or None.

        Returns:
            Insert flag and completed count.

        Raises:
            ExamRepositoryError: Mapped RPC failure.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT exam_run_id, case_id, inserted, completed_case_count
                    FROM app.persist_eval_exam_case_result(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        exam_run_id,
                        case_id,
                        hit,
                        gold_count,
                        ranked_hit_count,
                        latency_ms,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_exam(exc)
        if fetched is None:
            raise ExamRepositoryError("request_rejected")
        row = _cells(fetched)
        return ExamPersistResult(
            exam_run_id=_as_uuid(row[0]),
            case_id=_as_uuid(row[1]),
            inserted=bool(row[2]),
            completed_case_count=_as_int(row[3]),
        )

    def finalize(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
        gates_pass: bool,
        error_code: str | None,
    ) -> ExamFinalizeResult:
        """Write an immutable report or fail without one.

        Args:
            caller: Server-derived owner/admin.
            exam_run_id: Claimed exam.
            gates_pass: Overlay retrieve gates after scoring.
            error_code: When set, mark failed with no official report.

        Returns:
            Terminal status and report presence.

        Raises:
            ExamRepositoryError: Incomplete success finalize.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT exam_run_id, status, report_present
                    FROM app.finalize_eval_exam(%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        exam_run_id,
                        gates_pass,
                        error_code,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_exam(exc)
        if fetched is None:
            raise ExamRepositoryError("request_rejected")
        row = _cells(fetched)
        return ExamFinalizeResult(
            exam_run_id=_as_uuid(row[0]),
            status=str(row[1]),
            report_present=bool(row[2]),
        )

    def cancel(self, caller: CallerContext, *, exam_run_id: UUID) -> str:
        """Idempotent cancel of a non-terminal exam.

        Args:
            caller: Server-derived owner/admin.
            exam_run_id: Exam to cancel.

        Returns:
            Resulting status.

        Raises:
            ExamRepositoryError: Mapped RPC failure.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT exam_run_id, status
                    FROM app.cancel_eval_exam(%s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        exam_run_id,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_exam(exc)
        if fetched is None:
            raise ExamRepositoryError("not_found")
        return str(_cells(fetched)[1])

    def get(self, caller: CallerContext, *, exam_run_id: UUID) -> ExamRunStatus | None:
        """Return one run without private fields.

        Args:
            caller: Server-derived owner/admin.
            exam_run_id: Exam id.

        Returns:
            Status row, or None when missing.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT exam_run_id, split, status, dataset_hash,
                           candidate_fingerprint, case_count,
                           completed_case_count, holdout_opened, conversation_id
                    FROM app.get_eval_exam_run(%s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        exam_run_id,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_exam(exc)
        if fetched is None:
            return None
        row = _cells(fetched)
        return ExamRunStatus(
            exam_run_id=_as_uuid(row[0]),
            split=str(row[1]),
            status=str(row[2]),
            dataset_hash=str(row[3]),
            candidate_fingerprint=str(row[4]),
            case_count=_as_int(row[5]),
            completed_case_count=_as_int(row[6]),
            holdout_opened=bool(row[7]),
            conversation_id=_as_uuid(row[8]),
        )

    def enqueue(
        self,
        caller: CallerContext,
        *,
        split: str,
        idempotency_key: str,
        candidate_fingerprint: str,
        expected_dataset_hash: str | None = None,
    ) -> ExamEnqueueResult:
        """Queue one exam or reconnect the same idempotency key.

        Args:
            caller: Server-derived owner/admin.
            split: ``development`` or ``qualification``.
            idempotency_key: Client key, 8-128 characters.
            candidate_fingerprint: Server-captured Hybrid identity.
            expected_dataset_hash: Optional CAS hash.

        Returns:
            Enqueue row. ``replayed`` is true on idempotent reconnect.

        Raises:
            ExamRepositoryError: Mapped RPC failure including empty dataset.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT exam_run_id, status, dataset_hash, conversation_id,
                           replayed
                    FROM app.enqueue_eval_exam(%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        split,
                        idempotency_key,
                        exam_request_payload_hash(
                            split=split,
                            expected_dataset_hash=expected_dataset_hash,
                        ),
                        candidate_fingerprint,
                        expected_dataset_hash,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_exam(exc)
        if fetched is None:
            raise ExamRepositoryError("request_rejected")
        row = _cells(fetched)
        return ExamEnqueueResult(
            exam_run_id=_as_uuid(row[0]),
            status=str(row[1]),
            dataset_hash=str(row[2]),
            conversation_id=_as_uuid(row[3]),
            replayed=bool(row[4]),
        )

    def latest_report(
        self,
        caller: CallerContext,
        *,
        split: str,
    ) -> ExamLatestReport | None:
        """Return the latest succeeded report for one split.

        Args:
            caller: Server-derived owner/admin.
            split: ``development`` or ``qualification``.

        Returns:
            Count-only report, or None when none exists.
        """

        fetched: object | None = None
        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT exam_run_id, split, dataset_hash, case_count,
                           hit_count, hybrid_recall_at_10, gates_pass,
                           holdout_opened, created_at
                    FROM app.get_latest_eval_exam_report_for_split(
                      %s, %s, %s, %s
                    )
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        split,
                    ),
                ).fetchone()
        except psycopg.Error as exc:
            _raise_exam(exc)
        if fetched is None:
            return None
        row = _cells(fetched)
        return ExamLatestReport(
            exam_run_id=_as_uuid(row[0]),
            split=str(row[1]),
            dataset_hash=str(row[2]),
            case_count=_as_int(row[3]),
            hit_count=_as_int(row[4]),
            hybrid_recall_at_10=_as_float(row[5]),
            gates_pass=bool(row[6]),
            holdout_opened=bool(row[7]),
            created_at=_as_datetime(row[8]),
        )

    def list_report_cases(
        self,
        caller: CallerContext,
        *,
        exam_run_id: UUID,
    ) -> tuple[ExamReportCase, ...]:
        """Return count-only case rows for a succeeded report.

        Args:
            caller: Server-derived owner/admin.
            exam_run_id: Report exam id.

        Returns:
            Case rows. Empty when the report is missing (HTTP 404).
        """

        try:
            with self._connect() as connection:
                fetched = connection.execute(
                    """
                    SELECT exam_run_id, case_id, ordinal, hit, gold_count,
                           ranked_hit_count, latency_ms
                    FROM app.list_eval_exam_report_cases(%s, %s, %s, %s)
                    """,
                    (
                        caller.rpc_user_id(),
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        exam_run_id,
                    ),
                ).fetchall()
        except psycopg.Error as exc:
            _raise_exam(exc)
        rows: list[ExamReportCase] = []
        for item in fetched:
            row = _cells(item)
            latency = row[6]
            rows.append(
                ExamReportCase(
                    exam_run_id=_as_uuid(row[0]),
                    case_id=_as_uuid(row[1]),
                    ordinal=_as_int(row[2]),
                    hit=bool(row[3]),
                    gold_count=_as_int(row[4]),
                    ranked_hit_count=_as_int(row[5]),
                    latency_ms=None if latency is None else _as_int(latency),
                )
            )
        return tuple(rows)
