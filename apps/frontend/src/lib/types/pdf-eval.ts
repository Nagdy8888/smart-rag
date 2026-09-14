/**
 * Hosted PDF evaluation workspace HTTP types.
 *
 * Field names match `/admin/pdf-eval/` OpenAPI. Questions are never logged.
 */

/** Allow-listed quiz classes. Extra values are rejected by FastAPI. */
export const PDF_EVAL_QUERY_CLASSES = [
  "factual_definition",
  "exact_acronym",
  "semantic_paraphrase",
  "multi_part",
  "section_scoped",
] as const;

/** One allow-listed quiz class token. */
export type PdfEvalQueryClass = (typeof PDF_EVAL_QUERY_CLASSES)[number];

/** Workspace status without questions or filesystem paths. */
export type PdfEvalStatus = {
  enabled: boolean;
  case_count: number;
  revision: string | null;
  version_id: string | null;
  document_id: string | null;
  dataset_present: boolean;
  schema_ready?: boolean;
  holdout_opened?: boolean;
  draft_count?: number;
  approved_count?: number;
  rejected_count?: number;
  stale_gold_count?: number;
  live_count?: number;
  remaining_capacity?: number;
};

/** List row without question, answer, facts, or excerpts. */
export type PdfEvalCaseSummary = {
  case_id: string;
  split: string;
  query_class: string;
  human_approved: boolean;
  generated_only: boolean;
  reviewer: string | null;
  expected_refusal: boolean;
  gold_chunk_count: number;
  review_status: string;
  source_family_id: string | null;
  gold_stale: boolean;
  row_version: number;
};

/** Paginated summaries. */
export type PdfEvalCaseList = {
  revision: string;
  items: PdfEvalCaseSummary[];
  next_case_id: string | null;
};

/** Server-derived gold locator. */
export type PdfEvalGoldLocator = {
  ordinal: number;
  chunk_id: string;
  document_id: string;
  version_id: string;
  page_number: number | null;
  page_label: string | null;
  section_path: string[];
  stale: boolean;
};

/** Owner/admin case detail including private question fields. */
export type PdfEvalCaseDetail = {
  revision: string;
  case_id: string;
  split: string;
  query_class: string;
  human_approved: boolean;
  generated_only: boolean;
  reviewer: string | null;
  expected_refusal: boolean;
  expected_scope: string;
  chunk_ids: string[];
  page_numbers: number[];
  heading_paths: string[];
  required_terms: string[];
  question: string;
  expected_answer: string;
  atomic_facts: string[];
  review_status: string;
  source_family_id: string | null;
  source_run_id: string | null;
  document_id: string | null;
  version_id: string | null;
  gold: PdfEvalGoldLocator[];
  gold_stale: boolean;
  reviewer_user_id: string | null;
  row_version: number;
};

/** Create a development draft from a caller-owned run. No question field. */
export type PdfEvalCaseCreateRequest = {
  source_run_id: string;
  expected_answer?: string;
  atomic_facts?: string[];
  query_class: string;
  required_terms?: string[];
  split?: "development";
  source_family_id?: string | null;
  chunk_ids?: string[];
  idempotency_key: string;
};

/** Mutation result after create or CAS write. */
export type PdfEvalMutation = {
  case_id: string | null;
  row_version: number | null;
  replayed: boolean;
  inserted_count?: number | null;
  gold_chunk_count?: number | null;
};

/** Paginated authorized passages for one document. */
export type PdfEvalPassageList = {
  items: PdfEvalPassage[];
  next_chunk_id: string | null;
};

/** Authorized current representative passage. */
export type PdfEvalPassage = {
  chunk_id: string;
  document_id: string;
  version_id: string;
  page_number: number | null;
  heading_path: string[];
  raw_text: string;
};

/** Count-only citation overlap. Official Recall@10 stays on the exam runner. */
export type PdfEvalCompareRun = {
  case_id: string;
  split: string;
  gold_count: number;
  citation_count: number;
  intersection: number;
  ranked_hit_at_10: number;
  run_id: string;
  manual_ai_test: boolean;
};

/** 202 enqueue or idempotent reconnect. */
export type PdfEvalExamAccepted = {
  exam_run_id: string;
  status: string;
  dataset_hash: string;
  replayed: boolean;
  holdout_opened: boolean;
};

/** Poll row without questions or ranked IDs. */
export type PdfEvalExamStatus = {
  exam_run_id: string;
  split: string;
  status: string;
  dataset_hash: string;
  case_count: number;
  completed_case_count: number;
  holdout_opened: boolean;
  candidate_fingerprint: string | null;
};

/** Split-isolated official report. Partial runs never appear. */
export type PdfEvalExamReport = {
  present: boolean;
  holdout_opened: boolean;
  exam_run_id: string | null;
  split: string | null;
  dataset_hash: string | null;
  case_count: number | null;
  hit_count: number | null;
  hybrid_recall_at_10: number | null;
  gates_pass: boolean | null;
  created_at: string | null;
};

/** Count-only report case. Misses are `hit=false`. */
export type PdfEvalExamCase = {
  case_id: string;
  ordinal: number;
  hit: boolean;
  gold_count: number;
  ranked_hit_count: number;
  latency_ms: number | null;
};

/** Report case page. */
export type PdfEvalExamCaseList = {
  exam_run_id: string;
  items: PdfEvalExamCase[];
  missed_count: number;
};

/** Empty-dataset 422 counts. Never includes `gates_pass`. */
export type PdfEvalEmptyDataset = {
  detail: "empty_dataset";
  draft_count: number;
  approved_count: number;
  rejected_count: number;
  stale_gold_count: number;
  live_count: number;
};
