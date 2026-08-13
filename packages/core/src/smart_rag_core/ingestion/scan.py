"""Object scanning orchestration with hash verification and evidence mapping."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from smart_rag_core.gateways.clamav import ClamAvClient, ScanDisposition
from smart_rag_core.gateways.storage import StorageGateway
from smart_rag_core.ingestion.limits import SCAN_CONFIG_VERSION
from smart_rag_core.schema.enums import ScanResult


@dataclass(frozen=True, slots=True)
class ObjectScanInput:
    """Inputs required to scan one quarantined Storage object."""

    bucket: str
    path: str
    expected_hash: str
    expected_bytes: int


@dataclass(frozen=True, slots=True)
class ObjectScanResult:
    """Normalized scan output ready for ``document_scan_events`` persistence."""

    result: ScanResult
    object_hash: str
    bytes_examined: int
    scan_engine_version: str
    signature_version: str
    functionality_level: str | None
    signature_db_timestamp: str | None
    signature_db_ids: dict[str, str]
    config_version: str
    details: dict[str, object]


def scan_object_bytes(
    storage: StorageGateway,
    clamav: ClamAvClient,
    scan_input: ObjectScanInput,
) -> ObjectScanResult:
    """Download exact object bytes, verify hash, and scan via ClamAV ``INSTREAM``.

    Args:
        storage: Privileged Storage gateway.
        clamav: ClamAV client bound to ``clamd``.
        scan_input: Expected object location and hash/size contract.

    Returns:
        Append-only scan evidence payload. Failures remain quarantined.

    Raises:
        StorageGatewayError: When download fails before scan.
        ClamAvError: When engine metadata cannot be read.
    """

    data = storage.download_object(
        bucket=scan_input.bucket, object_path=scan_input.path
    )
    digest = hashlib.sha256(data).hexdigest().lower()
    if digest != scan_input.expected_hash.lower():
        return ObjectScanResult(
            result=ScanResult.HASH_MISMATCH,
            object_hash=digest,
            bytes_examined=len(data),
            scan_engine_version="unknown",
            signature_version="unknown",
            functionality_level=None,
            signature_db_timestamp=None,
            signature_db_ids={},
            config_version=SCAN_CONFIG_VERSION,
            details={"reason": "hash_mismatch", "expected": scan_input.expected_hash},
        )
    if len(data) != scan_input.expected_bytes:
        return ObjectScanResult(
            result=ScanResult.OVER_LIMIT,
            object_hash=digest,
            bytes_examined=len(data),
            scan_engine_version="unknown",
            signature_version="unknown",
            functionality_level=None,
            signature_db_timestamp=None,
            signature_db_ids={},
            config_version="scan_v1",
            details={
                "reason": "size_mismatch",
                "expected_bytes": scan_input.expected_bytes,
                "actual_bytes": len(data),
            },
        )

    engine_info = clamav.read_engine_info()
    scan = clamav.scan_stream(data, engine_info=engine_info)
    return ObjectScanResult(
        result=_map_disposition(scan.disposition),
        object_hash=digest,
        bytes_examined=scan.bytes_examined,
        scan_engine_version=scan.engine_info.engine_version,
        signature_version=_signature_version(scan.signature_db_ids),
        functionality_level=scan.engine_info.functionality_level,
        signature_db_timestamp=(
            scan.signature_db_timestamp.isoformat()
            if scan.signature_db_timestamp
            else None
        ),
        signature_db_ids=scan.signature_db_ids,
        config_version=scan.engine_info.config_version,
        details={
            "detail": scan.detail,
            "threat_name": scan.threat_name,
        },
    )


def _map_disposition(disposition: ScanDisposition) -> ScanResult:
    """Map ClamAV disposition enum to Postgres ``scan_result``."""

    mapping = {
        ScanDisposition.CLEAN: ScanResult.CLEAN,
        ScanDisposition.INFECTED: ScanResult.INFECTED,
        ScanDisposition.UNSCANNABLE: ScanResult.UNSCANNABLE,
        ScanDisposition.STALE_SIGNATURE: ScanResult.STALE_SIGNATURE,
        ScanDisposition.OVER_LIMIT: ScanResult.OVER_LIMIT,
        ScanDisposition.HASH_MISMATCH: ScanResult.HASH_MISMATCH,
    }
    return mapping[disposition]


def _signature_version(signature_db_ids: dict[str, str]) -> str:
    """Serialize signature database versions for the legacy column."""

    if not signature_db_ids:
        return "unknown"
    return ",".join(
        f"{name}:{version}" for name, version in sorted(signature_db_ids.items())
    )
