/**
 * Hosted exam start, poll, cancel, and latest-report queries.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import {
  cancelPdfEvalExam,
  fetchPdfEvalExam,
  fetchPdfEvalLatestReport,
  listPdfEvalExamCases,
  startPdfEvalExam,
  type ApiAuth,
} from "../../../lib/api";
import {
  clearEvalExamPointer,
  readEvalExamPointer,
  writeEvalExamPointer,
} from "../../../lib/eval-exam-pointer";
import {
  examPollIntervalMs,
  isExamActive,
  isExamTerminal,
} from "../../../lib/eval-workspace";
import { newIdempotencyKey } from "../../../lib/idempotency";
import { sessionQueryKeys } from "../../../lib/query-keys";
import type {
  PdfEvalEmptyDataset,
  PdfEvalExamCase,
  PdfEvalExamReport,
  PdfEvalExamStatus,
} from "../../../lib/types";

export type UseEvalExamInput = {
  /** Bearer auth. */
  auth: ApiAuth;
  /** Select a missed/hit case in the editor. */
  onOpenCase: (caseId: string) => void;
};

export type UseEvalExamResult = {
  split: "development" | "qualification";
  onSplit: (split: "development" | "qualification") => void;
  report: PdfEvalExamReport | undefined;
  reportPending: boolean;
  exam: PdfEvalExamStatus | undefined;
  examId: string | null;
  startPending: boolean;
  cancelPending: boolean;
  startError: string | null;
  /** True when 409 already_running can reconnect from sessionStorage. */
  canResume: boolean;
  emptyDataset: PdfEvalEmptyDataset | null;
  qualificationOpen: boolean;
  onOpenQualification: () => void;
  onCloseQualification: () => void;
  onStartDevelopment: () => void;
  onConfirmQualification: () => void;
  onCancel: () => void;
  onResume: () => void;
  cases: PdfEvalExamCase[];
  missedCount: number;
  caseFilter: "all" | "hit" | "miss";
  onCaseFilter: (value: "all" | "hit" | "miss") => void;
  visibleCases: PdfEvalExamCase[];
  caseNext: boolean;
  onLoadMoreCases: () => void;
  onOpenCase: (caseId: string) => void;
};

type ExtraCaseState = {
  revision: number;
  shown: number;
};

/**
 * Own exam start/poll/cancel and the split-isolated official report.
 *
 * @param input - Auth and case-editor selection.
 * @returns Scoreboard fields and mutations.
 * @remarks
 * Start/cancel are COST mutations. Polling uses bounded backoff. Partial
 * exams never replace the latest official report. Idempotency keys are
 * reused until split or dataset hash changes.
 */
