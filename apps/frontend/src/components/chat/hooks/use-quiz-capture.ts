/**
 * Ask Save-to-quiz mutations. Hidden chrome is not authorization.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import {
  comparePdfEvalRun,
  createPdfEvalCase,
  fetchPdfEvalCase,
  listPdfEvalCases,
  type ApiAuth,
} from "../../../lib/api";
import {
  QUIZ_MAX_GOLD_CHUNKS,
  quizScoreDecision,
  toggleQuizGoldChunk,
} from "../../../lib/eval-workspace";
import { newIdempotencyKey } from "../../../lib/idempotency";
import { sessionQueryKeys } from "../../../lib/query-keys";
import type {
  CitationResponse,
  PdfEvalCaseSummary,
  PdfEvalQueryClass,
} from "../../../lib/types";
import { PDF_EVAL_QUERY_CLASSES } from "../../../lib/types";
import type { SaveToQuizPopoverProps } from "../save-to-quiz-popover";

const QUIZ_SCORE_COPY = "not Recall@10";

export type UseQuizCaptureInput = {
  /** Bearer auth, or null when signed out. */
  auth: ApiAuth | null;
  /** Owner/admin plus capability. Queries stay disabled otherwise. */
  enabled: boolean;
  /** Current completed run id. */
  runId: string | null;
  /** Chat terminal event. */
  terminal: string | null;
  /** Live run question. Used only for score matching and display. */
  question: string;
  /** ACL-rechecked citations from the current run. */
  citations: readonly CitationResponse[];
  /** Fill the composer with a question only. */
  onFillComposer: (question: string) => void;
};

export type UseQuizCaptureResult = {
  queryClass: PdfEvalQueryClass;
  onQueryClass: (value: PdfEvalQueryClass) => void;
  expectedAnswer: string;
  onExpectedAnswer: (value: string) => void;
  selectedChunkIds: string[];
  goldBlocked: boolean;
  onToggleChunk: (chunkId: string) => void;
  savePending: boolean;
  saveError: string | null;
  saveNotice: string | null;
  onSave: () => void;
  cases: PdfEvalCaseSummary[];
  casesPending: boolean;
  casesError: boolean;
  nextCaseId: string | null;
  loadMorePending: boolean;
  onLoadMore: () => void;
  selectedCaseId: string | null;
  onSelectCase: (caseId: string) => void;
  selectedQuestion: string;
  detailPending: boolean;
  onAskQuestion: () => void;
  scoreAllowed: boolean;
  scoreReason: string;
  scorePending: boolean;
  scoreNotice: string | null;
  onScore: () => void;
  createdFromThisRun: ReadonlySet<string>;
};

type QuizFormState = {
  runId: string | null;
  queryClass: PdfEvalQueryClass;
  expectedAnswer: string;
  selectedChunkIds: string[];
  saveNotice: string | null;
  saveError: string | null;
  scoreNotice: string | null;
  selectedCaseId: string | null;
  createdIds: string[];
};

type ExtraPageState = {
  revision: number;
  extra: PdfEvalCaseSummary[];
  cursor: string | null;
};

function emptyForm(runId: string | null): QuizFormState {
  return {
    runId,
    queryClass: PDF_EVAL_QUERY_CLASSES[0],
    expectedAnswer: "",
    selectedChunkIds: [],
    saveNotice: null,
    saveError: null,
    scoreNotice: null,
    selectedCaseId: null,
    createdIds: [],
  };
}

/**
 * Own Ask quiz create, list, detail-after-select, and citation overlap.
 *
 * @param input - Auth, run, citations, and composer fill.
 * @returns Controlled quiz fields and mutations.
 * @remarks
 * Create omits question text. Score is disabled for drafts created from this
 * run. Compare sends `{ run_id }` only. Session query keys are invalidated
 * after save. Form state resets during render when the run id changes.
 */
