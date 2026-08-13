"""Resumable Storage promotion saga with crash-safe reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import psycopg

from smart_rag_core.gateways.storage import StorageGateway, StorageGatewayError


class PromotionStep(StrEnum):
    """Ordered promotion saga steps persisted in Postgres."""

    INTENT = "intent"
    COPY_DONE = "copy_done"
    VERIFY_DONE = "verify_done"
    DB_SWITCHED = "db_switched"
    SOURCE_DELETED = "source_deleted"
    COMPLETED = "completed"


class PromotionSagaError(Exception):
    """Raised when promotion cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class PromotionContext:
    """Inputs for one version promotion."""

    saga_idempotency_key: str
    version_id: UUID
    reservation_id: UUID | None
    quarantine_bucket: str
    quarantine_path: str
    destination_bucket: str
    destination_path: str
    expected_hash: str
    expected_bytes: int
    media_type: str | None = None
    crash_after: PromotionStep | None = None


@dataclass(frozen=True, slots=True)
class PromotionSagaResult:
    """Outcome of one promotion saga execution."""

    saga_id: UUID
    final_step: PromotionStep
    destination_bucket: str
    destination_path: str


class PromotionSaga:
    """Execute or resume the Storage copy/verify/DB-switch/delete saga."""

    def __init__(self, connection: psycopg.Connection, storage: StorageGateway) -> None:
        """Bind one worker-role connection and Storage gateway."""

        self._connection = connection
        self._storage = storage

    def run(self, context: PromotionContext) -> PromotionSagaResult:
        """Run the promotion saga idempotently.

        Args:
            context: Promotion identifiers, paths, and optional crash injection
                point for contract tests.

        Returns:
            Final saga step and authoritative destination reference.

        Raises:
            PromotionSagaError: When a step fails and cannot be safely resumed.
        """

        saga_id = self._ensure_intent(context)
        current = self._read_step(saga_id)
        if current in {PromotionStep.INTENT, PromotionStep.COPY_DONE}:
            if current is PromotionStep.INTENT:
                self._maybe_crash(context, PromotionStep.INTENT)
                try:
                    self._storage.copy_object(
                        source_bucket=context.quarantine_bucket,
                        source_path=context.quarantine_path,
                        destination_bucket=context.destination_bucket,
                        destination_path=context.destination_path,
                    )
                except StorageGatewayError as exc:
                    raise PromotionSagaError(str(exc)) from exc
                if not self._advance(
                    saga_id, PromotionStep.INTENT, PromotionStep.COPY_DONE
                ):
                    current = self._read_step(saga_id)
                else:
                    current = PromotionStep.COPY_DONE
            if current is PromotionStep.COPY_DONE:
                self._maybe_crash(context, PromotionStep.COPY_DONE)
                try:
                    self._storage.verify_object(
                        bucket=context.destination_bucket,
                        object_path=context.destination_path,
                        expected_hash=context.expected_hash,
                        expected_bytes=context.expected_bytes,
                    )
                except StorageGatewayError as exc:
                    raise PromotionSagaError(str(exc)) from exc
                if not self._advance(
                    saga_id, PromotionStep.COPY_DONE, PromotionStep.VERIFY_DONE
                ):
                    current = self._read_step(saga_id)
                else:
                    current = PromotionStep.VERIFY_DONE

        if current in {PromotionStep.VERIFY_DONE, PromotionStep.DB_SWITCHED}:
            if current is PromotionStep.VERIFY_DONE:
                self._maybe_crash(context, PromotionStep.VERIFY_DONE)
                switched = self._complete_db_switch(context, saga_id)
                if not switched:
                    current = self._read_step(saga_id)
                else:
                    current = PromotionStep.DB_SWITCHED

        if current in {PromotionStep.DB_SWITCHED, PromotionStep.SOURCE_DELETED}:
            if current is PromotionStep.DB_SWITCHED:
                self._maybe_crash(context, PromotionStep.DB_SWITCHED)
                try:
                    self._storage.delete_object(
                        bucket=context.quarantine_bucket,
                        object_path=context.quarantine_path,
                    )
                except StorageGatewayError as exc:
                    raise PromotionSagaError(str(exc)) from exc
                if not self._advance(
                    saga_id,
                    PromotionStep.DB_SWITCHED,
                    PromotionStep.SOURCE_DELETED,
                ):
                    current = self._read_step(saga_id)
                else:
                    current = PromotionStep.SOURCE_DELETED

        if current is PromotionStep.SOURCE_DELETED:
            self._advance(
                saga_id, PromotionStep.SOURCE_DELETED, PromotionStep.COMPLETED
            )

        return PromotionSagaResult(
            saga_id=saga_id,
            final_step=self._read_step(saga_id),
            destination_bucket=context.destination_bucket,
            destination_path=context.destination_path,
        )

    def _ensure_intent(self, context: PromotionContext) -> UUID:
        """Insert or return existing saga intent row."""

        row = self._connection.execute(
            """
            SELECT app.upsert_promotion_saga_intent(
              %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                context.version_id,
                context.saga_idempotency_key,
                context.quarantine_bucket,
                context.quarantine_path,
                context.destination_bucket,
                context.destination_path,
                context.expected_hash,
                context.expected_bytes,
                context.reservation_id,
            ),
        ).fetchone()
        if row is None:
            raise PromotionSagaError("upsert_promotion_saga_intent returned no row")
        return UUID(str(row[0]))

    def _read_step(self, saga_id: UUID) -> PromotionStep:
        """Read current saga step."""

        row = self._connection.execute(
            "SELECT current_step FROM app.storage_promotion_sagas WHERE id = %s",
            (saga_id,),
        ).fetchone()
        if row is None:
            raise PromotionSagaError(f"saga {saga_id} missing")
        return PromotionStep(str(row[0]))

    def _advance(
        self, saga_id: UUID, expected: PromotionStep, new: PromotionStep
    ) -> bool:
        """Advance saga step when expected."""

        row = self._connection.execute(
            "SELECT app.advance_promotion_saga_step(%s, %s, %s)",
            (saga_id, expected.value, new.value),
        ).fetchone()
        return bool(row and row[0])

    def _complete_db_switch(self, context: PromotionContext, saga_id: UUID) -> bool:
        """Switch authoritative version reference to destination."""

        row = self._connection.execute(
            """
            SELECT app.complete_promotion_db_switch(
              %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                saga_id,
                context.version_id,
                context.destination_bucket,
                context.destination_path,
                context.expected_hash,
                context.expected_bytes,
                context.media_type,
            ),
        ).fetchone()
        return bool(row and row[0])

    @staticmethod
    def _maybe_crash(context: PromotionContext, step: PromotionStep) -> None:
        """Inject deterministic crash points for contract tests."""

        if context.crash_after is step:
            raise PromotionSagaError(f"injected crash after {step.value}")
