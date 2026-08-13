"""Security primitives shared across API, worker, and contract tests."""

from smart_rag_core.security.audit_chain import (
    AUDIT_CHAIN_GENESIS_HASH,
    canonical_audit_material,
    redact_audit_payload,
    sha256_hex,
)
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.security.jwks import (
    JwksVerificationError,
    JwksVerifier,
    VerifiedAccessToken,
)

__all__ = [
    "AUDIT_CHAIN_GENESIS_HASH",
    "CallerContext",
    "JwksVerificationError",
    "JwksVerifier",
    "UserRole",
    "VerifiedAccessToken",
    "canonical_audit_material",
    "redact_audit_payload",
    "sha256_hex",
]