export function useQuizCapture(input: UseQuizCaptureInput): UseQuizCaptureResult {
  const { auth, enabled, runId, terminal, question, onFillComposer } = input;
  const queryClient = useQueryClient();
  const keys = sessionQueryKeys(auth?.accessToken ?? null);
  const [form, setForm] = useState<QuizFormState>(() => emptyForm(runId));
  const [pages, setPages] = useState<ExtraPageState>({
    revision: 0,
    extra: [],
    cursor: null,
  });
  const idempotencyRef = useRef(newIdempotencyKey());
  const payloadRef = useRef("");

  if (form.runId !== runId) {
    setForm(emptyForm(runId));
  }

  const listQuery = useQuery({
    queryKey: keys.pdfEvalAskCases,
    queryFn: () =>
      listPdfEvalCases(auth as ApiAuth, fetch, {
        split: "development",
        limit: 20,
      }),
    enabled: enabled && auth !== null,
    retry: false,
  });

  const listRevision = listQuery.dataUpdatedAt;
  if (listRevision !== 0 && pages.revision !== listRevision) {
    setPages({
      revision: listRevision,
      extra: [],
      cursor: listQuery.data?.next_case_id ?? null,
    });
  }

  const detailQuery = useQuery({
    queryKey: keys.pdfEvalCase(form.selectedCaseId),
    queryFn: () => fetchPdfEvalCase(auth as ApiAuth, form.selectedCaseId as string),
    enabled: enabled && auth !== null && form.selectedCaseId !== null,
    retry: false,
  });

  const cases = useMemo(() => {
    const first = listQuery.data?.items ?? [];
    const seen = new Set(first.map((item) => item.case_id));
    const extra = pages.extra.filter((item) => {
      if (seen.has(item.case_id)) {
        return false;
      }
      seen.add(item.case_id);
      return true;
    });
    return [...first, ...extra];
  }, [listQuery.data?.items, pages.extra]);

  const nextCaseId =
    pages.extra.length > 0
      ? pages.cursor
      : (listQuery.data?.next_case_id ?? null);

  const save = useMutation({
    mutationFn: async () => {
      if (auth === null || runId === null) {
        throw new Error("request_rejected");
      }
      const payloadKey = JSON.stringify({
        runId,
        queryClass: form.queryClass,
        expectedAnswer: form.expectedAnswer,
        selectedChunkIds: form.selectedChunkIds,
      });
      if (payloadRef.current !== payloadKey) {
        idempotencyRef.current = newIdempotencyKey();
        payloadRef.current = payloadKey;
      }
      return createPdfEvalCase(auth, {
        source_run_id: runId,
        query_class: form.queryClass,
        split: "development",
        expected_answer: form.expectedAnswer,
        chunk_ids: form.selectedChunkIds.slice(0, QUIZ_MAX_GOLD_CHUNKS),
        idempotency_key: idempotencyRef.current,
      });
    },
    onSuccess: async (result) => {
      setForm((current) => ({
        ...current,
        saveError: null,
        saveNotice: result.replayed
          ? "Quiz draft already saved."
          : "Quiz draft saved. It is not a quality score for this answer.",
        createdIds:
          result.case_id && !current.createdIds.includes(result.case_id)
            ? [...current.createdIds, result.case_id]
            : current.createdIds,
      }));
      await queryClient.invalidateQueries({ queryKey: keys.pdfEvalAskCases });
      await queryClient.invalidateQueries({ queryKey: keys.pdfEvalCases });
      if (result.case_id) {
        await queryClient.invalidateQueries({
          queryKey: keys.pdfEvalCase(result.case_id),
        });
      }
    },
    onError: () => {
      setForm((current) => ({
        ...current,
        saveNotice: null,
        saveError: "Quiz case could not be saved. Try again.",
      }));
    },
  });

  const score = useMutation({
    mutationFn: async () => {
      if (auth === null || runId === null || form.selectedCaseId === null) {
        throw new Error("request_rejected");
      }
      return comparePdfEvalRun(auth, form.selectedCaseId, runId);
    },
    onSuccess: (result) => {
      setForm((current) => ({
        ...current,
        scoreNotice: `Citation overlap ${String(result.intersection)} of ${String(result.gold_count)} gold IDs (${QUIZ_SCORE_COPY}).`,
      }));
    },
    onError: () => {
      setForm((current) => ({
        ...current,
        scoreNotice: "Citation overlap could not be scored. Try again.",
      }));
    },
  });

  const loadMore = useMutation({
    mutationFn: async () => {
      if (auth === null || nextCaseId === null) {
        throw new Error("request_rejected");
      }
      return listPdfEvalCases(auth, fetch, {
        split: "development",
        after: nextCaseId,
        limit: 20,
      });
    },
    onSuccess: (page) => {
      setPages((current) => ({
        ...current,
        extra: [...current.extra, ...page.items],
        cursor: page.next_case_id,
      }));
    },
  });

  const createdFromThisRun = useMemo(
    () => new Set(form.createdIds),
    [form.createdIds],
  );
  const scoreDecision = quizScoreDecision({
    terminal,
    selectedCaseId: form.selectedCaseId,
    reviewStatus: detailQuery.data?.review_status ?? "",
    humanApproved: detailQuery.data?.human_approved ?? false,
    selectedQuestion: detailQuery.data?.question ?? "",
    currentQuestion: question,
    createdFromThisRun,
  });

  return {
    queryClass: form.queryClass,
    onQueryClass: (value) => {
      setForm((current) => ({ ...current, queryClass: value }));
    },
    expectedAnswer: form.expectedAnswer,
    onExpectedAnswer: (value) => {
      setForm((current) => ({ ...current, expectedAnswer: value }));
    },
    selectedChunkIds: form.selectedChunkIds,
    goldBlocked: form.selectedChunkIds.length >= QUIZ_MAX_GOLD_CHUNKS,
    onToggleChunk: (chunkId) => {
      setForm((current) => ({
        ...current,
        selectedChunkIds: toggleQuizGoldChunk(current.selectedChunkIds, chunkId)
          .next,
      }));
    },
    savePending: save.isPending,
    saveError: form.saveError,
    saveNotice: form.saveNotice,
    onSave: () => {
      if (runId === null) {
        return;
      }
      save.mutate();
    },
    cases,
    casesPending: listQuery.isPending,
    casesError: listQuery.isError,
    nextCaseId,
    loadMorePending: loadMore.isPending,
    onLoadMore: () => {
      if (nextCaseId === null || loadMore.isPending) {
        return;
      }
      loadMore.mutate();
    },
    selectedCaseId: form.selectedCaseId,
    onSelectCase: (caseId) => {
      setForm((current) => ({ ...current, selectedCaseId: caseId }));
    },
    selectedQuestion: detailQuery.data?.question ?? "",
    detailPending: detailQuery.isPending && form.selectedCaseId !== null,
    onAskQuestion: () => {
      const saved = detailQuery.data?.question ?? "";
      if (saved === "") {
        return;
      }
      onFillComposer(saved);
    },
    scoreAllowed: scoreDecision.allowed,
    scoreReason: scoreDecision.reason,
    scorePending: score.isPending,
    scoreNotice: form.scoreNotice,
    onScore: () => {
      if (!scoreDecision.allowed) {
        return;
      }
      score.mutate();
    },
    createdFromThisRun,
  };
}

