"""Local audit-chain export and HMAC signing adapters.

Phase 10 owns KMS keys, 15-minute chain-head anchors, and S3 Object Lock.
This module only verifies a local snapshot, signs with a process HMAC, and
fails closed on mutation, gap, fork, or signing failure. Full passage text
is forbidden in export payloads.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TypeAlias, cast
from uuid import UUID

from smart_rag_core.security.audit_chain import (
    AUDIT_CHAIN_GENESIS_HASH,
    canonical_audit_material,
    redact_audit_payload,
    sha256_hex,
)

_JsonScalar: TypeAlias = str | int | float | bool | None
_JsonValue: TypeAlias = _JsonScalar | list["_JsonValue"] | dict[str, "_JsonValue"]

_FORBIDDEN_PAYLOAD_FRAGMENTS = (
    "passage",
    "snippet",
    "source_text",
    "ocr_text",
    "full_text",
)


class AuditExportFault(StrEnum):
    """Faults that block audit readiness."""

    MUTATED_ROW = "mutated_row"
    GAP = "gap"
    FORK = "fork"
    SIGNING_FAILURE = "signing_failure"
    PASSAGE_TEXT = "passage_text_forbidden"


@dataclass(frozen=True, slots=True)
class AuditExportRow:
    """One chain row used by the local exporter.

    Attributes:
        chain_seq: Monotonic insert order.
        event_id: Audit event UUID.
        event_hash: Stored SHA-256 hex.
        previous_hash: Prior event hash or genesis.
        event_type: Event type string.
        actor_user_id: Actor when present.
        actor_role: Role label when present.
        target_type: Target class when present.
        target_id: Target id when present.
        authorization_version: Snapshot when recorded.
        visibility_generation: Visibility generation when recorded.
        session_id: Session identifier when recorded.
        purpose: Purpose label when recorded.
        resource_type: Resource class when recorded.
        resource_id: Resource id when recorded.
        payload: Already-redacted JSON object. Must not contain passage text.
        created_at_iso: UTC timestamp text matching SQL canonicalization.
    """

    chain_seq: int
    event_id: UUID
    event_hash: str
    previous_hash: str
    event_type: str
    actor_user_id: UUID | None
    actor_role: str | None
    target_type: str | None
    target_id: UUID | None
    authorization_version: int | None
    visibility_generation: int | None
    session_id: str | None
    purpose: str | None
    resource_type: str | None
    resource_id: UUID | None
    payload: Mapping[str, _JsonValue]
    created_at_iso: str


@dataclass(frozen=True, slots=True)
class AuditExportResult:
    """Exporter outcome.

    Attributes:
        ready: True only when the chain verified and the signature succeeded.
        fault: First blocking fault, if any.
        broken_event_id: Event that failed verification.
        signature_hex: HMAC of the chain head when ready.
        chain_head_hash: Last event hash when the walk completed.
    """

    ready: bool
    fault: AuditExportFault | None
    broken_event_id: UUID | None
    signature_hex: str | None
    chain_head_hash: str | None


def _payload_contains_passage(payload: Mapping[str, _JsonValue]) -> bool:
    """Return True when a payload key looks like full source text.

    Args:
        payload: Redacted audit payload.

    Returns:
        True if a forbidden fragment appears in a key name.
    """

    stack: list[_JsonValue] = [dict(payload)]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            mapping = cast(dict[str, _JsonValue], current)
            for key, child in mapping.items():
                if any(
                    fragment in key.casefold()
                    for fragment in _FORBIDDEN_PAYLOAD_FRAGMENTS
                ):
                    return True
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(cast(list[_JsonValue], current))
    return False


def verify_audit_export_rows(rows: Sequence[AuditExportRow]) -> AuditExportResult:
    """Walk rows in ``chain_seq`` order and detect mutation, gap, or fork.

    Args:
        rows: Local snapshot. Need not be a live database cursor.

    Returns:
        ``ready=False`` on the first fault. Empty input is a gap (not ready).
    """

    if not rows:
        return AuditExportResult(
            ready=False,
            fault=AuditExportFault.GAP,
            broken_event_id=None,
            signature_hex=None,
            chain_head_hash=None,
        )
    ordered = sorted(rows, key=lambda item: item.chain_seq)
    seen_seq: set[int] = set()
    seen_hash: dict[str, UUID] = {}
    expected_previous = AUDIT_CHAIN_GENESIS_HASH
    expected_seq = ordered[0].chain_seq
    head = AUDIT_CHAIN_GENESIS_HASH
    for row in ordered:
        if row.chain_seq in seen_seq:
            return AuditExportResult(
                ready=False,
                fault=AuditExportFault.FORK,
                broken_event_id=row.event_id,
                signature_hex=None,
                chain_head_hash=None,
            )
        seen_seq.add(row.chain_seq)
        if row.chain_seq != expected_seq:
            return AuditExportResult(
                ready=False,
                fault=AuditExportFault.GAP,
                broken_event_id=row.event_id,
                signature_hex=None,
                chain_head_hash=None,
            )
        expected_seq += 1
        if _payload_contains_passage(row.payload):
            return AuditExportResult(
                ready=False,
                fault=AuditExportFault.PASSAGE_TEXT,
                broken_event_id=row.event_id,
                signature_hex=None,
                chain_head_hash=None,
            )
        if row.previous_hash != expected_previous:
            return AuditExportResult(
                ready=False,
                fault=AuditExportFault.FORK,
                broken_event_id=row.event_id,
                signature_hex=None,
                chain_head_hash=None,
            )
        material = canonical_audit_material(
            event_type=row.event_type,
            actor_user_id=row.actor_user_id,
            actor_role=row.actor_role,
            target_type=row.target_type,
            target_id=row.target_id,
            authorization_version=row.authorization_version,
            visibility_generation=row.visibility_generation,
            session_id=row.session_id,
            purpose=row.purpose,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            payload=redact_audit_payload(row.payload),
            previous_hash=row.previous_hash,
            created_at_iso=row.created_at_iso,
        )
        computed = sha256_hex(material)
        if computed != row.event_hash:
            return AuditExportResult(
                ready=False,
                fault=AuditExportFault.MUTATED_ROW,
                broken_event_id=row.event_id,
                signature_hex=None,
                chain_head_hash=None,
            )
        if row.event_hash in seen_hash and seen_hash[row.event_hash] != row.event_id:
            return AuditExportResult(
                ready=False,
                fault=AuditExportFault.FORK,
                broken_event_id=row.event_id,
                signature_hex=None,
                chain_head_hash=None,
            )
        seen_hash[row.event_hash] = row.event_id
        expected_previous = row.event_hash
        head = row.event_hash
    return AuditExportResult(
        ready=True,
        fault=None,
        broken_event_id=None,
        signature_hex=None,
        chain_head_hash=head,
    )


class LocalHmacAuditExporter:
    """Sign a verified chain head with a local HMAC key. Not KMS.

    Args:
        secret: HMAC key bytes. Never logged.
        destination: Optional file path for the signed batch JSON.
    """

    def __init__(self, secret: bytes, *, destination: Path | None = None) -> None:
        """Store the HMAC secret and optional output path.

        Args:
            secret: Signing key. Empty secrets fail closed.
            destination: File written only after a successful sign.
        """

        self._secret = secret
        self._destination = destination

    def export(self, rows: Sequence[AuditExportRow]) -> AuditExportResult:
        """Verify then HMAC-sign the chain head.

        Args:
            rows: Local audit snapshot.

        Returns:
            Ready result with ``signature_hex`` or a blocking fault.

        Side Effects:
            Writes ``destination`` when set and verification succeeds.
            Does not store passage text.
        """

        verified = verify_audit_export_rows(rows)
        if not verified.ready or verified.chain_head_hash is None:
            return verified
        if not self._secret:
            return AuditExportResult(
                ready=False,
                fault=AuditExportFault.SIGNING_FAILURE,
                broken_event_id=None,
                signature_hex=None,
                chain_head_hash=verified.chain_head_hash,
            )
        try:
            signature = hmac.new(
                self._secret,
                verified.chain_head_hash.encode("ascii"),
                hashlib.sha256,
            ).hexdigest()
        except (TypeError, ValueError):
            return AuditExportResult(
                ready=False,
                fault=AuditExportFault.SIGNING_FAILURE,
                broken_event_id=None,
                signature_hex=None,
                chain_head_hash=verified.chain_head_hash,
            )
        if self._destination is not None:
            payload = {
                "chain_head_hash": verified.chain_head_hash,
                "signature_hex": signature,
                "event_ids": [str(row.event_id) for row in rows],
                "kms": False,
                "s3_object_lock": False,
                "phase_10_blocker": True,
            }
            self._destination.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return AuditExportResult(
            ready=True,
            fault=None,
            broken_event_id=None,
            signature_hex=signature,
            chain_head_hash=verified.chain_head_hash,
        )
