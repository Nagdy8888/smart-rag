/**
 * Compatibility barrel for OpenAPI-aligned frontend types.
 *
 * Field names match `docs/api/openapi.foundation.json`. Domain modules must
 * not import this file.
 */

export type { AcceptInvitationResponse, CreateInvitationRequest, CreateInvitationResponse, CurrentUserResponse, InviteRole, MetaResponse, OffboardResponse, PendingInvitation, WorkspaceDirectoryResponse, WorkspaceMember } from "./types/auth";
export { INVITE_ROLES } from "./types/auth";
export type {
  PdfEvalCaseCreateRequest,
  PdfEvalCaseDetail,
  PdfEvalCaseList,
  PdfEvalCaseSummary,
  PdfEvalCompareRun,
  PdfEvalEmptyDataset,
  PdfEvalExamAccepted,
  PdfEvalExamCase,
  PdfEvalExamCaseList,
  PdfEvalExamReport,
  PdfEvalExamStatus,
  PdfEvalGoldLocator,
  PdfEvalMutation,
  PdfEvalPassage,
  PdfEvalPassageList,
  PdfEvalQueryClass,
  PdfEvalStatus,
} from "./types/pdf-eval";
export { PDF_EVAL_QUERY_CLASSES } from "./types/pdf-eval";
export type { DependencyStatus, ReadinessResponse } from "./types/readiness";
export type { AnswerOrigin, CitationResponse, ConversationMessage, ConversationMessagesResponse, ConversationResponse, FeedbackResponse, FeedbackTag, RequestedSearchScope, RunResponse, SubmitMessageResponse } from "./types/chat";
export { ANSWER_ORIGINS, FEEDBACK_TAGS, FEEDBACK_TAGS_DOWN, FEEDBACK_TAGS_UP, REQUESTED_SEARCH_SCOPES, feedbackTagsFor, isRequestedSearchScope, requestedSearchScopeLabel } from "./types/chat";
export type { Bm25Diagnostics, DocumentIngestionStatusResponse, DocumentResponse, EnqueueWebsiteCrawlRequest, EnqueueWebsiteCrawlResponse, FinalizeUploadHttpRequest, FinalizeUploadHttpResponse, GraphHandoffDiagnostics, IngestionJobSummary, IngestionLifecycleStatus, IngestionStatusVersion, OcrDiagnostics, RetryIngestionJobResponse, ReviewDiagnostics, ScanDiagnostics, SignedUploadResponse } from "./types/documents";
export { INGESTION_LIFECYCLE_STATUSES } from "./types/documents";
export type { GraphEntityResponse, GraphInspectLimitation, GraphInspectLocator, GraphInspectNodeResponse, GraphInspectRequest, GraphInspectResponse } from "./types/graph";
export type { TableAggregation, TableAggregationOp, TableManifestResponse, TableAnalyzeResponse, TableOrder, TablePredicate, TablePredicateOperator, TableQueryPlan, TableSortDirection } from "./types/tables";
export { TABLE_AGGREGATION_OPS, TABLE_PREDICATE_OPERATORS, TABLE_SORT_DIRECTIONS } from "./types/tables";
export type { UsageResponse } from "./types/usage";
export type { ToolCardResponse, ToolMutationResponse, ToolPermission, ToolPermissionRequest, ToolSeedRequest } from "./types/admin-tools";
export { TOOL_PERMISSIONS } from "./types/admin-tools";
export type { EntityRuleConcurrencyRequest, EntityRuleListItem, EntityRuleListResponse, EntityRuleMutationResponse, EntityRuleSource, EntityRuleStatus, EntityRuleSuggestRequest, EntityRuleUpsertRequest, GlossaryAliasRequest, GlossaryEntryRequest, GlossaryEntryType, GlossaryImportResponse, GlossaryLanguage, GlossaryScope, ImportGlossaryRequest } from "./types/admin-knowledge";
export { ENTITY_RULE_SOURCES, ENTITY_RULE_STATUSES, GLOSSARY_ENTRY_TYPES, GLOSSARY_LANGUAGES, GLOSSARY_SCOPES } from "./types/admin-knowledge";
export type { KnownSseEventType, SseProgressPhase } from "./types/sse";
export { KNOWN_SSE_EVENT_TYPES, TERMINAL_SSE_EVENT_TYPES } from "./types/sse";