/**
 * Map hook state onto the Save-to-quiz popover contract.
 *
 * @param quiz - Ask capture hook result.
 * @param question - Display-only question from the current run.
 * @param citations - ACL-rechecked citations for gold suggestions.
 * @returns Popover props. Create still posts the run id, never `question`.
 */
export function toSaveToQuizPopoverProps(
  quiz: UseQuizCaptureResult,
  question: string,
  citations: readonly CitationResponse[],
): SaveToQuizPopoverProps {
  return {
    question,
    citations,
    queryClass: quiz.queryClass,
    onQueryClass: quiz.onQueryClass,
    expectedAnswer: quiz.expectedAnswer,
    onExpectedAnswer: quiz.onExpectedAnswer,
    selectedChunkIds: quiz.selectedChunkIds,
    goldBlocked: quiz.goldBlocked,
    onToggleChunk: quiz.onToggleChunk,
    savePending: quiz.savePending,
    saveError: quiz.saveError,
    saveNotice: quiz.saveNotice,
    onSave: quiz.onSave,
    cases: quiz.cases,
    casesPending: quiz.casesPending,
    casesError: quiz.casesError,
    nextCaseId: quiz.nextCaseId,
    loadMorePending: quiz.loadMorePending,
    onLoadMore: quiz.onLoadMore,
    selectedCaseId: quiz.selectedCaseId,
    onSelectCase: quiz.onSelectCase,
    selectedQuestion: quiz.selectedQuestion,
    detailPending: quiz.detailPending,
    onAskQuestion: quiz.onAskQuestion,
    scoreAllowed: quiz.scoreAllowed,
    scoreReason: quiz.scoreReason,
    scorePending: quiz.scorePending,
    scoreNotice: quiz.scoreNotice,
    onScore: quiz.onScore,
  };
}
