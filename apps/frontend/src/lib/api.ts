/**
 * Compatibility barrel for the authenticated FastAPI client.
 *
 * Domain modules must not import this file.
 */

export { throwClassifiedAdminError } from "./api/admin-errors";
export type {
  ApiFailure,
  AuthFailure,
  BudgetFailure,
  ConflictFailure,
  DeletedFailure,
  FailClosedFailure,
  HandshakeFailure,
  ProtocolFailure,
  UnavailableFailure,
  RateFailure,
  ServerFailure,
  ValidationFailure,
} from "./api/errors";
export {
  ClassifiedApiError,
  classifiedOrGenericFailure,
  classifyApiError,
  isClassifiedApiError,
  isSafeDetailCode,
  retryAfterHeader,
  sanitizedDetail,
  throwIfNotOk,
} from "./api/errors";
export type { ApiAuth } from "./api/headers";
export {
  adminMutationHeaders,
  paidMutationHeaders,
  resumeHeaders,
  submitMessageBody,
} from "./api/headers";
export { apiUrl, readJsonObject } from "./api/http";
export { nextDocumentCursor, parseConversationResponse, parseDocumentResponse, parseFeedbackResponse, parseRunResponse } from "./api/parsers";
export { DOCUMENT_LIST_PAGE_SIZE } from "./api/documents-constants";
export {
  HEALTH_READY_TIMEOUT_MS,
  fetchMe,
  fetchMeta,
  fetchOperatorReady,
  fetchReady,
  loadConsoleReadiness,
  mergeReadiness,
} from "./api/readiness";
export {
  createConversation,
  deleteConversation,
  fetchConversation,
  fetchConversationMessages,
  fetchRun,
  generateConversationTitle,
  listConversations,
} from "./api/chat";
export { cancelRun, fetchCitationDetail, fetchCitationPagePng, listCitations, parseCitationItem, parseHttpsSourceUrl, submitFeedback } from "./api/chat-run";
export { deleteDocument, fetchDocument, fetchVersionStatus, listDocuments, type DocumentFetchResult } from "./api/documents";
export {
  enqueueWebsiteCrawl,
  finalizeUpload,
  reserveUpload,
  retryIngestionJob,
} from "./api/documents-ingest";
export { inspectGraph, searchGraphEntities } from "./api/graph";
export { analyzeTable, listTables } from "./api/tables";
export { fetchUsageCompany, fetchUsageMe } from "./api/usage";
export { acceptInvitation, createInvitation, listWorkspaceUsers, offboardUser } from "./api/invitations";
export { enableTool, listTools, seedTool, setToolPermission } from "./api/tools";
export { approveGlossaryImport, importGlossary, rollbackGlossaryImport } from "./api/knowledge";
export {
  cancelPdfEvalExam,
  comparePdfEvalRun,
  createPdfEvalCase,
  deletePdfEvalCase,
  fetchPdfEvalCase,
  fetchPdfEvalExam,
  fetchPdfEvalLatestReport,
  fetchPdfEvalStatus,
  listPdfEvalCases,
  listPdfEvalExamCases,
  listPdfEvalPassages,
  patchPdfEvalCase,
  regeneratePdfEvalDrafts,
  replacePdfEvalGold,
  setPdfEvalApproval,
  startPdfEvalExam,
  type PdfEvalCaseListQuery,
  type PdfEvalPassageListQuery,
} from "./api/pdf-eval";
export { approveEntityRule, listEntityRules, patchEntityRule, revokeEntityRule, suggestEntityRule, upsertEntityRule } from "./api/knowledge-rules";
export { resumeEventStream, shouldResumeExistingRun, startMessageStream, startOrResumeMessageStream, type PaidRunPointer, type StreamStart } from "./api/sse";
