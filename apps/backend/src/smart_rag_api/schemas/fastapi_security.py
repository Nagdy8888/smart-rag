"""Pydantic schemas for Phase 6 packet 5 HTTP routes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from smart_rag_core.feedback.tags import FeedbackTag
from smart_rag_core.gateways.cost_reporting import CostReporting
from smart_rag_core.knowledge import KnowledgeResult
from smart_rag_core.observability.checkpoint_usage import CheckpointUsageSummary
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.tables.plan import TableQueryPlan


class MetaResponse(BaseModel):
    """Compatibility handshake fields. Packet 6 owns enforcement.

    ``web_search_enabled`` is the runtime flag for public Exa web research.
    It is never the Exa key and never means company-document search.
    Hosted environments reject ``WEB_SEARCH_ENABLED=true`` at settings
    load, so this field stays false in staging and production.
    """

    model_config = ConfigDict(frozen=True)

    api_version: str
    sse_schema_version: str
    min_client_version: str
    pdf_eval_workspace: bool = False
    web_search_enabled: bool = Field(
        default=False,
        description=("When true, the Ask dropdown may offer Web. Never includes keys."),
    )


class CurrentUserResponse(BaseModel):
    """Authenticated caller snapshot. Role is server-derived."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    role: str
    authorization_version: int
    upload_enabled: bool
    mfa_enrolled: bool = Field(
        description=(
            "Deprecated compatibility field. Always false. Never used for "
            "authorization."
        ),
    )


class CreateInvitationRequest(BaseModel):
    """Owner/admin invitation create body."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    role: str = Field(min_length=5, max_length=16)
    upload_enabled: bool = False


class CreateInvitationResponse(BaseModel):
    """Invitation identifiers. The one-time token is delivered by mail only."""

    model_config = ConfigDict(frozen=True)

    invitation_id: UUID
    email: str
    role: str
    upload_enabled: bool
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    """Invitation accept body. Email comes from the verified token."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    token: str = Field(min_length=8, max_length=256)


class ConversationCreateRequest(BaseModel):
    """Create conversation body."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = Field(default=None, max_length=512)


class ConversationResponse(BaseModel):
    """Conversation JSON. Title is escaped untrusted text.

    ``prompt_tokens`` and ``completion_tokens`` are provider usage for this
    HTTP response. They are meaningful on ``POST /conversations/{id}/title``
    (0 when the model was skipped or failed). List, get, and create return 0.
    """

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    creator_user_id: UUID
    title: str | None
    created_at: datetime | None = None
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)


class CitationResponse(BaseModel):
    """Citation identifiers plus ACL-checked title, PDF page, and excerpt."""

    model_config = ConfigDict(frozen=True)

    citation_id: UUID
    citation_index: int
    chunk_id: UUID | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    source_unavailable: bool = False
    source_kind: str = "company_document"
    web_source_id: UUID | None = None
    paragraph_index: int | None = None
    document_title: str | None = None
    pdf_page_number: int | None = None
    evidence_excerpt: str | None = None


class CitationDetailResponse(CitationResponse):
    """One citation with a bounded ACL-checked excerpt or HTTPS Web URL."""

    model_config = ConfigDict(frozen=True)

    source_url: str | None = None


def _empty_citation_responses() -> list[CitationResponse]:
    """Return an empty citation list for additive HTTP defaults.

    Returns:
        Empty list. Never shared across model instances.
    """

    return []


class ConversationMessage(BaseModel):
    """One creator-owned transcript message. Content is escaped untrusted text."""

    model_config = ConfigDict(frozen=True)

    message_id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    run_id: UUID | None = None
    run_status: str | None = None
    requested_search_scope: str | None = None
    answer_origin: str | None = None
    citation_count: int = Field(default=0, ge=0, le=50)
    source_kind: Literal["company_document", "web"] | None = None
    knowledge_result: KnowledgeResult | None = None
    citations: list[CitationResponse] = Field(default_factory=_empty_citation_responses)


class ConversationMessagesResponse(BaseModel):
    """Keyset page of conversation messages, newest first.

    ``next_before_id`` is the last item's id when the page is full (exactly
    ``limit`` rows). Clients pass it as ``before`` to load older messages.
    """

    model_config = ConfigDict(frozen=True)

    items: list[ConversationMessage]
    next_before_id: UUID | None = None


class SubmitMessageRequest(BaseModel):
    """Idempotent Auto chat submit. Composite envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message: str = Field(min_length=1, max_length=16_384)
    idempotency_key: UUID | None = Field(
        default=None,
        description="Required on paid POST unless Idempotency-Key header is set.",
    )
    search_scope: RequestedSearchScope = Field(
        default=RequestedSearchScope.AUTO,
        description="Answer-source preference. Not a route, document, or ACL selector.",
    )


class SubmitMessageResponse(BaseModel):
    """Admission result. Stream path is packet 6 transport."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    stream_path: str
    reconnect: bool
    reservation_id: UUID
    route_family: str
    status: str
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO


class RunResponse(BaseModel):
    """Owned run fetch/cancel payload."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    conversation_id: UUID
    creator_user_id: UUID
    status: str
    reservation_id: UUID | None = None
    created_at: datetime | None = None
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO


