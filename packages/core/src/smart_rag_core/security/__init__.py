"""Security primitives shared across API, worker, and contract tests."""

from smart_rag_core.security.audit_chain import (
    AUDIT_CHAIN_GENESIS_HASH,
    canonical_audit_material,
    redact_audit_payload,
    sha256_hex,
)
from smart_rag_core.security.audit_export import (
    AuditExportFault,
    AuditExportRow,
    LocalHmacAuditExporter,
    verify_audit_export_rows,
)
from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    DetectorResult,
    ExternalProcessingDecision,
    ExternalProcessingDecisionInput,
    decide_external_processing,
)
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.security.jwks import (
    JwksVerificationError,
    JwksVerifier,
    VerifiedAccessToken,
)
from smart_rag_core.security.profile_snapshot import (
    ProfileSnapshot,
    build_caller_context,
    is_session_revoked,
    load_profile_snapshot,
)
from smart_rag_core.security.untrusted import isolate_untrusted_text

__all__ = [
    "AUDIT_CHAIN_GENESIS_HASH",
    "AuditExportFault",
    "AuditExportRow",
    "CallerContext",
    "CategoryDisposition",
    "ContentClass",
    "DetectorResult",
    "ExternalProcessingDecision",
    "ExternalProcessingDecisionInput",
    "JwksVerificationError",
    "JwksVerifier",
    "LocalHmacAuditExporter",
    "ProfileSnapshot",
    "UserRole",
    "VerifiedAccessToken",
    "build_caller_context",
    "canonical_audit_material",
    "decide_external_processing",
    "is_session_revoked",
    "isolate_untrusted_text",
    "load_profile_snapshot",
    "redact_audit_payload",
    "sha256_hex",
    "verify_audit_export_rows",
]
