/**
 * Local PDF evaluation workspace HTTP types.
 *
 * Field names match `/admin/pdf-eval/` OpenAPI. Questions are never logged.
 */

/** Workspace status without questions or filesystem paths. */
export type PdfEvalStatus = {
  enabled: boolean;
  case_count: number;
  revision: string | null;
  version_id: string | null;
  document_id: string | null;
  dataset_present: boolean;
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
};

/** Paginated summaries. */
export type PdfEvalCaseList = {
  revision: string;
  items: PdfEvalCaseSummary[];
  next_case_id: string | null;
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

/** Count-only citation overlap. Official Recall@10 stays CLI. */
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
