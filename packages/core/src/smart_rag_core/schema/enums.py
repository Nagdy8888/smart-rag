"""Postgres enum mirrors for Smart RAG authoritative schema."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Company membership roles enforced by profiles and RLS (Packet 3)."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class DocumentVisibility(StrEnum):
    """Document ACL visibility states."""

    COMPANY_VISIBLE = "company_visible"
    RESTRICTED = "restricted"


class DocumentStatus(StrEnum):
    """Ingestion/index lifecycle for a document version."""

    UPLOADED = "uploaded"
    SCANNING = "scanning"
    PARSING = "parsing"
    HYBRID_READY = "hybrid_ready"
    GRAPH_PENDING = "graph_pending"
    GRAPH_READY = "graph_ready"
    GRAPH_INELIGIBLE = "graph_ineligible"
    DELETION_PENDING = "deletion_pending"
    FAILED = "failed"


class SourceType(StrEnum):
    """Origin of a document source row."""

    FILE_UPLOAD = "file_upload"
    WEBSITE_CRAWL = "website_crawl"


class ScanResult(StrEnum):
    """Malware scan disposition for quarantine/promotion."""

    CLEAN = "clean"
    INFECTED = "infected"
    UNSCANNABLE = "unscannable"
    STALE_SIGNATURE = "stale_signature"
    OVER_LIMIT = "over_limit"


class ApprovalStatus(StrEnum):
    """URL/source approval workflow states."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class JobStatus(StrEnum):
    """Shared durable queue lifecycle."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class JobPriority(StrEnum):
    """Queue priority bands."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class JobErrorCategory(StrEnum):
    """Retry/dead-letter classification for worker routing."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    BUDGET = "budget"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class Bm25JobOperation(StrEnum):
    """BM25 outbox mutation intent."""

    UPSERT = "upsert"
    DELETE = "delete"


class LightragJobOperation(StrEnum):
    """LightRAG indexing/cleanup operations."""

    INDEX = "index"
    REMOVE = "remove"
    GRAPH_ACL_REMOVE = "graph_acl_remove"
    REBUILD = "rebuild"


class RunStatus(StrEnum):
    """LangGraph/API run lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class BudgetReservationStatus(StrEnum):
    """Durable budget/quota reservation lifecycle."""

    RESERVED = "reserved"
    COMMITTED = "committed"
    RELEASED = "released"
    EXPIRED = "expired"


class ToolPermissionLevel(StrEnum):
    """Optional tool catalog permission bands."""

    NONE = "none"
    READ = "read"
    EXECUTE = "execute"
    ADMIN = "admin"