class FeedbackRequest(BaseModel):
    """Thumbs feedback with a required unmerged Phase 6 tag."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thumbs_up: bool
    tag: FeedbackTag
    comment: str | None = Field(default=None, max_length=2000)
    share_with_reviewers: bool = False


class FeedbackResponse(BaseModel):
    """Created feedback id."""

    model_config = ConfigDict(frozen=True)

    feedback_id: UUID


class UsageResponse(BaseModel):
    """Usage totals without prompt text."""

    model_config = ConfigDict(frozen=True)

    scope: str
    cost_usd: Decimal
    cost_reporting: CostReporting | None = None
    checkpoint_usage: CheckpointUsageSummary | None = None
    display_cost_usd: Decimal | None = None
    prompt_tokens: int
    completion_tokens: int
    usage_rows: int


class DocumentResponse(BaseModel):
    """Visible document summary."""

    model_config = ConfigDict(frozen=True)

    document_id: UUID
    title: str | None
    visibility: str
    current_version_id: UUID | None
    visibility_generation: int
    created_at: datetime | None = None


class UpdateDocumentTitleRequest(BaseModel):
    """Owner/admin document title body. Max length matches finalize.

    Attributes:
        title: Non-empty trimmed title, at most 512 characters.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1, max_length=512)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        """Reject whitespace-only titles after trim.

        Args:
            value: Submitted title.

        Returns:
            Trimmed title.

        Raises:
            ValueError: When the trimmed title is empty.
        """

        trimmed = value.strip()
        if trimmed == "":
            raise ValueError("title_required")
        return trimmed


class SignedUploadRequest(BaseModel):
    """Quota reserve for a quarantine upload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    declared_bytes: int = Field(ge=1, le=104_857_600)
    idempotency_key: str = Field(min_length=8, max_length=256)


class SignedUploadResponse(BaseModel):
    """Reservation plus storage path. CloudFront signing is Phase 10."""

    model_config = ConfigDict(frozen=True)

    reservation_id: UUID
    storage_bucket: str
    storage_path: str
    expires_at: datetime
    signed_url: str | None = None
    upload_method: str = "supabase_storage_jwt"


class FinalizeUploadHttpRequest(BaseModel):
    """Finalize after the browser Storage upload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reservation_id: UUID
    object_name: str = Field(min_length=1, max_length=512)
    content_hash: str = Field(min_length=16, max_length=128)
    actual_bytes: int = Field(ge=1, le=104_857_600)
    media_type: str | None = Field(default=None, max_length=128)
    declared_category: str = Field(min_length=1, max_length=64)
    attestation_policy_version: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=256)
    document_title: str | None = Field(default=None, max_length=512)


class FinalizeUploadHttpResponse(BaseModel):
    """Finalize identifiers."""

    model_config = ConfigDict(frozen=True)

    reservation_id: UUID
    document_id: UUID
    version_id: UUID
    job_id: UUID


class TableManifestResponse(BaseModel):
    """Authorized table manifest without storage paths."""

    model_config = ConfigDict(frozen=True)

    table_id: UUID
    document_id: UUID
    version_id: UUID
    table_name: str
    sheet_name: str | None
    row_count: int | None
    column_count: int | None


class TableAnalyzeRequest(BaseModel):
    """Bounded analysis POST. Extra fields forbidden via TableQueryPlan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: TableQueryPlan


class TableAnalyzeResponse(BaseModel):
    """Deterministic table values. Cell text is escaped."""

    model_config = ConfigDict(frozen=True)

    table_id: UUID
    version_id: UUID
    document_id: UUID
    rows: tuple[dict[str, Any], ...]
    source_ranges: tuple[str, ...]


class ToolCardResponse(BaseModel):
    """Permission-filtered catalog card. No unauthorized names."""

    model_config = ConfigDict(frozen=True)

    tool_key: str
    version_label: str
    short_name: str
    purpose: str
    required_role: str
    risk_class: str
    active: bool


class ToolSeedRequest(BaseModel):
    """Owner/admin catalog seed. Key must be in-code allow-listed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_key: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    active: bool = False


class ToolEnableRequest(BaseModel):
    """Owner/admin enable flag."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    active: bool


class ToolPermissionRequest(BaseModel):
    """Owner/admin permission seed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_role: str = Field(min_length=5, max_length=16)
    permission: str = Field(min_length=4, max_length=16)


class ToolMutationResponse(BaseModel):
    """Admin tool row id."""

    model_config = ConfigDict(frozen=True)

    id: UUID


class GraphEntityResponse(BaseModel):
    """Authorized entity search hit."""

    model_config = ConfigDict(frozen=True)

    object_id: str
    object_type: str
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    support: float


class AcceptInvitationResponse(BaseModel):
    """Accepted invitation id."""

    model_config = ConfigDict(frozen=True)

    invitation_id: UUID


class OffboardResponse(BaseModel):
    """Completed offboarding identifiers."""

    model_config = ConfigDict(frozen=True)

    request_id: UUID
    subject_user_id: UUID
    completed_at: datetime


class WorkspaceMemberResponse(BaseModel):
    """One workspace profile for owner/admin Team listing."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    email: str
    display_name: str | None
    role: str
    upload_enabled: bool
    disabled_at: datetime | None
    created_at: datetime | None = None


class PendingInvitationResponse(BaseModel):
    """One unaccepted invitation. The token hash is never included."""

    model_config = ConfigDict(frozen=True)

    invitation_id: UUID
    email: str
    role: str
    upload_enabled: bool
    expires_at: datetime
    created_at: datetime | None = None


class WorkspaceDirectoryResponse(BaseModel):
    """Bounded owner/admin directory. Max 200 members and 200 invitations."""

    model_config = ConfigDict(frozen=True)

    members: list[WorkspaceMemberResponse]
    pending_invitations: list[PendingInvitationResponse]