export function useEvalExam(input: UseEvalExamInput): UseEvalExamResult {
  const { auth, onOpenCase } = input;
  const queryClient = useQueryClient();
  const keys = sessionQueryKeys(auth.accessToken);
  const [split, setSplit] = useState<"development" | "qualification">(
    () => readEvalExamPointer()?.split ?? "development",
  );
  const [examId, setExamId] = useState<string | null>(
    () => readEvalExamPointer()?.examRunId ?? null,
  );
  const [startError, setStartError] = useState<string | null>(null);
  const [canResume, setCanResume] = useState(false);
  const [emptyDataset, setEmptyDataset] = useState<PdfEvalEmptyDataset | null>(
    null,
  );
  const [qualificationOpen, setQualificationOpen] = useState(false);
  const [caseFilter, setCaseFilter] = useState<"all" | "hit" | "miss">("all");
  const [casePages, setCasePages] = useState<ExtraCaseState>({
    revision: 0,
    shown: 20,
  });
  const idempotencyRef = useRef(newIdempotencyKey());
  const payloadRef = useRef("");

  const reportQuery = useQuery({
    queryKey: keys.pdfEvalLatestReport(split),
    queryFn: () => fetchPdfEvalLatestReport(auth, split),
    retry: false,
  });
  const examQuery = useQuery({
    queryKey: keys.pdfEvalExam(examId),
    queryFn: async () => {
      const row = await fetchPdfEvalExam(auth, examId as string);
      if (isExamTerminal(row.status)) {
        clearEvalExamPointer();
      }
      if (row.status === "succeeded") {
        await queryClient.invalidateQueries({
          queryKey: keys.pdfEvalLatestReport(split),
        });
        if (row.exam_run_id) {
          await queryClient.invalidateQueries({
            queryKey: keys.pdfEvalExamCases(row.exam_run_id),
          });
        }
      }
      return row;
    },
    enabled: examId !== null,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || !isExamActive(status)) {
        return false;
      }
      return examPollIntervalMs(query.state.dataUpdateCount);
    },
  });
  const reportExamId = reportQuery.data?.present
    ? reportQuery.data.exam_run_id
    : null;
  const casesQuery = useQuery({
    queryKey: keys.pdfEvalExamCases(reportExamId),
    queryFn: () => listPdfEvalExamCases(auth, reportExamId as string),
    enabled: reportExamId !== null,
    retry: false,
  });
  const caseRevision = casesQuery.dataUpdatedAt;
  if (caseRevision !== 0 && casePages.revision !== caseRevision) {
    setCasePages({ revision: caseRevision, shown: 20 });
  }
  const cases = useMemo(
    () => casesQuery.data?.items ?? [],
    [casesQuery.data?.items],
  );
  const filtered = useMemo(() => {
    if (caseFilter === "hit") {
      return cases.filter((item) => item.hit);
    }
    if (caseFilter === "miss") {
      return cases.filter((item) => !item.hit);
    }
    return cases;
  }, [caseFilter, cases]);
  const visibleCases = filtered.slice(0, casePages.shown);

  const start = useMutation({
    mutationFn: (nextSplit: "development" | "qualification") => {
      const hash = reportQuery.data?.dataset_hash ?? "";
      const payloadKey = `${nextSplit}:${hash}`;
      if (payloadRef.current !== payloadKey) {
        idempotencyRef.current = newIdempotencyKey();
        payloadRef.current = payloadKey;
      }
      return startPdfEvalExam(auth, {
        split: nextSplit,
        idempotency_key: idempotencyRef.current,
        expected_dataset_hash: hash !== "" ? hash : null,
      });
    },
    onSuccess: async (result, nextSplit) => {
      setStartError(null);
      setCanResume(false);
      setEmptyDataset(null);
      setExamId(result.exam_run_id);
      writeEvalExamPointer({ examRunId: result.exam_run_id, split: nextSplit });
      await queryClient.invalidateQueries({
        queryKey: keys.pdfEvalExam(result.exam_run_id),
      });
    },
    onError: (error: unknown) => {
      if (error instanceof Error && error.message === "empty_dataset") {
        const empty = error as Error & PdfEvalEmptyDataset;
        setEmptyDataset({
          detail: "empty_dataset",
          draft_count: empty.draft_count ?? 0,
          approved_count: empty.approved_count ?? 0,
          rejected_count: empty.rejected_count ?? 0,
          stale_gold_count: empty.stale_gold_count ?? 0,
          live_count: empty.live_count ?? 0,
        });
        setStartError(null);
        return;
      }
      if (error instanceof Error && error.message === "already_running") {
        const stored = readEvalExamPointer();
        setCanResume(stored !== null);
        setStartError(
          stored
            ? "An exam is already running. Resume the active exam from this browser session."
            : "An exam is already running in this workspace. This browser has no resume id.",
        );
        return;
      }
      if (error instanceof Error && error.message === "qualification_consumed") {
        setStartError(
          "This dataset and candidate already used the one qualification attempt.",
        );
        return;
      }
      if (error instanceof Error && error.message === "stale_dataset_hash") {
        setStartError("The labeled dataset changed. Reloaded the latest hash.");
        void queryClient.invalidateQueries({
          queryKey: keys.pdfEvalLatestReport(split),
        });
        return;
      }
      setStartError("The exam could not start.");
    },
  });

  const cancel = useMutation({
    mutationFn: () => cancelPdfEvalExam(auth, examId as string),
    onSuccess: async () => {
      clearEvalExamPointer();
      await queryClient.invalidateQueries({
        queryKey: keys.pdfEvalExam(examId),
      });
    },
  });

  return {
    split,
    onSplit: (next) => {
      setSplit(next);
      setStartError(null);
      setCanResume(false);
      setEmptyDataset(null);
    },
    report: reportQuery.data,
    reportPending: reportQuery.isPending,
    exam: examQuery.data,
    examId,
    startPending: start.isPending,
    cancelPending: cancel.isPending,
    startError,
    canResume,
    emptyDataset,
    qualificationOpen,
    onOpenQualification: () => setQualificationOpen(true),
    onCloseQualification: () => setQualificationOpen(false),
    onStartDevelopment: () => {
      setSplit("development");
      start.mutate("development");
    },
    onConfirmQualification: () => {
      setQualificationOpen(false);
      setSplit("qualification");
      start.mutate("qualification");
    },
    onCancel: () => {
      if (examId) {
        cancel.mutate();
      }
    },
    onResume: () => {
      const stored = readEvalExamPointer();
      if (stored) {
        setSplit(stored.split);
        setExamId(stored.examRunId);
        setStartError(null);
        setCanResume(false);
      }
    },
    cases,
    missedCount: casesQuery.data?.missed_count ?? 0,
    caseFilter,
    onCaseFilter: setCaseFilter,
    visibleCases,
    caseNext: filtered.length > casePages.shown,
    onLoadMoreCases: () => {
      setCasePages((current) => ({
        ...current,
        shown: Math.min(current.shown + 20, 60),
      }));
    },
    onOpenCase,
  };
}
