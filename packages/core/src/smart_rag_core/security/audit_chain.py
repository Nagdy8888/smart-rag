"""Local helpers for audit hash-chain verification and payload redaction.

SQL remains authoritative for insert-time hashing via
``app.audit_events_hash_chain_bi``. These helpers mirror the canonical material
and redaction rules so contract tests can assert Python/SQL agreement without
reimplementing Postgres ``digest``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import TypeAlias
from uuid import UUID

AUDIT_CHAIN_GENESIS_HASH = "0" * 64
_SENSITIVE_KEY_FRAGMENTS = ("password", "token", "secret", "raw_ip")
_JsonScalar: TypeAlias = str | int | float | bool | None
_JsonValue: TypeAlias = _JsonScalar | list["_JsonValue"] | dict[str, "_JsonValue"]
_JsonObject: TypeAlias = dict[str, _JsonValue]


def redact_audit_payload(payload: Mapping[str, _JsonValue] | None) -> _JsonObject:
    """Redact sensitive keys from an audit payload mapping.

    Keys whose lowercased name contains ``password``, ``token``, ``secret``, or
    ``raw_ip`` are replaced with ``[REDACTED]``. Nested objects and arrays are
    walked recursively.

    Args:
        payload: Raw audit payload, or ``None`` for an empty object.

    Returns:
        A new dictionary safe to store and hash.
    """

    if payload is None:
        return {}
    return _redact_mapping(payload)


def _redact_mapping(value: Mapping[str, _JsonValue]) -> _JsonObject:
    """Redact every value in one string-keyed JSON object.

    Args:
        value: JSON object whose nested values may contain sensitive fields.

    Returns:
        A recursively copied and redacted JSON object.
    """

    result: _JsonObject = {}
    for key, child in value.items():
        lower = key.lower()
        if any(fragment in lower for fragment in _SENSITIVE_KEY_FRAGMENTS):
            result[key] = "[REDACTED]"
        else:
            result[key] = _redact_value(child)
    return result


def _redact_value(value: _JsonValue) -> _JsonValue:
    """Recursively redact one JSON-compatible value.

    Args:
        value: Scalar, object, or array from an audit payload.

    Returns:
        A copied value with sensitive nested object fields redacted.
    """

    if isinstance(value, dict):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def canonical_audit_material(
    *,
    event_type: str,
    actor_user_id: UUID | None,
    actor_role: str | None,
    target_type: str | None,
    target_id: UUID | None,
    authorization_version: int | None,
    visibility_generation: int | None,
    session_id: str | None,
    purpose: str | None,
    resource_type: str | None,
    resource_id: UUID | None,
    payload: Mapping[str, _JsonValue],
    previous_hash: str,
    created_at_iso: str,
) -> str:
    """Build deterministic JSON text matching ``app.audit_event_canonical_material``.

    Args:
        event_type: Audit event type string.
        actor_user_id: Acting user id when present.
        actor_role: Acting role label when present.
        target_type: Target object class when present.
        target_id: Target object id when present.
        authorization_version: Authorization snapshot when recorded.
        visibility_generation: Visibility generation when recorded.
        session_id: Session identifier when recorded.
        purpose: Purpose label when recorded.
        resource_type: Resource class when recorded.
        resource_id: Resource id when recorded.
        payload: Already-redacted payload object.
        previous_hash: Prior event hash or genesis constant.
        created_at_iso: UTC timestamp string as Postgres ``timestamptz`` text.

    Returns:
        Canonical JSON text used as SHA-256 input.
    """

    material = {
        "event_type": event_type,
        "actor_user_id": str(actor_user_id) if actor_user_id is not None else None,
        "actor_role": actor_role,
        "target_type": target_type,
        "target_id": str(target_id) if target_id is not None else None,
        "authorization_version": authorization_version,
        "visibility_generation": visibility_generation,
        "session_id": session_id,
        "purpose": purpose,
        "resource_type": resource_type,
        "resource_id": str(resource_id) if resource_id is not None else None,
        "payload": dict(payload),
        "previous_hash": previous_hash,
        "created_at": created_at_iso,
    }
    stripped = {key: value for key, value in material.items() if value is not None}
    # Match Postgres jsonb::text key ordering (lexicographic).
    return json.dumps(
        stripped, separators=(",", ":"), ensure_ascii=False, sort_keys=True
    )


def sha256_hex(material: str) -> str:
    """Return the lowercase hex SHA-256 digest of UTF-8 ``material``.

    Args:
        material: Canonical audit material string.

    Returns:
        64-character lowercase hex digest.
    """

    return hashlib.sha256(material.encode("utf-8")).hexdigest()
